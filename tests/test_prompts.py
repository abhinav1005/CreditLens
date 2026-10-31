import importlib.util
from pathlib import Path

from assistant.prompts import load_bundle

ROOT = Path(__file__).resolve().parents[1]


def _lint():
    spec = importlib.util.spec_from_file_location(
        "lint", ROOT / "scripts" / "check_prompt_immutability.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_loads_with_all_tools():
    bundle = load_bundle()
    assert [t["name"] for t in bundle.tools] == [
        "get_credit_profile",
        "get_score_history",
        "get_utilization",
        "simulate_payoff",
        "explain_factor",
    ]
    assert bundle.version == "system:v1+tools:v1"


def test_render_inserts_profile_id():
    rendered = load_bundle().render_system("story_001")
    assert "`story_001`" in rendered and "{{profile_id}}" not in rendered


def test_content_hash_is_stable_and_sensitive():
    a, b = load_bundle(), load_bundle()
    assert a.content_hash == b.content_hash
    changed = type(a)(a.system_version, a.tools_version, a.system_template + " ", a.tools)
    assert changed.content_hash != a.content_hash


def test_repo_prompts_are_locked_and_unchanged():
    assert _lint().check(ROOT / "prompts") == []


def test_lint_catches_edit_and_allows_new_version(tmp_path):
    lint = _lint()
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "v1.md").write_text("hello")
    lint.lock_new(tmp_path)
    assert lint.check(tmp_path) == []
    (tmp_path / "system" / "v2.md").write_text("new version")
    assert any("not in lock" in p for p in lint.check(tmp_path))
    lint.lock_new(tmp_path)
    assert lint.check(tmp_path) == []
    (tmp_path / "system" / "v1.md").write_text("edited")
    assert any("was edited" in p for p in lint.check(tmp_path))
    lint.lock_new(tmp_path)  # --lock must not paper over the edit
    assert any("was edited" in p for p in lint.check(tmp_path))


def test_tool_schemas_have_no_refs():
    import json

    for tool in load_bundle().tools:
        text = json.dumps(tool["input_schema"])
        assert "$ref" not in text and "$defs" not in text, tool["name"]
    explain = next(t for t in load_bundle().tools if t["name"] == "explain_factor")
    assert "UTILIZATION" in explain["input_schema"]["properties"]["factor_code"]["enum"]


def test_degraded_prompt_loads_and_lacks_safety_rules():
    bundle = load_bundle("v1-degraded")
    assert "estimate how many points" in bundle.system_template
    assert "Never promise" not in bundle.system_template
    assert "Educational information only" not in bundle.system_template
    assert bundle.content_hash != load_bundle("v1").content_hash
