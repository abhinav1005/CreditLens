import pytest
from pydantic import ValidationError

from credit.factors import FactorCode
from credit.profile import Account, AccountType, CreditProfile

MONTHS = [f"2025-{m:02d}" for m in range(7, 13)] + [f"2026-{m:02d}" for m in range(1, 7)]


def _card(**overrides):
    data = dict(
        account_id="acc_01",
        masked_number="****4821",
        type=AccountType.CREDIT_CARD,
        creditor_name="Example Bank",
        opened="2020-03",
        credit_limit=5000,
        monthly_balances=[1000] * 12,
    )
    data.update(overrides)
    return Account(**data)


def _profile(**overrides):
    scores = [{"month": m, "score": 720, "penalties": {FactorCode.UTILIZATION: 30}} for m in MONTHS]
    data = dict(profile_id="p_001", months=MONTHS, accounts=[_card()], score_history=scores)
    data.update(overrides)
    return CreditProfile(**data)


def test_valid_profile():
    assert _profile().accounts[0].credit_limit == 5000


@pytest.mark.parametrize("number", ["4111111111114821", "****482", "1234-4821"])
def test_account_number_must_be_masked(number):
    with pytest.raises(ValidationError):
        _card(masked_number=number)


def test_card_requires_limit():
    with pytest.raises(ValidationError):
        _card(credit_limit=None)


def test_loan_requires_original_amount():
    with pytest.raises(ValidationError):
        _card(type=AccountType.AUTO_LOAN, credit_limit=None)


def test_balances_must_align_with_months():
    with pytest.raises(ValidationError):
        _profile(accounts=[_card(monthly_balances=[0] * 11)])


def test_late_payment_must_reference_known_account():
    with pytest.raises(ValidationError):
        _profile(late_payments=[{"account_id": "acc_99", "month": "2026-01", "days_late": 30}])


def test_profile_id_prefixes():
    _profile(profile_id="story_001")
    _profile(profile_id="inj_001")
    with pytest.raises(ValidationError):
        _profile(profile_id="real_001")
