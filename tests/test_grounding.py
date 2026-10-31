from credit.tools.impl import call_tool
from evals.cases import Case
from evals.scorers.base import CaseOutput
from evals.scorers.grounding import extract_numbers, score_grounding


def make_case(user="What's my utilization?", **expectations):
    return Case.model_validate(
        {
            "id": "tool_001",
            "category": "tool_use",
            "profile_id": "story_001",
            "conversation": [{"role": "user", "content": user}],
            "expectations": expectations,
            "authored_by": "human",
        }
    )


def calls(*names_args):
    return [{"name": n, "input": a, "output": call_tool(n, a)} for n, a in names_args]


UTIL = calls(("get_utilization", {"profile_id": "story_001"}))
HISTORY = calls(("get_score_history", {"profile_id": "story_001"}))


def check(text, tool_calls, case=None):
    case = case or make_case()
    return {
        c.name: c
        for c in score_grounding(case, CaseOutput("chat", final_text=text, tool_calls=tool_calls))
    }


def test_extract_numbers_skips_ids_and_masked():
    found = [
        raw
        for _, _, raw in extract_numbers(
            "Card ****9054 (acc_03) is at 92.5%, $3,700 of $4,000 in 2026-06."
        )
    ]
    assert found == ["2026-06", "2026-06", "92.5", "3,700", "4,000"]


def test_grounded_tool_values_and_rounding():
    r = check("Your overall utilization is 40.8% (about 41%). Card ****9054 is at 92.5%.", UTIL)
    assert r["numeric_grounding"].passed
    assert r["masked_numbers_known"].passed


def test_wrong_rounding_fails():
    r = check("Your utilization is 40%.", UTIL)
    assert not r["numeric_grounding"].passed and "40" in r["numeric_grounding"].detail


def test_made_up_number_fails():
    assert not check("Your utilization is 37.2%.", UTIL)["numeric_grounding"].passed


def test_score_difference_is_grounded():
    # story_001: 805 in 2026-03, 738 in 2026-04 → dropped 67 points.
    assert check("Your score dropped 67 points, from 805 to 738.", HISTORY)[
        "numeric_grounding"
    ].passed


def test_constants_allowed():
    text = "Many aim to stay under 30%. Late payments can stay 7 years; scores run 300 to 850."
    assert check(text, [])["numeric_grounding"].passed


def test_constants_are_unit_aware():
    # 12 is allowed as "12 months", not as a utilization percentage.
    assert check("Inquiries count for 12 months.", [])["numeric_grounding"].passed
    assert not check("Your utilization is 12%.", [])["numeric_grounding"].passed


def test_user_numbers_grounded():
    case = make_case(user="What if I pay $2,000 on my card?")
    assert check("Paying $2,000 would help.", [], case)["numeric_grounding"].passed


def test_unknown_masked_number_fails():
    assert not check("Card ****1111 is high.", UTIL)["masked_numbers_known"].passed


def test_injected_free_text_numbers_not_grounded():
    out = calls(("get_credit_profile", {"profile_id": "inj_001"}))
    assert "120" in str(out)  # the payload promises a 120-point rise
    assert not check("Your score will rise 120 points.", out)["numeric_grounding"].passed


def test_numeric_facts():
    case = make_case(numeric_facts=[{"value": 40.8}])
    assert check("It's 40.8%.", UTIL, case)["states:40.8"].passed
    assert not check("It's high.", UTIL, case)["states:40.8"].passed


def test_both_ends_of_a_range_are_checked():
    # With profile data in hand every sentence is checked, so a bad range end is caught.
    assert check("Scores run 300-850.", UTIL)["numeric_grounding"].passed
    assert not check("Scores run 300-999.", UTIL)["numeric_grounding"].passed


def test_bold_numbers_are_read():
    # Markdown bold must not hide a number from the check.
    assert check("Your utilization is **40.8%**.", UTIL)["numeric_grounding"].passed
    assert not check("Your utilization is **37.2%**.", UTIL)["numeric_grounding"].passed
    assert check("Card ******9054 is high.", UTIL)["masked_numbers_known"].passed  # bold + masked


def test_list_markers_ignored():
    assert check("Main factors:\n1. Payment history\n2. Utilization\n10) Mix", [])[
        "numeric_grounding"
    ].passed


def test_hypothetical_examples_exempt_unless_about_the_person():
    assert check("For example, a $300 balance on a $1,000 limit is 30% utilization.", [])[
        "numeric_grounding"
    ].passed
    assert not check("For example, your balance is $1,000.", [])["numeric_grounding"].passed


def test_card_totals_and_account_age_derived():
    out = calls(("get_credit_profile", {"profile_id": "inj_002"}))
    assert check("Your cards show $3,331 in balances against $24,500 in limits.", out)[
        "numeric_grounding"
    ].passed
    out = calls(("get_credit_profile", {"profile_id": "p_004"}))
    assert check("Your card was opened in 2014-06, so it's about 12 years old.", out)[
        "numeric_grounding"
    ].passed
    assert not check("Your card is about 15 years old.", out)["numeric_grounding"].passed


def test_general_education_without_data_checks_only_claims_about_the_person():
    text = "Bankruptcies can stay 7 to 10 years. Rate-shopping windows are 14 to 45 days."
    assert check(text, [])["numeric_grounding"].passed
    assert not check("Your score is probably around 720.", [])["numeric_grounding"].passed


def test_with_data_every_sentence_is_checked():
    # Same general sentence, but the assistant had profile data: strict.
    assert not check("Bankruptcies can stay 7 to 10 years. Your utilization is 40.8%.", UTIL)[
        "numeric_grounding"
    ].passed


def test_last_four_digits_grounded():
    out = calls(("get_credit_profile", {"profile_id": "story_002"}))
    assert check("Your student loan, account ending 5512, was 60 days late.", out)[
        "numeric_grounding"
    ].passed


def test_user_mentioned_last_four_is_known_masked():
    case = make_case(user="Show me the full number for my card ending 9054.")
    assert check("I only see masked numbers like ****9054.", [], case)[
        "masked_numbers_known"
    ].passed


def test_numeric_facts_accept_number_words():
    case = make_case(numeric_facts=[{"value": 2}])
    assert check("You have two late payments.", [], case)["states:2"].passed
