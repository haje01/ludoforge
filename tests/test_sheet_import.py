"""웹 MVP: 시트(CSV) → `.lf` `table` 절 결정론 변환기 테스트 (D32 P3).

LLM이 개입하지 않는 경로다 — 스프레드시트 격자는 D18 표와 동형이므로 기계 변환한다.
변환 결과는 항상 text_loader가 파싱 가능한 `.lf` 조각이어야 한다(왕복 보증).
"""

from __future__ import annotations

import pytest

from core.text_loader import parse_rule_text
from web.sheet_import import SheetImportError, csv_to_table


def test_flat_two_column_csv() -> None:
    out = csv_to_table("reward", "goblin,2\ndragon,10\n")
    assert out == "table reward { goblin: 2, dragon: 10 }"


def test_flat_csv_with_header_row_skipped() -> None:
    # 2열 CSV의 첫 행 값이 숫자가 아니면 헤더로 보고 건너뛴다(시트 내보내기 관례).
    out = csv_to_table("reward", "monster,gold\ngoblin,2\ndragon,10\n")
    assert out == "table reward { goblin: 2, dragon: 10 }"


def test_grid_csv_to_nested_table() -> None:
    csv_text = ",fighter,rogue\ngoblin,0.92,0.72\ndragon,0.58,0.08\n"
    out = csv_to_table("win", csv_text)
    assert out == (
        "table win {\n"
        "    goblin: { fighter: 0.92, rogue: 0.72 }\n"
        "    dragon: { fighter: 0.58, rogue: 0.08 }\n"
        "}"
    )


def test_grid_first_header_cell_may_be_label() -> None:
    # 첫 셀이 "monster" 같은 라벨이어도 무시한다(격자 관례).
    csv_text = "monster,fighter,rogue\ngoblin,4,6\ndragon,7,11\n"
    out = csv_to_table("beat", csv_text)
    assert "goblin: { fighter: 4, rogue: 6 }" in out


def test_output_parses_as_lf_fragment() -> None:
    # 왕복 보증: 변환 결과가 실제 .lf 로더를 통과해야 한다.
    table = csv_to_table("win", ",fighter,rogue\ngoblin,0.92,0.72\n")
    src = "domain { monster: enum { goblin }  role: enum { fighter, rogue }  g: int 0..9 }\n"
    src += table + "\n"
    src += (
        "for mon in [goblin], cls in [fighter, rogue]:\n"
        '    transition "hit_${mon}_${cls}":\n'
        "        when role == cls and monster == mon\n"
        "        outcomes:\n"
        "            win[mon][cls] -> g = g + 1\n"
        "            rest -> g = g\n"
    )
    rs = parse_rule_text(src)
    assert rs.transitions[0].outcomes[0].weight == 0.92


def test_invalid_table_name_rejected() -> None:
    with pytest.raises(SheetImportError, match="표 이름"):
        csv_to_table("2bad", "a,1\n")


def test_invalid_key_rejected_with_position() -> None:
    with pytest.raises(SheetImportError, match="2행.*식별자"):
        csv_to_table("t", "ok,1\n큰돼지,2\n")


def test_non_numeric_value_rejected_with_position() -> None:
    with pytest.raises(SheetImportError, match="3행"):
        csv_to_table("t", "a,1\nb,2\nc,많이\n")


def test_empty_csv_rejected() -> None:
    with pytest.raises(SheetImportError, match="비어"):
        csv_to_table("t", "\n")


def test_ragged_grid_rejected() -> None:
    with pytest.raises(SheetImportError, match="열 수"):
        csv_to_table("t", ",a,b\nx,1\n")


def test_duplicate_key_rejected() -> None:
    with pytest.raises(SheetImportError, match="중복"):
        csv_to_table("t", "a,1\na,2\n")
