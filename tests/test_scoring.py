from credit.factors import FactorCode
from credit.months import month_range
from credit.profile import Account, AccountType, DerogatoryMark, Inquiry, LatePayment
from credit.scoring import (
    compute_penalties,
    compute_score_history,
    score_from_penalties,
    top_factors,
    utilization,
)

MONTHS = month_range("2026-06", 12)
LAST = len(MONTHS) - 1


def card(balance=1500, limit=5000, opened="2021-06", acc_id="acc_01", closed=None):
    return Account(
        account_id=acc_id,
        masked_number="****1234",
        type=AccountType.CREDIT_CARD,
        creditor_name="Example Bank",
        opened=opened,
        closed=closed,
        credit_limit=limit,
        monthly_balances=[balance] * 12,
    )


def loan(opened="2021-06", acc_id="acc_02"):
    return Account(
        account_id=acc_id,
        masked_number="****5678",
        type=AccountType.AUTO_LOAN,
        creditor_name="Example Auto",
        opened=opened,
        original_amount=20000,
        monthly_balances=[10000] * 12,
    )


def score(accounts, lates=(), inquiries=(), marks=()):
    p = compute_penalties(accounts, list(lates), list(inquiries), list(marks), MONTHS, LAST)
    return score_from_penalties(p), p


def test_docs_example_is_761():
    # Matches the worked example in docs/scoring.md.
    accounts = [card(opened="2021-06"), loan(opened="2021-06")]  # both 60 months old
    s, p = score(accounts, inquiries=[Inquiry(month="2026-02", creditor_name="X")])
    assert p[FactorCode.UTILIZATION] == 45
    assert p[FactorCode.ACCOUNT_AGE] == 17
    assert s == 761


def test_higher_utilization_lowers_score():
    low, _ = score([card(balance=500), loan()])
    high, _ = score([card(balance=4500), loan()])
    assert high < low


def test_late_payment_lowers_score_and_older_lates_count_half():
    base, _ = score([card(), loan()])
    recent, p_recent = score(
        [card(), loan()], lates=[LatePayment(account_id="acc_01", month="2026-05", days_late=30)]
    )
    old, p_old = score(
        [card(), loan()], lates=[LatePayment(account_id="acc_01", month="2025-03", days_late=30)]
    )
    assert recent < old < base
    assert p_recent[FactorCode.PAYMENT_HISTORY] == 40
    assert p_old[FactorCode.PAYMENT_HISTORY] == 20


def test_inquiries_capped():
    _, p = score([card(), loan()], inquiries=[Inquiry(month="2026-01", creditor_name="X")] * 9)
    assert p[FactorCode.RECENT_INQUIRIES] == 60


def test_inquiry_older_than_a_year_ignored():
    _, p = score([card(), loan()], inquiries=[Inquiry(month="2025-06", creditor_name="X")])
    assert p[FactorCode.RECENT_INQUIRIES] == 0


def test_score_clamped_to_range():
    marks = [DerogatoryMark(month="2026-01", kind="COLLECTION")] * 3
    lates = [LatePayment(account_id="acc_01", month="2026-04", days_late=90)] * 5
    s, _ = score(
        [card(balance=5000, opened="2026-05")],
        lates=lates,
        marks=marks,
        inquiries=[Inquiry(month="2026-05", creditor_name="X")] * 5,
    )
    assert s == 300


def test_closed_card_not_counted_in_utilization():
    accounts = [
        card(balance=0, acc_id="acc_01"),
        card(balance=0, limit=10000, acc_id="acc_03", closed="2026-01"),
    ]
    assert utilization(accounts, MONTHS, LAST) == 0.0


def test_score_history_covers_all_months():
    history = compute_score_history([card(), loan()], [], [], [], MONTHS)
    assert [h.month for h in history] == MONTHS
    assert all(300 <= h.score <= 850 for h in history)


def test_top_factors_order():
    p = {f: 0 for f in FactorCode}
    p[FactorCode.UTILIZATION] = 40
    p[FactorCode.CREDIT_MIX] = 40
    p[FactorCode.ACCOUNT_AGE] = 70
    assert top_factors(p) == [FactorCode.ACCOUNT_AGE, FactorCode.UTILIZATION, FactorCode.CREDIT_MIX]
