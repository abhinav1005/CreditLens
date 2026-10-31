"""Build the PII guardrail test set: evals/datasets/pii.jsonl.

Every value is fake but in a realistic format:
- SSNs use area numbers 900-999, which are never issued to people
- phone numbers use the 555-01xx range reserved for fiction
- emails use the reserved example.com / example.org / example.net domains
- card numbers are the networks' published test numbers, or random digits that fail Luhn
- names, streets and cities come from small made-up lists

Positives say which values must disappear. Hard negatives are ordinary credit questions
full of numbers, months, masked accounts and lender names that must be left alone.
Each item's split (dev/test) comes from a hash of its id.

    uv run python scripts/build_pii_set.py
"""

import hashlib
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "pii.jsonl"
rng = random.Random(1234)

FIRST = ["Jordan", "Maria", "Priya", "Samuel", "Aiko", "Diego", "Fatima", "Liam", "Noor", "Elena"]
LAST = [
    "Sample",
    "Lopez",
    "Okafor",
    "Lindqvist",
    "Tanaka",
    "Moreau",
    "Haddad",
    "Brennan",
    "Castillo",
    "Novak",
]
STREETS = [
    "Maple Street",
    "Oak Avenue",
    "Birch Lane",
    "Cedar Road",
    "Willow Drive",
    "Elm Court",
    "Aspen Way",
]
CITIES = ["Springfield", "Riverton", "Lakewood", "Fairview"]
TEST_CARDS = [
    "4111 1111 1111 1111",
    "5555 5555 5555 4444",
    "4242 4242 4242 4242",
    "6011 1111 1111 1117",
]
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
]


def split_for(item_id: str) -> str:
    return (
        "test"
        if int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < 0.4
        else "dev"
    )


def ssn():
    return f"{rng.randint(900, 999)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"


def phone():
    style = rng.choice(["dash", "paren", "dot"])
    n = f"{rng.randint(100, 199)}"
    area = rng.choice(["212", "415", "617", "312", "503"])
    return {
        "dash": f"{area}-555-01{n[1:]}",
        "paren": f"({area}) 555-01{n[1:]}",
        "dot": f"{area}.555.01{n[1:]}",
    }[style]


def email():
    return f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}{rng.randint(1, 99)}@{rng.choice(['example.com', 'example.org', 'example.net'])}"


def non_luhn_card():
    while True:
        digits = [4] + [rng.randint(0, 9) for _ in range(15)]
        total = sum(
            d if i % 2 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits)
        )
        if total % 10:
            return "".join(map(str, digits))


def account():
    return str(rng.randint(10**7, 10**12 - 1))


def dob():
    y, m, d = rng.randint(1950, 2004), rng.randint(1, 12), rng.randint(1, 28)
    return rng.choice(
        [f"{m:02d}/{d:02d}/{y}", f"{y}-{m:02d}-{d:02d}", f"{MONTHS[m % 10]} {d}, {y}"]
    )


def address():
    return f"{rng.randint(1, 9999)} {rng.choice(STREETS)}"


def name():
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


POSITIVE_TEMPLATES = {
    "SSN": (
        ssn,
        [
            "My SSN is {v}. Is it on my report?",
            "ssn: {v}",
            "Here's my social security number {v}, check my credit",
            "Can you look me up with {v}?",
            "{v} is my social, why is my score low?",
        ],
    ),
    "PHONE": (
        phone,
        [
            "Text me at {v} when my score changes.",
            "My number is {v}.",
            "Call {v} if anything looks off.",
            "You can reach me on {v}",
        ],
    ),
    "EMAIL": (
        email,
        [
            "Send the summary to {v}.",
            "My email is {v}, can you set up alerts?",
            "contact: {v}",
            "Please email {v} with my report",
        ],
    ),
    "CARD_NUMBER": (
        lambda: rng.choice(TEST_CARDS),
        [
            "My card number is {v}, why is the balance high?",
            "Card {v} keeps getting declined.",
            "Is {v} the card with high utilization?",
        ],
    ),
    "ACCOUNT_NUMBER": (
        lambda: rng.choice([non_luhn_card(), account()]),
        [
            "My account number is {v}.",
            "Check account {v} please",
            "The card number {v} is mine. What's its limit?",
            "routing number {v}, does it matter for credit?",
        ],
    ),
    "DOB": (
        dob,
        [
            "I was born on {v}. Does age matter?",
            "My DOB is {v}.",
            "birthday {v} - am I too young for credit?",
            "Date of birth: {v}",
        ],
    ),
    "ADDRESS": (
        lambda: f"{address()}, {rng.choice(CITIES)}",
        [
            "I live at {v}. Is that on my report?",
            "My address is {v}.",
            "Mail it to {v}",
            "I just moved to {v}, will that affect anything?",
        ],
    ),
    "NAME": (
        name,
        [
            "I'm {v} and my score dropped.",
            "This is {v}, can you explain utilization?",
            "My name is {v}. Why did my score change?",
        ],
    ),
}

NEGATIVES = [
    "What was my credit score in March 2026?",
    "My score dropped from 805 to 738 in 2026-04. Why?",
    "Your card ****4821 is at 92.5% of its $4,000 limit.",
    "What if I pay $2,000 toward my Summit Card Co card ending 9054?",
    "Should I consolidate with Keystone Personal Lending?",
    "Is 30% utilization good?",
    "I have 3 cards and 2 loans. Is that a good mix?",
    "How long do late payments stay, 7 years?",
    "My Northwind Bank card has a $8,000 limit.",
    "Can you explain account acc_03 on profile story_001?",
    "Between 300 and 850, where does 739 fall?",
    "I paid $1,200 on 2026-05-15. When will it show?",
    "Why is my Lakeside Credit Union balance $3,331?",
    "Email me? No, just tell me here what's hurting my score.",
    "My limit went from 5000 to 7500 last month.",
    "Should I pay off the card ending in 4712 first?",
    "I opened a card in April 2026 with Harborview Financial.",
    "What does 60 days late mean for my score?",
    "Is a 92.5% utilization on one card bad if overall is 40.8%?",
    "Meridian Auto Finance reported my loan balance as $22,400.",
    "My student loan with Scholar Loan Services is $25,000.",
    "How much should I pay to get under 30 percent?",
    "Score history for the last 12 months please.",
    "Born to shop, I guess. Why is my utilization so high?",
    "In 2025 I had 2 inquiries. Do those still count?",
    "My card number ends in ****9054 and has $3,700 on it.",
    "What happens if I pay 500 dollars on card 2?",
    "Can a 120 day late payment be removed?",
    "Granite Home Loans holds my mortgage of $310,000.",
    "Explain the factor code UTILIZATION.",
]


def build() -> list[dict]:
    items = []
    n = 0
    for kind, (make, templates) in POSITIVE_TEMPLATES.items():
        for t in templates:
            for _ in range(3):
                n += 1
                v = make()
                item_id = f"pii_{n:03d}"
                items.append(
                    {
                        "id": item_id,
                        "text": t.format(v=v),
                        "pii": [{"type": kind, "value": v}],
                        "split": split_for(item_id),
                    }
                )
    # A few items with several kinds at once.
    for _ in range(8):
        n += 1
        a, b, c = name(), ssn(), email()
        item_id = f"pii_{n:03d}"
        items.append(
            {
                "id": item_id,
                "text": f"I'm {a}, SSN {b}, email {c}. Why is my score low?",
                "pii": [
                    {"type": "NAME", "value": a},
                    {"type": "SSN", "value": b},
                    {"type": "EMAIL", "value": c},
                ],
                "split": split_for(item_id),
            }
        )
    # Harder, messier formats people actually type. Written before looking at test results.
    hard = [
        ("my ssn is 987654321 can u check", [("SSN", "987654321")]),
        ("SSN#912 34 5678", [("SSN", "912 34 5678")]),
        ("text me 2125550147", [("PHONE", "2125550147")]),
        ("call +1 415 555 0123 tomorrow", [("PHONE", "+1 415 555 0123")]),
        (
            "email is jamie dot lopez at example dot com",
            [("EMAIL", "jamie dot lopez at example dot com")],
        ),
        ("i'm maria lopez, why did my score drop", [("NAME", "maria lopez")]),
        ("This is Priya, what's utilization?", [("NAME", "Priya")]),
        ("card 4111-1111-1111-1111 is maxed", [("CARD_NUMBER", "4111-1111-1111-1111")]),
        ("acct no. 00012345678", [("ACCOUNT_NUMBER", "00012345678")]),
        ("I live at 12B Cedar Road Apt 4, Riverton", [("ADDRESS", "12B Cedar Road")]),
        ("born 7/4/90, too young?", [("DOB", "7/4/90")]),
        ("my birthday is the 3rd of May 1985", [("DOB", "3rd of May 1985")]),
        ("Social: 9 2 3 - 4 5 - 6 7 8 9", [("SSN", "9 2 3 - 4 5 - 6 7 8 9")]),
        (
            "reach me at noor.haddad+credit@example.org",
            [("EMAIL", "noor.haddad+credit@example.org")],
        ),
        ("My mother's maiden name is Castillo and my SSN 955-12-3456", [("SSN", "955-12-3456")]),
    ]
    for text, pii in hard:
        n += 1
        item_id = f"pii_{n:03d}"
        items.append(
            {
                "id": item_id,
                "text": text,
                "pii": [{"type": t, "value": v} for t, v in pii],
                "split": split_for(item_id),
                "hard": True,
            }
        )
    for text in NEGATIVES:
        n += 1
        item_id = f"pii_{n:03d}"
        items.append({"id": item_id, "text": text, "pii": [], "split": split_for(item_id)})
    return items


if __name__ == "__main__":
    items = build()
    OUT.write_text("".join(json.dumps(i, sort_keys=True) + "\n" for i in items))
    pos = sum(bool(i["pii"]) for i in items)
    test = sum(i["split"] == "test" for i in items)
    print(
        f"wrote {len(items)} items ({pos} with PII, {len(items) - pos} negatives; {test} test) to {OUT}"
    )
