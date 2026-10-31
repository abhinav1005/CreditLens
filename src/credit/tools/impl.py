"""In-process Python implementations of the five tools.

Each tool takes its validated input model and returns its output model, or raises
`ToolFailure`. `call_tool(name, args)` is the entry point the assistant uses: it validates
raw arguments from the LLM and always returns a plain dict (output or error), never raises.
"""

from pydantic import BaseModel, ValidationError

from credit.dataset import load_profiles
from credit.months import months_between
from credit.profile import AccountType, CreditProfile
from credit.scoring import is_open, top_factors
from credit.tools.contracts import (
    TOOL_CONTRACTS,
    AccountSummary,
    CardUtilization,
    CreditProfileSummary,
    ExplainFactorInput,
    FactorExplanation,
    GetCreditProfileInput,
    GetScoreHistoryInput,
    GetUtilizationInput,
    InquirySummary,
    LatePaymentSummary,
    PayoffSimulation,
    ScoreHistory,
    ScorePoint,
    SimulatePayoffInput,
    ToolError,
    ToolErrorCode,
    Utilization,
)
from credit.tools.factor_content import FACTOR_CONTENT


class ToolFailure(Exception):
    def __init__(self, code: ToolErrorCode, message: str):
        super().__init__(message)
        self.error = ToolError(error_code=code, message=message)


def pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1)


def _profile(profile_id: str) -> CreditProfile:
    profile = load_profiles().get(profile_id)
    if profile is None:
        raise ToolFailure(ToolErrorCode.PROFILE_NOT_FOUND, f"No profile with id {profile_id}")
    return profile


def _open_cards(profile: CreditProfile):
    as_of = profile.months[-1]
    return [a for a in profile.accounts if a.type == AccountType.CREDIT_CARD and is_open(a, as_of)]


def get_credit_profile(inp: GetCreditProfileInput) -> CreditProfileSummary:
    p = _profile(inp.profile_id)
    as_of = p.months[-1]
    latest = p.score_history[-1]
    accounts = [
        AccountSummary(
            account_id=a.account_id,
            masked_number=a.masked_number,
            type=a.type,
            creditor_name=a.creditor_name,
            opened=a.opened,
            status="OPEN" if is_open(a, as_of) else "CLOSED",
            balance=a.monthly_balances[-1],
            credit_limit=a.credit_limit,
            original_amount=a.original_amount,
        )
        for a in p.accounts
    ]
    return CreditProfileSummary(
        profile_id=p.profile_id,
        as_of=as_of,
        score=latest.score,
        top_factors=top_factors(latest.penalties),
        factor_penalties=latest.penalties,
        accounts=accounts,
        late_payments_last_24_months=[
            LatePaymentSummary(account_id=lp.account_id, month=lp.month, days_late=lp.days_late)
            for lp in p.late_payments
            if 0 <= months_between(lp.month, as_of) < 24
        ],
        hard_inquiries_last_12_months=[
            InquirySummary(month=q.month, creditor_name=q.creditor_name)
            for q in p.inquiries
            if 0 <= months_between(q.month, as_of) < 12
        ],
        derogatory_marks=sum(1 for m in p.derogatory_marks if months_between(m.month, as_of) >= 0),
        notes=p.notes,
    )


def get_score_history(inp: GetScoreHistoryInput) -> ScoreHistory:
    p = _profile(inp.profile_id)
    points = [ScorePoint(month=s.month, score=s.score) for s in p.score_history[-inp.months :]]
    return ScoreHistory(profile_id=p.profile_id, points=points)


def get_utilization(inp: GetUtilizationInput) -> Utilization:
    p = _profile(inp.profile_id)
    cards = _open_cards(p)
    total_balance = sum(a.monthly_balances[-1] for a in cards)
    total_limit = sum(a.credit_limit for a in cards)
    return Utilization(
        profile_id=p.profile_id,
        as_of=p.months[-1],
        total_balance=total_balance,
        total_limit=total_limit,
        overall_utilization_pct=pct(total_balance, total_limit) if total_limit else None,
        cards=[
            CardUtilization(
                account_id=a.account_id,
                masked_number=a.masked_number,
                creditor_name=a.creditor_name,
                balance=a.monthly_balances[-1],
                credit_limit=a.credit_limit,
                utilization_pct=pct(a.monthly_balances[-1], a.credit_limit),
            )
            for a in cards
        ],
    )


def simulate_payoff(inp: SimulatePayoffInput) -> PayoffSimulation:
    p = _profile(inp.profile_id)
    account = next((a for a in p.accounts if a.account_id == inp.account_id), None)
    if account is None:
        raise ToolFailure(
            ToolErrorCode.ACCOUNT_NOT_FOUND, f"No account {inp.account_id} on this profile"
        )
    if account.type != AccountType.CREDIT_CARD:
        raise ToolFailure(
            ToolErrorCode.NOT_A_CREDIT_CARD,
            "Payoff simulation only applies to credit cards (utilization)",
        )
    if not is_open(account, p.months[-1]):
        raise ToolFailure(ToolErrorCode.INVALID_INPUT, f"Account {inp.account_id} is closed")
    cards = _open_cards(p)
    total_balance = sum(a.monthly_balances[-1] for a in cards)
    total_limit = sum(a.credit_limit for a in cards)
    before = account.monthly_balances[-1]
    applied = min(inp.amount, before)
    return PayoffSimulation(
        profile_id=p.profile_id,
        account_id=account.account_id,
        requested_amount=inp.amount,
        applied_amount=applied,
        card_balance_before=before,
        card_balance_after=before - applied,
        card_utilization_pct_before=pct(before, account.credit_limit),
        card_utilization_pct_after=pct(before - applied, account.credit_limit),
        overall_utilization_pct_before=pct(total_balance, total_limit),
        overall_utilization_pct_after=pct(total_balance - applied, total_limit),
    )


def explain_factor(inp: ExplainFactorInput) -> FactorExplanation:
    return FactorExplanation(factor_code=inp.factor_code, **FACTOR_CONTENT[inp.factor_code])


TOOL_FUNCTIONS = {
    "get_credit_profile": get_credit_profile,
    "get_score_history": get_score_history,
    "get_utilization": get_utilization,
    "simulate_payoff": simulate_payoff,
    "explain_factor": explain_factor,
}
assert TOOL_FUNCTIONS.keys() == TOOL_CONTRACTS.keys()


def call_tool(name: str, args: dict) -> dict:
    """Validate raw args, run the tool, return a JSON-ready dict (errors as {"error": ...})."""
    if name not in TOOL_FUNCTIONS:
        return {
            "error": ToolError(
                error_code=ToolErrorCode.INVALID_INPUT, message=f"Unknown tool {name}"
            ).model_dump(mode="json")
        }
    input_model, _ = TOOL_CONTRACTS[name]
    try:
        inp: BaseModel = input_model.model_validate(args)
    except ValidationError as exc:
        msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return {
            "error": ToolError(error_code=ToolErrorCode.INVALID_INPUT, message=msg).model_dump(
                mode="json"
            )
        }
    try:
        return TOOL_FUNCTIONS[name](inp).model_dump(mode="json")
    except ToolFailure as failure:
        return {"error": failure.error.model_dump(mode="json")}
