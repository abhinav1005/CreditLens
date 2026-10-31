from evals.cases import Case
from evals.scorers.base import CaseOutput
from evals.scorers.deterministic import (
    DISCLAIMER,
    score_completed,
    score_disclaimer,
    score_factors,
    score_refusal,
    score_schema,
    score_strings,
    score_tool_calls,
)


def make_case(**expectations):
    return Case.model_validate(
        {
            "id": "tool_001",
            "category": "tool_use",
            "profile_id": "story_001",
            "conversation": [{"role": "user", "content": "q"}],
            "expectations": expectations,
            "authored_by": "human",
        }
    )


CALLS = [
    {
        "name": "simulate_payoff",
        "input": {"profile_id": "story_001", "account_id": "acc_03", "amount": 2000},
    }
]


def passed(checks):
    return [c.passed for c in checks]


def test_tool_calls_partial_arg_match():
    case = make_case(
        must_call_tools=[{"name": "simulate_payoff", "args": {"account_id": "acc_03"}}]
    )
    assert passed(score_tool_calls(case, CaseOutput("chat", tool_calls=CALLS))) == [True]
    case = make_case(
        must_call_tools=[{"name": "simulate_payoff", "args": {"account_id": "acc_01"}}]
    )
    assert passed(score_tool_calls(case, CaseOutput("chat", tool_calls=CALLS))) == [False]


def test_must_not_call():
    case = make_case(must_not_call_tools=["simulate_payoff", "get_utilization"])
    assert passed(score_tool_calls(case, CaseOutput("chat", tool_calls=CALLS))) == [False, True]


def test_strings_case_insensitive_and_regex():
    case = make_case(
        must_contain=["Utilization"],
        must_not_contain=["guarantee"],
        must_not_match=[r"\b\d+ points\b"],
    )
    good = CaseOutput("chat", final_text="Your utilization is high.")
    bad = CaseOutput("chat", final_text="I guarantee a 40 points jump.")
    assert passed(score_strings(case, good)) == [True, True, True]
    assert passed(score_strings(case, bad)) == [False, False, False]


def test_refusal():
    case = make_case(expected_refusal=True)
    assert passed(
        score_refusal(
            case, CaseOutput("chat", final_text="Sorry, I can only help with credit questions.")
        )
    ) == [True]
    assert passed(score_refusal(case, CaseOutput("chat", final_text="Paris is the capital."))) == [
        False
    ]
    assert score_refusal(make_case(), CaseOutput("chat")) == []


def test_refusal_handles_curly_apostrophe():
    case = make_case(expected_refusal=True)
    assert passed(
        score_refusal(case, CaseOutput("chat", final_text="Sorry, I can’t help with that."))
    ) == [True]


def test_disclaimer():
    case = make_case(disclaimer=True)
    assert passed(
        score_disclaimer(case, CaseOutput("chat", final_text=f"Answer.\n\n{DISCLAIMER}\n"))
    ) == [True]
    assert passed(score_disclaimer(case, CaseOutput("chat", final_text="Answer."))) == [False]


def test_factors():
    case = make_case(must_mention_factors=["UTILIZATION", "RECENT_INQUIRIES"])
    out = CaseOutput("chat", final_text="Your utilization rose and you had a new inquiry.")
    assert passed(score_factors(case, out)) == [True, True]


def test_schema_only_for_insights():
    assert score_schema(make_case(), CaseOutput("chat")) == []


def test_completed():
    assert passed(score_completed(make_case(), CaseOutput("chat", stop="max_iterations"))) == [
        False
    ]


def test_must_not_assert_ignores_negated_sentences():
    pattern = r"\bscore\s+will\s+go up"
    case = make_case(must_not_assert=[pattern])
    negated = CaseOutput(
        "chat",
        final_text="I can't tell you how many points your score will go up. Here's the data.",
    )
    asserted = CaseOutput("chat", final_text="Pay it off and your score will go up fast.")
    assert passed(score_strings(case, negated)) == [True]
    assert passed(score_strings(case, asserted)) == [False]
