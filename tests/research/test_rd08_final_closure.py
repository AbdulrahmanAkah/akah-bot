from spotbot.research.rd08_final_closure import TrialSequence, classify_near_miss


def test_trial_sequence_is_frozen() -> None:
    assert TrialSequence().total == 76


def test_registered_near_miss_does_not_pass() -> None:
    assert classify_near_miss(0.196680, 0.055994) == "UNCONFIRMED_NEAR_MISS"
    assert classify_near_miss(0.04, 0.04) == "REGISTERED_GATE_PASSED"
