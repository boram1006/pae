"""
Feedback validation: rule-based + rapidfuzz similarity against reference data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process

from src.excel_io import read_sheet_data_with_duplicates
from src.matcher import MatchedRow
from src.utils import RefColumnConfig, normalize_text, safe_str


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class ValidationStatus(str, Enum):
    NORMAL = "정상"
    CHECK_NEEDED = "확인 필요"
    MISSING_SUSPECTED = "누락 의심"
    DETAIL_INSUFFICIENT = "상세내용 부족"
    NOT_ENTERED = "미입력"
    NOT_VERIFIED = "미검증"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    key: str
    current_feedback: str
    current_detail: str
    recommended_feedback: str = ""
    similar_ref_detail: str = ""
    similarity_score: float = 0.0
    status: ValidationStatus = ValidationStatus.NOT_VERIFIED
    note: str = ""


# ---------------------------------------------------------------------------
# Reference data loading
# ---------------------------------------------------------------------------

def load_reference_data(
    ref_path: str,
    ref_sheet: str,
    ref_col_config: RefColumnConfig,
) -> List[Dict[str, str]]:
    """
    Load (key, feedback, detail) triples from the answer-key file.
    Returns list of {"key": ..., "feedback": ..., "detail": ..., "norm_detail": ...}.
    Hidden columns/rows are included because we use openpyxl directly.
    """
    value_cols = [ref_col_config.partner_feedback, ref_col_config.detail]
    raw, _ = read_sheet_data_with_duplicates(
        ref_path, ref_sheet, ref_col_config.key, value_cols
    )

    records: List[Dict[str, str]] = []
    for key, occurrences in raw.items():
        for occ in occurrences:
            fb = safe_str(occ.get(ref_col_config.partner_feedback, ""))
            dt = safe_str(occ.get(ref_col_config.detail, ""))
            norm_dt = normalize_text(dt)
            if not norm_dt and not fb:
                continue
            records.append(
                {
                    "key": key,
                    "feedback": fb,
                    "detail": dt,
                    "norm_detail": norm_dt,
                }
            )
    return records


# ---------------------------------------------------------------------------
# Single-row validation
# ---------------------------------------------------------------------------

_DETAIL_MIN_LEN = 5   # characters threshold for "too short"
_SIM_THRESHOLD = 70   # similarity score threshold for "normal"
_SIM_LOW = 40         # below this → "not verified"


def validate_single(
    key: str,
    feedback: str,
    detail: str,
    reference_data: Optional[List[Dict[str, str]]],
    keyword_rules: Optional[Dict[str, List[str]]] = None,
) -> ValidationResult:
    """
    Classify feedback quality for one row.

    Rules
    -----
    1. Both empty       → NOT_ENTERED
    2. Detail empty, feedback exists → NORMAL (no detail to verify against)
    3. Detail exists, feedback empty → MISSING_SUSPECTED
    4. Detail too short              → DETAIL_INSUFFICIENT
    5. Keyword check (if rules defined for this feedback label):
       - Any expected keyword found in detail → keyword_matched = True
       - No keyword found → CHECK_NEEDED (exit early)
    6. No reference data:
       - keyword_matched → NORMAL
       - otherwise       → NOT_VERIFIED
    7. Find most similar ref detail via rapidfuzz
       - sim >= THRESHOLD & feedback matches ref → NORMAL
       - sim >= THRESHOLD & feedback differs    → CHECK_NEEDED
       - sim >= LOW & < THRESHOLD               → CHECK_NEEDED
       - sim < LOW                              → NOT_VERIFIED
    """
    norm_fb = normalize_text(feedback)
    norm_dt = normalize_text(detail)

    result = ValidationResult(
        key=key,
        current_feedback=feedback,
        current_detail=detail,
    )

    # Rule 1
    if not norm_fb and not norm_dt:
        result.status = ValidationStatus.NOT_ENTERED
        return result

    # Rule 3: detail exists but feedback empty
    if norm_dt and not norm_fb:
        result.status = ValidationStatus.MISSING_SUSPECTED
        result.note = "상세내용이 있는데 협력사 Feedback이 비어 있습니다."
        return result

    # Rule 2: feedback exists, no detail
    if norm_fb and not norm_dt:
        result.status = ValidationStatus.NORMAL
        result.note = "상세내용 없음 (Feedback만 존재)"
        return result

    # Rule 4: detail too short
    if len(norm_dt) < _DETAIL_MIN_LEN:
        result.status = ValidationStatus.DETAIL_INSUFFICIENT
        result.note = f"상세내용이 너무 짧습니다 ({len(norm_dt)}자)."
        return result

    # Rule 5: keyword-based check
    keyword_matched = False
    fb_key = feedback.strip() if feedback else ""
    if keyword_rules and fb_key:
        keywords = keyword_rules.get(fb_key, [])
        if keywords:
            norm_keywords = [normalize_text(kw) for kw in keywords]
            keyword_matched = any(kw and kw in norm_dt for kw in norm_keywords)
            if not keyword_matched:
                result.status = ValidationStatus.CHECK_NEEDED
                result.note = "상세내용에 피드백 관련 키워드가 없습니다."
                return result

    # Rule 6: no reference
    if not reference_data:
        if keyword_matched:
            result.status = ValidationStatus.NORMAL
            result.note = "키워드 기반 검증 통과"
        else:
            result.status = ValidationStatus.NOT_VERIFIED
            result.note = "정답지 없음 — 자동 판단 불가"
        return result

    # Rule 7: rapidfuzz similarity
    ref_details = [r["norm_detail"] for r in reference_data]
    match = process.extractOne(
        norm_dt,
        ref_details,
        scorer=fuzz.token_set_ratio,
    )

    if match is None:
        result.status = ValidationStatus.NOT_VERIFIED
        return result

    best_norm_detail, score, idx = match
    result.similarity_score = score
    best_ref = reference_data[idx]
    result.similar_ref_detail = best_ref["detail"]
    result.recommended_feedback = best_ref["feedback"]

    norm_rec_fb = normalize_text(best_ref["feedback"])

    if score >= _SIM_THRESHOLD:
        if norm_rec_fb == norm_fb or _feedback_similar(norm_rec_fb, norm_fb):
            result.status = ValidationStatus.NORMAL
        else:
            result.status = ValidationStatus.CHECK_NEEDED
            result.note = "유사 사례와 Feedback 내용이 다릅니다."
    elif score >= _SIM_LOW:
        result.status = ValidationStatus.CHECK_NEEDED
        result.note = f"유사 사례 있으나 유사도가 낮습니다 ({score:.0f}점)."
    else:
        result.status = ValidationStatus.NOT_VERIFIED
        result.note = f"유사 사례를 찾기 어렵습니다 (최고 유사도 {score:.0f}점)."

    return result


def _feedback_similar(a: str, b: str, threshold: int = 85) -> bool:
    """Check if two feedback strings are similar enough."""
    if not a or not b:
        return a == b
    return fuzz.token_set_ratio(a, b) >= threshold


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_all(
    matched_rows: List[MatchedRow],
    col_config,
    reference_data: Optional[List[Dict[str, str]]],
    keyword_rules: Optional[Dict[str, List[str]]] = None,
) -> List[ValidationResult]:
    """
    Validate all matched rows.
    col_config is a ColumnConfig with .partner_feedback and .detail fields.
    keyword_rules maps feedback label → expected keywords for keyword-based validation.
    """
    results: List[ValidationResult] = []
    fb_col = col_config.partner_feedback
    dt_col = col_config.detail

    for row in matched_rows:
        feedback = safe_str(row.values.get(fb_col, ""))
        detail = safe_str(row.values.get(dt_col, ""))
        vr = validate_single(row.key, feedback, detail, reference_data, keyword_rules)
        results.append(vr)

    return results
