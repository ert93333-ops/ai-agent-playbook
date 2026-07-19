"""상태 머신 + 권리 게이트 테스트."""
import pytest

import app.config as config


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    import app.db as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    yield


def _make(license_type="commentary"):
    from app import db
    return db.create_job("kr", category="global_meme", license_type=license_type,
                         source_url="https://example.com/v", source_title="t",
                         priority=50)


def test_happy_path_transitions():
    from app import db
    j = _make()
    for st in ["RIGHTS_OK", "ACQUIRED", "ANALYZED", "EDITED", "RENDERED",
               "APPROVED", "PUBLISHED_YT", "DONE"]:
        db.transition(j, st)
    assert db.get_job(j)["state"] == "DONE"


def test_illegal_transition_raises():
    from app import db
    j = _make()
    with pytest.raises(ValueError):
        db.transition(j, "APPROVED")   # DISCOVERED에서 점프 불가


def test_rights_gate_blocks_unknown_license():
    from app import db
    from app.stages.m2_acquire import rights_gate
    j = _make(license_type=None)
    assert rights_gate(db.get_job(j)) is False
    assert db.get_job(j)["state"] == "BLOCKED_RIGHTS"


def test_retry_then_fail():
    from app import db
    j = _make()
    assert db.record_failure(j, "boom", max_retries=2) is True
    assert db.record_failure(j, "boom", max_retries=2) is False
    assert db.get_job(j)["state"] == "FAILED"


def test_autonomy_level_roundtrip():
    from app import db
    assert db.autonomy_level("kr") == 0
    db.set_autonomy_level("kr", 2)
    assert db.autonomy_level("kr") == 2
