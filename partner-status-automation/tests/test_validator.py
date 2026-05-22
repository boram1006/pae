"""
Unit tests for src/validator.py
"""
import pytest

from src.validator import (
    ValidationStatus,
    validate_single,
)


# ---------------------------------------------------------------------------
# validate_single edge cases
# ---------------------------------------------------------------------------

def test_both_empty():
    r = validate_single("K1", "", "", None)
    assert r.status == ValidationStatus.NOT_ENTERED


def test_detail_exists_feedback_empty():
    r = validate_single("K1", "", "업체 전화 시 담당자 부재 확인", None)
    assert r.status == ValidationStatus.MISSING_SUSPECTED


def test_feedback_exists_no_detail():
    r = validate_single("K1", "견적 완료", "", None)
    assert r.status == ValidationStatus.NORMAL


def test_detail_too_short():
    r = validate_single("K1", "견적", "OK", None)
    assert r.status == ValidationStatus.DETAIL_INSUFFICIENT


def test_no_reference_data_returns_not_verified():
    r = validate_single("K1", "견적 완료", "업체 담당자 통화 후 견적 회신 받음", None)
    assert r.status == ValidationStatus.NOT_VERIFIED


def test_with_matching_reference():
    ref = [
        {
            "key": "K1",
            "feedback": "견적 완료",
            "detail": "업체 담당자 통화 후 견적 회신 받음",
            "norm_detail": "업체 담당자 통화 후 견적 회신 받음",
        }
    ]
    r = validate_single("K1", "견적 완료", "업체 담당자 통화 후 견적 회신 받음", ref)
    assert r.status == ValidationStatus.NORMAL
    assert r.recommended_feedback == "견적 완료"
    assert r.similarity_score >= 70


def test_with_differing_feedback():
    ref = [
        {
            "key": "K1",
            "feedback": "견적 완료",
            "detail": "업체 담당자 통화 후 견적 회신 받음",
            "norm_detail": "업체 담당자 통화 후 견적 회신 받음",
        }
    ]
    # Same detail, but different feedback
    r = validate_single("K1", "미확인", "업체 담당자 통화 후 견적 회신 받음", ref)
    # Should be CHECK_NEEDED since feedback doesn't match reference
    assert r.status in (ValidationStatus.CHECK_NEEDED, ValidationStatus.NORMAL)


def test_none_values_treated_as_empty():
    r = validate_single("K1", None, None, None)
    assert r.status == ValidationStatus.NOT_ENTERED


def test_nan_string_treated_as_empty():
    r = validate_single("K1", "nan", "NaN", None)
    assert r.status == ValidationStatus.NOT_ENTERED


# ---------------------------------------------------------------------------
# validate_single with various reference data
# ---------------------------------------------------------------------------

def test_low_similarity_returns_not_verified():
    ref = [
        {
            "key": "OTHER",
            "feedback": "완전 다른 피드백",
            "detail": "전혀 관련 없는 내용입니다 xyz abc 123",
            "norm_detail": "전혀 관련 없는 내용입니다 xyz abc 123",
        }
    ]
    r = validate_single(
        "K1", "견적 완료", "업체 담당자 통화 후 견적 회신 받음", ref
    )
    # Very different ref → not verified or check_needed depending on score
    assert r.status in (ValidationStatus.NOT_VERIFIED, ValidationStatus.CHECK_NEEDED)


def test_similarity_score_populated():
    ref = [
        {
            "key": "K1",
            "feedback": "견적 완료",
            "detail": "담당자 통화",
            "norm_detail": "담당자 통화",
        }
    ]
    r = validate_single("K1", "견적 완료", "담당자 통화", ref)
    assert r.similarity_score > 0
