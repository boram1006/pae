"""
Matching logic: VLOOKUP-style key matching between final file and alba file.
Supports optional date-based filtering via the encourage_date column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from src.excel_io import (
    read_final_file_rows,
    read_sheet_data_with_duplicates,
)
from src.utils import ColumnConfig, dates_match, safe_str


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MatchedRow:
    """A row successfully matched by key (and passing the date filter if active)."""
    key: str
    final_row: int
    alba_row: int
    values: Dict[str, Any]          # col_letter → raw value from alba file
    original_feedback: str = ""     # value as-read from alba file
    final_feedback: str = ""        # value to write to final file (may be user-edited)
    feedback_changed: bool = False  # True when user modified final_feedback


@dataclass
class UnmatchedRow:
    """A row in the final file with no matching key in the alba file."""
    key: str
    final_row: int


@dataclass
class DuplicateInfo:
    """A key that appears more than once in the alba file."""
    key: str
    rows: List[int]   # all row numbers in alba file
    used_row: int     # row whose values were actually used (first occurrence)


@dataclass
class AlbaOnlyRow:
    """A key present in alba file but absent from the final file."""
    key: str
    alba_row: int
    values: Dict[str, Any]


@dataclass
class MatchResult:
    matched: List[MatchedRow] = field(default_factory=list)
    unmatched: List[UnmatchedRow] = field(default_factory=list)
    duplicates: List[DuplicateInfo] = field(default_factory=list)
    alba_only: List[AlbaOnlyRow] = field(default_factory=list)
    date_filtered: List[MatchedRow] = field(default_factory=list)  # key matched but excluded by date

    filter_date: Optional[date] = None
    date_filter_active: bool = False

    @property
    def total_final_keys(self) -> int:
        return len(self.matched) + len(self.unmatched) + len(self.date_filtered)

    @property
    def total_alba_keys(self) -> int:
        matched_keys = {r.key for r in self.matched} | {r.key for r in self.date_filtered}
        alba_only_keys = {r.key for r in self.alba_only}
        return len(matched_keys | alba_only_keys)


# ---------------------------------------------------------------------------
# Main matching function
# ---------------------------------------------------------------------------

def run_matching(
    final_path: str,
    final_sheet: str,
    alba_path: str,
    alba_sheet: str,
    col_config: ColumnConfig,
    filter_date: Optional[date] = None,
) -> MatchResult:
    """
    Perform VLOOKUP-style matching.

    If *filter_date* is provided, matched rows whose encourage_date column
    does NOT equal *filter_date* are moved to MatchResult.date_filtered and
    NOT included in MatchResult.matched (i.e. NOT written to the final file).
    """
    value_cols = list(col_config.value_columns().values())

    # --- final file keys (order preserved) ---
    final_rows: List[Tuple[int, str]] = read_final_file_rows(
        final_path, final_sheet, col_config.key
    )

    # --- alba file data (all occurrences) ---
    alba_data, _ = read_sheet_data_with_duplicates(
        alba_path, alba_sheet, col_config.key, value_cols
    )

    result = MatchResult(filter_date=filter_date, date_filter_active=filter_date is not None)
    final_key_set: set = set()

    for final_row_num, key in final_rows:
        final_key_set.add(key)

        if key not in alba_data:
            result.unmatched.append(UnmatchedRow(key=key, final_row=final_row_num))
            continue

        occurrences = alba_data[key]
        first = occurrences[0]
        values = {k: v for k, v in first.items() if k != "_row"}
        alba_row_num = first["_row"]

        fb_col = col_config.partner_feedback
        fb_val = safe_str(first.get(fb_col, ""))

        matched_row = MatchedRow(
            key=key,
            final_row=final_row_num,
            alba_row=alba_row_num,
            values=values,
            original_feedback=fb_val,
            final_feedback=fb_val,
        )

        # Duplicate detection
        if len(occurrences) > 1:
            result.duplicates.append(
                DuplicateInfo(
                    key=key,
                    rows=[o["_row"] for o in occurrences],
                    used_row=alba_row_num,
                )
            )

        # Date filter
        if filter_date is not None:
            date_col = col_config.encourage_date
            date_val = values.get(date_col)
            if dates_match(date_val, filter_date):
                result.matched.append(matched_row)
            else:
                result.date_filtered.append(matched_row)
        else:
            result.matched.append(matched_row)

    # --- alba-only keys ---
    for key, occurrences in alba_data.items():
        if key not in final_key_set:
            first = occurrences[0]
            values = {k: v for k, v in first.items() if k != "_row"}
            result.alba_only.append(
                AlbaOnlyRow(key=key, alba_row=first["_row"], values=values)
            )

    return result


# ---------------------------------------------------------------------------
# Build change list for excel_io.save_with_changes
# ---------------------------------------------------------------------------

def build_changes(
    match_result: MatchResult,
    col_config: ColumnConfig,
) -> List[Dict]:
    """
    Convert matched rows into the list of cell changes for save_with_changes().

    Uses final_feedback (not original_feedback) for the partner_feedback column
    so that user edits made in the UI are preserved in the saved file.
    """
    changes: List[Dict] = []
    value_col_map = col_config.value_columns()  # logical_name → col_letter
    fb_col = col_config.partner_feedback

    for matched in match_result.matched:
        for logical_name, col_letter in value_col_map.items():
            if col_letter == fb_col:
                value = matched.final_feedback
            else:
                value = matched.values.get(col_letter)
            changes.append(
                {"row": matched.final_row, "col_letter": col_letter, "value": value}
            )

    return changes
