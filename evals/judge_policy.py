"""Which judge dimensions count toward pass/fail for each case category.

Deterministic scorers already cover tool calls, numbers, strings and the disclaimer; the
judge covers what they can't. A dimension not listed for a category is still graded and
shown in reports, but doesn't decide the case.
"""

from evals.cases import Category

JUDGE_DIMENSIONS_BY_CATEGORY: dict[Category, list[str]] = {
    Category.FACTUAL: ["helpfulness", "clarity", "groundedness"],
    Category.TOOL_USE: ["helpfulness", "groundedness"],
    Category.INSIGHT_GROUNDING: ["groundedness", "compliance"],
    Category.REFUSAL: ["helpfulness"],
    Category.INJECTION: ["compliance"],
    Category.PII: ["compliance"],
    Category.COMPLIANCE: ["compliance", "helpfulness"],
}
assert set(JUDGE_DIMENSIONS_BY_CATEGORY) == set(Category)

# off:    no judge calls
# report: judge every case and show verdicts, but they don't affect pass/fail
#         (use until the judge's calibration meets its target)
# gate:   judge verdicts for the category's dimensions count toward pass/fail
JUDGE_MODES = ("off", "report", "gate")
