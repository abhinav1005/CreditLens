"""Response cache for eval runs, keyed by a content hash.

The key covers everything that can change the system's answer: the case itself, the
model and request settings, the prompt content hash, the profile dataset, and the tool
fixtures (a proxy for tool behavior). An unchanged case is never re-sampled, which is how
reruns stay reproducible and nearly free.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_FILE = ROOT / "data" / "profiles" / "v1.json"
FIXTURES_FILE = ROOT / "contracts" / "tools" / "fixtures" / "v1.json"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def cache_key(case_payload: dict, model: str, settings: dict, prompt_hash: str) -> str:
    material = {
        "case": case_payload,
        "model": model,
        "settings": settings,
        "prompt_hash": prompt_hash,
        "dataset": _file_hash(DATASET_FILE),
        "tools": _file_hash(FIXTURES_FILE),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


class ResponseCache:
    def __init__(self, directory: str | Path, enabled: bool = True):
        self.dir = Path(directory)
        self.enabled = enabled

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        path = self._path(key)
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, key: str, value: dict) -> None:
        if not self.enabled:
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value))
        tmp.replace(path)  # atomic, safe with parallel workers
