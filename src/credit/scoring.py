"""Toy credit-scoring formula. NOT a real scoring model.

score = 850 - sum(penalty for each factor), clamped to 300..850.
Each penalty is a simple, documented function of the profile at one month,
so every score change has a cause we can read straight off the data.
The rules are written out in docs/scoring.md; keep the two in sync.
"""

from credit.factors import FactorCode
from credit.months import months_between
from credit.profile import Account, AccountType, DerogatoryMark, Inquiry, LatePayment, MonthlyScore

BASE_SCORE = 850
MIN_SCORE = 300

UTILIZATION_MAX_PENALTY = 150  # penalty = 150 * utilization (capped at 100%)
LATE_PENALTY = {30: 40, 60: 60, 90: 80}  # per late payment in the last 24 months
LATE_LOOKBACK_MONTHS = 24
LATE_HALVED_AFTER_MONTHS = 12  # lates older than this count half
LATE_MAX_PENALTY = 200
INQUIRY_PENALTY = 12  # per hard inquiry in the last 12 months
INQUIRY_LOOKBACK_MONTHS = 12
INQUIRY_MAX_PENALTY = 60
AGE_TARGET_MONTHS = 84  # average account age at which the penalty reaches 0
AGE_PENALTY_PER_MONTH = 0.7
MIX_PENALTY = {1: 30, 2: 15}  # by number of distinct open account types; 3+ → 0
DEROGATORY_PENALTY = 100  # per collection / charge-off on file
DEROGATORY_MAX_PENALTY = 200


def is_open(account: Account, month: str) -> bool:
    opened = months_between(account.opened, month) >= 0
    not_closed = account.closed is None or months_between(account.closed, month) < 0
    return opened and not_closed


def utilization(accounts: list[Account], months: list[str], i: int) -> float | None:
    """Total card balance / total card limit for open cards at month i. None if no open cards."""
    cards = [a for a in accounts if a.type == AccountType.CREDIT_CARD and is_open(a, months[i])]
    total_limit = sum(a.credit_limit for a in cards)
    if total_limit == 0:
        return None
    return sum(a.monthly_balances[i] for a in cards) / total_limit


def utilization_penalty(util: float | None) -> int:
    if util is None:
        return 0
    return round(UTILIZATION_MAX_PENALTY * min(util, 1.0))


def payment_history_penalty(late_payments: list[LatePayment], month: str) -> int:
    total = 0.0
    for lp in late_payments:
        age = months_between(lp.month, month)
        if age < 0 or age >= LATE_LOOKBACK_MONTHS:
            continue
        weight = 0.5 if age >= LATE_HALVED_AFTER_MONTHS else 1.0
        total += LATE_PENALTY[lp.days_late] * weight
    return min(round(total), LATE_MAX_PENALTY)


def inquiry_penalty(inquiries: list[Inquiry], month: str) -> int:
    recent = [q for q in inquiries if 0 <= months_between(q.month, month) < INQUIRY_LOOKBACK_MONTHS]
    return min(INQUIRY_PENALTY * len(recent), INQUIRY_MAX_PENALTY)


def average_age_months(accounts: list[Account], month: str) -> float:
    open_accounts = [a for a in accounts if is_open(a, month)]
    if not open_accounts:
        return 0.0
    return sum(months_between(a.opened, month) for a in open_accounts) / len(open_accounts)


def account_age_penalty(accounts: list[Account], month: str) -> int:
    shortfall = max(0.0, AGE_TARGET_MONTHS - average_age_months(accounts, month))
    return round(shortfall * AGE_PENALTY_PER_MONTH)


def credit_mix_penalty(accounts: list[Account], month: str) -> int:
    types = {a.type for a in accounts if is_open(a, month)}
    return MIX_PENALTY.get(len(types), 0)


def derogatory_penalty(marks: list[DerogatoryMark], month: str) -> int:
    on_file = [m for m in marks if months_between(m.month, month) >= 0]
    return min(DEROGATORY_PENALTY * len(on_file), DEROGATORY_MAX_PENALTY)


def compute_penalties(
    accounts: list[Account],
    late_payments: list[LatePayment],
    inquiries: list[Inquiry],
    derogatory_marks: list[DerogatoryMark],
    months: list[str],
    i: int,
) -> dict[FactorCode, int]:
    month = months[i]
    return {
        FactorCode.UTILIZATION: utilization_penalty(utilization(accounts, months, i)),
        FactorCode.PAYMENT_HISTORY: payment_history_penalty(late_payments, month),
        FactorCode.RECENT_INQUIRIES: inquiry_penalty(inquiries, month),
        FactorCode.ACCOUNT_AGE: account_age_penalty(accounts, month),
        FactorCode.CREDIT_MIX: credit_mix_penalty(accounts, month),
        FactorCode.DEROGATORY: derogatory_penalty(derogatory_marks, month),
    }


def score_from_penalties(penalties: dict[FactorCode, int]) -> int:
    return max(MIN_SCORE, BASE_SCORE - sum(penalties.values()))


def compute_score_history(
    accounts: list[Account],
    late_payments: list[LatePayment],
    inquiries: list[Inquiry],
    derogatory_marks: list[DerogatoryMark],
    months: list[str],
) -> list[MonthlyScore]:
    history = []
    for i, month in enumerate(months):
        penalties = compute_penalties(
            accounts, late_payments, inquiries, derogatory_marks, months, i
        )
        history.append(
            MonthlyScore(month=month, score=score_from_penalties(penalties), penalties=penalties)
        )
    return history


def top_factors(penalties: dict[FactorCode, int], n: int = 3) -> list[FactorCode]:
    """Factors with the largest non-zero penalties, largest first (ties: enum order)."""
    order = list(FactorCode)
    ranked = sorted(
        (f for f, p in penalties.items() if p > 0), key=lambda f: (-penalties[f], order.index(f))
    )
    return ranked[:n]
