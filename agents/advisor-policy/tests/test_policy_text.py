"""Reading a policy's own text (#904): fetching it (`policy_text.py`), reading a PDF
(`pdf_text.py`), and keeping only the readings whose quote is in the text (`extract.py`). The web
is faked with recorded pages and the model with `FakeModel`; the network is blocked."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dd_agent_advisor_policy import pdf_text
from dd_agent_advisor_policy.classes import Actor, ActorRole, ObligationKind, Strength
from dd_agent_advisor_policy.extract import (
    Extraction,
    ModelExtractor,
    NoExtractor,
    Read,
    check,
    found,
    prompt,
)
from dd_agent_advisor_policy.policy_text import (
    MAX_CHARS,
    PolicyPages,
    PolicyText,
    UnreadableError,
    html_text,
    readable_url,
)
from dd_agent_advisor_policy.retrieve import RegistryUnavailable
from dd_sdk.agent import RunContext
from dd_sdk.testing import FakeModel
from dd_sdk.tracing import make_tracing

DATA = Path(__file__).parent / "data"
HTML = (DATA / "policy-example.html").read_bytes()
PDF = (DATA / "policy-example.pdf").read_bytes()
URL = "https://funder.example/data-policy"
SRC = Actor(role=ActorRole.FUNDER, name="Social Research Council")


def pages(body: bytes, media_type: str, status: int = 200) -> PolicyPages:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers={"content-type": media_type})

    return PolicyPages(client=httpx.Client(transport=httpx.MockTransport(handler)))


def ctx() -> RunContext:
    return RunContext(tracer=make_tracing(service_name="test").tracer, input_ref="", input_hash="")


# --- fetching and text ------------------------------------------------------------------------


def test_a_pages_text_leaves_out_its_scripts_styles_and_navigation() -> None:
    text = html_text(HTML.decode())
    assert "Grant holders must offer their data for deposit" in text
    assert "CC BY 4.0" in text
    for furniture in ("window.analytics", "font-family", "About us", "Funding", "©"):
        assert furniture not in text


def test_a_page_is_fetched_as_evidence_with_the_hash_of_its_bytes() -> None:
    page = pages(HTML, "text/html; charset=utf-8").fetch(URL)
    assert page.url == URL and page.media_type == "text/html" and not page.truncated
    assert len(page.sha256) == 64 and "Social Survey Archive" in page.text
    assert {"url", "media_type", "sha256", "text", "truncated"} <= set(page.document())
    assert pages(HTML, "text/html").snapshot_ref().label.startswith("policy-text:live:")


def test_a_pdf_policy_is_read() -> None:
    page = pages(PDF, "application/pdf").fetch(URL + ".pdf")
    assert page.media_type == "application/pdf"
    assert "within two years of the end of the grant" in page.text
    # Served with no media type, a PDF is known by its first bytes.
    assert pages(PDF, "").fetch(URL).media_type == "application/pdf"


def test_what_cannot_be_read_is_unreadable_and_what_cannot_be_fetched_is_unavailable() -> None:
    with pytest.raises(UnreadableError):
        pages(b"\x89PNG", "image/png").fetch(URL)
    with pytest.raises(UnreadableError):
        pages(b"%PDF-1.4 not really", "application/pdf").fetch(URL)
    with pytest.raises(UnreadableError):
        pages(b"<html><script>x</script></html>", "text/html").fetch(URL)
    with pytest.raises(RegistryUnavailable):
        pages(b"gone", "text/html", status=404).fetch(URL)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(RegistryUnavailable):
        PolicyPages(client=httpx.Client(transport=httpx.MockTransport(down))).fetch(URL)


def test_a_landing_page_has_the_pdfs_it_links_to_on_its_own_site_read_too() -> None:
    landing = (
        b"<html><body><main><h1>Example research data policy</h1>"
        b'<a href="/files/policy.pdf">Example research data policy (PDF)</a>'
        b'<a href="https://elsewhere.example/advert.pdf">Advert</a>'
        b"</main></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/files/policy.pdf":
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        assert request.url.host == "funder.example", "a PDF on another site is not fetched"
        return httpx.Response(200, content=landing, headers={"content-type": "text/html"})

    page = PolicyPages(client=httpx.Client(transport=httpx.MockTransport(handler))).fetch(URL)
    assert page.media_type == "text/html"
    assert [d.url for d in page.linked] == ["https://funder.example/files/policy.pdf"]
    assert "within two years of the end of the grant" in page.text
    assert page.document()["linked"][0]["sha256"] == page.linked[0].sha256


def test_a_page_with_text_of_its_own_does_not_follow_its_links() -> None:
    page = pages(HTML.replace(b"</main>", b'<a href="/p.pdf">PDF</a></main>'), "text/html")
    assert page.fetch(URL).linked == ()


def test_a_long_policy_is_cut_short_and_says_so() -> None:
    body = ("<p>" + "The data policy says a great deal. " * 5000 + "</p>").encode()
    page = pages(body, "text/html").fetch(URL)
    assert page.truncated and len(page.text) == MAX_CHARS


def test_a_pdf_with_no_text_reads_as_none() -> None:
    assert pdf_text.text(b"not a pdf") is None


@pytest.mark.parametrize(
    ("given", "readable"),
    [(URL, True), ("http://x.example/p", True), ("ftp://x.example/p", False), ("", False)],
)
def test_only_web_addresses_are_read(given: str, readable: bool) -> None:
    assert (readable_url(given) is not None) is readable


# --- keeping only what the text says ----------------------------------------------------------

TEXT = PolicyText(
    url=URL,
    media_type="text/html",
    sha256="0" * 64,
    text=html_text(HTML.decode()),
)
DEPOSIT = Read(
    kind="repository",
    strength="required",
    value="Social Survey Archive",
    quote="Grant holders must offer their data for deposit with the Social Survey Archive",
)


def test_a_quote_is_found_despite_typography_and_line_breaks() -> None:
    assert found("Grant holders must offer their data for deposit with the\n Social", TEXT.text)
    assert found("released under a Creative Commons Attribution licence (CC BY 4.0)", TEXT.text)
    # Curly quotes, dashes and no-break spaces in a model's copy match their plain forms.
    assert found("the policy\u2019s term \u2013 two years", "the policy's term - two years")
    assert found("CC\u00a0BY\u00a04.0", TEXT.text)
    assert not found("Grant holders may offer their data", TEXT.text)


def test_a_reading_whose_quote_is_not_in_the_text_is_dropped_with_the_reason() -> None:
    invented = Read(
        kind="embargo",
        strength="required",
        value="24 months",
        quote="Data may be withheld for no longer than 24 months after collection.",
    )
    short = Read(kind="licence", strength="recommended", value="CC BY", quote="CC BY 4.0")
    checked = check(Extraction(obligations=[DEPOSIT, invented, short, DEPOSIT]), TEXT)
    assert [(o.kind, o.strength, o.value) for o in checked.stated] == [
        (ObligationKind.REPOSITORY, Strength.REQUIRED, "Social Survey Archive")
    ]
    # Each dropped reading is named, so a reader can see what the model said and was not kept.
    assert len(checked.dropped) == 2
    assert {d.split(":")[0] for d in checked.dropped} == {"embargo", "licence"}


def test_the_model_is_given_the_text_as_quoted_data_in_the_user_turn() -> None:
    model = FakeModel(Extraction(obligations=[DEPOSIT]).model_dump_json())
    reading = ModelExtractor(model).extract(SRC, TEXT, ctx(), None)
    assert reading.why_not is None and len(reading.checked.stated) == 1
    assert reading.calls is not None and len(reading.calls.calls) == 1
    sent = model.sent[0]
    # The policy's text is in the user turn only, never in the system prompt.
    assert "Social Survey Archive" not in sent.system
    assert "Social Survey Archive" in json.dumps([str(m) for m in sent.messages])
    assert prompt(SRC, TEXT).endswith("</policy_text>")


@pytest.mark.parametrize("model", [FakeModel(refuse=True), FakeModel("not json")])
def test_a_refusal_or_an_unreadable_reply_reads_nothing_and_says_why(model: FakeModel) -> None:
    reading = ModelExtractor(model).extract(SRC, TEXT, ctx(), None)
    assert reading.checked.stated == [] and reading.why_not
    assert reading.calls is not None  # the call is still recorded


def test_without_a_model_nothing_is_read() -> None:
    reading = NoExtractor().extract(SRC, TEXT, ctx(), None)
    assert reading.checked.stated == [] and reading.why_not
