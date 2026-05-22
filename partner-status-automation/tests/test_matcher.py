"""
Unit tests for src/matcher.py
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.matcher import (
    AlbaOnlyRow,
    DuplicateInfo,
    MatchResult,
    MatchedRow,
    UnmatchedRow,
    build_changes,
    run_matching,
)
from src.utils import ColumnConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_col_config():
    return ColumnConfig(
        key="A",
        encourage_yn="B",
        encourage_method="C",
        encourage_date="D",
        partner_feedback="E",
        detail="F",
        quote_reply_yn="G",
        reply_date="H",
    )


# ---------------------------------------------------------------------------
# build_changes tests
# ---------------------------------------------------------------------------

def test_build_changes_basic(simple_col_config):
    mr = MatchResult()
    mr.matched = [
        MatchedRow(
            key="PARTNER-001",
            final_row=2,
            alba_row=3,
            values={
                "B": "Y",
                "C": "전화",
                "D": "2026-05-01",
                "E": "견적 완료",
                "F": "전화 통화 후 확인",
                "G": "Y",
                "H": "2026-05-02",
            },
        )
    ]
    changes = build_changes(mr, simple_col_config)
    assert len(changes) == 7  # 7 value columns
    rows = [c["row"] for c in changes]
    assert all(r == 2 for r in rows)
    col_letters = {c["col_letter"] for c in changes}
    assert col_letters == {"B", "C", "D", "E", "F", "G", "H"}


def test_build_changes_empty(simple_col_config):
    mr = MatchResult()
    assert build_changes(mr, simple_col_config) == []


def test_build_changes_multiple_rows(simple_col_config):
    mr = MatchResult()
    mr.matched = [
        MatchedRow(key="K1", final_row=2, alba_row=5,
                   values={"B": "Y", "C": "", "D": "", "E": "", "F": "", "G": "", "H": ""}),
        MatchedRow(key="K2", final_row=10, alba_row=7,
                   values={"B": "N", "C": "", "D": "", "E": "", "F": "", "G": "", "H": ""}),
    ]
    changes = build_changes(mr, simple_col_config)
    assert len(changes) == 14


# ---------------------------------------------------------------------------
# MatchResult properties
# ---------------------------------------------------------------------------

def test_match_result_total_final_keys():
    mr = MatchResult()
    mr.matched = [MatchedRow("K1", 1, 1, {}), MatchedRow("K2", 2, 2, {})]
    mr.unmatched = [UnmatchedRow("K3", 3)]
    assert mr.total_final_keys == 3


def test_match_result_total_alba_keys():
    mr = MatchResult()
    mr.matched = [MatchedRow("K1", 1, 1, {}), MatchedRow("K2", 2, 2, {})]
    mr.alba_only = [AlbaOnlyRow("K5", 10, {})]
    assert mr.total_alba_keys == 3


# ---------------------------------------------------------------------------
# run_matching integration (with real xlsx files)
# ---------------------------------------------------------------------------

def _make_xlsx(path: str, rows: list, col_config: ColumnConfig):
    """Helper: create minimal xlsx for testing."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for row_data in rows:
        ws.append(row_data)
    wb.save(path)


def test_run_matching_basic(tmp_path, simple_col_config):
    """Three keys in final, two in alba → 2 matched, 1 unmatched, 1 alba-only."""
    final_xlsx = str(tmp_path / "final.xlsx")
    alba_xlsx = str(tmp_path / "alba.xlsx")

    # final file: A column = keys
    _make_xlsx(final_xlsx, [
        ["K1"],
        ["K2"],
        ["K3"],
    ], simple_col_config)

    # alba file: A=key, B=encourage_yn, E=partner_feedback, F=detail
    _make_xlsx(alba_xlsx, [
        ["K1", "Y", "전화", None, "정상", "통화 완료", "Y", None],
        ["K2", "N", None, None, None, None, None, None],
        ["K4", "Y", None, None, "미확인", None, None, None],
    ], simple_col_config)

    result = run_matching(
        final_xlsx, "Sheet", alba_xlsx, "Sheet", simple_col_config
    )
    assert len(result.matched) == 2
    assert len(result.unmatched) == 1
    assert result.unmatched[0].key == "K3"
    assert len(result.alba_only) == 1
    assert result.alba_only[0].key == "K4"


def test_run_matching_duplicates(tmp_path, simple_col_config):
    """Duplicate key in alba → first occurrence used, duplicate recorded."""
    final_xlsx = str(tmp_path / "final.xlsx")
    alba_xlsx = str(tmp_path / "alba.xlsx")

    _make_xlsx(final_xlsx, [["K1"]], simple_col_config)
    _make_xlsx(alba_xlsx, [
        ["K1", "Y", None, None, "첫번째", None, None, None],
        ["K1", "N", None, None, "두번째", None, None, None],
    ], simple_col_config)

    result = run_matching(
        final_xlsx, "Sheet", alba_xlsx, "Sheet", simple_col_config
    )
    assert len(result.matched) == 1
    assert len(result.duplicates) == 1
    dup = result.duplicates[0]
    assert dup.key == "K1"
    assert len(dup.rows) == 2
    # First occurrence value should be used
    matched = result.matched[0]
    assert matched.values.get("E") == "첫번째"
