"""
Unit tests for src/feedback_manager.py
"""
import json
import pytest

from src.feedback_manager import FeedbackManager


@pytest.fixture
def mgr(tmp_path):
    path = str(tmp_path / "feedback_master.json")
    return FeedbackManager(config_path=path)


# ---------------------------------------------------------------------------
# Default loading
# ---------------------------------------------------------------------------

def test_default_load_has_items(mgr):
    items = mgr.get_all_items()
    assert len(items) > 0


def test_default_active_labels_all_active(mgr):
    active = mgr.get_active_labels()
    all_items = mgr.get_all_items()
    assert len(active) == sum(1 for i in all_items if i.get("active", True))


def test_default_contains_call_done(mgr):
    labels = mgr.get_active_labels()
    assert "통화완료" in labels


# ---------------------------------------------------------------------------
# Load from file
# ---------------------------------------------------------------------------

def test_load_from_file(tmp_path):
    data = {
        "version": 1,
        "items": [
            {"id": "A", "label": "테스트", "active": True, "aliases": [], "sort_order": 1}
        ],
    }
    p = tmp_path / "fb.json"
    p.write_text(json.dumps(data, ensure_ascii=False))
    m = FeedbackManager(str(p))
    assert m.get_active_labels() == ["테스트"]


# ---------------------------------------------------------------------------
# get_active_labels
# ---------------------------------------------------------------------------

def test_only_active_in_active_labels(mgr):
    mgr.deactivate_item("NO_ANSWER")
    active = mgr.get_active_labels()
    assert "부재" not in active


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------

def test_add_item(mgr):
    before = len(mgr.get_all_items())
    mgr.add_item("신규항목")
    assert len(mgr.get_all_items()) == before + 1
    assert "신규항목" in mgr.get_active_labels()


def test_add_item_is_active_by_default(mgr):
    mgr.add_item("새항목")
    items = [i for i in mgr.get_all_items() if i["label"] == "새항목"]
    assert items[0]["active"] is True


# ---------------------------------------------------------------------------
# deactivate / toggle
# ---------------------------------------------------------------------------

def test_deactivate_item(mgr):
    mgr.deactivate_item("CALL_DONE")
    active = mgr.get_active_labels()
    assert "통화완료" not in active
    all_labels = [i["label"] for i in mgr.get_all_items()]
    assert "통화완료" in all_labels     # still present, just inactive


def test_toggle_active(mgr):
    mgr.deactivate_item("CALL_DONE")
    mgr.toggle_active("CALL_DONE")
    assert "통화완료" in mgr.get_active_labels()


# ---------------------------------------------------------------------------
# get_unknown_labels
# ---------------------------------------------------------------------------

def test_get_unknown_labels_known_returns_empty(mgr):
    unknown = mgr.get_unknown_labels(["통화완료", "부재"])
    assert unknown == []


def test_get_unknown_labels_unknown_returned(mgr):
    unknown = mgr.get_unknown_labels(["완전히없는값XYZ"])
    assert "완전히없는값XYZ" in unknown


def test_get_unknown_labels_alias_is_known(mgr):
    # "통화 완료" is an alias of 통화완료
    unknown = mgr.get_unknown_labels(["통화 완료"])
    assert unknown == []


def test_get_unknown_labels_empty_string_excluded(mgr):
    unknown = mgr.get_unknown_labels(["", None])
    assert unknown == []


# ---------------------------------------------------------------------------
# save and reload
# ---------------------------------------------------------------------------

def test_save_and_reload(tmp_path):
    p = str(tmp_path / "fb.json")
    m = FeedbackManager(p)
    m.add_item("저장테스트")
    m.save()

    m2 = FeedbackManager(p)
    assert "저장테스트" in m2.get_active_labels()


def test_save_preserves_inactive(tmp_path):
    p = str(tmp_path / "fb.json")
    m = FeedbackManager(p)
    m.deactivate_item("CALL_DONE")
    m.save()

    m2 = FeedbackManager(p)
    assert "통화완료" not in m2.get_active_labels()
    assert any(i["label"] == "통화완료" for i in m2.get_all_items())


# ---------------------------------------------------------------------------
# update_label
# ---------------------------------------------------------------------------

def test_update_label(mgr):
    mgr.update_label("CALL_DONE", "전화완료")
    labels = mgr.get_active_labels()
    assert "전화완료" in labels
    assert "통화완료" not in labels
