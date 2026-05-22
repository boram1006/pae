"""
Common utilities: text normalization, Excel column validation, filename generation.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Column configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class ColumnConfig:
    """Mapping of logical field names to Excel column letters."""
    key: str = "A"
    encourage_yn: str = "CR"
    encourage_method: str = "CS"
    encourage_date: str = "CT"
    partner_feedback: str = "CU"
    detail: str = "CV"
    quote_reply_yn: str = "CW"
    reply_date: str = "CX"

    def value_columns(self) -> Dict[str, str]:
        """Return only the columns to be copied from alba → final (excl. key)."""
        return {
            "encourage_yn": self.encourage_yn,
            "encourage_method": self.encourage_method,
            "encourage_date": self.encourage_date,
            "partner_feedback": self.partner_feedback,
            "detail": self.detail,
            "quote_reply_yn": self.quote_reply_yn,
            "reply_date": self.reply_date,
        }

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> "ColumnConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RefColumnConfig:
    """Column mapping for the answer-key (reference) file."""
    key: str = "A"
    partner_feedback: str = "CU"
    detail: str = "CV"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> "RefColumnConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Excel column letter helpers
# ---------------------------------------------------------------------------

_VALID_COL_RE = re.compile(r"^[A-Z]{1,3}$")


def is_valid_excel_column(col: str) -> bool:
    """Return True if *col* is a valid Excel column letter (e.g. 'A', 'CR', 'XFD')."""
    if not col:
        return False
    col = col.strip().upper()
    if not _VALID_COL_RE.match(col):
        return False
    # openpyxl column_index_from_string raises ValueError for > 'XFD'
    try:
        from openpyxl.utils import column_index_from_string
        idx = column_index_from_string(col)
        return 1 <= idx <= 16384
    except Exception:
        return False


def col_letter_to_index(col: str) -> int:
    """Convert 'A' → 1, 'Z' → 26, 'AA' → 27, 'CR' → 96 …"""
    from openpyxl.utils import column_index_from_string
    return column_index_from_string(col.strip().upper())


def col_index_to_letter(idx: int) -> str:
    """Convert 1 → 'A', 96 → 'CR' …"""
    from openpyxl.utils import get_column_letter
    return get_column_letter(idx)


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def normalize_text(text) -> str:
    """Normalize text for comparison: strip, collapse whitespace, NFC."""
    if text is None:
        return ""
    s = str(text)
    # NaN check
    if s.lower() in ("nan", "none", "null"):
        return ""
    # Unicode normalization
    s = unicodedata.normalize("NFC", s)
    # Remove leading/trailing whitespace & collapse internal whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def safe_str(value) -> str:
    """Convert a cell value to str, returning '' for None/NaN."""
    if value is None:
        return ""
    s = str(value)
    if s.lower() in ("nan", "none", "null"):
        return ""
    return s.strip()


def is_empty(value) -> bool:
    return normalize_text(value) == ""


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------

def generate_output_filename(original_path: str) -> str:
    """
    Given '/path/to/report.xlsx', return
    '/path/to/report_completed_20260523_1530.xlsx'.
    """
    p = Path(original_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return str(p.parent / f"{p.stem}_completed_{ts}{p.suffix}")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_column_config(cfg: ColumnConfig) -> List[str]:
    """Return list of error messages, empty if all columns are valid."""
    errors: List[str] = []
    for field_name, col in cfg.to_dict().items():
        if not is_valid_excel_column(col):
            errors.append(f"'{field_name}' 의 컬럼값 '{col}' 이 유효하지 않습니다.")
    return errors


def validate_ref_column_config(cfg: RefColumnConfig) -> List[str]:
    errors: List[str] = []
    for field_name, col in cfg.to_dict().items():
        if not is_valid_excel_column(col):
            errors.append(f"정답지 '{field_name}' 의 컬럼값 '{col}' 이 유효하지 않습니다.")
    return errors
