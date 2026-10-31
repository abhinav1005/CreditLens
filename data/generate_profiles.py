"""Generate the synthetic profile dataset.

uv run python data/generate_profiles.py --seed 42 --out data/profiles/v1.json
"""

import argparse
from pathlib import Path

from credit.generate import dataset_to_json, generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/profiles/v1.json"))
    args = parser.parse_args()
    profiles = generate_dataset(seed=args.seed)
    args.out.write_text(dataset_to_json(profiles))
    print(f"wrote {len(profiles)} profiles to {args.out}")


if __name__ == "__main__":
    main()
