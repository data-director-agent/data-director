"""The admin service (admin/, docs/guide/operations/admin.md): its pages over stores, a VM laid
out under tmp_path, a stand-in for systemd and the doctor, and agents served in memory."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from dd_admin import config_files, operations, spend, usage
from dd_admin.app import Admin, build_app, is_loopback_host
from dd_admin.cache import Cached
from dd_admin.cli import loopback, main
from dd_admin.settings import AdminSettings
from dd_admin.system import Done, System
from dd_harness.projects import ProjectStore
from dd_harness.settings import SettingsError
from dd_harness.store import RunStore
from dd_harness.testing.doubles import AbstainingStub
from dd_harness.testing.serving import asgi_client_factory
from dd_harness.testing.storage import stored_envelope
from dd_sdk import serve
from dd_sdk.contract.models import Principal, new_invocation_id

ADA = "https://orcid.org/0000-0001-0000-0001"
BEN = "https://orcid.org/0000-0001-0000-0002"
SHA = "a" * 40
OLD = "b" * 40
STUB_URL = "http://stub.agents.test"
DOWN_URL = "http://down.agents.test"
GATEWAY = "http://127.0.0.1:4000"
GATEWAY_KEY = "sk-viewer-not-to-be-shown"
SONNET = "claude-sonnet-5-5"


def model_info() -> dict[str, Any]:
    """`/model/info` as LiteLLM answers it: one priced model, one without prices."""
    return {
        "data": [
            {
                "model_name": SONNET,
                "litellm_params": {"model": f"anthropic/{SONNET}"},
                "model_info": {"input_cost_per_token": 3e-6, "output_cost_per_token": 15e-6},
            },
            {"model_name": "gpt", "litellm_params": {"model": "openai/x"}, "model_info": {}},
            {
                "model_name": "llama-local",
                "litellm_params": {"model": "ollama_chat/llama3.1"},
                "model_info": {"input_cost_per_token": 0, "output_cost_per_token": 0},
            },
        ]
    }


def spend_row(at: datetime, cost: float, key: str = "advisor-standards") -> dict[str, Any]:
    return {
        "startTime": at.isoformat(),
        "model_group": SONNET,
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "spend": cost,
        "request_tags": [f"agent:{key}", "User-Agent: Anthropic/Python"],
        "metadata": {"user_api_key_alias": key},
    }


@dataclass
class FakeSystem(System):
    """systemctl, journalctl, the doctor and the app's `/api/about` as a VM answers them; files
    are read from tmp_path as they are."""

    doctor: Done = field(
        default_factory=lambda: Done(
            1,
            json.dumps(
                {
                    "target": {"kind": "vm", "release": SHA, "root": False},
                    "problems": [
                        {"text": "the backup is 3 days old", "fix": "sudo data-director backup"}
                    ],
                    "notes": ["the branch's tip is waiting for CI"],
                    "skipped": ["credentials/"],
                }
            ),
        )
    )
    about: dict[str, Any] | None = field(
        default_factory=lambda: {
            "commit": SHA,
            "app_version": "0.3.0a8",
            "harness_version": "0.2.0a4",
            "profile": {"id": "test", "version": 1, "digest": "d" * 64, "orchestrator": "o"},
            "unavailable": [],
            "incompatible": [],
            "feedback_enabled": False,
        }
    )
    commands: list[tuple[str, ...]] = field(default_factory=list)
    # The gateway's spend logs, as pages; None for a gateway that does not answer.
    spend_pages: list[list[dict[str, Any]]] | None = field(
        default_factory=lambda: [
            [spend_row(datetime.now(UTC) - timedelta(hours=1), 0.75)],
            [spend_row(datetime.now(UTC) - timedelta(hours=2), 0.25, key="orchestrator")],
        ]
    )
    sent_headers: list[dict[str, str]] = field(default_factory=list)

    def run(self, *cmd: str, timeout_s: float = 60.0) -> Done:
        self.commands.append(cmd)
        if cmd[0] == "doctor":
            return self.doctor
        if cmd[:2] == ("systemctl", "show"):
            units = [c for c in cmd[2:] if not c.startswith("-")]
            return Done(
                0,
                "\n\n".join(
                    f"Id={u}\nActiveState={'failed' if 'workbench' in u else 'active'}\n"
                    f"SubState=running\nUnitFileState=enabled\nNRestarts=0\nResult=success"
                    for u in units
                )
                + "\n",
            )
        if cmd[0] == "journalctl":
            return Done(0, f"2026-11-12T10:00:00+0000 vm {cmd[2]}[1]: started\n")
        return Done(127, "", "not here")

    def get_json(self, url: str, headers: Any = None) -> object | None:
        if url.endswith("/api/about"):
            return self.about
        if not url.startswith(GATEWAY):
            return None
        self.sent_headers.append(dict(headers or {}))
        if self.spend_pages is None:
            return None
        if url.endswith("/model/info"):
            return model_info()
        if "/spend/logs/v2?" in url:
            page = int(httpx.URL(url).params["page"])
            return {
                "data": self.spend_pages[page - 1],
                "total_pages": len(self.spend_pages),
                "total_is_capped": False,
            }
        return None


def client_factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
    if base_url.startswith(STUB_URL):
        app = serve.app(AbstainingStub(), base_url=STUB_URL)
        return asgi_client_factory(app)(base_url, timeout_s)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url=base_url)


@pytest.fixture
def stores(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A run store and a project store holding a little of two people's work."""
    runs, projects = tmp_path / "runs", tmp_path / "projects"
    run_store = RunStore(runs)
    project_store = ProjectStore(projects)
    ada = Principal(principal_id=ADA, name="Ada Lovelace")
    project_id = project_store.create(acted_for=ada, caused_by=new_invocation_id(), title="Looms")
    first = stored_envelope("c1", project_id=project_id, principal_id=ADA)
    first["acting_for"]["name"] = "Ada Lovelace"
    first["telemetry"] = {
        "model_id": SONNET,
        "input_tokens": 2000,
        "output_tokens": 400,
        "model_calls": [
            {
                "model_provider": "anthropic",
                "model_id": SONNET,
                "called_at": first["completed_at"],
                "prompt_digest": "c" * 64,
                "input_tokens": 2000,
                "output_tokens": 400,
            }
        ],
    }
    run_store.append(first)
    failed = stored_envelope(principal_id=BEN, status="failed")
    failed["acting_for"]["name"] = "Ben Franklin"
    failed["agent_id"] = "advisor.quality"
    run_store.append(failed)
    return runs, projects, {"project": project_id, "first": first["invocation_id"]}


@pytest.fixture
def vm(tmp_path: Path) -> tuple[Path, Path]:
    """/opt/data-director and /etc/data-director, as a deployment lays them out."""
    root, etc = tmp_path / "opt", tmp_path / "etc"
    for sha in (SHA, OLD):
        (root / "releases" / sha).mkdir(parents=True)
        (root / "releases" / sha / ".built").write_text("")
    (root / "current").symlink_to(root / "releases" / SHA)
    (root / "failed-commits").write_text(OLD + "\nnot-a-commit\n")
    (etc / "agents").mkdir(parents=True)
    (etc / "deployment.yaml").write_text("name: test\norchestrator: stub\n")
    (etc / "app.env").write_text(
        "DD_OIDC_ISSUER=https://orcid.org\nDD_OIDC_CLIENT_SECRET=hunter2\n"
        "DD_OIDC_CLIENT_SECRET_FILE=orcid-client-secret\n# DD_FEEDBACK_GITHUB_TOKEN=commented\n"
    )
    (etc / "agents" / "advisor-quality.env").write_text("ANTHROPIC_API_KEY=sk-leaked\nPORT=8102\n")
    return root, etc


@pytest.fixture
def agents_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "agents.yaml"
    path.write_text(
        f"agents:\n  - name: stub\n    url: {STUB_URL}\n  - name: down\n    url: {DOWN_URL}\n"
    )
    return path


@pytest.fixture
def system() -> FakeSystem:
    return FakeSystem()


@pytest.fixture
def client(
    stores: tuple[Path, Path, dict[str, str]],
    vm: tuple[Path, Path],
    agents_yaml: Path,
    system: FakeSystem,
) -> TestClient:
    runs, projects, _ = stores
    root, etc = vm
    settings = AdminSettings(
        runs=runs,
        projects=projects,
        agents_config=agents_yaml,
        doctor=("doctor", "--json"),
        deploy_root=root,
        etc=etc,
        systemd=True,
    )
    admin = Admin.open(settings, system, client_factory)
    return TestClient(build_app(admin), base_url="http://localhost:8200")


@pytest.fixture
def gateway_client(
    stores: tuple[Path, Path, dict[str, str]], system: FakeSystem, tmp_path: Path
) -> TestClient:
    """The admin service with the LLM gateway configured and a budget of $1.10."""
    key = tmp_path / "litellm-key"
    key.write_text(GATEWAY_KEY + "\n")
    settings = AdminSettings(
        runs=stores[0],
        projects=stores[1],
        litellm_url=GATEWAY,
        litellm_key_file=key,
        monthly_budget=1.10,
    )
    return TestClient(build_app(Admin.open(settings, system)), base_url="http://localhost:8200")


# --- Reaching it ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "admitted"),
    [
        ("localhost:8200", True),
        ("127.0.0.1:8200", True),
        ("127.0.0.1", True),
        ("[::1]:8200", True),
        ("admin.localhost:8200", True),
        ("data-director.example.ac.uk", False),
        ("attacker.example:8200", False),
        ("10.0.0.5:8200", False),
        ("", False),
    ],
)
def test_only_a_loopback_host_is_admitted(host: str, admitted: bool) -> None:
    assert is_loopback_host(host) is admitted


def test_a_request_for_another_host_is_refused(client: TestClient) -> None:
    response = client.get("/", headers={"host": "attacker.example"})
    assert response.status_code == 421


def test_every_page_carries_headers_that_keep_it_private(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "script-src" not in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/operations",
        "/agents",
        "/people",
        "/runs",
        "/spend",
        "/projects",
        "/config",
        "/feedback",
    ],
)
def test_every_page_answers_get_and_nothing_that_could_change_state(
    client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, path).status_code == 405


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.4", "example.org"])
def test_serve_refuses_an_address_off_loopback(host: str) -> None:
    assert not loopback(host)
    with pytest.raises(SystemExit) as exit_:
        main(["serve", "--host", host])
    assert "loopback" in str(exit_.value)


def test_serve_admits_loopback_addresses() -> None:
    assert all(loopback(h) for h in ("127.0.0.1", "::1", "localhost", "127.0.0.2"))


# --- Usage ---------------------------------------------------------------------------------------


def test_the_overview_counts_runs_projects_and_people(client: TestClient) -> None:
    page = client.get("/").text
    assert "Ada Lovelace" in page and "Ben Franklin" in page
    assert 'class="tile bad" href="/operations"' in page  # the doctor found a problem
    assert 'class="tile warn" href="/agents"' in page  # one agent of two is down


def test_people_lists_everyone_in_the_stores(client: TestClient) -> None:
    page = client.get("/people").text
    assert "Ada Lovelace" in page and "Ben Franklin" in page
    assert "0000-0001-0000-0001" in page


def test_a_person_page_shows_their_runs_and_projects(client: TestClient) -> None:
    page = client.get("/person", params={"id": ADA}).text
    assert "Looms" in page
    assert "stub.storage" in page and "advisor.quality" not in page
    assert client.get("/person", params={"id": "https://orcid.org/nobody"}).status_code == 404


def test_runs_filter_by_outcome_and_person(client: TestClient) -> None:
    failed = client.get("/runs", params={"status": "failed"}).text
    assert "advisor.quality" in failed and "Ada Lovelace" not in failed
    ada = client.get("/runs", params={"principal": ADA}).text
    assert "Ada Lovelace" in ada and "Ben Franklin" not in ada


def test_a_run_page_shows_its_envelope(
    client: TestClient, stores: tuple[Path, Path, dict[str, str]]
) -> None:
    run_id = stores[2]["first"]
    page = client.get(f"/runs/{run_id}").text
    assert run_id in page and "Stored for a storage check." in page
    assert client.get(f"/runs/{new_invocation_id()}").status_code == 404
    assert client.get("/runs/..%2F..%2Fetc").status_code == 404


def test_a_project_page_shows_its_events_and_runs(
    client: TestClient, stores: tuple[Path, Path, dict[str, str]]
) -> None:
    page = client.get(f"/projects/{stores[2]['project']}").text
    assert "Looms" in page and "project_created" in page and "stub.storage" in page
    assert client.get(f"/projects/{new_invocation_id()}").status_code == 404


def test_usage_counts_by_day_and_by_period(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    for days_ago in (0, 0, 3, 20, 60):
        envelope = stored_envelope(principal_id=ADA)
        envelope["completed_at"] = (now - timedelta(days=days_ago)).isoformat()
        store.append(envelope)
    found = usage.count(store, None, now=now)
    assert found.runs_since(7) == 3 and found.runs_since(30) == 4 and len(found.runs) == 5
    assert found.per_day[-1] == ("2026-11-12", 2)
    assert len(found.per_day) == usage.DAYS_CHARTED
    assert found.active_people(30) == 1


def test_a_store_that_cannot_be_read_is_shown_not_raised() -> None:
    class Broken:
        def iter_envelopes(self) -> Any:
            raise OSError("disk on fire")

    found = usage.count(Broken(), None)  # type: ignore[arg-type]
    assert found.runs == [] and any("disk on fire" in e for e in found.errors)


# --- Spend ---------------------------------------------------------------------------------------


def test_without_a_gateway_spend_shows_run_tokens_and_names_the_setting(
    client: TestClient,
) -> None:
    page = client.get("/spend").text
    assert "DD_ADMIN_LITELLM_URL" in page
    assert "Ada Lovelace" in page and "Looms" in page and SONNET in page
    assert "$" not in page.split("<main", 1)[1].split("Amounts are in", 1)[0]


def test_with_a_gateway_spend_shows_its_figures_and_the_estimates(
    gateway_client: TestClient, system: FakeSystem
) -> None:
    page = gateway_client.get("/spend").text
    assert "$1.00" in page  # 0.75 + 0.25, over both pages of the spend logs
    assert "advisor-standards" in page and "orchestrator" in page
    assert "$0.01" in page  # Ada's run: 2000 at $3/M plus 400 at $15/M is $0.012
    assert all(h == {"Authorization": f"Bearer {GATEWAY_KEY}"} for h in system.sent_headers)
    assert system.sent_headers


def test_the_gateway_key_reaches_no_page(gateway_client: TestClient) -> None:
    for path in ("/", "/spend", "/config", "/people", "/person?id=" + ADA):
        assert GATEWAY_KEY not in gateway_client.get(path).text, path


def test_the_overview_tile_follows_the_budget(gateway_client: TestClient) -> None:
    # $1.00 of $1.10 is past 80 %, unless the month began within the last two hours.
    page = gateway_client.get("/").text
    assert 'class="tile warn" href="/spend"' in page or 'class="tile good" href="/spend"' in page


def test_a_gateway_that_does_not_answer_is_named_and_the_page_still_shows(
    gateway_client: TestClient, system: FakeSystem
) -> None:
    system.spend_pages = None
    response = gateway_client.get("/spend", params={"fresh": "1"})
    assert response.status_code == 200
    assert GATEWAY in response.text and "Ada Lovelace" in response.text


def test_a_person_project_and_run_show_their_estimated_cost(
    gateway_client: TestClient, stores: tuple[Path, Path, dict[str, str]]
) -> None:
    for path in (
        f"/person?id={ADA}",
        f"/projects/{stores[2]['project']}",
        f"/runs/{stores[2]['first']}",
    ):
        page = gateway_client.get(path).text
        assert "Estimated cost" in page and "$0.01" in page, path


def test_spend_logs_are_summed_by_month_day_model_and_key() -> None:
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    rows = [
        spend_row(now - timedelta(hours=1), 1.0),
        spend_row(now - timedelta(days=5), 2.0, key="orchestrator"),  # 7 November
        spend_row(now - timedelta(days=20), 4.0),  # 23 October: last 30 days, not this month
        spend_row(now - timedelta(days=45), 8.0),  # neither
        {"startTime": "not a time", "spend": 16.0},
    ]
    found = spend.summarise(rows, now)
    assert found.month_to_date == 3.0 and found.last_30_days == 7.0
    assert found.requests_30_days == 3
    assert len(found.per_day) == usage.DAYS_CHARTED and found.per_day[-1] == ("2026-11-12", 1.0)
    assert dict(found.by_model)[SONNET].cost == 7.0
    assert dict(found.by_key)["advisor-standards"].cost == 5.0
    assert [name for name, _ in found.by_key] == ["advisor-standards", "orchestrator"]


def test_a_call_is_named_by_its_agent_tag_when_its_key_has_no_alias() -> None:
    row = spend_row(datetime(2026, 11, 12, tzinfo=UTC), 1.0)
    row["metadata"] = {}
    found = spend.summarise([row], datetime(2026, 11, 12, 12, tzinfo=UTC))
    assert [name for name, _ in found.by_key] == ["agent:advisor-standards"]


def test_prices_are_found_by_name_upstream_name_and_dated_suffix() -> None:
    prices = spend.Prices.from_model_info(model_info())
    for name in (SONNET, f"anthropic/{SONNET}", f"{SONNET}-20261001"):
        assert prices.lookup(name) == spend.Price(3e-6, 15e-6), name
    assert prices.lookup("gpt") is None  # listed without prices
    assert prices.lookup("llama3.1") == spend.Price(0.0, 0.0)  # free is a price
    assert prices.lookup("claude-opus-5-5") is None


def test_tokens_on_an_unpriced_model_are_counted_as_unpriced_not_free() -> None:
    prices = spend.Prices.from_model_info(model_info())
    line = spend.cost_of([(SONNET, 1_000_000, 0), ("mystery", 10, 5)], prices)
    assert line.cost == pytest.approx(3.0)
    assert line.unpriced_tokens == 15 and line.input_tokens == 1_000_010


def test_a_runs_tokens_by_model_fall_back_to_its_totals() -> None:
    calls = [{"model_id": SONNET, "input_tokens": 3, "output_tokens": 1}] * 2
    assert usage.model_calls({"model_calls": calls}) == [(SONNET, 3, 1), (SONNET, 3, 1)]
    totals = {"model_id": "m", "input_tokens": 7, "output_tokens": 2, "model_calls": []}
    assert usage.model_calls(totals) == [("m", 7, 2)]
    assert usage.model_calls({"input_tokens": None}) == []


def test_estimates_group_by_person_and_project(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    for principal, days_ago in ((ADA, 1), (ADA, 2), (BEN, 3), (BEN, 40)):
        envelope = stored_envelope(principal_id=principal, project_id=None)
        envelope["completed_at"] = (now - timedelta(days=days_ago)).isoformat()
        envelope["telemetry"] = {"model_id": SONNET, "input_tokens": 1000, "output_tokens": 0}
        store.append(envelope)
    found = spend.estimate(
        usage.count(store, None, now=now), spend.Prices.from_model_info(model_info())
    )
    by_person = {k: line for k, _, line in found.by_person}
    assert by_person[ADA].cost == pytest.approx(0.006) and by_person[BEN].cost == pytest.approx(
        0.003
    )
    assert found.by_person[0][0] == ADA
    assert found.priced and found.total.input_tokens == 3000


@pytest.mark.parametrize(
    ("limit", "spent", "state"),
    [
        (None, 5.0, "none"),
        (10.0, None, "none"),
        (10.0, 5.0, "good"),
        (10.0, 8.0, "warn"),
        (10.0, 10.0, "over"),
    ],
)
def test_budget_states(limit: float | None, spent: float | None, state: str) -> None:
    assert spend.Budget(limit, spent).state == state


def test_a_budget_that_is_not_a_positive_number_is_refused() -> None:
    for value in ("-5", "0", "lots", "inf", "nan"):
        with pytest.raises(SettingsError):
            AdminSettings.from_env({"DD_ADMIN_MONTHLY_BUDGET": value})
    assert AdminSettings.from_env({"DD_ADMIN_MONTHLY_BUDGET": "250"}).monthly_budget == 250.0


def test_the_gateway_key_defaults_to_the_units_credential(tmp_path: Path) -> None:
    env = {"DD_ADMIN_LITELLM_URL": GATEWAY + "/", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    assert AdminSettings.from_env(env).litellm_key_file is None
    (tmp_path / "litellm-key").write_text(GATEWAY_KEY)
    found = AdminSettings.from_env(env)
    assert found.litellm_key_file == tmp_path / "litellm-key" and found.litellm_url == GATEWAY


def test_a_gateway_without_a_key_is_named_not_called() -> None:
    system = FakeSystem()
    found = spend.read_gateway(AdminSettings(litellm_url=GATEWAY), system)
    assert found.configured and found.error and not system.sent_headers


# --- Operations ----------------------------------------------------------------------------------


def test_operations_shows_the_doctors_problems_with_their_fixes(client: TestClient) -> None:
    page = client.get("/operations").text
    assert "the backup is 3 days old" in page
    assert "sudo data-director backup" in page
    assert "credentials/" in page


def test_a_doctor_that_prints_no_report_is_named(system: FakeSystem, client: TestClient) -> None:
    system.doctor = Done(1, "Traceback …", "ModuleNotFoundError: no module named yaml")
    page = client.get("/operations", params={"fresh": "1"}).text
    assert "the doctor printed no report" in page and "ModuleNotFoundError" in page


def test_without_a_doctor_the_page_says_which_setting_is_unset() -> None:
    report = operations.run_doctor(AdminSettings(), FakeSystem())
    assert not report.configured


def test_releases_name_the_live_one_and_those_that_failed(vm: tuple[Path, Path]) -> None:
    found = operations.releases(AdminSettings(deploy_root=vm[0]), FakeSystem())
    assert found.current == SHA
    assert [r.name for r in found.releases] == [SHA, OLD]
    assert found.releases[0].current and found.releases[1].failed
    assert found.failed_commits == [OLD]


def test_services_and_their_journals(client: TestClient, system: FakeSystem) -> None:
    page = client.get("/operations").text
    assert "data-director-agent@stub.service" in page and "failed" in page
    journal = client.get("/operations/journal/data-director-app.service")
    assert journal.status_code == 200 and "started" in journal.text


def test_a_journal_is_read_only_for_a_unit_of_this_deployment(
    client: TestClient, system: FakeSystem
) -> None:
    for unit in ("sshd.service", "data-director-app.service;id", "--since=yesterday"):
        assert client.get(f"/operations/journal/{unit}").status_code == 404
    assert not any(cmd[0] == "journalctl" for cmd in system.commands)


# --- Agents --------------------------------------------------------------------------------------


def test_agents_show_which_cards_answer(client: TestClient) -> None:
    page = client.get("/agents").text
    assert "stub.abstain" in page and DOWN_URL in page
    assert "a-up" in page and "a-down" in page


def test_an_agent_page_shows_its_card(client: TestClient) -> None:
    page = client.get("/agents/stub").text
    assert "stub.abstain" in page and "Agent card" in page
    assert client.get("/agents/nobody").status_code == 404


# --- Configuration -------------------------------------------------------------------------------


def test_a_secret_value_is_hidden_and_a_secret_file_named(client: TestClient) -> None:
    page = client.get("/config").text
    assert "hunter2" not in page and "sk-leaked" not in page
    assert "DD_OIDC_CLIENT_SECRET_FILE=orcid-client-secret" in page
    assert "orchestrator: stub" in page
    assert "sudo data-director apply" in page
    assert "advisor-quality.env" in page


def test_redact_leaves_comments_and_other_settings() -> None:
    text = "# KEY=example\nPORT=8102\nexport GITHUB_TOKEN=ghp_x\nDD_PASSWORD=\n"
    found = config_files.redact(text)
    assert "# KEY=example" in found and "PORT=8102" in found
    assert "ghp_x" not in found and "GITHUB_TOKEN=" in found
    assert "DD_PASSWORD=" in found


# --- Unconfigured --------------------------------------------------------------------------------


def test_with_nothing_configured_every_page_still_answers() -> None:
    system = FakeSystem(about=None)
    client = TestClient(build_app(Admin.open(AdminSettings(), system)), base_url="http://localhost")
    for path in (
        "/",
        "/operations",
        "/agents",
        "/people",
        "/runs",
        "/spend",
        "/projects",
        "/config",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
    assert "DD_ADMIN_DOCTOR" in client.get("/operations").text
    assert system.commands == []


def test_a_cached_value_is_made_again_once_it_is_old() -> None:
    clock = [0.0]
    made: list[int] = []

    def make() -> int:
        made.append(1)
        return len(made)

    cached = Cached(make, ttl_s=60, clock=lambda: clock[0])
    assert cached.get() == 1 and cached.get() == 1
    clock[0] = 61
    assert cached.get() == 2
    assert cached.get(fresh=True) == 3


def test_a_call_a_persons_own_account_paid_for_is_not_the_deployments_spend() -> None:
    """docs/specs/model-accounts.md, invariant 9: a run records whose account paid."""
    own = {"model_id": SONNET, "input_tokens": 3, "output_tokens": 1, "model_account": "own"}
    ours = {**own, "model_account": "deployment"}
    assert usage.model_calls({"model_calls": [own, ours]}) == [(SONNET, 3, 1)]
    # A run paid for wholly by the person's own account does not fall back to its totals.
    telemetry = {"model_id": SONNET, "input_tokens": 3, "output_tokens": 1, "model_calls": [own]}
    assert usage.model_calls(telemetry) == []
