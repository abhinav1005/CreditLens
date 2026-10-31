"""Write shared tool fixtures (input → expected output) to contracts/tools/fixtures/.

Any implementation of the tools (Python now, Java in M5) must reproduce these exactly.
Hand-checked values for key cases live in tests/test_tools.py.

    uv run python scripts/make_fixtures.py          # write
    uv run python scripts/make_fixtures.py --check  # fail if stale
"""

import json
import sys
from pathlib import Path

from credit.factors import FactorCode
from credit.tools.impl import call_tool

OUT = Path(__file__).resolve().parents[1] / "contracts" / "tools" / "fixtures" / "v1.json"

CASES = (
    [
        ("get_credit_profile", {"profile_id": "story_001"}),
        ("get_credit_profile", {"profile_id": "story_002"}),
        ("get_credit_profile", {"profile_id": "inj_002"}),
        ("get_credit_profile", {"profile_id": "p_999"}),
        ("get_score_history", {"profile_id": "story_001"}),
        ("get_score_history", {"profile_id": "story_003", "months": 3}),
        ("get_score_history", {"profile_id": "story_003", "months": 13}),
        ("get_utilization", {"profile_id": "story_001"}),
        ("get_utilization", {"profile_id": "p_001"}),
        ("simulate_payoff", {"profile_id": "story_001", "account_id": "acc_03", "amount": 2000}),
        ("simulate_payoff", {"profile_id": "story_001", "account_id": "acc_03", "amount": 99999}),
        ("simulate_payoff", {"profile_id": "story_001", "account_id": "acc_02", "amount": 100}),
        ("simulate_payoff", {"profile_id": "story_001", "account_id": "acc_09", "amount": 100}),
        ("simulate_payoff", {"profile_id": "story_001", "account_id": "acc_03", "amount": -5}),
    ]
    + [("explain_factor", {"factor_code": f.value}) for f in FactorCode]
    + [
        ("explain_factor", {"factor_code": "SHOE_SIZE"}),
    ]
)


def rendered() -> str:
    fixtures = [{"tool": t, "input": a, "output": call_tool(t, a)} for t, a in CASES]
    return json.dumps({"version": "v1", "fixtures": fixtures}, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    text = rendered()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text() == text
        print(
            "fixtures up to date"
            if ok
            else "fixtures stale: run uv run python scripts/make_fixtures.py"
        )
        sys.exit(0 if ok else 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {len(CASES)} fixtures to {OUT}")
