from evals.labeling import load_pool
from evals.split import assign, build_split, load_split


def test_assignment_is_deterministic_and_near_target():
    ids = [i["item_id"] for i in load_pool()]
    assert build_split(ids) == build_split(list(reversed(ids)))
    share = sum(assign(i) == "test" for i in ids) / len(ids)
    assert 0.2 < share < 0.4


def test_committed_split_matches_pool():
    split = load_split()
    pool_ids = {i["item_id"] for i in load_pool()}
    assert set(split) == pool_ids
    assert all(split[i] == assign(i) for i in pool_ids)
