"""BMC HTML 리포트(D15): 자체 완결형 HTML 시각화 + CLI --html 옵션 검증.

텍스트 리포트와 동일 내용을 시각화하되, 외부 의존성·JS 없이 결정론적으로 렌더되는지,
반례·도달 경로(trace)와 상태 배지가 들어가는지 본다. 상태 카드가 모든 변수값을 인라인으로
보여주므로 호버 툴팁은 두지 않는다(sim HTML과 달리 중복일 뿐).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from core.loader import load_rule_file
from logic.solver.bmc import BmcReport, PropertyResult, Step, Trace, run_bmc
from logic.solver.html_report import render_bmc_html
from ludoforge.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def test_html_has_self_contained_structure() -> None:
    report = run_bmc(load_rule_file(EXAMPLES / "dungeon.lf"), k=14)
    html = render_bmc_html(report)
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    assert "BMC 검사 결과" in html
    assert "k=14" in html
    # 유계(k-bound) 정직성 라벨이 머리에 박혀야 한다(D15).
    assert "유계" in html
    # 외부 의존성·CDN 없음(오프라인 자체 완결) — 인라인 JS는 허용하되 원격 스크립트는 금지.
    assert "<script src" not in html
    assert "http://" not in html and "https://" not in html
    assert "<style>" in html
    # 호버 툴팁·JS는 두지 않는다 — 상태 카드가 값을 인라인으로 다 펼친다(중복 제거).
    assert "<script>" not in html
    assert "data-tip" not in html


def test_trace_steps_show_inline_values_without_tooltip() -> None:
    # 경로의 각 상태 카드는 모든 변수값을 칩으로 인라인 노출하며 호버 툴팁은 없다.
    html = render_bmc_html(run_bmc(load_rule_file(EXAMPLES / "dungeon.lf"), k=14))
    assert 'class="step">' in html  # data-tip 없는 평범한 상태 카드
    assert "data-tip" not in html
    assert '<span class="svar">room=hall</span>' in html  # 변수값이 카드에 직접 보인다


def test_html_renders_reachable_trace() -> None:
    report = run_bmc(load_rule_file(EXAMPLES / "dungeon.lf"), k=14)
    html = render_bmc_html(report)
    assert "winnable" in html  # reachable 속성
    assert 'class="badge ok"' in html  # 도달 가능 → 녹색 배지
    assert 'class="trace"' in html and 'class="step"' in html  # 경로 시각화
    assert "enter_l1" in html  # 전이 action 라벨


def test_html_marks_violation_and_deadlock() -> None:
    # 불변식 위반·데드락은 bad 배지로 표시되고 반례 경로가 들어간다.
    inv = render_bmc_html(run_bmc(load_rule_file(FIXTURES / "bmc_counter.rule"), k=10))
    assert 'class="badge bad"' in inv  # never4 위반
    dead = render_bmc_html(run_bmc(load_rule_file(FIXTURES / "bmc_deadlock.rule"), k=10))
    assert 'class="badge bad"' in dead
    assert 'class="trace"' in dead


def test_trace_highlights_changed_vars() -> None:
    # 직전 스텝 대비 바뀐 변수만 강조(changed) — 첫 스텝엔 강조가 없다.
    trace = Trace(
        steps=(
            Step({"x": "0", "y": "9"}),
            Step({"x": "1", "y": "9"}),  # x만 변함
        ),
        actions=("inc_x",),
    )
    report = BmcReport(
        k=5,
        results=(
            PropertyResult(
                prop_id="p", kind="reachable", desc=None, status="reachable", depth=1, trace=trace
            ),
        ),
        skipped_other=(),
    )
    html = render_bmc_html(report)
    assert '<span class="svar changed">x=1</span>' in html  # 바뀐 변수 강조
    assert '<span class="svar">y=9</span>' in html  # 안 바뀐 변수는 평범
    assert "inc_x" in html


def test_render_is_deterministic() -> None:
    report = run_bmc(load_rule_file(EXAMPLES / "dungeon.lf"), k=12)
    assert render_bmc_html(report) == render_bmc_html(report)


def test_html_escapes_user_text() -> None:
    report = BmcReport(
        k=3,
        results=(
            PropertyResult(
                prop_id="x",
                kind="reachable",
                desc="<script>alert(1)</script>",
                status="reachable",
                depth=0,
                trace=None,
            ),
        ),
        skipped_other=(),
    )
    html = render_bmc_html(report)
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_cli_bmc_writes_html(tmp_path: Path) -> None:
    out = tmp_path / "bmc.html"
    result = CliRunner().invoke(
        app, ["bmc", str(EXAMPLES / "dungeon.lf"), "--k", "14", "--html", str(out)]
    )
    assert result.exit_code == 0
    assert "HTML 리포트를 저장했습니다" in result.output
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert "BMC 검사 결과" in content
