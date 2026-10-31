"""Response cache for eval runs, keyed by a content hash.

The key covers everything that can change the system's answer: the case itself, the
model and request settings, the prompt content hash, the profile dataset, the tool
fixtures, and the answer-producing code itself (see `code_hash`). An unchanged case is
never re-sampled, which is how
reruns stay reproducible and nearly free.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_FILE = ROOT / "data" / "profiles" / "v1.json"
FIXTURES_FILE = ROOT / "contracts" / "tools" / "fixtures" / "v1.json"
CODE_DIRS = ["src/assistant", "src/guardrails", "src/credit"]
# The HTTP layer wraps `run_turn` but never changes an answer, and evals don't call it.
CODE_EXCLUDE = {"src/assistant/api.py"}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def code_hash() -> str:
    """Hash of the code that produces answers (assistant, guardrails, tools, config).

    Any edit here, such as adding a guardrail filter in M3, must invalidate cached answers.
    Otherwise evals would keep scoring outputs from the old pipeline.
    """
    files = sorted(
        p
        for d in CODE_DIRS
        for p in (ROOT / d).rglob("*.py")
        if "__pycache__" not in p.parts and str(p.relative_to(ROOT)) not in CODE_EXCLUDE
    ) + [ROOT / "config.yaml"]
    digest = hashlib.sha256()
    for p in files:
        digest.update(str(p.relative_to(ROOT)).encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()[:16]


def cache_key(case_payload: dict, model: str, settings: dict, prompt_hash: str) -> str:
    material = {
        "case": case_payload,
        "model": model,
        "settings": settings,
        "prompt_hash": prompt_hash,
        "dataset": _file_hash(DATASET_FILE),
        "tools": _file_hash(FIXTURES_FILE),
        "code": code_hash(),
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
