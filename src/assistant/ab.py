"""A/B assignment for model upgrades (docs/model-upgrade.md).

A conversation is assigned once, by a hash of its id, so it never switches model mid-way
and the same id always lands in the same arm. The variant is recorded on every transcript.
"""

import hashlib


def assign_variant(conversation_id: str, percent: int) -> str:
    """'candidate' for `percent`% of conversations, else 'control'."""
    bucket = int(hashlib.sha256(conversation_id.encode()).hexdigest()[:8], 16) % 100
    return "candidate" if bucket < percent else "control"
