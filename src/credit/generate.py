"""Seeded generator for synthetic credit profiles.

Everything comes from one `random.Random(seed)`, so the same seed always gives the same
profiles. Scores are never random: they are computed from the generated events by
`credit.scoring`, so each score change has a readable cause.

Creditor names are made up. No person names are generated at all.
"""

import random

from credit.months import from_index, month_range, to_index
from credit.profile import Account, AccountType, CreditProfile, DerogatoryMark, Inquiry, LatePayment
from credit.scoring import compute_score_history

WINDOW_END = "2026-06"  # fixed, so the data doesn't depend on today's date
WINDOW_MONTHS = 12
DEFAULT_COUNT = 50

CARD_ISSUERS = [
    "Northwind Bank",
    "Lakeside Credit Union",
    "Harborview Financial",
    "Summit Card Co",
    "Bluebird Savings",
    "Redwood Trust",
]
LOAN_LENDERS = {
    AccountType.AUTO_LOAN: ["Meridian Auto Finance", "Crossroads Motors Credit"],
    AccountType.STUDENT_LOAN: ["Scholar Loan Services", "Campus Lending Group"],
    AccountType.PERSONAL_LOAN: ["Keystone Personal Lending", "Lakeside Credit Union"],
    AccountType.MORTGAGE: ["Granite Home Loans", "Harborview Financial"],
}


def _masked_number(rng: random.Random) -> str:
    return f"****{rng.randint(0, 9999):04d}"


def _make_card(rng, acc_id, months, opened_index, base_util) -> Account:
    limit = rng.randrange(1000, 15001, 500)
    first = to_index(months[0])
    balances = []
    util = base_util
    for i in range(len(months)):
        if first + i < opened_index:
            balances.append(0)
            continue
        util = min(1.0, max(0.0, util + rng.uniform(-0.08, 0.08)))
        balances.append(round(limit * util))
    return Account(
        account_id=acc_id,
        masked_number=_masked_number(rng),
        type=AccountType.CREDIT_CARD,
        creditor_name=rng.choice(CARD_ISSUERS),
        opened=from_index(opened_index),
        credit_limit=limit,
        monthly_balances=balances,
    )


def _make_loan(rng, acc_id, months, opened_index, loan_type) -> Account:
    amount_range = {
        AccountType.AUTO_LOAN: (8000, 40000),
        AccountType.STUDENT_LOAN: (5000, 60000),
        AccountType.PERSONAL_LOAN: (2000, 20000),
        AccountType.MORTGAGE: (120000, 450000),
    }[loan_type]
    term = {
        AccountType.AUTO_LOAN: 60,
        AccountType.STUDENT_LOAN: 120,
        AccountType.PERSONAL_LOAN: 36,
        AccountType.MORTGAGE: 360,
    }[loan_type]
    amount = rng.randrange(amount_range[0], amount_range[1] + 1, 500)
    first = to_index(months[0])
    balances = []
    for i in range(len(months)):
        age = first + i - opened_index
        if age < 0:
            balances.append(0)
        else:
            # Straight-line paydown keeps the numbers easy to check by hand.
            balances.append(max(0, round(amount * (1 - age / term))))
    return Account(
        account_id=acc_id,
        masked_number=_masked_number(rng),
        type=loan_type,
        creditor_name=rng.choice(LOAN_LENDERS[loan_type]),
        opened=from_index(opened_index),
        original_amount=amount,
        monthly_balances=balances,
    )


def build_profile(
    profile_id,
    months,
    accounts,
    late_payments=(),
    inquiries=(),
    derogatory_marks=(),
    notes="",
    story=None,
) -> CreditProfile:
    """Assemble a profile and compute its score history from its events."""
    late_payments, inquiries, derogatory_marks = (
        list(late_payments),
        list(inquiries),
        list(derogatory_marks),
    )
    history = compute_score_history(accounts, late_payments, inquiries, derogatory_marks, months)
    return CreditProfile(
        profile_id=profile_id,
        months=months,
        accounts=accounts,
        late_payments=late_payments,
        inquiries=inquiries,
        derogatory_marks=derogatory_marks,
        notes=notes,
        score_history=history,
        story=story,
    )


def generate_random_profile(
    rng: random.Random, profile_id: str, months: list[str]
) -> CreditProfile:
    end = to_index(months[-1])
    first = to_index(months[0])
    accounts: list[Account] = []
    inquiries: list[Inquiry] = []

    def opened_month() -> int:
        # Most accounts predate the window; some open inside it.
        return end - rng.randint(1, 180)

    base_util = rng.choice([0.03, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8])
    for _ in range(rng.randint(1, 3)):
        acc_id = f"acc_{len(accounts) + 1:02d}"
        opened = opened_month()
        accounts.append(_make_card(rng, acc_id, months, opened, base_util))
    for loan_type in rng.sample(list(LOAN_LENDERS), k=rng.randint(0, 2)):
        acc_id = f"acc_{len(accounts) + 1:02d}"
        accounts.append(_make_loan(rng, acc_id, months, opened_month(), loan_type))

    # A hard inquiry accompanies every account opened in the last 24 months.
    for acc in accounts:
        if end - to_index(acc.opened) < 24:
            inquiries.append(Inquiry(month=acc.opened, creditor_name=acc.creditor_name))

    late_payments: list[LatePayment] = []
    if rng.random() < 0.3:
        for _ in range(rng.randint(1, 2)):
            acc = rng.choice(accounts)
            earliest = max(to_index(acc.opened) + 1, first - 12)
            if earliest > end:
                continue
            month = from_index(rng.randint(earliest, end))
            late_payments.append(
                LatePayment(
                    account_id=acc.account_id, month=month, days_late=rng.choice([30, 30, 60, 90])
                )
            )
    late_payments.sort(key=lambda lp: (lp.month, lp.account_id))

    derogatory_marks: list[DerogatoryMark] = []
    if rng.random() < 0.06:
        derogatory_marks.append(
            DerogatoryMark(
                month=from_index(end - rng.randint(0, 30)),
                kind=rng.choice(["COLLECTION", "CHARGE_OFF"]),
            )
        )

    inquiries.sort(key=lambda q: q.month)
    return build_profile(profile_id, months, accounts, late_payments, inquiries, derogatory_marks)


def generate_dataset(seed: int = 42, count: int = DEFAULT_COUNT) -> list[CreditProfile]:
    rng = random.Random(seed)
    months = month_range(WINDOW_END, WINDOW_MONTHS)
    return [generate_random_profile(rng, f"p_{n:03d}", months) for n in range(1, count + 1)]


def dataset_to_json(profiles: list[CreditProfile]) -> str:
    """Stable serialization: same profiles → byte-identical text."""
    import json

    payload = {"version": "v1", "profiles": [p.model_dump(mode="json") for p in profiles]}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
