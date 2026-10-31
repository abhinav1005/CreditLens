import json

import pytest

from assistant.loop import COMPLIANCE_FALLBACK, run_turn
from assistant.providers.fake import FakeProvider, FakeTurn
from guardrails.compliance import ComplianceGuard, sentence_violations
from guardrails.pipeline import GuardrailSet

DISC = "_Educational information only, not financial advice._"


def verdict(rules):
    return FakeTurn(
        text=json.dumps(
            {
                "rationale": "r",
                "violated_rules": rules,
                "verdict": "violation" if rules else "compliant",
            }
        )
    )


@pytest.mark.parametrize(
    "sentence,rule",
    [
        ("Paying it off will raise your score by 40 points.", "no_score_promises"),
        ("Your score will be back above 800 next month.", "no_score_promises"),
        ("You'll hit 750 by spring.", "no_score_promises"),
        ("I recommend Summit Card Co for building credit.", "no_product_recommendations"),
        ("Married people tend to have better scores.", "no_protected_characteristics"),
    ],
)
def test_sentence_rules_catch_violations(sentence, rule):
    assert rule in sentence_violations(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "I can't predict how much your score will go up.",
        "Your score dropped 67 points in April.",
        "Your Summit Card Co card is at 92.5% utilization.",
        "Marital status is not a factor in credit scores.",
        "Lower utilization generally helps.",
    ],
)
def test_sentence_rules_allow_compliant_text(sentence):
    assert sentence_violations(sentence) == []


def run(answer_turns, classifier_verdicts, tmp_path):
    clf = FakeProvider([verdict(v) for v in classifier_verdicts])  # scripted classifier verdicts
    guard = ComplianceGuard(provider=clf, cache_dir=tmp_path)
    fake = FakeProvider(answer_turns)
    r = run_turn(
        [{"role": "user", "content": "Will paying off my card help?"}],
        "p_010",
        provider=fake,
        guardrails=GuardrailSet(output=[guard]),
    )
    return r, fake


def test_compliant_reply_untouched(tmp_path):
    r, fake = run([FakeTurn(text=f"Lower utilization generally helps.\n\n{DISC}")], [[]], tmp_path)
    assert not r.retracted and r.extra["compliance"] == {
        "violations": [],
        "regenerated": False,
        "fallback": False,
    }
    assert len(fake.requests) == 1


def test_violation_regenerates_once(tmp_path):
    r, fake = run(
        [
            # Passes the sentence rules; only the classifier catches it.
            FakeTurn(text="Lots of people love the Summit Platinum card for this."),
            FakeTurn(text=f"Lower utilization helps.\n\n{DISC}"),
        ],
        [["no_product_recommendations"], []],
        tmp_path,
    )
    assert r.retracted and r.final_text.startswith("Lower utilization helps.")
    assert r.extra["compliance"]["regenerated"] and not r.extra["compliance"]["fallback"]
    assert "no_product_recommendations" in fake.requests[1].messages[-1]["content"]
    assert any(e["type"] == "retract" for e in r.events)
    assert r.messages[-1]["role"] == "assistant"  # retry exchange kept out of the transcript


def test_second_violation_falls_back(tmp_path):
    r, _ = run(
        [FakeTurn(text="Trust me on this."), FakeTurn(text="Still trust me.")],
        [["no_score_promises"], ["no_score_promises"]],
        tmp_path,
    )
    assert r.final_text == COMPLIANCE_FALLBACK and r.extra["compliance"]["fallback"]


def test_rule_sentence_dropped_before_streaming(tmp_path):
    r, _ = run(
        [FakeTurn(text=f"Utilization matters. This will raise your score by 40 points. {DISC}")],
        [[]],
        tmp_path,
    )
    assert "40 points" not in r.final_text and "Utilization matters." in r.final_text
