"""
UI-level sync tests: Feedback 확인 필요 탭 드롭다운 변경 시
전체 결과 탭과 데이터 모델이 즉시 동기화되는지 검증한다.

Qt 위젯이 필요하므로 offscreen 플랫폼으로 실행한다.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from src.matcher import MatchedRow

# 공유 QApplication (테스트 전체에서 1개만 생성)
_qapp: QApplication | None = None


def _get_qapp() -> QApplication:
    global _qapp
    if _qapp is None:
        _qapp = QApplication.instance() or QApplication([])
    return _qapp


@pytest.fixture
def win():
    _get_qapp()
    from app import MainWindow
    w = MainWindow()
    yield w
    w.close()


def _setup_all_tab(win, headers, n_rows: int = 1):
    """_tab_all 을 n_rows 행으로 초기화하는 헬퍼."""
    win._tab_all.setRowCount(n_rows)
    win._tab_all.setColumnCount(len(headers))
    for r in range(n_rows):
        for c in range(len(headers)):
            win._tab_all.setItem(r, c, QTableWidgetItem(""))


# ---------------------------------------------------------------------------
# _sync_all_tab_row
# ---------------------------------------------------------------------------

def test_sync_updates_feedback_column(win):
    from app import _ALL_TAB_HEADERS, _ALL_IDX_FEEDBACK

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}

    win._sync_all_tab_row("K1", "통화완료", False)

    assert win._tab_all.item(0, _ALL_IDX_FEEDBACK).text() == "통화완료"


def test_sync_sets_changed_text(win):
    from app import _ALL_TAB_HEADERS, _ALL_IDX_CHANGED

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}

    win._sync_all_tab_row("K1", "새값", True)

    assert win._tab_all.item(0, _ALL_IDX_CHANGED).text() == "수정됨"


def test_sync_clears_changed_text_when_reverted(win):
    from app import _ALL_TAB_HEADERS, _ALL_IDX_FEEDBACK, _ALL_IDX_CHANGED

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}

    win._sync_all_tab_row("K1", "수정값", True)
    win._sync_all_tab_row("K1", "원래값", False)

    assert win._tab_all.item(0, _ALL_IDX_FEEDBACK).text() == "원래값"
    assert win._tab_all.item(0, _ALL_IDX_CHANGED).text() == ""


def test_sync_unknown_key_does_not_raise(win):
    win._all_tab_row_by_key = {}
    win._sync_all_tab_row("NONEXISTENT", "val", True)   # must not raise


def test_sync_multiple_keys_only_updates_target(win):
    from app import _ALL_TAB_HEADERS, _ALL_IDX_FEEDBACK, _ALL_IDX_CHANGED

    _setup_all_tab(win, _ALL_TAB_HEADERS, n_rows=2)
    win._all_tab_row_by_key = {"K1": 0, "K2": 1}
    win._tab_all.item(0, _ALL_IDX_FEEDBACK).setText("K1_orig")
    win._tab_all.item(1, _ALL_IDX_FEEDBACK).setText("K2_orig")

    win._sync_all_tab_row("K1", "K1_new", True)

    # K1 updated
    assert win._tab_all.item(0, _ALL_IDX_FEEDBACK).text() == "K1_new"
    assert win._tab_all.item(0, _ALL_IDX_CHANGED).text() == "수정됨"
    # K2 untouched
    assert win._tab_all.item(1, _ALL_IDX_FEEDBACK).text() == "K2_orig"
    assert win._tab_all.item(1, _ALL_IDX_CHANGED).text() == ""


# ---------------------------------------------------------------------------
# _on_feedback_changed – end-to-end (validation tab + all tab + data model)
# ---------------------------------------------------------------------------

def _make_validation_row(win, row_idx: int = 0):
    """_tab_validation 에 더미 행 하나를 추가하는 헬퍼."""
    win._tab_validation.setRowCount(row_idx + 1)
    win._tab_validation.setColumnCount(5)
    for c in range(5):
        win._tab_validation.setItem(row_idx, c, QTableWidgetItem(""))


def test_on_feedback_changed_updates_data_model(win):
    from app import _ALL_TAB_HEADERS

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}
    _make_validation_row(win, 0)

    mr = MatchedRow("K1", 1, 1, {}, original_feedback="원래값", final_feedback="원래값")
    win._on_feedback_changed(mr, "새값", 0)

    assert mr.final_feedback == "새값"
    assert mr.feedback_changed is True


def test_on_feedback_changed_syncs_all_tab(win):
    from app import _ALL_TAB_HEADERS, _ALL_IDX_FEEDBACK, _ALL_IDX_CHANGED

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}
    _make_validation_row(win, 0)

    mr = MatchedRow("K1", 1, 1, {}, original_feedback="원래값", final_feedback="원래값")
    win._on_feedback_changed(mr, "통화완료", 0)

    assert win._tab_all.item(0, _ALL_IDX_FEEDBACK).text() == "통화완료"
    assert win._tab_all.item(0, _ALL_IDX_CHANGED).text() == "수정됨"


def test_on_feedback_changed_colors_col1_red_when_changed(win):
    from app import _ALL_TAB_HEADERS

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}
    _make_validation_row(win, 0)

    mr = MatchedRow("K1", 1, 1, {}, original_feedback="원래값", final_feedback="원래값")
    win._on_feedback_changed(mr, "부재", 0)

    # col 1 (원래 Feedback) should be red when changed
    from PySide6.QtGui import QColor
    assert win._tab_validation.item(0, 1).background().color() == QColor("#ffb3b3")


def test_on_feedback_changed_reverts_correctly(win):
    from app import _ALL_TAB_HEADERS, _ALL_IDX_CHANGED

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}
    _make_validation_row(win, 0)

    mr = MatchedRow("K1", 1, 1, {}, original_feedback="원래값", final_feedback="원래값")

    # 변경 후 원래값으로 복원
    win._on_feedback_changed(mr, "임시값", 0)
    assert mr.feedback_changed is True

    win._on_feedback_changed(mr, "원래값", 0)
    assert mr.feedback_changed is False
    assert win._tab_all.item(0, _ALL_IDX_CHANGED).text() == ""


def test_on_feedback_changed_original_feedback_preserved(win):
    from app import _ALL_TAB_HEADERS

    _setup_all_tab(win, _ALL_TAB_HEADERS)
    win._all_tab_row_by_key = {"K1": 0}
    _make_validation_row(win, 0)

    mr = MatchedRow("K1", 1, 1, {}, original_feedback="원래값", final_feedback="원래값")
    win._on_feedback_changed(mr, "수정값", 0)

    # original_feedback 은 절대 변경되지 않아야 한다
    assert mr.original_feedback == "원래값"
