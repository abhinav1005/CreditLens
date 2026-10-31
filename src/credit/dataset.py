"""Load the committed profile dataset. Evals and tools read this file, not the generator."""

import json
from functools import lru_cache
from pathlib import Path

from credit.profile import CreditProfile

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "profiles" / "v1.json"


@lru_cache(maxsize=4)
def load_profiles(path: Path = DATASET_PATH) -> dict[str, CreditProfile]:
    payload = json.loads(path.read_text())
    return {p["profile_id"]: CreditProfile.model_validate(p) for p in payload["profiles"]}
