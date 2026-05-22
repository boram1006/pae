"""
Unit tests for src/validator.py
"""
import pytest

from src.validator import (
    ValidationStatus,
    validate_single,
    validate_all,
)
from src.matcher import MatchedRow
from src.utils import ColumnConfig


# ---------------------------------------------------------------------------
# validate_single edge cases
# ---------------------------------------------------------------------------

def test_both_empty():
    assert validate_single("K1", "", "", None).status == ValidationStatus.NOT_ENTERED


def test_detail_exists_feedback_empty():
    r = validate_single("K1", "", "업체 전화 시 담당자 부재 확인", None)
    assert r.status == ValidationStatus.MISSING_SUSPECTED


def test_feedback_exists_no_detail():
    r = validate_single("K1", "견적 완료", "", None)
    assert r.status == ValidationStatus.NORMAL


def test_detail_too_short():
    r = validate_single("K1", "견적", "OK", None)
    assert r.status == ValidationStatus.DETAIL_INSUFFICIENT


def test_no_reference_returns_not_verified():
    r = validate_single("K1", "견적 완료", "업체 담당자 통화 후 견적 회신 받음", None)
    assert r.status == ValidationStatus.NOT_VERIFIED


def test_with_matching_reference():
    ref = [{
        "key": "K1",
        "feedback": "견적 완료",
        "detail": "업체 담당자 통화 후 견적 회신 받음",
        "norm_detail": "업체 담당자 통화 후 견적 회신 받음",
    }]
    r = validate_single("K1", "견적 완료", "업체 담당자 통화 후 견적 회신 받음", ref)
    assert r.status == ValidationStatus.NORMAL
    assert r.recommended_feedback == "견적 완료"
    assert r.similarity_score >= 70


def test_with_differing_feedback():
    ref = [{
        "key": "K1",
        "feedback": "견적 완료",
        "detail": "업체 담당자 통화 후 견적 회신 받음",
        "norm_detail": "업체 담당자 통화 후 견적 회신 받음",
    }]
    r = validate_single("K1", "미확인", "업체 담당자 통화 후 견적 회신 받음", ref)
    assert r.status in (ValidationStatus.CHECK_NEEDED, ValidationStatus.NORMAL)


def test_none_values_treated_as_empty():
    assert validate_single("K1", None, None, None).status == ValidationStatus.NOT_ENTERED


def test_nan_string_treated_as_empty():
    assert validate_single("K1", "nan", "NaN", None).status == ValidationStatus.NOT_ENTERED


def test_low_similarity_returns_not_verified():
    ref = [{
        "key": "OTHER",
        "feedback": "완전 다른 피드백",
        "detail": "전혀 관련 없는 내용입니다 xyz abc 123",
        "norm_detail": "전혀 관련 없는 내용입니다 xyz abc 123",
    }]
    r = validate_single("K1", "견적 완료", "업체 담당자 통화 후 견적 회신 받음", ref)
    assert r.status in (ValidationStatus.NOT_VERIFIED, ValidationStatus.CHECK_NEEDED)


def test_similarity_score_populated():
    ref = [{"key": "K1", "feedback": "견적 완료",
            "detail": "담당자 통화", "norm_detail": "담당자 통화"}]
    r = validate_single("K1", "견적 완료", "담당자 통화", ref)
    assert r.similarity_score > 0


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------

def _make_matched_row(key, feedback="", detail="") -> MatchedRow:
    cfg = ColumnConfig()
    return MatchedRow(
        key=key, final_row=1, alba_row=1,
        values={cfg.partner_feedback: feedback, cfg.detail: detail},
        original_feedback=feedback,
        final_feedback=feedback,
    )


def test_validate_all_empty():
    assert validate_all([], ColumnConfig(), None) == []


def test_validate_all_detects_missing_feedback():
    rows = [_make_matched_row("K1", feedback="", detail="상세내용이 충분히 길게 입력됨")]
    results = validate_all(rows, ColumnConfig(), None)
    assert len(results) == 1
    assert results[0].status == ValidationStatus.MISSING_SUSPECTED


def test_validate_all_detects_not_entered():
    rows = [_make_matched_row("K1", feedback="", detail="")]
    results = validate_all(rows, ColumnConfig(), None)
    assert results[0].status == ValidationStatus.NOT_ENTERED


def test_validate_all_result_key_matches():
    rows = [_make_matched_row("PARTNER-XYZ", feedback="", detail="")]
    results = validate_all(rows, ColumnConfig(), None)
    assert results[0].key == "PARTNER-XYZ"


# ---------------------------------------------------------------------------
# Feedback check statuses (ensure tab filter works correctly)
# ---------------------------------------------------------------------------

def test_feedback_check_statuses_cover_problematic():
    """CHECK_NEEDED, MISSING_SUSPECTED, DETAIL_INSUFFICIENT, NOT_VERIFIED
    must all be in the set used by the UI tab filter."""
    from app import _FEEDBACK_CHECK_STATUSES
    assert ValidationStatus.CHECK_NEEDED        in _FEEDBACK_CHECK_STATUSES
    assert ValidationStatus.MISSING_SUSPECTED   in _FEEDBACK_CHECK_STATUSES
    assert ValidationStatus.DETAIL_INSUFFICIENT in _FEEDBACK_CHECK_STATUSES
    assert ValidationStatus.NOT_VERIFIED        in _FEEDBACK_CHECK_STATUSES
    assert ValidationStatus.NORMAL              not in _FEEDBACK_CHECK_STATUSES
    assert ValidationStatus.NOT_ENTERED         not in _FEEDBACK_CHECK_STATUSES
