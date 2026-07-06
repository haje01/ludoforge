"""규칙서 생성기(docgen, D29 12차 P2) 테스트.

HTML 스냅샷 대신 **구조 단언** 위주로 고정한다(PLAN 12차 — 취약성 회피): 절 구분·용어집·
표 행렬·접힌 템플릿·[[이름]] 링크 해소·check 모음·자체 완결성·결정론.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from core.docgen import build_doc_model, render_doc_html, render_doc_markdown
from ludoforge.cli import app

runner = CliRunner()
_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

_SRC = """
section "경제 규칙"

domain {
    gold: int 0..30 desc "보유 보물"
    room: enum { hall, l1 }
}

table win desc "격파 확률" {
    goblin: { fighter: 0.92, rogue: 0.72 }
    dragon: { fighter: 0.58, rogue: 0.08 }
}

init: gold == 0 and room == hall

constraint cap:
    author "planner_A"
    desc "보물은 [[gold]] 상한을 따른다"
    note "상한을 넘는 보상은 버려진다(포화)."
    ref "룰북 p.12"
    tag economy
    then gold <= 30

section "전투 규칙"

for mon in [goblin, dragon]:
    transition "fight_${mon}":
        note "몬스터 ${mon} 전투 — [[win]] 표 참조. 승리 값 [[hall]]은 enum."
        when room == l1
        outcomes:
            0.7 -> { gold = gold + 1; room = hall }
            0.3 -> room = hall

check winnable
    desc "[[gold]]를 채울 수 있어야 한다"
    reachable: gold >= 10
check no_stuck no_deadlock
"""


def test_model_sections_and_checks_split() -> None:
    model = build_doc_model(_SRC, "테스트 규칙서")
    assert [s.title for s in model.sections] == ["경제 규칙", "전투 규칙"]
    # check는 본문에서 빠져 맨 끝 모음으로 — 본문 절에는 check가 없다.
    assert [c.id for c in model.checks] == ["winnable", "no_stuck"]
    assert {"gold", "room", "win", "cap", "fight_${mon}"} <= set(model.anchors)


def test_template_stays_folded() -> None:
    """for 템플릿은 접힌 형태 그대로 — 펼친 항목(fight_goblin 등)이 나오면 안 된다(D29)."""
    md = render_doc_markdown(_SRC, "테스트 규칙서")
    assert "fight_${mon}" in md
    assert "fight_goblin" not in md and "fight_dragon" not in md
    assert "mon ∈ {goblin, dragon}" in md


def test_markdown_structure() -> None:
    md = render_doc_markdown(_SRC, "테스트 규칙서")
    assert md.startswith("# 테스트 규칙서")
    # 목차·용어집·표 행렬·메타·note 인용·검증 절
    assert "## 목차" in md and "- 경제 규칙" in md
    assert "| `gold` | `int 0..30` | 보유 보물 |" in md
    assert "| **goblin** | 0.92 | 0.72 |" in md
    assert "작성 planner_A · 출처 룰북 p.12" in md
    assert "> 상한을 넘는 보상은 버려진다(포화)." in md
    assert "## 검증·추정 성질" in md
    assert "불변" not in md.split("## 검증·추정 성질")[0].split("### cap")[1].split("###")[0]
    # 가드/효과는 키워드 없이 식만
    assert "- **언제**: `room == l1`" in md
    assert "`0.7` → `{ gold = gold + 1; room = hall }`" in md


def test_html_crossref_links_and_terms() -> None:
    """[[앵커 있는 이름]]은 링크로, 없는 이름(enum 값)은 용어 스타일로 렌더한다."""
    html_out = render_doc_html(_SRC, "테스트 규칙서")
    assert '<a class="xref" href="#def-gold">gold</a>' in html_out
    assert '<a class="xref" href="#def-win">win</a>' in html_out
    assert '<span class="term">hall</span>' in html_out  # enum 값 — 앵커 없음
    assert 'id="def-gold"' in html_out and 'id="def-win"' in html_out and 'id="def-cap"' in html_out


def test_html_self_contained_and_deterministic() -> None:
    html_out = render_doc_html(_SRC, "테스트 규칙서")
    # 외부 의존 없음(CSP·오프라인) — 외부 스크립트/스타일/이미지 로드가 없다.
    assert "<script src" not in html_out and "<link" not in html_out and "<img" not in html_out
    assert html_out == render_doc_html(_SRC, "테스트 규칙서")  # 결정론


def test_dungeon_example_renders() -> None:
    """실전 예제(dungeon.lf)가 규칙서로 렌더된다 — 접힌 8-way 전투 템플릿 포함."""
    src = (_EXAMPLES / "dungeon.lf").read_text(encoding="utf-8")
    md = render_doc_markdown(src, "dungeon 규칙서")
    assert "fight_${mon}_${cls}" in md and "fight_goblin_fighter" not in md
    assert "## 검증·추정 성질" in md and "no_stuck" in md
    # chance/rest(D30)는 룰북 원형 그대로 렌더 — 규칙서에 주사위 판정이 노출된다.
    assert "chance(2d6 >= beat[mon][cls])" in md and "`rest`" in md


def test_cli_doc_writes_html(tmp_path: Path) -> None:
    src_file = tmp_path / "mini.lf"
    src_file.write_text(_SRC, encoding="utf-8")
    out = tmp_path / "mini.html"
    result = runner.invoke(app, ["doc", str(src_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists() and "<!DOCTYPE html>" in out.read_text(encoding="utf-8")


def test_cli_doc_default_output_and_md(tmp_path: Path) -> None:
    src_file = tmp_path / "mini.lf"
    src_file.write_text(_SRC, encoding="utf-8")
    result = runner.invoke(app, ["doc", str(src_file), "--md"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "mini.doc.md").exists()


def test_cli_doc_rejects_yaml_and_broken_refs(tmp_path: Path) -> None:
    yaml_file = tmp_path / "old.rule"
    yaml_file.write_text("domain:\n  variables:\n    x: { type: int }\n", encoding="utf-8")
    result = runner.invoke(app, ["doc", str(yaml_file)])
    assert result.exit_code == 2

    broken = tmp_path / "broken.lf"
    broken.write_text(
        'domain { gold: int 0..30 desc "[[nope]]" }\nconstraint c: then gold <= 30\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["doc", str(broken)])
    assert result.exit_code == 2  # 참조 게이트 실패 — 깨진 모델의 규칙서는 안 만든다
