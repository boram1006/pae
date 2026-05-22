"""
OpenAI-based feedback suggestion for partner detail text.
Returns (results_dict, error_message). error_message is "" on success.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

_BATCH_SIZE = 20


def suggest_feedback_batch(
    items: List[Tuple[str, str]],   # [(key, detail), ...]
    feedback_labels: List[str],
    api_key: str,
    model: str = "gpt-4o-mini",
) -> Tuple[Dict[str, str], str]:
    """
    Call OpenAI to classify each (key, detail) pair into one feedback label.
    Returns ({key: label}, error_str). error_str is "" on success.
    """
    if not api_key:
        return {}, "API 키 없음"
    if not items:
        return {}, "분류 대상 행 없음 (상세내용 비어있음)"
    if not feedback_labels:
        return {}, "피드백 레이블 목록 없음"

    try:
        from openai import OpenAI
    except ImportError:
        return {}, "openai 패키지 미설치 (pip install openai)"

    client = OpenAI(api_key=api_key)
    label_set = set(feedback_labels)
    labels_str = "\n".join(f"- {lb}" for lb in sorted(feedback_labels))

    system_prompt = (
        "너는 협력사 업무 피드백 분류 전문가다.\n"
        "상세내용을 읽고 아래 피드백 카테고리 중 가장 적합한 것을 하나만 선택해라.\n\n"
        "규칙:\n"
        "- 반드시 아래 목록에 있는 카테고리 이름을 그대로 사용해라\n"
        "- '번호: 카테고리명' 형식으로만 답해라 (설명 없이)\n"
        "- 견적 제출을 완료했으면 1-1, 기한을 연장하거나 나중에 제출하겠다고 하면 1-2\n"
        "- 견적이 어렵다/불가/거절이면 2-x 카테고리 중 이유에 맞게 선택\n"
        "- 아직 대기/확인 중이면 3-x 선택\n\n"
        f"카테고리 목록:\n{labels_str}"
    )

    results: Dict[str, str] = {}
    last_error = ""

    for batch_start in range(0, len(items), _BATCH_SIZE):
        batch = items[batch_start : batch_start + _BATCH_SIZE]
        numbered = "\n".join(f"{i+1}. {detail}" for i, (_, detail) in enumerate(batch))
        user_msg = (
            "다음 각 상세내용을 분류해라.\n\n"
            + numbered
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=len(batch) * 80,
            )
            answer = resp.choices[0].message.content or ""
            _parse_batch_response(answer, batch, label_set, feedback_labels, results)
        except Exception as exc:
            last_error = str(exc)

    return results, last_error


def _parse_batch_response(
    answer: str,
    batch: List[Tuple[str, str]],
    label_set: set,
    feedback_labels: List[str],
    results: Dict[str, str],
) -> None:
    """Parse LLM response lines into results dict."""
    for line in answer.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Match "N: text" or "N. text" (N is a positive integer)
        m = re.match(r'^(\d+)[:.]\s*(.+)$', line)
        if not m:
            continue

        idx = int(m.group(1)) - 1
        label_text = m.group(2).strip()

        if not (0 <= idx < len(batch)):
            continue

        key = batch[idx][0]

        # Exact match first
        if label_text in label_set:
            results[key] = label_text
            continue

        # Partial match: find the label that appears inside the response text
        for lb in feedback_labels:
            if lb in label_text:
                results[key] = lb
                break
