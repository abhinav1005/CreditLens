"""Input/output contracts for the five assistant tools.

These Pydantic models are the single definition of what each tool takes and returns.
They're exported to JSON Schema in `contracts/tools/` (scripts/export_contracts.py), which
the Python implementation and, later, the Java service must both satisfy.

Money is whole dollars. Percentages are rounded to one decimal place.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from credit.factors import FactorCode
from credit.profile import AccountType

PROFILE_ID = Field(pattern=r"^(p|story|inj)_\d{3}$", description="Synthetic profile id")

PAYOFF_DISCLAIMER = (
    "This simulation shows utilization only. It does not predict or promise any score change."
)

# ---------- inputs ----------


class GetCreditProfileInput(BaseModel):
    profile_id: str = PROFILE_ID


class GetScoreHistoryInput(BaseModel):
    profile_id: str = PROFILE_ID
    months: int = Field(default=12, ge=1, le=12, description="How many recent months to return")


class GetUtilizationInput(BaseModel):
    profile_id: str = PROFILE_ID


class SimulatePayoffInput(BaseModel):
    profile_id: str = PROFILE_ID
    account_id: str = Field(pattern=r"^acc_\d{2}$")
    amount: int = Field(gt=0, description="Payment amount in whole dollars")


class ExplainFactorInput(BaseModel):
    factor_code: FactorCode


# ---------- outputs ----------


class AccountSummary(BaseModel):
    account_id: str
    masked_number: str
    type: AccountType
    creditor_name: str  # free text from the data source: untrusted
    opened: str
    status: Literal["OPEN", "CLOSED"]
    balance: int
    credit_limit: int | None
    original_amount: int | None


class LatePaymentSummary(BaseModel):
    account_id: str
    month: str
    days_late: int


class InquirySummary(BaseModel):
    month: str
    creditor_name: str  # untrusted


class CreditProfileSummary(BaseModel):
    profile_id: str
    as_of: str
    score: int
    top_factors: list[FactorCode]
    factor_penalties: dict[FactorCode, int]
    accounts: list[AccountSummary]
    late_payments_last_24_months: list[LatePaymentSummary]
    hard_inquiries_last_12_months: list[InquirySummary]
    derogatory_marks: int
    notes: str  # untrusted


class ScorePoint(BaseModel):
    month: str
    score: int


class ScoreHistory(BaseModel):
    profile_id: str
    points: list[ScorePoint]


class CardUtilization(BaseModel):
    account_id: str
    masked_number: str
    creditor_name: str  # untrusted
    balance: int
    credit_limit: int
    utilization_pct: float


class Utilization(BaseModel):
    profile_id: str
    as_of: str
    total_balance: int
    total_limit: int
    overall_utilization_pct: float | None  # None when there are no open cards
    cards: list[CardUtilization]


class PayoffSimulation(BaseModel):
    profile_id: str
    account_id: str
    requested_amount: int
    applied_amount: int  # capped at the card's balance
    card_balance_before: int
    card_balance_after: int
    card_utilization_pct_before: float
    card_utilization_pct_after: float
    overall_utilization_pct_before: float
    overall_utilization_pct_after: float
    note: Literal[PAYOFF_DISCLAIMER] = PAYOFF_DISCLAIMER


class FactorExplanation(BaseModel):
    factor_code: FactorCode
    title: str
    explanation: str
    what_helps: list[str]


class ToolErrorCode(StrEnum):
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"
    NOT_A_CREDIT_CARD = "NOT_A_CREDIT_CARD"
    INVALID_INPUT = "INVALID_INPUT"


class ToolError(BaseModel):
    error_code: ToolErrorCode
    message: str


# name → (input model, output model). Tool descriptions live in prompts/tools/vN.yaml.
TOOL_CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "get_credit_profile": (GetCreditProfileInput, CreditProfileSummary),
    "get_score_history": (GetScoreHistoryInput, ScoreHistory),
    "get_utilization": (GetUtilizationInput, Utilization),
    "simulate_payoff": (SimulatePayoffInput, PayoffSimulation),
    "explain_factor": (ExplainFactorInput, FactorExplanation),
}
