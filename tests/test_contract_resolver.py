from erasmus.contract_resolver import Resolution, resolve

def test_immutable_conflicts_halt():
    assert resolve(conflict="stale_sha").resolution is Resolution.HALT

def test_transient_deadlock_quarantines_then_halts():
    assert resolve(conflict="deadlock", attempts=0).retryable
    decision = resolve(conflict="deadlock", attempts=3)
    assert decision.resolution is Resolution.HALT and not decision.retryable

def test_unknown_conflict_denies_without_crashing():
    assert resolve(conflict="anything").resolution is Resolution.DENY
