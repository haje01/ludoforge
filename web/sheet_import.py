"""시트(CSV) → `.lf` `table` 절 결정론 변환기 (D32 P3).

스프레드시트 격자는 D18 표와 동형이므로 LLM 없이 기계 변환한다 — 오류 원천을 줄이고
수치 데이터가 번역을 거치며 왜곡될 여지를 없앤다. 지원 형태는 두 가지다:

- 2열(key,value): 평면 표  `table name { k1: v1, k2: v2 }`
  (첫 행의 값이 숫자가 아니면 헤더로 보고 건너뛴다 — 시트 내보내기 관례)
- 3열 이상(격자): 첫 행 = 열 키(첫 셀은 라벨이라 무시), 이후 행 = 행 키 + 값들
  → 중첩 표  `table name { row: { col: v, ... } ... }`

키/이름은 `.lf` 식별자(NAME)여야 하고 값은 수(int/float)여야 한다. 실패는 행 번호를
짚어 SheetImportError로 보고한다(§7 — 예외를 삼키지 않는다).
"""

from __future__ import annotations

import csv
import io
import re

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SheetImportError(Exception):
    """CSV → table 변환 실패. 메시지에 문제 위치(행)를 담는다."""


def csv_to_table(name: str, csv_text: str) -> str:
    """CSV 본문을 `.lf` `table` 절 텍스트로 변환한다(결정론 — LLM 불개입)."""
    if not _NAME.match(name):
        raise SheetImportError(f"표 이름이 .lf 식별자가 아닙니다: {name!r}")

    rows = [row for row in csv.reader(io.StringIO(csv_text)) if any(c.strip() for c in row)]
    if not rows:
        raise SheetImportError("CSV가 비어 있습니다.")

    width = len(rows[0])
    if width < 2:
        raise SheetImportError("CSV는 최소 2열(키, 값)이어야 합니다.")
    return _flat_table(name, rows) if width == 2 else _grid_table(name, rows)


def _flat_table(name: str, rows: list[list[str]]) -> str:
    start = 0
    # 첫 행 값이 숫자가 아니면 헤더 행으로 보고 건너뛴다(예: "monster,gold").
    if not _is_number(rows[0][1].strip()):
        if len(rows) == 1:
            # 헤더로 볼 여지도 없이 데이터가 없다 — 값 문제로 위치를 짚는다.
            raise SheetImportError(f"1행: 값 '{rows[0][1].strip()}'는 수가 아닙니다.")
        start = 1

    entries: list[str] = []
    seen: set[str] = set()
    for i, row in enumerate(rows[start:], start=start + 1):
        if len(row) != 2:
            raise SheetImportError(f"{i}행: 열 수가 2가 아닙니다 (현재 {len(row)}).")
        key = _parse_key(row[0], i)
        if key in seen:
            raise SheetImportError(f"{i}행: 키 '{key}' 중복.")
        seen.add(key)
        entries.append(f"{key}: {_parse_number(row[1], i)}")
    return f"table {name} {{ {', '.join(entries)} }}"


def _grid_table(name: str, rows: list[list[str]]) -> str:
    header, *body = rows
    if not body:
        raise SheetImportError("헤더뿐이고 데이터 행이 없습니다.")
    # 첫 셀은 라벨(비어 있거나 "monster" 등) — 열 키는 2번째 셀부터.
    col_keys = [_parse_key(c, 1) for c in header[1:]]
    if len(set(col_keys)) != len(col_keys):
        raise SheetImportError("1행: 열 키 중복.")

    lines: list[str] = [f"table {name} {{"]
    seen: set[str] = set()
    for i, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise SheetImportError(f"{i}행: 열 수가 헤더와 다릅니다 ({len(row)} != {len(header)}).")
        row_key = _parse_key(row[0], i)
        if row_key in seen:
            raise SheetImportError(f"{i}행: 행 키 '{row_key}' 중복.")
        seen.add(row_key)
        cells = ", ".join(
            f"{ck}: {_parse_number(v, i)}" for ck, v in zip(col_keys, row[1:], strict=True)
        )
        lines.append(f"    {row_key}: {{ {cells} }}")
    lines.append("}")
    return "\n".join(lines)


def _parse_key(cell: str, row_no: int) -> str:
    key = cell.strip()
    if not _NAME.match(key):
        raise SheetImportError(f"{row_no}행: 키 '{key}'는 .lf 식별자가 아닙니다.")
    return key


def _parse_number(cell: str, row_no: int) -> str:
    """수 값의 원문 표기를 보존해 반환한다(파싱 가능성만 검증 — 무손실)."""
    lexeme = cell.strip()
    if not _is_number(lexeme):
        raise SheetImportError(f"{row_no}행: 값 '{lexeme}'는 수가 아닙니다.")
    return lexeme


def _is_number(lexeme: str) -> bool:
    if not lexeme:
        return False
    try:
        float(lexeme)
    except ValueError:
        return False
    return True
