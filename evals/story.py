"""The plain-language summary of the results, shared by the web Overview page and the README.

Input is the dashboard data, so every number in these sentences is read from the reports.
The words around the numbers are written by hand, and words can go stale when data changes
("the safety rules mattered" might stop being true). `check_claims` states each such claim
as a condition, and a test fails if one stops holding, so the wording gets revisited.
"""

import math

# PRD section 6 sets this target. It is a goal, not a measurement.
PII_RECALL_TARGET = 0.95

MODEL_NAMES = {
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-haiku-5-5": "Haiku 5.5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
}
PROMPT_NAMES = {
    "v1": "All instructions",
    "v1-no-grounding": "Without the “use real numbers” part",
    "v1-no-rules": "Without the safety rules",
    "v1-minimal": "Almost no instructions",
}


def pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def _model(data: dict, model_id: str) -> dict:
    return next(r for r in data["models"]["rows"] if r["model"] == model_id)


def _prompt(x: dict, prompt: str) -> dict:
    return next(r for r in x["ablation"] if r["prompt"] == prompt)


def _harm(x: dict, prompt: str, guardrails: str) -> dict:
    return next(d for d in x["defense"] if d["prompt"] == prompt and d["guardrails"] == guardrails)


def _bars(title: str, rows: list[dict]) -> dict:
    return {"type": "bars", "title": title, "rows": rows}


def reliability_finding(x: dict) -> dict:
    rel = x["reliability"]
    return {
        "id": "noise",
        "headline": "The same exam gave different scores",
        "meaning": (
            f"We ran the exact same test {len(rel['runs'])} times and changed nothing. The score "
            f"still moved between {pct(rel['min'])} and {pct(rel['max'])}. So a small drop after "
            "a change could just be luck."
        ),
        "fine_print": (
            f"{len(rel['flaky'])} of the {rel['n_cases']} questions passed on some runs and "
            f"failed on others. The automatic check uses a shorter {rel['smoke_n']}-question "
            f"test and allows a drop of {rel['gate_limit_cases']} questions, but that test moved "
            f"by {rel['smoke_swing']} by chance. Saved safety-check decisions were reused, so "
            "this measures variation in the chatbot's answers."
        ),
        "charts": [
            {
                "type": "dots",
                "title": "Score on each run, with nothing changed",
                "axis_min": (math.floor(rel["min"] * 100) - 1) / 100,
                "axis_max": (math.ceil(rel["max"] * 100) + 1) / 100,
                "points": [
                    {"label": f"Run {i + 1}", "value": p, "display": pct(p)}
                    for i, p in enumerate(rel["pass_rates"])
                ],
            }
        ],
    }


def model_finding(data: dict, x: dict) -> dict:
    rows = data["models"]["rows"]
    sonnet, haiku = _model(data, "claude-sonnet-5-5"), _model(data, "claude-haiku-5-5")
    times = round(sonnet["cost_per_case_usd"] / haiku["cost_per_case_usd"])
    summary_cards = "insight_grounding"
    rel = x["reliability"]
    return {
        "id": "models",
        "headline": f"A cheap AI model kept up with one that costs {times} times more",
        "meaning": (
            f"The cheaper model ({MODEL_NAMES[haiku['model']]}) scored {pct(haiku['pass_rate'])}. "
            f"The expensive one ({MODEL_NAMES[sonnet['model']]}) scored "
            f"{pct(sonnet['pass_rate'])}. Paying more didn't get better results here."
        ),
        "fine_print": (
            f"Each model was tested once, so this doesn't prove the cheaper one is better. "
            f"{MODEL_NAMES[sonnet['model']]} scored 100% everywhere except written summary cards "
            f"({pct(sonnet['categories'][summary_cards], 0)} against "
            f"{pct(haiku['categories'][summary_cards], 0)}). That is also the least stable part "
            f"of the test: {rel['flaky_by_category'][summary_cards]} of the "
            f"{len(rel['flaky'])} questions that changed between runs were there."
        ),
        "charts": [
            _bars(
                "Test score",
                [
                    {
                        "label": MODEL_NAMES[r["model"]],
                        "value": r["pass_rate"],
                        "display": pct(r["pass_rate"]),
                        "highlight": r["model"] == haiku["model"],
                    }
                    for r in rows
                ],
            ),
            _bars(
                "Cost per 1,000 questions",
                [
                    {
                        "label": MODEL_NAMES[r["model"]],
                        "value": r["cost_per_case_usd"] / sonnet["cost_per_case_usd"],
                        "display": f"${r['cost_per_case_usd'] * 1000:.2f}",
                        "highlight": r["model"] == haiku["model"],
                    }
                    for r in rows
                ],
            ),
        ],
    }


def prompt_finding(x: dict) -> dict:
    full, no_rules = _prompt(x, "v1"), _prompt(x, "v1-no-rules")
    no_numbers, minimal = _prompt(x, "v1-no-grounding"), _prompt(x, "v1-minimal")
    return {
        "id": "prompt",
        "headline": "Some of the chatbot's instructions matter, and some don't",
        "meaning": (
            "We removed parts of its written instructions to see what broke. Without the safety "
            f"rules, it refused only {pct(no_rules['categories']['refusal'], 0)} of the requests "
            f"it should refuse, down from {pct(full['categories']['refusal'], 0)}. Removing the "
            "“use real numbers” part made no real difference."
        ),
        "fine_print": (
            f"Each version was tested once, with the safety checks off. Overall score: "
            f"{pct(full['pass_rate'])} with all instructions, {pct(no_numbers['pass_rate'])} "
            f"without the “use real numbers” part, {pct(no_rules['pass_rate'])} without the "
            f"safety rules and {pct(minimal['pass_rate'])} with almost no instructions."
        ),
        "charts": [
            _bars(
                "Requests it correctly refused",
                [
                    {
                        "label": PROMPT_NAMES[r["prompt"]],
                        "value": r["categories"]["refusal"],
                        "display": pct(r["categories"]["refusal"], 0),
                        "highlight": r["prompt"] == "v1-no-rules",
                    }
                    for r in x["ablation"]
                ],
            )
        ],
    }


def guardrail_finding(x: dict) -> dict:
    weak_off, weak_on = _harm(x, "v1-minimal", "off"), _harm(x, "v1-minimal", "on")
    full_off, full_on = _harm(x, "v1", "off"), _harm(x, "v1", "on")
    return {
        "id": "guardrails",
        "headline": "A safety net caught what the chatbot missed",
        "meaning": (
            f"We gave the chatbot almost no instructions and tried {weak_off['n']} attacks on "
            f"it. {weak_off['harm']} of them worked. With separate safety checks switched on, "
            f"{weak_on['harm']} worked."
        ),
        "fine_print": (
            f"With all its instructions, {full_off['harm']} of {full_off['n']} attacks worked "
            f"without the safety checks and {full_on['harm']} with them. These attacks were "
            "written for this project, so this isn't proof against real attackers."
        ),
        "charts": [
            {
                "type": "before_after",
                "title": "Attacks that worked",
                "before_label": "Safety checks off",
                "after_label": "Safety checks on",
                "rows": [
                    {
                        "label": "Almost no instructions",
                        "before": weak_off["harm"],
                        "after": weak_on["harm"],
                        "n": weak_off["n"],
                    },
                    {
                        "label": "All instructions",
                        "before": full_off["harm"],
                        "after": full_on["harm"],
                        "n": full_off["n"],
                    },
                ],
            }
        ],
    }


GRADER_FINDING = {
    "id": "grader",
    "headline": "The exam itself had a bug",
    "meaning": (
        "It marked good answers like “there's no guarantee your score will go up” as bad "
        "promises. That made the chatbot look worse than it was. We fixed the bug and re-marked "
        "all the saved answers."
    ),
    "fine_print": "Anyone can repeat the re-marking with: uv run python -m evals rescore --all",
    "charts": [],
}


def gaps(data: dict) -> list[str]:
    """What is not finished or not good enough yet. Each line appears only while it's true."""
    golden, calibration, out = data["golden"], data["calibration"], []
    if golden["human_reviewed"] < golden["n_cases"]:
        out.append(
            "An AI wrote the test questions, and a person still needs to check them "
            f"({golden['human_reviewed']} of {golden['n_cases']} done). Until then, treat every "
            "score as rough."
        )
    if not calibration["rows"]:
        out.append("The AI marker hasn't been compared with human marking yet.")
    pii = next(r for r in data["guardrails"]["rows"] if r["guardrail"] == "pii")
    if pii["recall"] < PII_RECALL_TARGET:
        out.append(
            f"The personal-data filter caught {pct(pii['recall'])} of test examples. The goal is "
            f"{pct(PII_RECALL_TARGET, 0)}."
        )
    x = data.get("experiments")
    if x and x["reliability"]["smoke_swing"] > x["reliability"]["gate_limit_cases"]:
        out.append(
            "The automatic check is too strict for how much scores move, so luck can fail it."
        )
    return out


def build_story(data: dict) -> dict:
    golden, x = data["golden"], data.get("experiments")
    attacks = data["end_to_end"]["scenarios"][0]["n"]
    findings = []
    if x:
        findings = [
            reliability_finding(x),
            model_finding(data, x),
            prompt_finding(x),
            guardrail_finding(x),
        ]
    return {
        "title": "An automatic exam for an AI chatbot",
        "summary": (
            "CreditLens is a chatbot that answers questions about credit scores, using made-up "
            "people. The chatbot isn't the point. The point is the exam it has to pass, which "
            "shows whether it can be trusted and whether a change made it worse."
        ),
        "steps": [
            {
                "title": "Ask",
                "text": (
                    f"The chatbot answers {golden['n_cases']} test questions. {attacks} of them "
                    "try to trick it."
                ),
            },
            {
                "title": "Mark",
                "text": "Each answer is marked automatically, like an exam with an answer key.",
            },
            {
                "title": "Catch",
                "text": (
                    "When someone changes the chatbot, it's re-tested. If it got worse, the "
                    "check fails."
                ),
            },
        ],
        "findings": [*findings, GRADER_FINDING],
        "gaps": gaps(data),
    }


def check_claims(data: dict) -> list[str]:
    """Hand-written wording in this file that the data no longer supports. Should be empty."""
    x = data["experiments"]
    rel = x["reliability"]
    noise = rel["max"] - rel["min"]
    sonnet, haiku = _model(data, "claude-sonnet-5-5"), _model(data, "claude-haiku-5-5")
    full, no_rules = _prompt(x, "v1"), _prompt(x, "v1-no-rules")
    no_numbers = _prompt(x, "v1-no-grounding")
    others = [v for k, v in sonnet["categories"].items() if k != "insight_grounding"]
    most_flaky = max(rel["flaky_by_category"], key=rel["flaky_by_category"].get)
    claims = {
        "scores vary with nothing changed": noise > 0,
        "the check can fail by chance": rel["smoke_swing"] > rel["gate_limit_cases"],
        "the cheap model kept up": haiku["pass_rate"] >= sonnet["pass_rate"],
        "paying more didn't get better results": haiku["pass_rate"] >= sonnet["pass_rate"],
        "the cheap model costs less": haiku["cost_per_case_usd"] < sonnet["cost_per_case_usd"],
        "Sonnet is 100% except summary cards": all(v == 1.0 for v in others),
        "summary cards are the least stable category": most_flaky == "insight_grounding",
        "safety rules matter": (no_rules["categories"]["refusal"] < full["categories"]["refusal"]),
        "the numbers section changed nothing beyond noise": (
            abs(no_numbers["pass_rate"] - full["pass_rate"]) <= noise
        ),
        "guardrails stopped the weak prompt's attacks": (
            _harm(x, "v1-minimal", "off")["harm"] > 0 and _harm(x, "v1-minimal", "on")["harm"] == 0
        ),
    }
    return [claim for claim, holds in claims.items() if not holds]
