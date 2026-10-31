from credit.generate import dataset_to_json, generate_dataset
from credit.scoring import compute_score_history


def test_same_seed_same_output():
    assert dataset_to_json(generate_dataset(seed=7)) == dataset_to_json(generate_dataset(seed=7))


def test_different_seed_different_output():
    assert dataset_to_json(generate_dataset(seed=7)) != dataset_to_json(generate_dataset(seed=8))


def test_default_count_and_ids():
    profiles = generate_dataset()
    assert len(profiles) == 57  # 50 random + 4 story + 3 injection
    assert profiles[0].profile_id == "p_001"
    assert len({p.profile_id for p in profiles}) == 57


def test_scores_come_from_formula():
    for p in generate_dataset():
        expected = compute_score_history(
            p.accounts, p.late_payments, p.inquiries, p.derogatory_marks, p.months
        )
        assert p.score_history == expected


def test_scores_vary_across_profiles():
    scores = {p.score_history[-1].score for p in generate_dataset()}
    assert len(scores) > 20
