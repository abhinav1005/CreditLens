import pytest

from credit.factors import FactorCode as F
from credit.generate import generate_dataset
from credit.stories import INJECTION_PAYLOADS, build_story_profiles, default_months

STORIES = {p.profile_id: p for p in build_story_profiles(default_months())}

# The cause each story was designed to have. If the formula changes and these break,
# the story (not this table) needs fixing.
DESIGNED = {
    # New account lowers average age (+17 penalty) more than the inquiry does (+12).
    "story_001": ("drop", [F.UTILIZATION, F.ACCOUNT_AGE, F.RECENT_INQUIRIES]),
    "story_002": ("drop", [F.PAYMENT_HISTORY]),
    "story_003": ("drop", [F.DEROGATORY]),
    "story_004": ("rise", [F.UTILIZATION]),
}


@pytest.mark.parametrize("profile_id", sorted(DESIGNED))
def test_story_cause_matches_design(profile_id):
    story = STORIES[profile_id].story
    direction, cause = DESIGNED[profile_id]
    assert story.direction == direction
    assert story.change_cause == cause


@pytest.mark.parametrize("profile_id", sorted(DESIGNED))
def test_score_moves_in_story_direction(profile_id):
    p = STORIES[profile_id]
    i = p.months.index(p.story.change_month)
    delta = p.score_history[i].score - p.score_history[i - 1].score
    assert (delta < 0) if p.story.direction == "drop" else (delta > 0)
    assert abs(delta) >= 10


def test_dataset_contains_all_groups():
    ids = [p.profile_id for p in generate_dataset()]
    assert sum(i.startswith("p_") for i in ids) == 50
    assert sum(i.startswith("story_") for i in ids) == 4
    assert [i for i in ids if i.startswith("inj_")] == sorted(INJECTION_PAYLOADS)


def test_injection_payloads_are_planted():
    profiles = {p.profile_id: p for p in generate_dataset()}
    for profile_id, (_, payload) in INJECTION_PAYLOADS.items():
        assert payload in profiles[profile_id].model_dump_json()


def test_adding_stories_does_not_change_random_profiles():
    import random

    from credit.generate import generate_random_profile

    rng = random.Random(42)
    first = generate_random_profile(rng, "p_001", default_months())
    assert generate_dataset()[0] == first
