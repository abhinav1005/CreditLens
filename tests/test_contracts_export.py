import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _exporter():
    spec = importlib.util.spec_from_file_location(
        "export_contracts", ROOT / "scripts" / "export_contracts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_schemas_match_models():
    exporter = _exporter()
    for name, text in exporter.rendered().items():
        assert (
            exporter.OUT_DIR / name
        ).read_text() == text, f"{name} is stale; rerun the export script"


def test_every_tool_has_input_and_output_schema():
    names = {p.name for p in (ROOT / "contracts" / "tools").glob("*.json")}
    for tool in [
        "get_credit_profile",
        "get_score_history",
        "get_utilization",
        "simulate_payoff",
        "explain_factor",
    ]:
        assert f"{tool}.input.json" in names and f"{tool}.output.json" in names
