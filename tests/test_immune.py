from erasmus.immune import deterministic_screen


def test_confidence_without_evidence_alerts():
    alerts = deterministic_screen(
        confidence_delta=0.4,
        new_evidence=0,
        authority_delta=0,
        consequence=0.8,
    )
    assert alerts
    assert alerts[0].detector == "confidence_without_evidence"
