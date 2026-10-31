"""The closed list of scoring factors.

One enum is shared by the scoring formula, the `explain_factor` tool, insight cards,
and the story profiles' stored causes, so a factor can't exist in one place and not another.
"""

from enum import StrEnum


class FactorCode(StrEnum):
    UTILIZATION = "UTILIZATION"
    PAYMENT_HISTORY = "PAYMENT_HISTORY"
    RECENT_INQUIRIES = "RECENT_INQUIRIES"
    ACCOUNT_AGE = "ACCOUNT_AGE"
    CREDIT_MIX = "CREDIT_MIX"
    DEROGATORY = "DEROGATORY"
