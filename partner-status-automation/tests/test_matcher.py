"""
Unit tests for src/matcher.py
"""
from datetime import date, datetime

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
from src.utils import ColumnConfig, parse_date, dates_match


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg():
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


def _xlsx(path: str, rows: list):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)


# ---------------------------------------------------------------------------
# build_changes: uses final_feedback for feedback column
# ---------------------------------------------------------------------------

def test_build_changes_uses_final_feedback(cfg):
    mr = MatchResult()
    mr.matched = [
        MatchedRow(
            key="K1", final_row=2, alba_row=3,
            values={"B":"Y","C":"전화","D":"2026-05-01","E":"원래값","F":"상세","G":"Y","H":None},
            original_feedback="원래값",
            final_feedback="수정값",
            feedback_changed=True,
        )
    ]
    changes = build_changes(mr, cfg)
    fb_changes = [c for c in changes if c["col_letter"] == "E"]
    assert len(fb_changes) == 1
    assert fb_changes[0]["value"] == "수정값"   # final_feedback, not original


def test_build_changes_preserves_original_feedback(cfg):
    """When feedback is unchanged, final_feedback == original_feedback."""
    mr = MatchResult()
    mr.matched = [
        MatchedRow(
            key="K1", final_row=2, alba_row=3,
            values={"B":"Y","C":"","D":"","E":"통화완료","F":"","G":"","H":""},
            original_feedback="통화완료",
            final_feedback="통화완료",
        )
    ]
    changes = build_changes(mr, cfg)
    fb_changes = [c for c in changes if c["col_letter"] == "E"]
    assert fb_changes[0]["value"] == "통화완료"


def test_build_changes_empty(cfg):
    assert build_changes(MatchResult(), cfg) == []


def test_build_changes_multiple_rows(cfg):
    mr = MatchResult()
    mr.matched = [
        MatchedRow("K1", 2, 5, {"B":"Y","C":"","D":"","E":"","F":"","G":"","H":""}),
        MatchedRow("K2", 10, 7, {"B":"N","C":"","D":"","E":"","F":"","G":"","H":""}),
    ]
    assert len(build_changes(mr, cfg)) == 14  # 7 value cols × 2 rows


# ---------------------------------------------------------------------------
# MatchedRow feedback fields
# ---------------------------------------------------------------------------

def test_feedback_changed_flag():
    row = MatchedRow("K1", 1, 1, {}, original_feedback="A", final_feedback="A")
    assert not row.feedback_changed
    row.final_feedback = "B"
    row.feedback_changed = row.final_feedback != row.original_feedback
    assert row.feedback_changed


def test_original_feedback_preserved():
    row = MatchedRow("K1", 1, 1, {}, original_feedback="원래값", final_feedback="원래값")
    row.final_feedback = "새값"
    # original must not be touched
    assert row.original_feedback == "원래값"


# ---------------------------------------------------------------------------
# MatchResult properties
# ---------------------------------------------------------------------------

def test_total_final_keys():
    mr = MatchResult()
    mr.matched        = [MatchedRow("K1", 1, 1, {}), MatchedRow("K2", 2, 2, {})]
    mr.unmatched      = [UnmatchedRow("K3", 3)]
    mr.date_filtered  = [MatchedRow("K4", 4, 4, {})]
    assert mr.total_final_keys == 4


def test_total_alba_keys():
    mr = MatchResult()
    mr.matched    = [MatchedRow("K1", 1, 1, {}), MatchedRow("K2", 2, 2, {})]
    mr.alba_only  = [AlbaOnlyRow("K5", 10, {})]
    assert mr.total_alba_keys == 3


# ---------------------------------------------------------------------------
# run_matching basic
# ---------------------------------------------------------------------------

def test_run_matching_basic(tmp_path, cfg):
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"], ["K2"], ["K3"]])
    _xlsx(alba,  [
        ["K1", "Y", "전화", None, "정상", "통화 완료", "Y", None],
        ["K2", "N", None,  None, None,  None,       None, None],
        ["K4", "Y", None,  None, "미확인", None,    None, None],
    ])
    result = run_matching(final, "Sheet", alba, "Sheet", cfg)
    assert len(result.matched)   == 2
    assert len(result.unmatched) == 1
    assert result.unmatched[0].key == "K3"
    assert len(result.alba_only) == 1
    assert result.alba_only[0].key == "K4"


def test_run_matching_duplicates(tmp_path, cfg):
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"]])
    _xlsx(alba,  [
        ["K1", "Y", None, None, "첫번째", None, None, None],
        ["K1", "N", None, None, "두번째", None, None, None],
    ])
    result = run_matching(final, "Sheet", alba, "Sheet", cfg)
    assert len(result.matched)    == 1
    assert len(result.duplicates) == 1
    assert result.duplicates[0].key == "K1"
    assert result.matched[0].values.get("E") == "첫번째"


def test_run_matching_sets_feedback_fields(tmp_path, cfg):
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"]])
    _xlsx(alba,  [["K1", "Y", "전화", None, "통화완료", "상세내용", "Y", None]])
    result = run_matching(final, "Sheet", alba, "Sheet", cfg)
    row = result.matched[0]
    assert row.original_feedback == "통화완료"
    assert row.final_feedback    == "통화완료"
    assert not row.feedback_changed


# ---------------------------------------------------------------------------
# Date filter
# ---------------------------------------------------------------------------

def test_date_filter_passes_matching_date(tmp_path, cfg):
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"], ["K2"]])
    _xlsx(alba,  [
        ["K1", "Y", "전화", "2026-05-23", "통화완료", "", "Y", None],
        ["K2", "N", "",     "2026-05-22", "부재",     "", "", None],
    ])
    result = run_matching(
        final, "Sheet", alba, "Sheet", cfg,
        filter_date=date(2026, 5, 23),
    )
    assert len(result.matched)       == 1
    assert result.matched[0].key     == "K1"
    assert len(result.date_filtered) == 1
    assert result.date_filtered[0].key == "K2"


def test_date_filter_off_includes_all(tmp_path, cfg):
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"], ["K2"]])
    _xlsx(alba,  [
        ["K1", "Y", "", "2026-05-23", "", "", "", None],
        ["K2", "N", "", "2026-05-22", "", "", "", None],
    ])
    result = run_matching(final, "Sheet", alba, "Sheet", cfg, filter_date=None)
    assert len(result.matched)       == 2
    assert len(result.date_filtered) == 0


def test_date_filter_with_datetime_value(tmp_path, cfg):
    """Excel-stored date as datetime object should compare correctly."""
    import openpyxl
    from datetime import datetime as dt

    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"]])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["K1", "Y", "", dt(2026, 5, 23), "FB", "", "", None])
    wb.save(alba)

    result = run_matching(
        final, "Sheet", alba, "Sheet", cfg,
        filter_date=date(2026, 5, 23),
    )
    assert len(result.matched) == 1


def test_date_filter_with_dotted_string(tmp_path, cfg):
    """String date '2026.05.23' should match date(2026, 5, 23)."""
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"]])
    _xlsx(alba,  [["K1", "Y", "", "2026.05.23", "FB", "", "", None]])
    result = run_matching(
        final, "Sheet", alba, "Sheet", cfg,
        filter_date=date(2026, 5, 23),
    )
    assert len(result.matched) == 1


def test_date_filter_with_month_day_string(tmp_path, cfg):
    """String date '5/23' should match date(current_year, 5, 23)."""
    from datetime import date as d_cls
    today = d_cls.today()
    final = str(tmp_path / "final.xlsx")
    alba  = str(tmp_path / "alba.xlsx")
    _xlsx(final, [["K1"]])
    _xlsx(alba,  [["K1", "Y", "", "5/23", "FB", "", "", None]])
    result = run_matching(
        final, "Sheet", alba, "Sheet", cfg,
        filter_date=d_cls(today.year, 5, 23),
    )
    assert len(result.matched) == 1


# ---------------------------------------------------------------------------
# parse_date / dates_match utilities
# ---------------------------------------------------------------------------

def test_parse_date_datetime():
    from datetime import datetime as dt
    assert parse_date(dt(2026, 5, 23, 10, 0)) == date(2026, 5, 23)


def test_parse_date_date_obj():
    assert parse_date(date(2026, 5, 23)) == date(2026, 5, 23)


def test_parse_date_string_formats():
    assert parse_date("2026-05-23") == date(2026, 5, 23)
    assert parse_date("2026.05.23") == date(2026, 5, 23)
    assert parse_date("2026/05/23") == date(2026, 5, 23)


def test_parse_date_none():
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("nan") is None


def test_dates_match_true():
    assert dates_match("2026-05-23", date(2026, 5, 23))


def test_dates_match_false():
    assert not dates_match("2026-05-22", date(2026, 5, 23))


def test_dates_match_none():
    assert not dates_match(None, date(2026, 5, 23))
