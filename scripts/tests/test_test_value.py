"""The test value report in scripts/test_value.py: what it counts as new, fanned out or unreached."""

from __future__ import annotations

import sys
from pathlib import Path

from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import test_value as tv  # noqa: E402


def lines(*numbers: int, path: str = "src/m.py") -> frozenset[tv.Line]:
    return frozenset((path, n) for n in numbers)


def test_a_context_names_its_case_whatever_the_phase() -> None:
    for phase in ("setup", "run", "teardown"):
        assert tv.case_of(f"t/test_a.py::test_x[1]|{phase}") == "t/test_a.py::test_x[1]"
    assert tv.case_of("") is None


def test_the_cases_of_a_parametrised_test_share_a_function() -> None:
    assert tv.function_of("t/test_a.py::test_x[a-b]") == tv.function_of("t/test_a.py::test_x[c]")
    assert tv.function_of("t/test_a.py::test_x") == "t/test_a.py::test_x"


def test_a_function_reaching_only_lines_others_reach_adds_nothing_new() -> None:
    reach = {
        "t/test_a.py::test_wide": lines(1, 2, 3),
        "t/test_a.py::test_narrow": lines(2),
        "t/test_b.py::test_own": lines(9),
    }
    report = tv.analyse(reach, reach)
    assert report.nothing_new == {"t/test_a.py": (["test_narrow"], 2)}


def test_one_check_run_per_file_is_fan_out() -> None:
    same = {f"t/test_a.py::test_each[{n}]": lines(1, 2) for n in range(tv.FAN_OUT_MIN_CASES)}
    varied = {f"t/test_a.py::test_varied[{n}]": lines(n) for n in range(tv.FAN_OUT_MIN_CASES)}
    report = tv.analyse({**same, **varied}, [])
    assert [(f.function, f.paths) for f in report.fan_out] == [("t/test_a.py::test_each", 1)]


def test_a_passing_test_that_ran_no_measured_line_reaches_no_code() -> None:
    reach = {"t/test_a.py::test_code": lines(1)}
    passed = ["t/test_a.py::test_code", "t/test_a.py::test_data[x]", "t/test_a.py::test_data[y]"]
    report = tv.analyse(reach, passed)
    assert report.reaches_no_code == ["t/test_a.py::test_data"]
    assert (report.functions, report.cases) == (2, 3)


def test_the_report_has_its_three_sections() -> None:
    reach = {"t/test_a.py::test_x": lines(1), "t/test_a.py::test_y": lines(1)}
    text = tv.render(tv.analyse(reach, reach))
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## Nothing new", "## Fan-out", "## Reaches no code"]
    assert "`t/test_a.py`" in text


def test_the_report_reads_a_run_from_its_data(tmp_path: Path) -> None:
    data = CoverageData(basename=str(tmp_path / ".coverage"))
    source = str(ROOT / "src" / "m.py")
    data.set_context("t/test_a.py::test_x|run")
    data.add_lines({source: [1, 2]})
    data.write()
    (tmp_path / "report.json").write_text(
        '{"tests": [{"nodeid": "t/test_a.py::test_x", "outcome": "passed"},'
        ' {"nodeid": "t/test_a.py::test_y", "outcome": "failed"}]}',
        encoding="utf-8",
    )
    assert tv.read_reach(tmp_path / ".coverage") == {"t/test_a.py::test_x": lines(1, 2)}
    assert tv.read_passed(tmp_path / "report.json") == ["t/test_a.py::test_x"]
