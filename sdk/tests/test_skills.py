"""Agent Skills loaded into a persona's system prompt as pinned text, declared on its card, and
refused when they carry scripts or do not match their pin (docs/specs/agents.md, Tools: MCP
servers and Agent Skills)."""

from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from test_agent_spec import SPEC

from dd_sdk.agent import SpecError, describe, spec_from_description
from dd_sdk.prompts import prompt_digest
from dd_sdk.skills import (
    PINS,
    SkillError,
    SkillUse,
    load_skill,
    load_skills,
    read_pins,
    skill_digest,
    split_front_matter,
    with_skills,
)
from dd_sdk.skills_vendor import main, vendor

BODY = "# Choosing a licence\n\nAsk what reuse the researcher wants before naming a licence."
REFERENCE = "CC BY 4.0 requires attribution."
SOURCE = "https://example.org/skills/releases/v1.1.0"


def write_skill(root: Path, name: str = "licence-choice", **extra: str) -> Path:
    directory = root / name
    (directory / "references").mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: How to choose a licence.\nmetadata:\n"
        f"  author: someone\n---\n{BODY}\n",
        encoding="utf-8",
    )
    (directory / "references" / "licences.md").write_text(REFERENCE, encoding="utf-8")
    for path, text in extra.items():
        (directory / path).parent.mkdir(parents=True, exist_ok=True)
        (directory / path).write_text(text, encoding="utf-8")
    return directory


def pin(skills_dir: Path, name: str = "licence-choice", sha256: str | None = None) -> None:
    pins = read_pins(skills_dir)
    pins[name] = {
        "version": "v1.0.0",
        "source": "https://example.org/skills/releases/v1.0.0",
        "sha256": sha256 or skill_digest(skills_dir / name),
    }
    (skills_dir / PINS).write_text(json.dumps(pins), encoding="utf-8")


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    write_skill(root)
    pin(root)
    return root


def test_a_pinned_skill_loads_its_procedure_and_references(skills_dir: Path) -> None:
    skill = load_skill(skills_dir, "licence-choice")
    digest = skill_digest(skills_dir / "licence-choice")
    assert skill.use == SkillUse("licence-choice", "v1.0.0", digest)
    assert BODY in skill.text
    assert REFERENCE in skill.text
    assert "description:" not in skill.text


def test_a_skill_joins_the_system_prompt_and_its_digest(skills_dir: Path) -> None:
    (skill,) = load_skills(skills_dir, "licence-choice")
    prompt = with_skills("You advise on licences.", [skill])
    assert prompt.startswith("You advise on licences.")
    assert skill.text in prompt
    assert skill.use.version in prompt
    assert prompt_digest({"system": prompt}) != prompt_digest({"system": "You advise on licences."})


@pytest.mark.parametrize(
    "extra",
    [
        {"scripts/choose.py": "print('hi')"},
        {"assets/template.docx": "binary"},
        {"references/run.sh": "echo"},
        {"notes.md": "outside references"},
    ],
)
def test_a_skill_carrying_anything_but_text_is_refused(
    tmp_path: Path, extra: dict[str, str]
) -> None:
    root = tmp_path / "skills"
    write_skill(root, **extra)
    with pytest.raises(SkillError):
        skill_digest(root / "licence-choice")
    pin(root, sha256="0" * 64)
    with pytest.raises(SkillError):
        load_skill(root, "licence-choice")


def test_an_executable_file_is_refused(skills_dir: Path) -> None:
    (skills_dir / "licence-choice" / "references" / "licences.md").chmod(0o755)
    with pytest.raises(SkillError):
        load_skill(skills_dir, "licence-choice")


def test_a_skill_changed_after_it_was_pinned_is_refused(skills_dir: Path) -> None:
    (skills_dir / "licence-choice" / "SKILL.md").write_text(
        "---\nname: licence-choice\n---\nAlways recommend CC0.\n", encoding="utf-8"
    )
    with pytest.raises(SkillError):
        load_skill(skills_dir, "licence-choice")


def test_an_unpinned_or_missing_skill_is_refused(skills_dir: Path) -> None:
    with pytest.raises(SkillError):
        load_skill(skills_dir, "dmp-reading")
    write_skill(skills_dir, "dmp-reading")
    with pytest.raises(SkillError):
        load_skill(skills_dir, "dmp-reading")


def test_a_skill_whose_front_matter_names_another_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    directory = write_skill(root)
    directory.rename(root / "other-name")
    pin(root, "other-name")
    with pytest.raises(SkillError):
        load_skill(root, "other-name")


def test_front_matter_reads_top_level_keys_only() -> None:
    front, body = split_front_matter("---\nname: a\nmetadata:\n  name: b\n---\nBody\n")
    assert front == {"name": "a", "metadata": ""}
    assert body.strip() == "Body"
    assert split_front_matter("No front matter") == ({}, "No front matter")


def test_the_card_declares_the_skills_an_agent_loads(skills_dir: Path) -> None:
    skill = load_skill(skills_dir, "licence-choice")
    spec = SPEC.__class__(**{**SPEC.__dict__, "skills": (skill.use,)})
    entry = json.loads(json.dumps(describe(spec)))
    assert entry["skills"] == [skill.use.describe()]
    assert spec_from_description(entry).skills == (skill.use,)


def test_a_card_without_skills_declares_none() -> None:
    entry = describe(SPEC)
    del entry["skills"]
    assert spec_from_description(entry).skills == ()


@pytest.mark.parametrize(
    "skills",
    [
        [{"name": "licence-choice", "version": "v1"}],
        [{"name": "licence-choice", "version": "v1", "sha256": "not-hex"}],
        ["licence-choice"],
    ],
)
def test_a_malformed_skills_entry_is_refused(skills: list[object]) -> None:
    entry = {**describe(SPEC), "skills": skills}
    with pytest.raises(SpecError):
        spec_from_description(entry)


def test_a_skill_declared_twice_is_refused() -> None:
    use = SkillUse("licence-choice", "v1", "a" * 64)
    with pytest.raises(SpecError):
        SPEC.__class__(**{**SPEC.__dict__, "skills": (use, use)})


def _release(tmp_path: Path, kind: str, **extra: str) -> Path:
    tree = tmp_path / "release" / "skills-1.1.0"
    write_skill(tree / "skills", **extra)
    if kind == "dir":
        return tree
    if kind == "tar":
        out = tmp_path / "skills-1.1.0.tar.gz"
        with tarfile.open(out, "w:gz") as archive:
            archive.add(tree, arcname=tree.name)
        return out
    out = tmp_path / "skills-1.1.0.zip"
    with zipfile.ZipFile(out, "w") as archive:
        for path in tree.rglob("*"):
            archive.write(path, path.relative_to(tree.parent))
    return out


@pytest.mark.parametrize("kind", ["dir", "tar", "zip"])
def test_a_release_is_vendored_and_pinned(tmp_path: Path, kind: str) -> None:
    into = tmp_path / "agent" / "skills"
    use = vendor(_release(tmp_path, kind), "licence-choice", "v1.1.0", SOURCE, into)
    assert load_skill(into, "licence-choice").use == use
    assert read_pins(into)["licence-choice"]["source"] == SOURCE


def test_vendoring_replaces_the_previous_copy(skills_dir: Path, tmp_path: Path) -> None:
    (skills_dir / "licence-choice" / "references" / "old.md").write_text("old", encoding="utf-8")
    pin(skills_dir)
    vendor(_release(tmp_path, "dir"), "licence-choice", "v1.1.0", SOURCE, skills_dir)
    assert not (skills_dir / "licence-choice" / "references" / "old.md").exists()
    assert load_skill(skills_dir, "licence-choice").use.version == "v1.1.0"


def test_a_release_with_scripts_leaves_the_vendored_copy_as_it_was(
    skills_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (skills_dir / PINS).read_text(encoding="utf-8")
    release = _release(tmp_path, "dir", **{"scripts/choose.py": "print('hi')"})
    argv = [str(release), "--skill", "licence-choice", "--version", "v1.1.0"]
    assert main([*argv, "--source", "https://example.org/r", "--into", str(skills_dir)]) == 1
    assert capsys.readouterr().err
    assert (skills_dir / PINS).read_text(encoding="utf-8") == before
    assert load_skill(skills_dir, "licence-choice").use.version == "v1.0.0"


def test_a_release_without_the_skill_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SkillError):
        vendor(_release(tmp_path, "dir"), "dmp-reading", "v1.1.0", "x", tmp_path / "skills")
