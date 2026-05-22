"""
Matching logic: VLOOKUP-style key matching between final file and alba file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.excel_io import (
    read_final_file_rows,
    read_sheet_data_with_duplicates,
)
from src.utils import ColumnConfig, safe_str


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MatchedRow:
    """A row that was successfully matched."""
    key: str
    final_row: int
    alba_row: int
    values: Dict[str, Any]  # col_letter → value from alba file


@dataclass
class UnmatchedRow:
    """A row in the final file that had no matching key in the alba file."""
    key: str
    final_row: int


@dataclass
class DuplicateInfo:
    """A key that appeared more than once in the alba file."""
    key: str
    rows: List[int]  # All row numbers where the key appears in alba file
    used_row: int    # The row whose values were actually used (first occurrence)


@dataclass
class AlbaOnlyRow:
    """A key present in the alba file but not in the final file."""
    key: str
    alba_row: int
    values: Dict[str, Any]


@dataclass
class MatchResult:
    matched: List[MatchedRow] = field(default_factory=list)
    unmatched: List[UnmatchedRow] = field(default_factory=list)
    duplicates: List[DuplicateInfo] = field(default_factory=list)
    alba_only: List[AlbaOnlyRow] = field(default_factory=list)

    # Summary counts
    @property
    def total_final_keys(self) -> int:
        return len(self.matched) + len(self.unmatched)

    @property
    def total_alba_keys(self) -> int:
        matched_keys = {r.key for r in self.matched}
        alba_only_keys = {r.key for r in self.alba_only}
        return len(matched_keys) + len(alba_only_keys)


# ---------------------------------------------------------------------------
# Main matching function
# ---------------------------------------------------------------------------

def run_matching(
    final_path: str,
    final_sheet: str,
    alba_path: str,
    alba_sheet: str,
    col_config: ColumnConfig,
) -> MatchResult:
    """
    Perform VLOOKUP-style matching between final file and alba file.

    Strategy
    --------
    1. Read all (row, key) pairs from final file.
    2. Read all rows from alba file (with duplicate detection).
    3. For each final-file key:
       - If found in alba: record as matched (use first occurrence if duplicate).
       - If not found: record as unmatched.
    4. Keys in alba but not in final → alba_only.
    5. Keys with multiple rows in alba → duplicates.
    """
    value_cols = list(col_config.value_columns().values())

    # --- Step 1: final file keys (preserves order) ---
    final_rows: List[Tuple[int, str]] = read_final_file_rows(
        final_path, final_sheet, col_config.key
    )

    # --- Step 2: alba file data ---
    alba_data, _ = read_sheet_data_with_duplicates(
        alba_path, alba_sheet, col_config.key, value_cols
    )

    # --- Step 3 & 4 ---
    result = MatchResult()
    final_key_set: set = set()

    for final_row_num, key in final_rows:
        final_key_set.add(key)

        if key not in alba_data:
            result.unmatched.append(UnmatchedRow(key=key, final_row=final_row_num))
            continue

        occurrences = alba_data[key]

        # Use first occurrence
        first = occurrences[0]
        values = {k: v for k, v in first.items() if k != "_row"}
        alba_row_num = first["_row"]

        result.matched.append(
            MatchedRow(
                key=key,
                final_row=final_row_num,
                alba_row=alba_row_num,
                values=values,
            )
        )

        # Record duplicates
        if len(occurrences) > 1:
            result.duplicates.append(
                DuplicateInfo(
                    key=key,
                    rows=[o["_row"] for o in occurrences],
                    used_row=alba_row_num,
                )
            )

    # --- Step 5: alba-only keys ---
    for key, occurrences in alba_data.items():
        if key not in final_key_set:
            first = occurrences[0]
            values = {k: v for k, v in first.items() if k != "_row"}
            result.alba_only.append(
                AlbaOnlyRow(
                    key=key,
                    alba_row=first["_row"],
                    values=values,
                )
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
    Each entry: {"row": int, "col_letter": str, "value": any}
    """
    changes: List[Dict] = []
    value_col_map = col_config.value_columns()  # logical_name → col_letter

    for matched in match_result.matched:
        for logical_name, col_letter in value_col_map.items():
            value = matched.values.get(col_letter)
            changes.append(
                {"row": matched.final_row, "col_letter": col_letter, "value": value}
            )

    return changes
