"""Dev/test split for judge calibration, frozen before any labels or judge iteration.

Each pool item goes to `test` if its id hashes into the bottom 30%. The split depends only
on the item id, so it can't be influenced by labels or judge results. Judge-prompt changes
are tuned on `dev`; only `test` agreement is reported as the headline number.

    uv run python -m evals.split    # writes label_split.json once; refuses to change it
"""

import hashlib
import json
import sys

from evals.cases import DATASETS_DIR
from evals.labeling import load_pool

SPLIT_PATH = DATASETS_DIR / "label_split.json"
TEST_FRACTION = 0.30


def assign(item_id: str) -> str:
    bucket = int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if bucket < TEST_FRACTION else "dev"


def build_split(item_ids: list[str]) -> dict:
    split = {"test_fraction": TEST_FRACTION, "dev": [], "test": []}
    for i in sorted(item_ids):
        split[assign(i)].append(i)
    return split


def load_split() -> dict[str, str]:
    data = json.loads(SPLIT_PATH.read_text())
    return {i: s for s in ("dev", "test") for i in data[s]}


if __name__ == "__main__":
    split = build_split([i["item_id"] for i in load_pool()])
    text = json.dumps(split, indent=1) + "\n"
    if SPLIT_PATH.exists() and SPLIT_PATH.read_text() != text:
        sys.exit(
            "label_split.json already exists and differs; the split is frozen. Not overwriting."
        )
    SPLIT_PATH.write_text(text)
    print(f"dev {len(split['dev'])}, test {len(split['test'])} → {SPLIT_PATH}")
