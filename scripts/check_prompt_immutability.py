"""Committed prompt files are immutable: a change means a new version file.

prompts/prompts.lock.json stores the sha256 of every prompt file.

    uv run python scripts/check_prompt_immutability.py          # fail if a locked file changed
    uv run python scripts/check_prompt_immutability.py --lock   # add NEW files to the lock

`--lock` never overwrites an existing entry, so the only way past a failure is a new file.
"""

import hashlib
import json
import sys
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
LOCK_NAME = "prompts.lock.json"


def file_hashes(prompts_dir: Path) -> dict[str, str]:
    return {
        str(p.relative_to(prompts_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(prompts_dir.rglob("*"))
        if p.is_file() and p.name != LOCK_NAME
    }


def check(prompts_dir: Path) -> list[str]:
    lock_path = prompts_dir / LOCK_NAME
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    current = file_hashes(prompts_dir)
    problems = []
    for name, digest in lock.items():
        if name not in current:
            problems.append(f"{name}: locked prompt file was deleted")
        elif current[name] != digest:
            problems.append(f"{name}: locked prompt file was edited; create a new version instead")
    for name in current.keys() - lock.keys():
        problems.append(f"{name}: new prompt file not in lock; run with --lock")
    return problems


def lock_new(prompts_dir: Path) -> list[str]:
    lock_path = prompts_dir / LOCK_NAME
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    added = [n for n in file_hashes(prompts_dir) if n not in lock]
    for name, digest in file_hashes(prompts_dir).items():
        lock.setdefault(name, digest)
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return added


if __name__ == "__main__":
    if "--lock" in sys.argv:
        print("locked: " + (", ".join(lock_new(PROMPTS_DIR)) or "nothing new"))
        sys.exit(0)
    problems = check(PROMPTS_DIR)
    print("\n".join(problems) if problems else "prompt files unchanged")
    sys.exit(1 if problems else 0)
