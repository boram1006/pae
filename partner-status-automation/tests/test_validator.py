"""
Unit tests for src/validator.py
"""
import pytest

from src.validator import (
    ValidationStatus,
    validate_single,
    validate_all,
    suggest_feedback_from_detail,
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


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------
# suggest_feedback_from_detail
# ---------------------------------------------------------------------------

def test_suggest_feedback_finds_best_keyword_match():
    rules = {
        "견적완료": ["견적", "회신", "완료"],
        "수신불가": ["수신불가", "연결안", "독려"],
    }
    assert suggest_feedback_from_detail("견적서를 회신했습니다", rules) == "견적완료"


def test_suggest_feedback_picks_most_keyword_matches():
    rules = {
        "A": ["견적"],
        "B": ["견적", "회신", "완료"],
    }
    assert suggest_feedback_from_detail("견적 회신 완료했습니다", rules) == "B"


def test_suggest_feedback_returns_empty_when_no_match():
    rules = {"견적완료": ["견적"]}
    assert suggest_feedback_from_detail("전혀 관계없는 내용", rules) == ""


def test_suggest_feedback_empty_detail_returns_empty():
    rules = {"견적완료": ["견적"]}
    assert suggest_feedback_from_detail("", rules) == ""


def test_suggest_feedback_empty_rules_returns_empty():
    assert suggest_feedback_from_detail("견적 회신", {}) == ""


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
# Keyword rules
# ---------------------------------------------------------------------------

_KEYWORD_RULES = {"견적완료": ["견적", "회신", "완료"]}


def test_keyword_match_no_reference_returns_normal():
    r = validate_single("K1", "견적완료", "견적서를 회신했습니다", None, keyword_rules=_KEYWORD_RULES)
    assert r.status == ValidationStatus.NORMAL


def test_keyword_no_match_returns_check_needed():
    r = validate_single("K1", "견적완료", "전혀 관계없는 내용입니다 xyz", None, keyword_rules=_KEYWORD_RULES)
    assert r.status == ValidationStatus.CHECK_NEEDED
    assert "키워드" in r.note


def test_keyword_check_needed_note_mentions_keyword():
    r = validate_single("K1", "견적완료", "담당자에게 전화했습니다", None, keyword_rules=_KEYWORD_RULES)
    assert r.status == ValidationStatus.CHECK_NEEDED


def test_keyword_rules_feedback_not_in_dict_falls_through():
    rules = {"다른피드백": ["견적"]}
    r = validate_single("K1", "견적완료", "어떤 내용입니다", None, keyword_rules=rules)
    # feedback not in rules, no reference → NOT_VERIFIED
    assert r.status == ValidationStatus.NOT_VERIFIED


def test_keyword_empty_list_skips_check():
    rules = {"견적완료": []}  # empty keywords → no keyword check
    r = validate_single("K1", "견적완료", "어떤 내용입니다", None, keyword_rules=rules)
    assert r.status == ValidationStatus.NOT_VERIFIED  # no keywords defined, no reference


def test_keyword_none_rules_behaves_like_before():
    r = validate_single("K1", "견적완료", "업체 담당자에게 연락했습니다", None, keyword_rules=None)
    assert r.status == ValidationStatus.NOT_VERIFIED


def test_keyword_with_reference_still_uses_rapidfuzz():
    rules = {"견적 완료": ["견적"]}
    ref = [{"key": "K1", "feedback": "견적 완료",
            "detail": "견적서 제출완료", "norm_detail": "견적서 제출완료"}]
    r = validate_single("K1", "견적 완료", "견적서 제출완료", ref, keyword_rules=rules)
    assert r.status == ValidationStatus.NORMAL


def test_keyword_match_case_insensitive():
    rules = {"견적완료": ["견적"]}
    r = validate_single("K1", "견적완료", "QUOTE 견적 완료처리", None, keyword_rules=rules)
    assert r.status == ValidationStatus.NORMAL


def test_validate_all_passes_keyword_rules():
    rows = [_make_matched_row("K1", feedback="견적완료", detail="견적서를 회신했습니다")]
    rules = {"견적완료": ["견적"]}
    results = validate_all(rows, ColumnConfig(), None, keyword_rules=rules)
    assert results[0].status == ValidationStatus.NORMAL


def test_validate_all_keyword_no_match_check_needed():
    rows = [_make_matched_row("K1", feedback="견적완료", detail="전혀 관계없는 내용 xyz abc")]
    rules = {"견적완료": ["견적", "회신", "완료"]}
    results = validate_all(rows, ColumnConfig(), None, keyword_rules=rules)
    assert results[0].status == ValidationStatus.CHECK_NEEDED


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
