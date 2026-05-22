"""
OpenAI-based feedback suggestion for partner detail text.
Falls back silently if API key is missing, package not installed, or call fails.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


def suggest_feedback_batch(
    items: List[Tuple[str, str]],   # [(key, detail), ...]
    feedback_labels: List[str],
    api_key: str,
    model: str = "gpt-4o-mini",
) -> Dict[str, str]:
    """
    Call OpenAI to classify each (key, detail) pair into one feedback label.
    Returns {key: label}. Keys absent from result had no confident match.
    """
    if not api_key or not items or not feedback_labels:
        return {}

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai 패키지 미설치 — LLM 제안 건너뜀")
        return {}

    client = OpenAI(api_key=api_key)
    label_set = set(feedback_labels)
    labels_str = "\n".join(f"- {lb}" for lb in feedback_labels)
    system_prompt = (
        "너는 협력사 업무 피드백 분류 전문가다.\n"
        "상세내용을 읽고 아래 피드백 카테고리 중 가장 적합한 것을 하나만 선택해라.\n"
        "반드시 아래 목록에 있는 카테고리 이름만 정확히 답해라. 설명 없이 카테고리 이름만.\n\n"
        f"카테고리 목록:\n{labels_str}"
    )

    results: Dict[str, str] = {}

    for batch_start in range(0, len(items), _BATCH_SIZE):
        batch = items[batch_start : batch_start + _BATCH_SIZE]
        numbered = "\n".join(f"{i+1}. {detail}" for i, (_, detail) in enumerate(batch))
        user_msg = (
            "다음 각 상세내용에 대해 '번호: 카테고리명' 형식으로만 답해라.\n\n"
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
                max_tokens=len(batch) * 60,
            )
            answer = resp.choices[0].message.content or ""
            for line in answer.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                for sep in (":", "."):
                    if sep in line:
                        num_part, _, label_part = line.partition(sep)
                        num_part = num_part.strip()
                        label_part = label_part.strip()
                        if num_part.isdigit():
                            idx = int(num_part) - 1
                            if 0 <= idx < len(batch):
                                key = batch[idx][0]
                                if label_part in label_set:
                                    results[key] = label_part
                        break
        except Exception as exc:
            logger.error("OpenAI API 오류: %s", exc)

    return results
