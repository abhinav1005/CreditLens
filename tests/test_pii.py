import json

import pytest

from assistant.loop import run_turn
from assistant.providers.fake import FakeProvider, FakeTurn
from guardrails.pii import PIIRedactor
from guardrails.pipeline import GuardrailSet
from storage.sqlite import SQLiteStorage
from storage.transcripts import transcript_from_turn

G = PIIRedactor()


def redact(text, stage="input"):
    return G.check(text, {"stage": stage}).text


@pytest.mark.parametrize(
    "text,placeholder,original",
    [
        ("My SSN is 123-45-6789.", "<SSN_1>", "123-45-6789"),
        ("Card 4111 1111 1111 1111 is mine.", "<CARD_NUMBER_1>", "4111 1111 1111 1111"),
        ("Write to jamie.example@example.com.", "<EMAIL_1>", "jamie.example@example.com"),
        ("I was born on 03/14/1988.", "<DOB_1>", "03/14/1988"),
        ("Call 555-201-7788.", "<PHONE_1>", "555-201-7788"),
        ("I live at 42 Maple Street.", "<ADDRESS_1>", "42 Maple Street"),
        ("Account 1234567890 please.", "<ACCOUNT_NUMBER_1>", "1234567890"),
        ("I'm Jordan Sample.", "<NAME_1>", "Jordan Sample"),
    ],
)
def test_detects_and_redacts(text, placeholder, original):
    out = redact(text)
    assert placeholder in out and original not in out


@pytest.mark.parametrize(
    "text",
    [
        "What was my credit score in March 2026?",
        "Your card ****4821 is at 92.5% of its $4,000 limit.",
        "Should I consolidate with Keystone Personal Lending?",
        "Email a summary of my credit please.",
        "My score dropped from 805 to 738 in 2026-04.",
    ],
)
def test_leaves_normal_credit_text_alone(text):
    assert redact(text) == text


def test_same_value_same_placeholder_across_messages():
    ctx = {"stage": "input"}  # one shared context = one conversation
    first = G.check("SSN 123-45-6789", ctx).text
    second = G.check("again: 123-45-6789, and 078-05-1120", ctx).text
    assert first == "SSN <SSN_1>" and second == "again: <SSN_1>, and <SSN_2>"


def test_output_stage_skips_names():
    assert redact("Your Summit Card Co card is high, Jordan Sample.", stage="output").endswith(
        "Jordan Sample."
    )


def test_originals_never_reach_model_or_sqlite(tmp_path):
    fake = FakeProvider([FakeTurn(text="I can't use <SSN_1>, but here's your utilization.")])
    msg = "My SSN is 123-45-6789 and email jamie.example@example.com. What's my utilization?"
    r = run_turn(
        [{"role": "user", "content": msg}],
        "p_001",
        provider=fake,
        guardrails=GuardrailSet(input=[G], output=[G]),
    )
    assert "123-45-6789" not in json.dumps([m.messages for m in fake.requests])
    store = SQLiteStorage(tmp_path / "t.sqlite")
    t = transcript_from_turn(r, "c1", source="chat")
    store.put(t)
    raw = (tmp_path / "t.sqlite").read_bytes()
    assert b"123-45-6789" not in raw and b"jamie.example@example.com" not in raw
    assert any(d["name"] == "pii" and d["action"] == "redact" for d in t.guardrail_decisions)


def test_numbering_is_shared_across_messages_in_run_turn():
    """Regression: guardrails get shallow context copies, so the map must be shared up front."""
    fake = FakeProvider([FakeTurn(text="ok")])
    conv = [
        {"role": "user", "content": "My SSN is 912-34-5678."},
        {"role": "assistant", "content": "Noted."},
        {"role": "user", "content": "Sorry, it's actually 955-12-3456, not 912-34-5678."},
    ]
    run_turn(conv, "p_001", provider=fake, guardrails=GuardrailSet(input=[G]))
    users = [m["content"] for m in fake.requests[0].messages if m["role"] == "user"]
    assert users == ["My SSN is <SSN_1>.", "Sorry, it's actually <SSN_2>, not <SSN_1>."]
