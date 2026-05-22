"""
FeedbackManager: load/save/manage the Feedback master JSON.
Feedback values are never hard-coded in logic; they live in config/feedback_master.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_DEFAULT_MASTER: dict = {
    "version": 1,
    "items": [
        {"id": "CALL_DONE",       "label": "통화완료",        "active": True,  "aliases": ["통화 완료", "연락 완료"],      "sort_order": 10},
        {"id": "NO_ANSWER",       "label": "부재",            "active": True,  "aliases": ["미연결", "전화 안받음", "부재중"], "sort_order": 20},
        {"id": "CALL_BACK",       "label": "재통화 요청",      "active": True,  "aliases": ["다시 전화", "재연락 필요"],     "sort_order": 30},
        {"id": "QUOTE_EXPECTED",  "label": "견적 회신 예정",   "active": True,  "aliases": ["회신 예정", "견적 예정"],      "sort_order": 40},
        {"id": "QUOTE_RECEIVED",  "label": "견적 회신 완료",   "active": True,  "aliases": ["회신 완료", "견적 받음"],      "sort_order": 50},
        {"id": "NEEDS_CHECK",     "label": "담당자 확인 필요", "active": True,  "aliases": ["확인 필요", "담당 확인"],      "sort_order": 60},
        {"id": "REJECTED",        "label": "거절",            "active": True,  "aliases": ["진행 불가", "불가"],          "sort_order": 70},
        {"id": "OTHER",           "label": "기타",            "active": True,  "aliases": [],                            "sort_order": 999},
    ],
}


class FeedbackManager:
    def __init__(self, config_path: str = "config/feedback_master.json"):
        self.config_path = Path(config_path)
        self.data = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        import copy
        return copy.deepcopy(_DEFAULT_MASTER)

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_all_items(self) -> List[Dict]:
        return sorted(self.data.get("items", []), key=lambda x: x.get("sort_order", 999))

    def get_active_labels(self) -> List[str]:
        return [
            i["label"]
            for i in self.get_all_items()
            if i.get("active", True)
        ]

    def _known_labels(self) -> set:
        known: set = set()
        for item in self.data.get("items", []):
            known.add(item.get("label", ""))
            for alias in item.get("aliases", []):
                known.add(alias)
        known.discard("")
        return known

    def is_known_label(self, label: str) -> bool:
        return label in self._known_labels()

    def get_unknown_labels(self, labels: List[str]) -> List[str]:
        """Return labels not present in the master (label or alias)."""
        known = self._known_labels()
        return sorted({l for l in labels if l and l not in known})

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def add_item(self, label: str, item_id: Optional[str] = None) -> None:
        if not label.strip():
            return
        if item_id is None:
            item_id = re.sub(r"\s+", "_", label.strip()).upper()
        max_order = max(
            (i.get("sort_order", 0) for i in self.data.get("items", [])),
            default=0,
        )
        self.data.setdefault("items", []).append(
            {
                "id": item_id,
                "label": label.strip(),
                "active": True,
                "aliases": [],
                "sort_order": max_order + 10,
            }
        )

    def deactivate_item(self, item_id: str) -> None:
        for item in self.data.get("items", []):
            if item.get("id") == item_id:
                item["active"] = False
                return

    def activate_item(self, item_id: str) -> None:
        for item in self.data.get("items", []):
            if item.get("id") == item_id:
                item["active"] = True
                return

    def toggle_active(self, item_id: str) -> None:
        for item in self.data.get("items", []):
            if item.get("id") == item_id:
                item["active"] = not item.get("active", True)
                return

    def update_label(self, item_id: str, new_label: str) -> None:
        for item in self.data.get("items", []):
            if item.get("id") == item_id:
                item["label"] = new_label.strip()
                return


import re  # noqa: E402 (used in add_item)
