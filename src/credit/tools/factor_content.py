"""Static, educational explanations for each scoring factor (served by `explain_factor`).

General credit education only. No score promises, no product or lender recommendations.
"""

from credit.factors import FactorCode

FACTOR_CONTENT: dict[FactorCode, dict] = {
    FactorCode.UTILIZATION: {
        "title": "Credit utilization",
        "explanation": (
            "Utilization is how much of your available revolving credit you're using: your total "
            "credit card balances divided by your total credit card limits. Lower utilization "
            "generally reads as less risk. It's calculated from the balances your card issuers "
            "report, usually around your statement date, so it can change month to month."
        ),
        "what_helps": [
            "Paying balances down before the statement date",
            "Spreading balances across cards instead of maxing one out",
            "Avoiding closing old cards you don't use, since that removes available credit",
        ],
    },
    FactorCode.PAYMENT_HISTORY: {
        "title": "Payment history",
        "explanation": (
            "Payment history records whether you paid on time. Payments reported 30, 60, or 90+ "
            "days late count against you, and later is worse. The effect fades as the late "
            "payment gets older."
        ),
        "what_helps": [
            "Setting up automatic minimum payments so nothing is missed",
            "Bringing any past-due account current as soon as possible",
            "If a late payment was reported in error, disputing it with the credit bureau",
        ],
    },
    FactorCode.RECENT_INQUIRIES: {
        "title": "Recent hard inquiries",
        "explanation": (
            "A hard inquiry is recorded when you apply for new credit and a lender checks your "
            "report. Several in a short period can suggest you're taking on new debt. Checking "
            "your own credit is a soft inquiry and doesn't count."
        ),
        "what_helps": [
            "Applying for new credit only when you need it",
            "Giving recent inquiries time to age",
        ],
    },
    FactorCode.ACCOUNT_AGE: {
        "title": "Age of accounts",
        "explanation": (
            "This looks at how long your accounts have been open, including the average age. "
            "Opening new accounts lowers the average age. A longer history gives lenders more "
            "information."
        ),
        "what_helps": [
            "Keeping older accounts open and in good standing",
            "Being selective about opening new accounts",
        ],
    },
    FactorCode.CREDIT_MIX: {
        "title": "Credit mix",
        "explanation": (
            "Credit mix is the variety of account types you have, such as credit cards and "
            "installment loans (auto, student, personal, mortgage). It usually matters less than "
            "payment history or utilization."
        ),
        "what_helps": [
            "Managing the accounts you already have well",
            "Not opening a loan just to change your mix",
        ],
    },
    FactorCode.DEROGATORY: {
        "title": "Derogatory marks",
        "explanation": (
            "Derogatory marks are serious negative items such as accounts sent to collections or "
            "charged off. They weigh heavily and can stay on a report for years."
        ),
        "what_helps": [
            "Checking that each item is accurate, and disputing errors with the credit bureau",
            "Learning your rights from official sources such as the CFPB (consumerfinance.gov)",
        ],
    },
}
