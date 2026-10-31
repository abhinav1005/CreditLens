"""Build evals/datasets/long.jsonl: long conversations that end in a data question (M4.6).

Each case has ~15 earlier general-education turns (long assistant answers, no tool calls),
then a question that needs this person's data. With trimming on, the early turns get cut;
the case checks the final answer is still right. Numbers come from the tools.

    uv run python scripts/build_long_suite.py
"""

import json
from pathlib import Path

from credit.tools.impl import call_tool

OUT = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "long.jsonl"
TOPICS = [
    "utilization",
    "hard inquiries",
    "credit mix",
    "account age",
    "late payments",
    "collections",
    "charge-offs",
    "secured cards",
    "authorized users",
    "balance transfers",
    "credit limits",
    "statement dates",
    "disputes",
    "soft inquiries",
    "minimum payments",
]
FILLER = ("Here is a general explanation. " * 40).strip()


def history() -> list[dict]:
    msgs = []
    for t in TOPICS:
        msgs += [
            {"role": "user", "content": f"Can you explain {t} in general terms?"},
            {"role": "assistant", "content": f"Sure, about {t}: {FILLER}"},
        ]
    return msgs


def build() -> list[dict]:
    cases = []
    for i, pid in enumerate(["story_001", "p_010", "p_034", "p_005", "p_046"], start=1):
        u = call_tool("get_utilization", {"profile_id": pid})
        cases.append(
            {
                "id": f"long_{i:03d}",
                "category": "tool_use",
                "profile_id": pid,
                "conversation": history()
                + [{"role": "user", "content": "OK, now what's my actual overall utilization?"}],
                "expectations": {
                    "must_call_tools": [{"name": "get_utilization"}],
                    "disclaimer": True,
                    "numeric_facts": [
                        {
                            "value": u["overall_utilization_pct"],
                            "description": "overall utilization",
                        }
                    ],
                },
                "tags": ["long"],
                "authored_by": "llm_drafted",
            }
        )
    return cases


if __name__ == "__main__":
    cases = build()
    OUT.write_text("".join(json.dumps(c, sort_keys=True) + "\n" for c in cases))
    chars = len(json.dumps(cases[0]["conversation"]))
    print(f"wrote {len(cases)} long cases (~{chars // 4} tokens of history each) to {OUT}")
