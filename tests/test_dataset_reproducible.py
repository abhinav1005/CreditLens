"""The committed dataset must be exactly what the generator produces with seed 42.

If this fails, either regenerate on purpose as a new version (v2, with golden cases updated)
or undo the generator change. Never edit v1.json by hand.
"""

from credit.dataset import DATASET_PATH, load_profiles
from credit.generate import dataset_to_json, generate_dataset


def test_v1_is_byte_for_byte_reproducible():
    assert DATASET_PATH.read_text() == dataset_to_json(generate_dataset(seed=42))


def test_v1_loads_and_validates():
    profiles = load_profiles()
    assert len(profiles) == 57
    assert profiles["story_001"].story.kind == "new_card_high_utilization"
