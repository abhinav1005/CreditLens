"""Pydantic schema for a synthetic credit profile.

All data is generated (see `credit.generate`). Months are "YYYY-MM" strings. Every
per-month list on an account is aligned with `CreditProfile.months` (oldest first).

`creditor_name` and `notes` are free text and must be treated as untrusted input:
some generated profiles (ids starting with `inj_`) carry prompt-injection payloads there.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from credit.factors import FactorCode

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MASKED_NUMBER_PATTERN = r"^\*{4}\d{4}$"


class AccountType(StrEnum):
    CREDIT_CARD = "CREDIT_CARD"
    AUTO_LOAN = "AUTO_LOAN"
    STUDENT_LOAN = "STUDENT_LOAN"
    PERSONAL_LOAN = "PERSONAL_LOAN"
    MORTGAGE = "MORTGAGE"


class Account(BaseModel):
    account_id: str = Field(pattern=r"^acc_\d{2}$")
    masked_number: str = Field(pattern=MASKED_NUMBER_PATTERN)
    type: AccountType
    creditor_name: str  # free text, untrusted
    opened: str = Field(pattern=MONTH_PATTERN)
    closed: str | None = Field(default=None, pattern=MONTH_PATTERN)
    credit_limit: int | None = Field(default=None, gt=0)  # credit cards only
    original_amount: int | None = Field(default=None, gt=0)  # loans only
    # Balance at the end of each month, aligned with CreditProfile.months.
    # 0 for months before the account was opened or after it was closed.
    monthly_balances: list[int]

    @model_validator(mode="after")
    def _limit_matches_type(self) -> "Account":
        is_card = self.type == AccountType.CREDIT_CARD
        if is_card and self.credit_limit is None:
            raise ValueError("credit cards need a credit_limit")
        if not is_card and self.original_amount is None:
            raise ValueError("loans need an original_amount")
        if any(b < 0 for b in self.monthly_balances):
            raise ValueError("balances can't be negative")
        return self


class LatePayment(BaseModel):
    account_id: str
    month: str = Field(pattern=MONTH_PATTERN)
    days_late: Literal[30, 60, 90]


class Inquiry(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    creditor_name: str  # free text, untrusted


class DerogatoryMark(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    kind: Literal["COLLECTION", "CHARGE_OFF"]


class MonthlyScore(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    score: int = Field(ge=300, le=850)
    # Points subtracted from the 850 base by each factor that month (see credit.scoring).
    penalties: dict[FactorCode, int]


class Story(BaseModel):
    """Ground truth for a deliberate scenario profile, used by evals."""

    kind: str
    description: str
    # Factors whose penalties increased the most in the month of the score drop.
    score_drop_cause: list[FactorCode]
    drop_month: str = Field(pattern=MONTH_PATTERN)


class CreditProfile(BaseModel):
    profile_id: str = Field(pattern=r"^(p|story|inj)_\d{3}$")
    months: list[str] = Field(min_length=12, max_length=12)
    accounts: list[Account] = Field(min_length=1)
    late_payments: list[LatePayment] = []
    inquiries: list[Inquiry] = []
    derogatory_marks: list[DerogatoryMark] = []
    notes: str = ""  # free text, untrusted
    score_history: list[MonthlyScore]
    story: Story | None = None

    @model_validator(mode="after")
    def _aligned(self) -> "CreditProfile":
        if self.months != sorted(self.months):
            raise ValueError("months must be in ascending order")
        n = len(self.months)
        for acc in self.accounts:
            if len(acc.monthly_balances) != n:
                raise ValueError(f"{acc.account_id}: monthly_balances must have {n} entries")
        if [s.month for s in self.score_history] != self.months:
            raise ValueError("score_history must cover exactly the profile's months")
        ids = {a.account_id for a in self.accounts}
        if len(ids) != len(self.accounts):
            raise ValueError("duplicate account_id")
        for lp in self.late_payments:
            if lp.account_id not in ids:
                raise ValueError(f"late payment references unknown account {lp.account_id}")
        return self
