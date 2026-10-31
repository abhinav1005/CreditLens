"""Keep long conversations within a token budget (M4.6).

Older WHOLE turns are dropped first (a turn = a user message plus everything after it, up
to the next user message), so a tool call is never separated from its result. A short note
replaces what was dropped. The newest turn is always kept. Only the model's copy is
trimmed; the transcript keeps the full history.

Tokens are estimated as characters / 4. That's crude but stable, and fine for a budget
(provider token counting would add an API call per turn).
"""

import json

TRIM_NOTE = "[Earlier parts of this conversation were trimmed to save space: {n} message(s).]"


def estimate_tokens(messages: list[dict]) -> int:
    return (
        sum(
            len(json.dumps({k: v for k, v in m.items() if k != "provider_blocks"}))
            for m in messages
        )
        // 4
    )


def split_turns(messages: list[dict]) -> list[list[dict]]:
    turns: list[list[dict]] = []
    for m in messages:
        if m["role"] == "user" or not turns:
            turns.append([m])
        else:
            turns[-1].append(m)
    return turns


def trim_history(messages: list[dict], budget_tokens: int) -> tuple[list[dict], int]:
    """(messages to send, number of messages dropped)."""
    if budget_tokens <= 0 or estimate_tokens(messages) <= budget_tokens:
        return messages, 0
    turns = split_turns(messages)
    dropped = 0
    while len(turns) > 1 and estimate_tokens([m for t in turns for m in t]) > budget_tokens:
        dropped += len(turns.pop(0))
    kept = [m for t in turns for m in t]
    note = {"role": "user", "content": TRIM_NOTE.format(n=dropped)}
    # Keep alternation valid: the note is a user message, so merge it into the first user turn.
    first = kept[0]
    kept[0] = {**first, "content": note["content"] + "\n\n" + first["content"]}
    return kept, dropped
