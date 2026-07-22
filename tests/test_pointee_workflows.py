"""Structural validation for Pointee v2 workflow YAML files in workflows/.

These tests check formal/structural rules only. Semantic review (dangling
error handling, duplicate states, dangerous transitions, etc.) is done by the
`pointee-validator` subagent, not here.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / "workflows"

ALLOWED_BUILTINS = {
    "pointee.ai.tool",
    "pointee.agent.run",
    "pointee.form.request",
    "pointee.approval.request",
    "pointee.email.call",
    "pointee.code.run",
}

TRANSITION_KEYS = ("on_success", "on_failure", "on_approve", "on_reject", "next", "default")
LLM_EXTRACTION_TYPE = "llm_extraction"
DATA_PATH_PREFIX = "$.data."
ATTACHMENT_RE = re.compile(r"attachment(\d+)")


def _workflow_files() -> list[Path]:
    if not WORKFLOWS_DIR.is_dir():
        return []
    return sorted(WORKFLOWS_DIR.glob("*.yaml"))


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _iter_strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)


def _states(doc: dict) -> dict:
    return doc.get("states") or {}


def _transition_targets(state: dict) -> Iterator[str]:
    for transition in state.get("transitions") or []:
        if isinstance(transition, dict) and transition.get("to"):
            yield transition["to"]
    for key in TRANSITION_KEYS:
        target = state.get(key)
        if isinstance(target, str) and target:
            yield target


WORKFLOW_FILES = _workflow_files()
WORKFLOW_IDS = [f.name for f in WORKFLOW_FILES]


def _require_workflow_files() -> list[Path]:
    if not WORKFLOW_FILES:
        pytest.skip(f"No *.yaml files found in {WORKFLOWS_DIR}")
    return WORKFLOW_FILES


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_yaml_is_valid_and_parses(path: Path) -> None:
    doc = _load(path)
    assert isinstance(doc, dict), f"{path.name}: top-level YAML must be a mapping"
    assert "states" in doc, f"{path.name}: missing top-level 'states' key"
    assert isinstance(doc["states"], dict) and doc["states"], (
        f"{path.name}: 'states' must be a non-empty mapping"
    )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_data_paths_use_data_prefix(path: Path) -> None:
    doc = _load(path)
    offenders = [
        s for s in _iter_strings(doc)
        if s.startswith("$.") and not s.startswith(DATA_PATH_PREFIX)
    ]
    assert not offenders, (
        f"{path.name}: data paths must start with '{DATA_PATH_PREFIX}', "
        f"found: {offenders}"
    )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_llm_extraction_states_have_start_to_close_timeout(path: Path) -> None:
    doc = _load(path)
    bad_states = []
    for name, state in _states(doc).items():
        if not isinstance(state, dict) or state.get("type") != LLM_EXTRACTION_TYPE:
            continue
        timeout = state.get("timeout")
        if not isinstance(timeout, dict) or not timeout.get("startToClose"):
            bad_states.append(name)
    assert not bad_states, (
        f"{path.name}: llm_extraction states missing timeout.startToClose: {bad_states}"
    )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_attachment_slots_resolve(path: Path) -> None:
    doc = _load(path)
    attachments = doc.get("attachments") or {}
    if isinstance(attachments, dict):
        slot_count = attachments.get("count", 0)
    elif isinstance(attachments, list):
        slot_count = len(attachments)
    else:
        slot_count = 0

    referenced = {int(m.group(1)) for s in _iter_strings(doc) for m in ATTACHMENT_RE.finditer(s)}
    unresolved = sorted(i for i in referenced if i >= slot_count)
    assert not unresolved, (
        f"{path.name}: references to undeclared attachment slots "
        f"{[f'attachment{i}' for i in unresolved]} (declared count: {slot_count})"
    )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_transitions_point_to_existing_states(path: Path) -> None:
    doc = _load(path)
    states = _states(doc)
    dangling = []
    for name, state in states.items():
        if not isinstance(state, dict):
            continue
        for target in _transition_targets(state):
            if target not in states:
                dangling.append(f"{name} -> {target}")
    assert not dangling, f"{path.name}: dangling transitions: {dangling}"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_builtin_calls_are_allowlisted(path: Path) -> None:
    doc = _load(path)
    violations = {}
    for name, state in _states(doc).items():
        if not isinstance(state, dict):
            continue
        call = state.get("call")
        if call is not None and call not in ALLOWED_BUILTINS:
            violations[name] = call
    assert not violations, (
        f"{path.name}: states use non-allowlisted builtins: {violations} "
        f"(allowed: {sorted(ALLOWED_BUILTINS)})"
    )


def test_workflows_directory_is_covered() -> None:
    """Sanity check so this suite fails loudly if workflows/ is ever emptied
    without anyone noticing the parametrized tests silently skipped."""
    _require_workflow_files()
