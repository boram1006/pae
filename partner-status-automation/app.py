"""
협력사 현황 취합 자동화 — PySide6 로컬 데스크톱 앱

탭 구성:
  1. 취합 설정  – 파일 선택, 시트·컬럼 매핑, 날짜 필터, 실행
  2. 결과 확인  – 요약 카드, 결과 탭, Feedback 수정, 저장
  3. Feedback 관리 – 마스터 JSON 편집
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.excel_io import get_hidden_info, get_sheet_names, save_with_changes
from src.feedback_manager import FeedbackManager
from src.matcher import MatchResult, MatchedRow, build_changes, run_matching
from src.utils import (
    ColumnConfig,
    RefColumnConfig,
    generate_output_filename,
    is_valid_excel_column,
    safe_str,
    validate_column_config,
    validate_ref_column_config,
)
from src.validator import (
    ValidationResult,
    ValidationStatus,
    load_reference_data,
    validate_all,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_APP_DIR = Path(__file__).resolve().parent
_FEEDBACK_MASTER_PATH = _APP_DIR / "config" / "feedback_master.json"

# ---------------------------------------------------------------------------
# Validation statuses shown in "Feedback 확인 필요" tab
# ---------------------------------------------------------------------------
_FEEDBACK_CHECK_STATUSES = {
    ValidationStatus.CHECK_NEEDED,
    ValidationStatus.MISSING_SUSPECTED,
    ValidationStatus.DETAIL_INSUFFICIENT,
    ValidationStatus.NOT_VERIFIED,
}

# 전체 결과 탭 컬럼 정의 (인덱스를 상수로 관리해 sync 로직과 공유)
_ALL_TAB_HEADERS = ["키값", "구분", "최종행", "알바행", "날짜필터", "최종 Feedback", "수정됨"]
_ALL_IDX_KEY      = 0
_ALL_IDX_FEEDBACK = 5
_ALL_IDX_CHANGED  = 6

# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class WorkerThread(QThread):
    finished = Signal(object, object, object)  # match_result, val_results, debug_info
    error = Signal(str)

    def __init__(
        self,
        final_path, final_sheet,
        alba_path, alba_sheet,
        ref_path, ref_sheet,
        col_config: ColumnConfig,
        ref_col_config: RefColumnConfig,
        use_validation: bool,
        filter_date: Optional[date],
        keyword_rules: Optional[Dict] = None,
    ):
        super().__init__()
        self.final_path = final_path
        self.final_sheet = final_sheet
        self.alba_path = alba_path
        self.alba_sheet = alba_sheet
        self.ref_path = ref_path
        self.ref_sheet = ref_sheet
        self.col_config = col_config
        self.ref_col_config = ref_col_config
        self.use_validation = use_validation
        self.filter_date = filter_date
        self.keyword_rules = keyword_rules or {}

    def run(self):
        try:
            match_result = run_matching(
                self.final_path, self.final_sheet,
                self.alba_path, self.alba_sheet,
                self.col_config,
                filter_date=self.filter_date,
            )

            # Always run rule-based validation on matched rows.
            # Reference data enhances it with similarity matching.
            ref_data = None
            ref_count = 0
            if self.use_validation and self.ref_path:
                ref_data = load_reference_data(
                    self.ref_path, self.ref_sheet, self.ref_col_config
                )
                ref_count = len(ref_data)

            val_results = validate_all(
                match_result.matched, self.col_config, ref_data,
                keyword_rules=self.keyword_rules,
            )

            debug_info = {
                "has_ref": ref_data is not None,
                "ref_count": ref_count,
                "validation_ran": True,
                "filter_date": self.filter_date,
                "filter_active": self.filter_date is not None,
            }
            self.finished.emit(match_result, val_results, debug_info)
        except Exception:
            self.error.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _make_header(text: str) -> QLabel:
    lbl = QLabel(text)
    f = QFont(); f.setBold(True); f.setPointSize(10)
    lbl.setFont(f)
    return lbl


def _make_separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _table_item(text: str, bg: Optional[QColor] = None) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text) if text is not None else "")
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if bg:
        item.setBackground(bg)
    return item


def _status_color(status: ValidationStatus) -> QColor:
    return {
        ValidationStatus.NORMAL:               QColor("#d4edda"),
        ValidationStatus.CHECK_NEEDED:         QColor("#fff3cd"),
        ValidationStatus.MISSING_SUSPECTED:    QColor("#f8d7da"),
        ValidationStatus.DETAIL_INSUFFICIENT:  QColor("#fce8d4"),
        ValidationStatus.NOT_ENTERED:          QColor("#e2e3e5"),
        ValidationStatus.NOT_VERIFIED:         QColor("#ffffff"),
    }.get(status, QColor("#ffffff"))


def _make_table(cols: List[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fill_table(table: QTableWidget, headers: List[str], rows: List[List[Any]]):
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    for row_data in rows:
        r = table.rowCount()
        table.insertRow(r)
        for c, val in enumerate(row_data):
            table.setItem(r, c, _table_item(safe_str(val)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)


# ---------------------------------------------------------------------------
# Column mapping widget
# ---------------------------------------------------------------------------

_FIELD_LABELS = {
    "key":              "키값 컬럼",
    "encourage_yn":     "독려여부",
    "encourage_method": "독려방식",
    "encourage_date":   "독려일",
    "partner_feedback": "협력사 Feedback",
    "detail":           "상세내용(필요시)",
    "quote_reply_yn":   "견적회신여부",
    "reply_date":       "회신일",
}

_REF_FIELD_LABELS = {
    "key":              "정답지 키값 컬럼",
    "partner_feedback": "정답지 협력사 Feedback",
    "detail":           "정답지 상세내용",
}


class ColumnMappingWidget(QGroupBox):
    def __init__(self, title: str, fields: dict, defaults: dict, parent=None):
        super().__init__(title, parent)
        self._edits: Dict[str, QLineEdit] = {}
        form = QFormLayout(self)
        form.setContentsMargins(8, 8, 8, 8)
        for field_key, label in fields.items():
            edit = QLineEdit(defaults.get(field_key, ""))
            edit.setMaximumWidth(60)
            edit.setPlaceholderText("예: A")
            form.addRow(label + ":", edit)
            self._edits[field_key] = edit

    def get_values(self) -> Dict[str, str]:
        return {k: v.text().strip().upper() for k, v in self._edits.items()}

    def set_values(self, values: Dict[str, str]):
        for k, v in values.items():
            if k in self._edits:
                self._edits[k].setText(v.upper())


# ---------------------------------------------------------------------------
# Summary card
# ---------------------------------------------------------------------------

class SummaryCard(QWidget):
    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(2)
        self._value_lbl = QLabel(value)
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setBold(True); f.setPointSize(15)
        self._value_lbl.setFont(f)
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size:10px;")
        layout.addWidget(self._value_lbl)
        layout.addWidget(lbl)
        self.setStyleSheet(
            "background:#f0f4ff;border-radius:6px;border:1px solid #c0c8e0;"
        )

    def set_value(self, v):
        self._value_lbl.setText(str(v))


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("협력사 현황 취합 자동화")
        self.setMinimumSize(1200, 820)

        # State
        self._final_path: Optional[str] = None
        self._alba_path: Optional[str] = None
        self._ref_path: Optional[str] = None
        self._match_result: Optional[MatchResult] = None
        self._val_results: List[ValidationResult] = []
        self._val_debug: Dict = {}
        self._val_matched_rows: List[MatchedRow] = []   # mirrors rows in validation table
        self._all_tab_row_by_key: Dict[str, int] = {}   # key → row index in _tab_all (matched rows only)
        self._feedback_manager = FeedbackManager(str(_FEEDBACK_MASTER_PATH))
        self._discovered_feedback: set = set()
        self._worker: Optional[WorkerThread] = None

        self._build_ui()
        self.statusBar().showMessage(
            "파일을 선택하고 '취합 실행' 버튼을 눌러주세요."
        )

    # ======================================================================
    # Top-level UI
    # ======================================================================

    def _build_ui(self):
        self._outer_tabs = QTabWidget()
        self._outer_tabs.addTab(self._build_settings_tab(), "  취합 설정  ")
        self._outer_tabs.addTab(self._build_results_tab(), "  결과 확인  ")
        self._outer_tabs.addTab(self._build_feedback_mgmt_tab(), "  Feedback 관리  ")
        self.setCentralWidget(self._outer_tabs)

    # ======================================================================
    # Tab 1 – 취합 설정
    # ======================================================================

    def _build_settings_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        # Title
        title = QLabel("협력사 현황 취합 자동화")
        f = QFont(); f.setBold(True); f.setPointSize(18)
        title.setFont(f)
        title.setStyleSheet("color:#1a3c8f;")
        desc = QLabel(
            "최종 파일과 알바 취합 파일을 협력사 키값 기준으로 매칭하고, "
            "Feedback 입력 적정성을 검토합니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#555;")
        lay.addWidget(title)
        lay.addWidget(desc)
        lay.addWidget(_make_separator())

        # File selection
        lay.addWidget(_make_header("파일 선택"))
        lay.addWidget(self._build_file_section())
        lay.addWidget(_make_separator())

        # Sheet selection
        lay.addWidget(_make_header("시트 선택"))
        lay.addWidget(self._build_sheet_section())
        lay.addWidget(_make_separator())

        # Hidden columns/rows
        lay.addWidget(_make_header("숨김 컬럼 / 숨김 행 안내"))
        self._hidden_info_lbl = QLabel("파일과 시트를 선택하면 여기에 안내가 표시됩니다.")
        self._hidden_info_lbl.setWordWrap(True)
        self._hidden_info_lbl.setStyleSheet(
            "background:#fffbe6;border:1px solid #ffe58f;border-radius:4px;padding:6px;"
        )
        lay.addWidget(self._hidden_info_lbl)
        lay.addWidget(_make_separator())

        # Column mapping
        lay.addWidget(_make_header("컬럼 매핑 설정"))
        mapping_row = QHBoxLayout()
        self._col_mapping = ColumnMappingWidget(
            "최종 파일 / 알바 파일 컬럼", _FIELD_LABELS, ColumnConfig().to_dict()
        )
        mapping_row.addWidget(self._col_mapping)
        mapping_row.addStretch()
        lay.addLayout(mapping_row)

        # Ref column mapping (hidden until ref file selected)
        self._ref_mapping_group = QGroupBox("정답지 컬럼 설정")
        self._ref_col_mapping = ColumnMappingWidget(
            "", _REF_FIELD_LABELS, RefColumnConfig().to_dict()
        )
        ref_grp_lay = QVBoxLayout(self._ref_mapping_group)
        ref_grp_lay.addWidget(self._ref_col_mapping)
        self._ref_mapping_group.setVisible(False)
        lay.addWidget(self._ref_mapping_group)
        lay.addWidget(_make_separator())

        # Date filter
        lay.addWidget(_make_header("업데이트 기준 날짜"))
        lay.addWidget(self._build_date_filter_section())
        lay.addWidget(_make_separator())

        # Options
        lay.addWidget(_make_header("옵션 설정"))
        self._opt_validation = QCheckBox("정답지 검증 사용 (정답지 파일 선택 시 정답지 기반 유사도 활성화)")
        self._opt_validation.setChecked(True)
        lay.addWidget(self._opt_validation)
        lay.addWidget(_make_separator())

        # Execute button
        exec_row = QHBoxLayout()
        self._run_btn = QPushButton("취합 실행")
        self._run_btn.setFixedHeight(40)
        self._run_btn.setStyleSheet(
            "QPushButton{background:#1a3c8f;color:white;border-radius:5px;"
            "font-weight:bold;font-size:14px;padding:0 28px;}"
            "QPushButton:hover{background:#2752c9;}"
            "QPushButton:disabled{background:#aab;}"
        )
        self._run_btn.clicked.connect(self._on_run)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(12)
        exec_row.addWidget(self._run_btn)
        exec_row.addWidget(self._progress)
        exec_row.addStretch()
        lay.addLayout(exec_row)
        lay.addStretch()

        return scroll

    def _build_file_section(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        def _row(label, btn_text, lbl_attr, fn):
            h = QHBoxLayout()
            btn = QPushButton(btn_text)
            btn.setFixedWidth(220)
            btn.clicked.connect(fn)
            lbl = QLabel("선택된 파일 없음")
            lbl.setStyleSheet("color:#888;")
            lbl.setWordWrap(True)
            h.addWidget(QLabel(label))
            h.addWidget(btn)
            h.addWidget(lbl, stretch=1)
            setattr(self, lbl_attr, lbl)
            return h

        lay.addLayout(_row("필수  최종 완성 파일:", "최종 파일 선택", "_final_path_lbl", self._select_final))
        lay.addLayout(_row("필수  알바 취합 파일:", "알바 파일 선택", "_alba_path_lbl",  self._select_alba))
        lay.addLayout(_row("선택  5월 정답지 파일:", "정답지 파일 선택 (선택)", "_ref_path_lbl", self._select_ref))
        return w

    def _build_sheet_section(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        self._final_sheet_combo = QComboBox(); self._final_sheet_combo.setMinimumWidth(200)
        self._final_sheet_combo.currentTextChanged.connect(lambda: self._refresh_hidden_info("final"))
        self._alba_sheet_combo  = QComboBox(); self._alba_sheet_combo.setMinimumWidth(200)
        self._ref_sheet_combo   = QComboBox(); self._ref_sheet_combo.setMinimumWidth(200)
        self._ref_sheet_combo.currentTextChanged.connect(lambda: self._refresh_hidden_info("ref"))
        form.addRow("최종 파일 시트:", self._final_sheet_combo)
        form.addRow("알바 파일 시트:", self._alba_sheet_combo)
        self._ref_sheet_lbl = QLabel("정답지 파일 시트:")
        form.addRow(self._ref_sheet_lbl, self._ref_sheet_combo)
        self._ref_sheet_combo.setVisible(False)
        self._ref_sheet_lbl.setVisible(False)
        return w

    def _build_date_filter_section(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._date_filter_cb = QCheckBox("특정 독려일만 업데이트")
        self._date_filter_cb.setChecked(False)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("날짜:"))
        self._date_edit = QDateEdit(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setEnabled(False)
        date_row.addWidget(self._date_edit)
        date_row.addStretch()

        self._date_filter_cb.toggled.connect(self._date_edit.setEnabled)

        hint = QLabel(
            "체크하면 알바 파일의 독려일이 선택한 날짜와 일치하는 행만 최종 파일에 반영됩니다."
        )
        hint.setStyleSheet("color:#777;font-size:11px;")

        lay.addWidget(self._date_filter_cb)
        lay.addLayout(date_row)
        lay.addWidget(hint)
        return w

    # ======================================================================
    # Tab 2 – 결과 확인
    # ======================================================================

    def _build_results_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # Summary cards
        self._summary_strip = self._build_summary_strip()
        self._summary_strip.setVisible(False)
        lay.addWidget(self._summary_strip)

        # Date filter + validation debug info
        self._date_filter_info_lbl = QLabel("")
        self._date_filter_info_lbl.setVisible(False)
        self._date_filter_info_lbl.setStyleSheet(
            "background:#e8f4f8;border:1px solid #b8d9e8;border-radius:4px;padding:4px 8px;"
        )
        lay.addWidget(self._date_filter_info_lbl)

        self._val_debug_lbl = QLabel("정답지 검증이 실행되지 않았습니다.")
        self._val_debug_lbl.setWordWrap(True)
        self._val_debug_lbl.setStyleSheet(
            "background:#f5f5f5;border:1px solid #ddd;border-radius:4px;padding:4px 8px;"
        )
        self._val_debug_lbl.setVisible(False)
        lay.addWidget(self._val_debug_lbl)

        # Inner result tabs
        self._inner_tabs = self._build_inner_result_tabs()
        self._inner_tabs.setVisible(False)
        lay.addWidget(self._inner_tabs, stretch=1)

        # Save area
        lay.addWidget(_make_separator())
        save_row = QHBoxLayout()
        self._save_btn = QPushButton("완성본 엑셀 저장")
        self._save_btn.setEnabled(False)
        self._save_btn.setFixedHeight(36)
        self._save_btn.setStyleSheet(
            "QPushButton{background:#217a3c;color:white;border-radius:5px;"
            "font-weight:bold;font-size:13px;padding:0 20px;}"
            "QPushButton:hover{background:#2ea855;}"
            "QPushButton:disabled{background:#aab;}"
        )
        self._save_btn.clicked.connect(self._on_save)
        self._save_status_lbl = QLabel("")
        save_row.addWidget(self._save_btn)
        save_row.addWidget(self._save_status_lbl)
        save_row.addStretch()
        lay.addLayout(save_row)
        return w

    def _build_summary_strip(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#f7f9ff;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)
        self._cards: Dict[str, SummaryCard] = {}
        defs = [
            ("total_final",   "최종 파일\n전체 키"),
            ("total_alba",    "알바 파일\n키 수"),
            ("matched",       "매칭 성공"),
            ("unmatched",     "미매칭"),
            ("date_filtered", "날짜\n필터 제외"),
            ("alba_only",     "알바만\n존재"),
            ("duplicates",    "중복 키"),
            ("v_normal",      "검증 정상"),
            ("v_check",       "확인 필요"),
            ("v_missing",     "누락 의심"),
            ("v_short",       "상세내용\n부족"),
            ("v_none",        "미입력"),
            ("v_unverified",  "미검증"),
        ]
        for key, label in defs:
            card = SummaryCard(label)
            self._cards[key] = card
            lay.addWidget(card, stretch=1)
        return w

    def _build_inner_result_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        val_cols = [
            "키값", "원래 Feedback", "최종 Feedback", "상세내용",
            "추천 Feedback", "유사도", "검증 결과", "수정됨",
        ]
        self._tab_matched      = _make_table(["키값", "최종행", "알바행"] + list(_FIELD_LABELS.values())[1:])
        self._tab_unmatched    = _make_table(["키값", "최종행"])
        self._tab_duplicates   = _make_table(["키값", "중복 행 목록", "사용된 행"])
        self._tab_alba_only    = _make_table(["키값", "알바행"] + list(_FIELD_LABELS.values())[1:])
        self._tab_date_filtered = _make_table(["키값", "최종행", "알바행", "독려일(원본)"])
        self._tab_validation   = _make_table(val_cols)
        self._tab_all          = _make_table(_ALL_TAB_HEADERS)

        tabs.addTab(self._tab_matched,       "매칭 성공")
        tabs.addTab(self._tab_unmatched,     "미매칭")
        tabs.addTab(self._tab_duplicates,    "중복 키")
        tabs.addTab(self._tab_alba_only,     "알바만 존재")
        tabs.addTab(self._tab_date_filtered, "날짜 필터 제외")
        tabs.addTab(self._tab_validation,    "Feedback 확인 필요")
        tabs.addTab(self._tab_all,           "전체 결과")
        return tabs

    # ======================================================================
    # Tab 3 – Feedback 관리
    # ======================================================================

    def _build_feedback_mgmt_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        lay.addWidget(_make_header("Feedback 마스터 관리"))
        hint = QLabel(
            "협력사 Feedback 드롭다운에 표시할 값 목록을 관리합니다. "
            "삭제 대신 비활성화(active=false) 방식으로 과거 데이터를 보존합니다."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;font-size:11px;")
        lay.addWidget(hint)

        self._feedback_table = QTableWidget()
        self._feedback_table.setColumnCount(6)
        self._feedback_table.setHorizontalHeaderLabels(["ID", "라벨", "활성", "유사어", "순서", "키워드 (쉼표 구분)"])
        self._feedback_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._feedback_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self._feedback_table, stretch=1)

        ctrl = QHBoxLayout()
        add_btn    = QPushButton("신규 추가")
        toggle_btn = QPushButton("활성/비활성 전환")
        save_btn   = QPushButton("저장 (JSON)")
        add_btn.clicked.connect(self._on_add_feedback)
        toggle_btn.clicked.connect(self._on_toggle_feedback)
        save_btn.clicked.connect(self._on_save_feedback_master)
        save_btn.setStyleSheet(
            "QPushButton{background:#1a3c8f;color:white;border-radius:4px;padding:4px 14px;}"
            "QPushButton:hover{background:#2752c9;}"
        )
        ctrl.addWidget(add_btn)
        ctrl.addWidget(toggle_btn)
        ctrl.addStretch()
        ctrl.addWidget(save_btn)
        lay.addLayout(ctrl)

        lay.addWidget(_make_separator())
        lay.addWidget(_make_header("마스터에 없는 발견 값"))
        self._unknown_feedback_lbl = QLabel("취합을 실행하면 파일에서 발견된 Feedback 값과 마스터를 비교합니다.")
        self._unknown_feedback_lbl.setWordWrap(True)
        self._unknown_feedback_lbl.setStyleSheet(
            "background:#fff8e1;border:1px solid #ffe082;border-radius:4px;padding:6px;"
        )
        lay.addWidget(self._unknown_feedback_lbl)

        self._refresh_feedback_table()
        return w

    # ======================================================================
    # File selection
    # ======================================================================

    def _select_file(self, title: str) -> Optional[str]:
        path, _ = QFileDialog.getOpenFileName(
            self, title, "", "Excel 파일 (*.xlsx *.xlsm);;모든 파일 (*)"
        )
        return path if path else None

    def _select_final(self):
        path = self._select_file("최종 완성 파일 선택")
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm")):
            QMessageBox.warning(self, "파일 오류", ".xlsx / .xlsm 파일만 선택 가능합니다.")
            return
        self._final_path = path
        self._final_path_lbl.setText(Path(path).name)
        self._final_path_lbl.setStyleSheet("color:#1a3c8f;font-weight:bold;")
        self._load_sheets(path, self._final_sheet_combo)
        self._refresh_hidden_info("final")

    def _select_alba(self):
        path = self._select_file("알바 취합 파일 선택")
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm")):
            QMessageBox.warning(self, "파일 오류", ".xlsx / .xlsm 파일만 선택 가능합니다.")
            return
        self._alba_path = path
        self._alba_path_lbl.setText(Path(path).name)
        self._alba_path_lbl.setStyleSheet("color:#1a3c8f;font-weight:bold;")
        self._load_sheets(path, self._alba_sheet_combo)

    def _select_ref(self):
        path = self._select_file("5월 정답지 파일 선택")
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm")):
            QMessageBox.warning(self, "파일 오류", ".xlsx / .xlsm 파일만 선택 가능합니다.")
            return
        self._ref_path = path
        self._ref_path_lbl.setText(Path(path).name)
        self._ref_path_lbl.setStyleSheet("color:#1a3c8f;font-weight:bold;")
        self._load_sheets(path, self._ref_sheet_combo)
        self._ref_mapping_group.setVisible(True)
        self._ref_sheet_combo.setVisible(True)
        self._ref_sheet_lbl.setVisible(True)
        self._refresh_hidden_info("ref")

    def _load_sheets(self, path: str, combo: QComboBox):
        try:
            sheets = get_sheet_names(path)
            combo.clear()
            combo.addItems(sheets)
        except Exception as e:
            QMessageBox.warning(self, "시트 읽기 오류", f"시트 목록을 읽을 수 없습니다:\n{e}")

    # ======================================================================
    # Hidden column/row info
    # ======================================================================

    def _refresh_hidden_info(self, which: str):
        messages: List[str] = []

        def _describe(label: str, path: Optional[str], combo: QComboBox):
            if not path or not combo.currentText():
                return
            try:
                hcols, hrows = get_hidden_info(path, combo.currentText())
                if hcols:
                    messages.append(f"[{label}] 숨김 컬럼: {', '.join(hcols)}")
                if hrows:
                    disp = hrows[:20]
                    sfx  = f" … 외 {len(hrows)-20}행" if len(hrows) > 20 else ""
                    messages.append(f"[{label}] 숨김 행: {', '.join(map(str, disp))}{sfx}")
                if not hcols and not hrows:
                    messages.append(f"[{label}] 숨김 컬럼/행 없음")
            except Exception as e:
                messages.append(f"[{label}] 숨김 정보 읽기 오류: {e}")

        if which in ("final", "all"):
            _describe("최종 파일", self._final_path, self._final_sheet_combo)
        if which in ("ref", "all") and self._ref_path:
            _describe("정답지 파일", self._ref_path, self._ref_sheet_combo)

        self._hidden_info_lbl.setText(
            "\n".join(messages) if messages else "파일과 시트를 선택하면 여기에 안내가 표시됩니다."
        )

    # ======================================================================
    # Config helpers
    # ======================================================================

    def _get_col_config(self) -> Optional[ColumnConfig]:
        vals = self._col_mapping.get_values()
        try:
            cfg = ColumnConfig(**vals)
        except TypeError as e:
            QMessageBox.warning(self, "설정 오류", f"컬럼 매핑 설정 오류:\n{e}")
            return None
        errors = validate_column_config(cfg)
        if errors:
            QMessageBox.warning(self, "컬럼 설정 오류", "\n".join(errors))
            return None
        return cfg

    def _get_ref_col_config(self) -> Optional[RefColumnConfig]:
        vals = self._ref_col_mapping.get_values()
        try:
            cfg = RefColumnConfig(**vals)
        except TypeError as e:
            QMessageBox.warning(self, "설정 오류", f"정답지 컬럼 설정 오류:\n{e}")
            return None
        errors = validate_ref_column_config(cfg)
        if errors:
            QMessageBox.warning(self, "정답지 컬럼 오류", "\n".join(errors))
            return None
        return cfg

    def _get_filter_date(self) -> Optional[date]:
        if not self._date_filter_cb.isChecked():
            return None
        qd = self._date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    # ======================================================================
    # Run matching
    # ======================================================================

    def _on_run(self):
        if not self._final_path:
            QMessageBox.warning(self, "파일 미선택", "최종 완성 파일을 선택해주세요.")
            return
        if not self._alba_path:
            QMessageBox.warning(self, "파일 미선택", "알바 취합 파일을 선택해주세요.")
            return
        if not self._final_sheet_combo.currentText():
            QMessageBox.warning(self, "시트 미선택", "최종 파일의 시트를 선택해주세요.")
            return
        if not self._alba_sheet_combo.currentText():
            QMessageBox.warning(self, "시트 미선택", "알바 파일의 시트를 선택해주세요.")
            return

        col_config = self._get_col_config()
        if col_config is None:
            return
        ref_col_config = self._get_ref_col_config()
        if ref_col_config is None:
            return

        use_validation = self._opt_validation.isChecked()
        filter_date    = self._get_filter_date()

        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self.statusBar().showMessage("취합 실행 중 …")

        ref_sheet = self._ref_sheet_combo.currentText() if self._ref_path else ""
        self._worker = WorkerThread(
            final_path=self._final_path,
            final_sheet=self._final_sheet_combo.currentText(),
            alba_path=self._alba_path,
            alba_sheet=self._alba_sheet_combo.currentText(),
            ref_path=self._ref_path or "",
            ref_sheet=ref_sheet,
            col_config=col_config,
            ref_col_config=ref_col_config,
            use_validation=use_validation,
            filter_date=filter_date,
            keyword_rules=self._feedback_manager.get_keyword_rules(),
        )
        self._worker.finished.connect(self._on_run_finished)
        self._worker.error.connect(self._on_run_error)
        self._worker.start()

    def _on_run_finished(
        self,
        match_result: MatchResult,
        val_results: List[ValidationResult],
        debug_info: Dict,
    ):
        self._match_result  = match_result
        self._val_results   = val_results
        self._val_debug     = debug_info

        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._save_btn.setEnabled(True)

        # Collect discovered feedback values
        self._discovered_feedback = set()
        for row in match_result.matched + match_result.date_filtered:
            if row.original_feedback:
                self._discovered_feedback.add(row.original_feedback)

        self._populate_summary(match_result, val_results, debug_info)
        self._populate_tabs(match_result, val_results)
        self._update_val_debug_label(val_results, debug_info)
        self._update_unknown_feedback_label()

        self._summary_strip.setVisible(True)
        self._inner_tabs.setVisible(True)
        self._val_debug_lbl.setVisible(True)

        if debug_info.get("filter_active"):
            self._date_filter_info_lbl.setVisible(True)
        else:
            self._date_filter_info_lbl.setVisible(False)

        # Switch to results tab
        self._outer_tabs.setCurrentIndex(1)
        self.statusBar().showMessage(
            f"완료: 매칭 성공 {len(match_result.matched)}건 / "
            f"미매칭 {len(match_result.unmatched)}건 / "
            f"날짜필터 제외 {len(match_result.date_filtered)}건"
        )

    def _on_run_error(self, tb: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(
            self, "실행 오류",
            f"취합 실행 중 오류가 발생했습니다:\n\n{tb[-1800:]}"
        )
        self.statusBar().showMessage("오류 발생")

    # ======================================================================
    # Populate results
    # ======================================================================

    def _populate_summary(self, mr: MatchResult, vr: List[ValidationResult], debug: Dict):
        from collections import Counter
        vc = Counter(v.status for v in vr)

        self._cards["total_final"].set_value(mr.total_final_keys)
        self._cards["total_alba"].set_value(mr.total_alba_keys)
        self._cards["matched"].set_value(len(mr.matched))
        self._cards["unmatched"].set_value(len(mr.unmatched))
        self._cards["date_filtered"].set_value(len(mr.date_filtered))
        self._cards["alba_only"].set_value(len(mr.alba_only))
        self._cards["duplicates"].set_value(len(mr.duplicates))
        self._cards["v_normal"].set_value(vc.get(ValidationStatus.NORMAL, 0))
        self._cards["v_check"].set_value(vc.get(ValidationStatus.CHECK_NEEDED, 0))
        self._cards["v_missing"].set_value(vc.get(ValidationStatus.MISSING_SUSPECTED, 0))
        self._cards["v_short"].set_value(vc.get(ValidationStatus.DETAIL_INSUFFICIENT, 0))
        self._cards["v_none"].set_value(vc.get(ValidationStatus.NOT_ENTERED, 0))
        self._cards["v_unverified"].set_value(vc.get(ValidationStatus.NOT_VERIFIED, 0))

        if debug.get("filter_active") and debug.get("filter_date"):
            fd = debug["filter_date"]
            self._date_filter_info_lbl.setText(
                f"날짜 필터 기준: {fd}  |  통과: {len(mr.matched)}건  |  제외: {len(mr.date_filtered)}건"
            )

    def _update_val_debug_label(self, vr: List[ValidationResult], debug: Dict):
        from collections import Counter
        vc = Counter(v.status for v in vr)
        if not debug.get("has_ref"):
            ref_msg = "정답지 없음 (규칙 기반만 적용)"
        else:
            ref_msg = f"정답지 기준 데이터: {debug.get('ref_count', 0)}건"
        lines = [
            f"검증 실행: {'예' if debug.get('validation_ran') else '아니오'}  |  {ref_msg}",
            f"검증 대상: {len(vr)}건  |  "
            f"정상: {vc.get(ValidationStatus.NORMAL,0)}  |  "
            f"확인필요: {vc.get(ValidationStatus.CHECK_NEEDED,0)}  |  "
            f"누락의심: {vc.get(ValidationStatus.MISSING_SUSPECTED,0)}  |  "
            f"상세부족: {vc.get(ValidationStatus.DETAIL_INSUFFICIENT,0)}  |  "
            f"미입력: {vc.get(ValidationStatus.NOT_ENTERED,0)}  |  "
            f"미검증: {vc.get(ValidationStatus.NOT_VERIFIED,0)}",
        ]
        self._val_debug_lbl.setText("\n".join(lines))

    def _populate_tabs(self, mr: MatchResult, vr: List[ValidationResult]):
        cfg = self._get_col_config()
        val_cols   = list(cfg.value_columns().values()) if cfg else []
        val_labels = list(_FIELD_LABELS.values())[1:]   # skip "key"
        val_by_key = {v.key: v for v in vr}

        # --- Tab: 매칭 성공 ---
        self._tab_matched.setRowCount(0)
        self._tab_matched.setColumnCount(3 + len(val_labels))
        self._tab_matched.setHorizontalHeaderLabels(["키값", "최종행", "알바행"] + val_labels)
        for row in mr.matched:
            r = self._tab_matched.rowCount()
            self._tab_matched.insertRow(r)
            self._tab_matched.setItem(r, 0, _table_item(row.key))
            self._tab_matched.setItem(r, 1, _table_item(str(row.final_row)))
            self._tab_matched.setItem(r, 2, _table_item(str(row.alba_row)))
            for i, col_l in enumerate(val_cols):
                self._tab_matched.setItem(r, 3+i, _table_item(safe_str(row.values.get(col_l, ""))))
        self._tab_matched.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tab_matched.horizontalHeader().setStretchLastSection(True)

        # --- Tab: 미매칭 ---
        _fill_table(self._tab_unmatched, ["키값", "최종행"],
                    [[r.key, r.final_row] for r in mr.unmatched])

        # --- Tab: 중복 키 ---
        _fill_table(self._tab_duplicates, ["키값", "중복 행 목록", "사용된 행"],
                    [[d.key, ", ".join(map(str, d.rows)), d.used_row] for d in mr.duplicates])

        # --- Tab: 알바만 존재 ---
        self._tab_alba_only.setRowCount(0)
        self._tab_alba_only.setColumnCount(2 + len(val_labels))
        self._tab_alba_only.setHorizontalHeaderLabels(["키값", "알바행"] + val_labels)
        for row in mr.alba_only:
            r = self._tab_alba_only.rowCount()
            self._tab_alba_only.insertRow(r)
            self._tab_alba_only.setItem(r, 0, _table_item(row.key))
            self._tab_alba_only.setItem(r, 1, _table_item(str(row.alba_row)))
            for i, col_l in enumerate(val_cols):
                self._tab_alba_only.setItem(r, 2+i, _table_item(safe_str(row.values.get(col_l, ""))))
        self._tab_alba_only.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tab_alba_only.horizontalHeader().setStretchLastSection(True)

        # --- Tab: 날짜 필터 제외 ---
        date_col = cfg.encourage_date if cfg else ""
        self._tab_date_filtered.setRowCount(0)
        for row in mr.date_filtered:
            r = self._tab_date_filtered.rowCount()
            self._tab_date_filtered.insertRow(r)
            date_val = safe_str(row.values.get(date_col, "")) if date_col else ""
            self._tab_date_filtered.setItem(r, 0, _table_item(row.key))
            self._tab_date_filtered.setItem(r, 1, _table_item(str(row.final_row)))
            self._tab_date_filtered.setItem(r, 2, _table_item(str(row.alba_row)))
            self._tab_date_filtered.setItem(r, 3, _table_item(date_val))
        self._tab_date_filtered.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        # --- Tab: Feedback 확인 필요 (editable) ---
        self._populate_validation_tab(mr, vr)

        # --- Tab: 전체 결과 ---
        all_rows = []
        self._all_tab_row_by_key = {}
        for row in mr.matched:
            v = val_by_key.get(row.key)
            v_status = v.status.value if v else "—"
            changed  = "수정됨" if row.feedback_changed else ""
            self._all_tab_row_by_key[row.key] = len(all_rows)
            all_rows.append([
                row.key, f"매칭 성공 ({v_status})",
                row.final_row, row.alba_row, "통과",
                row.final_feedback, changed,
            ])
        for row in mr.date_filtered:
            all_rows.append([row.key, "날짜 필터 제외", row.final_row, row.alba_row, "제외", row.original_feedback, ""])
        for row in mr.unmatched:
            all_rows.append([row.key, "미매칭", row.final_row, "—", "—", "", ""])
        for row in mr.alba_only:
            all_rows.append([row.key, "알바만 존재", "—", row.alba_row, "—", "", ""])
        _fill_table(self._tab_all, _ALL_TAB_HEADERS, all_rows)

        # Update tab titles with counts
        self._inner_tabs.setTabText(0, f"매칭 성공 ({len(mr.matched)})")
        self._inner_tabs.setTabText(1, f"미매칭 ({len(mr.unmatched)})")
        self._inner_tabs.setTabText(2, f"중복 키 ({len(mr.duplicates)})")
        self._inner_tabs.setTabText(3, f"알바만 존재 ({len(mr.alba_only)})")
        self._inner_tabs.setTabText(4, f"날짜 필터 제외 ({len(mr.date_filtered)})")
        check_cnt = sum(1 for v in vr if v.status in _FEEDBACK_CHECK_STATUSES)
        self._inner_tabs.setTabText(5, f"Feedback 확인 필요 ({check_cnt})")
        self._inner_tabs.setTabText(6, f"전체 결과 ({len(all_rows)})")

    def _populate_validation_tab(self, mr: MatchResult, vr: List[ValidationResult]):
        self._val_matched_rows = []
        self._tab_validation.setRowCount(0)
        matched_by_key = {m.key: m for m in mr.matched}

        for v in vr:
            if v.status not in _FEEDBACK_CHECK_STATUSES:
                continue
            matched_row = matched_by_key.get(v.key)
            if matched_row is None:
                continue

            self._val_matched_rows.append(matched_row)
            r = self._tab_validation.rowCount()
            self._tab_validation.insertRow(r)
            bg = _status_color(v.status)

            # col 0: 키값
            self._tab_validation.setItem(r, 0, _table_item(v.key, bg))
            # col 1: 원래 Feedback (read-only)
            self._tab_validation.setItem(r, 1, _table_item(matched_row.original_feedback))
            # col 2: 최종 Feedback (editable combobox)
            combo = QComboBox()
            options = self._get_feedback_options(matched_row)
            combo.addItems(options)
            idx = combo.findText(matched_row.final_feedback)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif matched_row.final_feedback:
                combo.addItem(matched_row.final_feedback)
                combo.setCurrentText(matched_row.final_feedback)
            mr_ref = matched_row
            combo.currentTextChanged.connect(
                lambda text, _mr=mr_ref, _r=r: self._on_feedback_changed(_mr, text, _r)
            )
            self._tab_validation.setCellWidget(r, 2, combo)
            # col 3: 상세내용
            self._tab_validation.setItem(r, 3, _table_item(v.current_detail))
            # col 4: 추천 Feedback
            self._tab_validation.setItem(r, 4, _table_item(v.recommended_feedback))
            # col 5: 유사도
            sim = f"{v.similarity_score:.0f}" if v.similarity_score else ""
            self._tab_validation.setItem(r, 5, _table_item(sim))
            # col 6: 검증 결과
            self._tab_validation.setItem(r, 6, _table_item(v.status.value, bg))
            # col 7: 수정됨
            self._tab_validation.setItem(r, 7, _table_item(""))

        self._tab_validation.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._tab_validation.horizontalHeader().setStretchLastSection(True)

    def _get_feedback_options(self, matched_row: MatchedRow) -> List[str]:
        active = self._feedback_manager.get_active_labels()
        options: List[str] = [""] + list(active)
        orig = matched_row.original_feedback
        if orig and orig not in options:
            options.append(orig)
        return options

    def _sync_all_tab_row(self, key: str, final_feedback: str, feedback_changed: bool) -> None:
        """전체 결과 탭에서 해당 key 행의 최종 Feedback·수정됨 컬럼을 즉시 갱신한다."""
        row_idx = self._all_tab_row_by_key.get(key)
        if row_idx is None:
            return
        fb_item = self._tab_all.item(row_idx, _ALL_IDX_FEEDBACK)
        ch_item = self._tab_all.item(row_idx, _ALL_IDX_CHANGED)
        if fb_item:
            fb_item.setText(final_feedback)
        if ch_item:
            ch_item.setText("수정됨" if feedback_changed else "")
        bg = QColor("#fff3cd") if feedback_changed else QColor("#ffffff")
        for c in range(self._tab_all.columnCount()):
            cell = self._tab_all.item(row_idx, c)
            if cell:
                cell.setBackground(bg)

    def _on_feedback_changed(self, matched_row: MatchedRow, new_value: str, table_row: int):
        matched_row.final_feedback   = new_value
        matched_row.feedback_changed = (new_value != matched_row.original_feedback)

        # ── Feedback 확인 필요 탭 갱신 ──────────────────────────────
        changed_text = "수정됨" if matched_row.feedback_changed else ""
        changed_item = self._tab_validation.item(table_row, 7)
        if changed_item:
            changed_item.setText(changed_text)
        bg_val = QColor("#fff3cd") if matched_row.feedback_changed else QColor("#ffffff")
        for c in range(self._tab_validation.columnCount()):
            cell = self._tab_validation.item(table_row, c)
            if cell:
                cell.setBackground(bg_val)

        # ── 전체 결과 탭 즉시 동기화 ────────────────────────────────
        self._sync_all_tab_row(matched_row.key, new_value, matched_row.feedback_changed)

    # ======================================================================
    # Feedback management tab actions
    # ======================================================================

    def _refresh_feedback_table(self):
        items = self._feedback_manager.get_all_items()
        self._feedback_table.setRowCount(0)
        for item in items:
            r = self._feedback_table.rowCount()
            self._feedback_table.insertRow(r)
            self._feedback_table.setItem(r, 0, _table_item(item.get("id", "")))
            lbl_item = QTableWidgetItem(item.get("label", ""))
            self._feedback_table.setItem(r, 1, lbl_item)
            active     = item.get("active", True)
            act_item   = _table_item("✓" if active else "✗")
            if not active:
                act_item.setForeground(QColor("#aaa"))
            self._feedback_table.setItem(r, 2, act_item)
            self._feedback_table.setItem(r, 3, _table_item(", ".join(item.get("aliases", []))))
            self._feedback_table.setItem(r, 4, _table_item(str(item.get("sort_order", 999))))
            kw_item = QTableWidgetItem(", ".join(item.get("expected_keywords", [])))
            self._feedback_table.setItem(r, 5, kw_item)
        self._feedback_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._feedback_table.horizontalHeader().setStretchLastSection(True)

    def _on_add_feedback(self):
        label, ok = QInputDialog.getText(self, "신규 Feedback 추가", "라벨명:")
        if ok and label.strip():
            self._feedback_manager.add_item(label.strip())
            self._refresh_feedback_table()

    def _on_toggle_feedback(self):
        row = self._feedback_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 필요", "전환할 항목을 선택해주세요.")
            return
        items = self._feedback_manager.get_all_items()
        if row < len(items):
            self._feedback_manager.toggle_active(items[row]["id"])
            self._refresh_feedback_table()

    def _on_save_feedback_master(self):
        # Apply label and keyword edits from table before saving
        items = self._feedback_manager.get_all_items()
        for r, item in enumerate(items):
            lbl_cell = self._feedback_table.item(r, 1)
            if lbl_cell:
                item["label"] = lbl_cell.text().strip()
            kw_cell = self._feedback_table.item(r, 5)
            if kw_cell:
                kws = [k.strip() for k in kw_cell.text().split(",") if k.strip()]
                item["expected_keywords"] = kws
        try:
            self._feedback_manager.save()
            QMessageBox.information(
                self, "저장 완료",
                f"Feedback 마스터가 저장되었습니다.\n{self._feedback_manager.config_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"저장 실패:\n{e}")

    def _update_unknown_feedback_label(self):
        unknown = self._feedback_manager.get_unknown_labels(
            list(self._discovered_feedback)
        )
        if unknown:
            self._unknown_feedback_lbl.setText(
                "마스터에 없는 발견 값:\n"
                + ", ".join(sorted(unknown))
                + "\n\n필요하면 '신규 추가' 버튼으로 마스터에 등록하세요."
            )
        elif self._discovered_feedback:
            self._unknown_feedback_lbl.setText(
                "발견된 모든 Feedback 값이 마스터에 포함되어 있습니다."
            )
        else:
            self._unknown_feedback_lbl.setText(
                "취합을 실행하면 파일에서 발견된 Feedback 값과 마스터를 비교합니다."
            )

    # ======================================================================
    # Save
    # ======================================================================

    def _on_save(self):
        if not self._match_result:
            QMessageBox.warning(self, "저장 불가", "먼저 취합을 실행해주세요.")
            return
        col_config = self._get_col_config()
        if col_config is None:
            return

        default_path = generate_output_filename(self._final_path)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "완성본 엑셀 저장", default_path,
            "Excel 파일 (*.xlsx);;모든 파일 (*)"
        )
        if not save_path:
            return

        try:
            changes = build_changes(self._match_result, col_config)
            save_with_changes(
                source_path=self._final_path,
                output_path=save_path,
                sheet_name=self._final_sheet_combo.currentText(),
                changes=changes,
            )
            self._save_status_lbl.setText(f"저장 완료: {Path(save_path).name}")
            self._save_status_lbl.setStyleSheet("color:#217a3c;font-weight:bold;")
            self.statusBar().showMessage(f"저장 완료 → {save_path}")
            changed_cnt = sum(1 for m in self._match_result.matched if m.feedback_changed)
            QMessageBox.information(
                self, "저장 완료",
                f"완성본이 저장되었습니다:\n{save_path}\n\n"
                f"반영된 행: {len(self._match_result.matched)}건\n"
                f"Feedback 수정 반영: {changed_cnt}건",
            )
        except PermissionError:
            QMessageBox.critical(
                self, "저장 오류",
                "파일을 저장할 수 없습니다.\n"
                "저장하려는 파일이 Excel에서 열려 있다면 닫고 다시 시도해주세요.",
            )
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"저장 중 오류가 발생했습니다:\n{e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
