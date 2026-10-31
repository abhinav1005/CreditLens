"""Export tool contracts to JSON Schema in contracts/tools/.

uv run python scripts/export_contracts.py          # write files
uv run python scripts/export_contracts.py --check  # fail if files are out of date
"""

import json
import sys
from pathlib import Path

from credit.tools.contracts import TOOL_CONTRACTS, ToolError

OUT_DIR = Path(__file__).resolve().parents[1] / "contracts" / "tools"


def rendered() -> dict[str, str]:
    files = {}
    for name, (input_model, output_model) in TOOL_CONTRACTS.items():
        files[f"{name}.input.json"] = input_model.model_json_schema()
        files[f"{name}.output.json"] = output_model.model_json_schema()
    files["error.json"] = ToolError.model_json_schema()
    return {k: json.dumps(v, indent=2, sort_keys=True) + "\n" for k, v in files.items()}


def main() -> int:
    files = rendered()
    if "--check" in sys.argv:
        stale = [
            n
            for n, text in files.items()
            if not (OUT_DIR / n).exists() or (OUT_DIR / n).read_text() != text
        ]
        if stale:
            print(
                "out of date: "
                + ", ".join(stale)
                + "\nrun: uv run python scripts/export_contracts.py"
            )
            return 1
        print("contracts up to date")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT_DIR / name).write_text(text)
    print(f"wrote {len(files)} schema files to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
