"""
협력사 현황 취합 자동화 — PySide6 로컬 데스크톱 앱

로컬 파일 선택 → 시트 선택 → 컬럼 매핑 → 매칭 실행 → 결과 검토 → 저장
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.excel_io import get_hidden_info, get_sheet_names, save_with_changes
from src.matcher import MatchResult, build_changes, run_matching
from src.utils import (
    ColumnConfig,
    RefColumnConfig,
    generate_output_filename,
    is_valid_excel_column,
    safe_str,
    validate_column_config,
    validate_ref_column_config,
)
from src.validator import ValidationResult, ValidationStatus, load_reference_data, validate_all


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

class WorkerThread(QThread):
    finished = Signal(object, object)  # (MatchResult, List[ValidationResult])
    error = Signal(str)

    def __init__(
        self,
        final_path, final_sheet,
        alba_path, alba_sheet,
        ref_path, ref_sheet,
        col_config: ColumnConfig,
        ref_col_config: RefColumnConfig,
        use_validation: bool,
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

    def run(self):
        try:
            match_result = run_matching(
                self.final_path, self.final_sheet,
                self.alba_path, self.alba_sheet,
                self.col_config,
            )

            val_results: List[ValidationResult] = []
            if self.use_validation and self.ref_path:
                ref_data = load_reference_data(
                    self.ref_path, self.ref_sheet, self.ref_col_config
                )
                val_results = validate_all(
                    match_result.matched, self.col_config, ref_data
                )
            elif self.use_validation:
                val_results = validate_all(
                    match_result.matched, self.col_config, None
                )

            self.finished.emit(match_result, val_results)
        except Exception as e:
            self.error.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_header(text: str) -> QLabel:
    lbl = QLabel(text)
    font = QFont()
    font.setBold(True)
    font.setPointSize(10)
    lbl.setFont(font)
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
    colors = {
        ValidationStatus.NORMAL: QColor("#d4edda"),
        ValidationStatus.CHECK_NEEDED: QColor("#fff3cd"),
        ValidationStatus.MISSING_SUSPECTED: QColor("#f8d7da"),
        ValidationStatus.DETAIL_INSUFFICIENT: QColor("#fce8d4"),
        ValidationStatus.NOT_ENTERED: QColor("#e2e3e5"),
        ValidationStatus.NOT_VERIFIED: QColor("#ffffff"),
    }
    return colors.get(status, QColor("#ffffff"))


# ---------------------------------------------------------------------------
# Column mapping widget
# ---------------------------------------------------------------------------

_FIELD_LABELS = {
    "key": "키값 컬럼",
    "encourage_yn": "독려여부",
    "encourage_method": "독려방식",
    "encourage_date": "독려일",
    "partner_feedback": "협력사 Feedback",
    "detail": "상세내용(필요시)",
    "quote_reply_yn": "견적회신여부",
    "reply_date": "회신일",
}

_REF_FIELD_LABELS = {
    "key": "정답지 키값 컬럼",
    "partner_feedback": "정답지 협력사 Feedback",
    "detail": "정답지 상세내용",
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
# Summary card strip
# ---------------------------------------------------------------------------

class SummaryCard(QWidget):
    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self._value_lbl = QLabel(value)
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setBold(True)
        font.setPointSize(16)
        self._value_lbl.setFont(font)
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(self._value_lbl)
        layout.addWidget(lbl)
        self.setStyleSheet(
            "background:#f0f4ff;border-radius:6px;border:1px solid #c0c8e0;"
        )

    def set_value(self, v):
        self._value_lbl.setText(str(v))


# ---------------------------------------------------------------------------
# Result table helper
# ---------------------------------------------------------------------------

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
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("협력사 현황 취합 자동화")
        self.setMinimumSize(1100, 800)

        self._final_path: Optional[str] = None
        self._alba_path: Optional[str] = None
        self._ref_path: Optional[str] = None
        self._match_result: Optional[MatchResult] = None
        self._val_results: List[ValidationResult] = []
        self._worker: Optional[WorkerThread] = None

        self._build_ui()
        self.statusBar().showMessage("파일을 선택하고 '취합 실행' 버튼을 눌러주세요.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable area for settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll.setWidget(scroll_content)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(16, 12, 16, 12)
        scroll_layout.setSpacing(10)

        # ── Title ──────────────────────────────────────────────────────
        title_lbl = QLabel("협력사 현황 취합 자동화")
        font = QFont()
        font.setBold(True)
        font.setPointSize(18)
        title_lbl.setFont(font)
        title_lbl.setStyleSheet("color:#1a3c8f;")

        desc_lbl = QLabel(
            "최종 파일과 알바 취합 파일을 협력사 키값 기준으로 매칭하고, "
            "Feedback 입력 적정성을 검토합니다."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color:#555;")

        scroll_layout.addWidget(title_lbl)
        scroll_layout.addWidget(desc_lbl)
        scroll_layout.addWidget(_make_separator())

        # ── File selection ─────────────────────────────────────────────
        scroll_layout.addWidget(_make_header("파일 선택"))
        scroll_layout.addWidget(self._build_file_section())
        scroll_layout.addWidget(_make_separator())

        # ── Sheet selection ────────────────────────────────────────────
        scroll_layout.addWidget(_make_header("시트 선택"))
        scroll_layout.addWidget(self._build_sheet_section())
        scroll_layout.addWidget(_make_separator())

        # ── Hidden column/row info ─────────────────────────────────────
        scroll_layout.addWidget(_make_header("숨김 컬럼 / 숨김 행 안내"))
        self._hidden_info_lbl = QLabel("파일과 시트를 선택하면 여기에 안내가 표시됩니다.")
        self._hidden_info_lbl.setWordWrap(True)
        self._hidden_info_lbl.setStyleSheet(
            "background:#fffbe6;border:1px solid #ffe58f;"
            "border-radius:4px;padding:6px;"
        )
        scroll_layout.addWidget(self._hidden_info_lbl)
        scroll_layout.addWidget(_make_separator())

        # ── Column mapping ────────────────────────────────────────────
        scroll_layout.addWidget(_make_header("컬럼 매핑 설정"))
        mapping_row = QHBoxLayout()
        defaults = ColumnConfig().to_dict()
        self._col_mapping = ColumnMappingWidget(
            "최종 파일 / 알바 파일 컬럼", _FIELD_LABELS, defaults
        )
        mapping_row.addWidget(self._col_mapping)
        mapping_row.addStretch()
        scroll_layout.addLayout(mapping_row)
        scroll_layout.addWidget(_make_separator())

        # ── Reference column mapping (hidden initially) ───────────────
        self._ref_mapping_group = QGroupBox("정답지 컬럼 설정")
        ref_defaults = RefColumnConfig().to_dict()
        self._ref_col_mapping = ColumnMappingWidget(
            "", _REF_FIELD_LABELS, ref_defaults
        )
        ref_grp_layout = QVBoxLayout(self._ref_mapping_group)
        ref_grp_layout.addWidget(self._ref_col_mapping)
        self._ref_mapping_group.setVisible(False)
        scroll_layout.addWidget(self._ref_mapping_group)

        # ── Options ───────────────────────────────────────────────────
        scroll_layout.addWidget(_make_header("옵션 설정"))
        self._opt_validation = QCheckBox("정답지 검증 사용 (정답지 파일 선택 시 활성화)")
        self._opt_validation.setChecked(True)
        scroll_layout.addWidget(self._opt_validation)

        # ── Execute button + progress ─────────────────────────────────
        scroll_layout.addWidget(_make_separator())
        exec_row = QHBoxLayout()
        self._run_btn = QPushButton("취합 실행")
        self._run_btn.setFixedHeight(38)
        self._run_btn.setStyleSheet(
            "QPushButton{background:#1a3c8f;color:white;border-radius:5px;"
            "font-weight:bold;font-size:14px;padding:0 24px;}"
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
        scroll_layout.addLayout(exec_row)
        scroll_layout.addStretch()

        outer.addWidget(scroll, stretch=1)

        # ── Summary cards ─────────────────────────────────────────────
        outer.addWidget(_make_separator())
        self._summary_widget = self._build_summary_section()
        self._summary_widget.setVisible(False)
        outer.addWidget(self._summary_widget)

        # ── Result tabs ───────────────────────────────────────────────
        self._tabs = self._build_result_tabs()
        self._tabs.setVisible(False)
        outer.addWidget(self._tabs, stretch=2)

        # ── Save area ────────────────────────────────────────────────
        outer.addWidget(_make_separator())
        save_row = QHBoxLayout()
        save_row.setContentsMargins(16, 8, 16, 8)
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
        save_widget = QWidget()
        save_widget.setLayout(save_row)
        outer.addWidget(save_widget)

    def _build_file_section(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        def _file_row(label: str, btn_text: str, attr_lbl: str, select_fn):
            row = QHBoxLayout()
            btn = QPushButton(btn_text)
            btn.setFixedWidth(200)
            btn.clicked.connect(select_fn)
            lbl = QLabel("선택된 파일 없음")
            lbl.setStyleSheet("color:#888;")
            lbl.setWordWrap(True)
            row.addWidget(QLabel(label))
            row.addWidget(btn)
            row.addWidget(lbl, stretch=1)
            setattr(self, attr_lbl, lbl)
            return row

        layout.addLayout(
            _file_row("필수  최종 완성 파일:", "최종 파일 선택", "_final_path_lbl",
                      self._select_final)
        )
        layout.addLayout(
            _file_row("필수  알바 취합 파일:", "알바 파일 선택", "_alba_path_lbl",
                      self._select_alba)
        )
        layout.addLayout(
            _file_row("선택  5월 정답지 파일:", "정답지 파일 선택 (선택)", "_ref_path_lbl",
                      self._select_ref)
        )
        return w

    def _build_sheet_section(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)

        self._final_sheet_combo = QComboBox()
        self._final_sheet_combo.setMinimumWidth(200)
        self._final_sheet_combo.currentTextChanged.connect(
            lambda: self._refresh_hidden_info("final")
        )
        self._alba_sheet_combo = QComboBox()
        self._alba_sheet_combo.setMinimumWidth(200)
        self._ref_sheet_combo = QComboBox()
        self._ref_sheet_combo.setMinimumWidth(200)
        self._ref_sheet_combo.currentTextChanged.connect(
            lambda: self._refresh_hidden_info("ref")
        )

        form.addRow("최종 파일 시트:", self._final_sheet_combo)
        form.addRow("알바 파일 시트:", self._alba_sheet_combo)
        self._ref_sheet_row_label = QLabel("정답지 파일 시트:")
        form.addRow(self._ref_sheet_row_label, self._ref_sheet_combo)
        self._ref_sheet_combo.setVisible(False)
        self._ref_sheet_row_label.setVisible(False)
        return w

    def _build_summary_section(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#f7f9ff;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._cards: Dict[str, SummaryCard] = {}
        card_defs = [
            ("total_final", "최종 파일\n전체 키"),
            ("total_alba", "알바 파일\n키 수"),
            ("matched", "매칭 성공"),
            ("unmatched", "미매칭"),
            ("alba_only", "알바만 존재"),
            ("duplicates", "중복 키"),
            ("v_normal", "검증 정상"),
            ("v_check", "확인 필요"),
            ("v_missing", "누락 의심"),
            ("v_short", "상세내용 부족"),
            ("v_none", "미입력"),
            ("v_unverified", "미검증"),
        ]
        for key, label in card_defs:
            card = SummaryCard(label)
            self._cards[key] = card
            layout.addWidget(card, stretch=1)
        return w

    def _build_result_tabs(self) -> QTabWidget:
        tabs = QTabWidget()

        def _make_table(cols: List[str]) -> QTableWidget:
            t = QTableWidget()
            t.setColumnCount(len(cols))
            t.setHorizontalHeaderLabels(cols)
            t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            t.setAlternatingRowColors(True)
            t.horizontalHeader().setStretchLastSection(True)
            return t

        self._tab_matched = _make_table(["키값", "최종행", "알바행"] + list(_FIELD_LABELS.values())[1:])
        self._tab_unmatched = _make_table(["키값", "최종행"])
        self._tab_duplicates = _make_table(["키값", "중복 행 목록", "사용된 행"])
        self._tab_alba_only = _make_table(["키값", "알바행"] + list(_FIELD_LABELS.values())[1:])
        self._tab_validation = _make_table([
            "키값", "협력사 Feedback", "상세내용",
            "추천 Feedback", "유사 참고 사례", "유사도", "검증 결과", "비고"
        ])
        self._tab_all = _make_table(["키값", "구분", "최종행", "알바행"])

        tabs.addTab(self._tab_matched, "매칭 성공")
        tabs.addTab(self._tab_unmatched, "미매칭")
        tabs.addTab(self._tab_duplicates, "중복 키")
        tabs.addTab(self._tab_alba_only, "알바 파일에만 있는 키")
        tabs.addTab(self._tab_validation, "Feedback 확인 필요")
        tabs.addTab(self._tab_all, "전체 결과")
        return tabs

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

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
        self._ref_sheet_row_label.setVisible(True)
        self._refresh_hidden_info("ref")

    def _load_sheets(self, path: str, combo: QComboBox):
        try:
            sheets = get_sheet_names(path)
            combo.clear()
            combo.addItems(sheets)
        except Exception as e:
            QMessageBox.warning(self, "시트 읽기 오류", f"시트 목록을 읽을 수 없습니다:\n{e}")

    # ------------------------------------------------------------------
    # Hidden column / row info
    # ------------------------------------------------------------------

    def _refresh_hidden_info(self, which: str):
        messages: List[str] = []

        def _describe(label: str, path: Optional[str], combo: QComboBox):
            if not path or not combo.currentText():
                return
            try:
                hidden_cols, hidden_rows = get_hidden_info(path, combo.currentText())
                if hidden_cols:
                    messages.append(
                        f"[{label}] 숨김 컬럼: {', '.join(hidden_cols)}"
                    )
                if hidden_rows:
                    display = hidden_rows[:20]
                    suffix = f" … 외 {len(hidden_rows)-20}행" if len(hidden_rows) > 20 else ""
                    messages.append(
                        f"[{label}] 숨김 행: {', '.join(map(str,display))}{suffix}"
                    )
                if not hidden_cols and not hidden_rows:
                    messages.append(f"[{label}] 숨김 컬럼/행 없음")
            except Exception as e:
                messages.append(f"[{label}] 숨김 정보 읽기 오류: {e}")

        if which in ("final", "all"):
            _describe("최종 파일", self._final_path, self._final_sheet_combo)
        if which in ("ref", "all") and self._ref_path:
            _describe("정답지 파일", self._ref_path, self._ref_sheet_combo)

        if messages:
            self._hidden_info_lbl.setText("\n".join(messages))
        else:
            self._hidden_info_lbl.setText("파일과 시트를 선택하면 여기에 안내가 표시됩니다.")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Run matching
    # ------------------------------------------------------------------

    def _on_run(self):
        # Pre-flight checks
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

        use_validation = self._opt_validation.isChecked()
        if use_validation and not self._ref_path:
            reply = QMessageBox.question(
                self, "정답지 미선택",
                "정답지 파일이 선택되지 않았습니다. 검증 없이 진행하겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            use_validation = False

        col_config = self._get_col_config()
        if col_config is None:
            return
        ref_col_config = self._get_ref_col_config()
        if ref_col_config is None:
            return

        # UI state
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
        )
        self._worker.finished.connect(self._on_run_finished)
        self._worker.error.connect(self._on_run_error)
        self._worker.start()

    def _on_run_finished(self, match_result: MatchResult, val_results: List[ValidationResult]):
        self._match_result = match_result
        self._val_results = val_results

        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._save_btn.setEnabled(True)

        self._populate_summary(match_result, val_results)
        self._populate_tabs(match_result, val_results)

        self._summary_widget.setVisible(True)
        self._tabs.setVisible(True)

        self.statusBar().showMessage(
            f"완료: 매칭 성공 {len(match_result.matched)}건, "
            f"미매칭 {len(match_result.unmatched)}건"
        )

    def _on_run_error(self, tb: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(
            self, "실행 오류",
            f"취합 실행 중 오류가 발생했습니다:\n\n{tb[-1500:]}"
        )
        self.statusBar().showMessage("오류 발생 — 로그를 확인해주세요.")

    # ------------------------------------------------------------------
    # Populate summary
    # ------------------------------------------------------------------

    def _populate_summary(self, mr: MatchResult, vr: List[ValidationResult]):
        from collections import Counter
        vc = Counter(v.status for v in vr)

        self._cards["total_final"].set_value(mr.total_final_keys)
        self._cards["total_alba"].set_value(mr.total_alba_keys)
        self._cards["matched"].set_value(len(mr.matched))
        self._cards["unmatched"].set_value(len(mr.unmatched))
        self._cards["alba_only"].set_value(len(mr.alba_only))
        self._cards["duplicates"].set_value(len(mr.duplicates))
        self._cards["v_normal"].set_value(vc.get(ValidationStatus.NORMAL, 0))
        self._cards["v_check"].set_value(vc.get(ValidationStatus.CHECK_NEEDED, 0))
        self._cards["v_missing"].set_value(vc.get(ValidationStatus.MISSING_SUSPECTED, 0))
        self._cards["v_short"].set_value(vc.get(ValidationStatus.DETAIL_INSUFFICIENT, 0))
        self._cards["v_none"].set_value(vc.get(ValidationStatus.NOT_ENTERED, 0))
        self._cards["v_unverified"].set_value(vc.get(ValidationStatus.NOT_VERIFIED, 0))

    # ------------------------------------------------------------------
    # Populate result tabs
    # ------------------------------------------------------------------

    def _populate_tabs(self, mr: MatchResult, vr: List[ValidationResult]):
        cfg = self._get_col_config()
        val_cols = list(cfg.value_columns().values()) if cfg else []
        val_labels = list(_FIELD_LABELS.values())[1:]  # skip "key"

        # Tab 1: Matched
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
                v = safe_str(row.values.get(col_l, ""))
                self._tab_matched.setItem(r, 3 + i, _table_item(v))
        self._tab_matched.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._tab_matched.horizontalHeader().setStretchLastSection(True)

        # Tab 2: Unmatched
        _fill_table(
            self._tab_unmatched, ["키값", "최종행"],
            [[r.key, r.final_row] for r in mr.unmatched]
        )

        # Tab 3: Duplicates
        dup_rows = []
        for d in mr.duplicates:
            dup_rows.append([d.key, ", ".join(map(str, d.rows)), d.used_row])
        _fill_table(self._tab_duplicates, ["키값", "중복 행 목록", "사용된 행"], dup_rows)

        # Tab 4: Alba only
        self._tab_alba_only.setRowCount(0)
        self._tab_alba_only.setColumnCount(2 + len(val_labels))
        self._tab_alba_only.setHorizontalHeaderLabels(["키값", "알바행"] + val_labels)
        for row in mr.alba_only:
            r = self._tab_alba_only.rowCount()
            self._tab_alba_only.insertRow(r)
            self._tab_alba_only.setItem(r, 0, _table_item(row.key))
            self._tab_alba_only.setItem(r, 1, _table_item(str(row.alba_row)))
            for i, col_l in enumerate(val_cols):
                v = safe_str(row.values.get(col_l, ""))
                self._tab_alba_only.setItem(r, 2 + i, _table_item(v))
        self._tab_alba_only.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._tab_alba_only.horizontalHeader().setStretchLastSection(True)

        # Tab 5: Validation
        self._tab_validation.setRowCount(0)
        vr_map = {v.key: v for v in vr}
        for v in vr:
            bg = _status_color(v.status)
            r = self._tab_validation.rowCount()
            self._tab_validation.insertRow(r)
            for c, val in enumerate([
                v.key, v.current_feedback, v.current_detail,
                v.recommended_feedback, v.similar_ref_detail,
                f"{v.similarity_score:.0f}" if v.similarity_score else "",
                v.status.value, v.note,
            ]):
                item = _table_item(val, bg)
                self._tab_validation.setItem(r, c, item)
        self._tab_validation.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._tab_validation.horizontalHeader().setStretchLastSection(True)

        # Tab 6: All results
        all_rows = []
        for row in mr.matched:
            status = vr_map[row.key].status.value if row.key in vr_map else "—"
            all_rows.append([row.key, f"매칭 성공 ({status})", row.final_row, row.alba_row])
        for row in mr.unmatched:
            all_rows.append([row.key, "미매칭", row.final_row, "—"])
        for row in mr.alba_only:
            all_rows.append([row.key, "알바만 존재", "—", row.alba_row])
        _fill_table(self._tab_all, ["키값", "구분", "최종행", "알바행"], all_rows)

        # Rename tabs with counts
        self._tabs.setTabText(0, f"매칭 성공 ({len(mr.matched)})")
        self._tabs.setTabText(1, f"미매칭 ({len(mr.unmatched)})")
        self._tabs.setTabText(2, f"중복 키 ({len(mr.duplicates)})")
        self._tabs.setTabText(3, f"알바만 존재 ({len(mr.alba_only)})")
        self._tabs.setTabText(4, f"Feedback 확인 ({len(vr)})")
        self._tabs.setTabText(5, f"전체 결과 ({len(all_rows)})")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

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
            QMessageBox.information(
                self, "저장 완료",
                f"완성본이 저장되었습니다:\n{save_path}\n\n"
                f"반영된 행: {len(self._match_result.matched)}건"
            )
        except PermissionError:
            QMessageBox.critical(
                self, "저장 오류",
                "파일을 저장할 수 없습니다.\n"
                "저장하려는 파일이 Excel에서 열려 있다면 닫고 다시 시도해주세요."
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
