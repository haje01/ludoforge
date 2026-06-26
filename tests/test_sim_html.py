"""sim HTML 리포트(D19): 자체 완결형 HTML 시각화 + CLI --html 옵션 검증.

텍스트 리포트와 동일 내용을 시각화하되, 외부 의존성·JS 없이 결정론적으로 렌더되는지 본다.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from core.loader import load_rule_file
from ludoforge.cli import app
from sim.aggregate import (
    ConfigResult,
    DistributionResult,
    ProportionResult,
    SimReport,
    simulate,
)
from sim.html_report import render_sim_html

EXAMPLES = Path(__file__).parent.parent / "examples"


def _dungeon_report() -> SimReport:
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    return simulate(rs, samples=200, horizon=40, seed=0)


def test_html_has_self_contained_structure() -> None:
    html = render_sim_html(_dungeon_report())
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    assert "Monte Carlo 추정 결과 (sim)" in html
    # 정직성 라벨(증명 아님)이 머리에 박혀야 한다(D19).
    assert "증명 아님" in html
    # 외부 의존성·CDN·JS 없음(오프라인 자체 완결).
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html
    assert "cdn" not in html.lower()
    # 스타일·시각요소(SVG)가 인라인으로 들어 있다.
    assert "<style>" in html
    assert "<svg" in html


def test_html_renders_all_check_kinds() -> None:
    html = render_sim_html(_dungeon_report())
    assert "winnable" in html  # reachable
    assert "gold_nonneg" in html  # invariant
    assert "final_gold" in html  # distribution
    # no_deadlock(no_stuck)은 sim이 안 다룸 → 건너뜀 안내.
    assert "건너뜀" in html and "no_stuck" in html


def test_discrete_distribution_carries_histogram() -> None:
    # 정수 gold 분포는 distinct가 적어 히스토그램이 살아 있어야 한다(시각화용 pass-through).
    report = _dungeon_report()
    dists = [c for cfg in report.configs for c in cfg.checks if isinstance(c, DistributionResult)]
    assert dists, "distribution 체크가 없습니다"
    assert any(d.histogram is not None for d in dists)


def test_render_is_deterministic() -> None:
    # 같은 SimReport는 같은 HTML(비결정 요소 없음 — 타임스탬프 등 금지).
    report = _dungeon_report()
    assert render_sim_html(report) == render_sim_html(report)


def test_html_escapes_user_text() -> None:
    # desc 같은 사용자 텍스트는 HTML 이스케이프되어야 한다(주입 방지).
    malicious = ConfigResult(
        config={},
        n_samples=10,
        truncated=0,
        terminated=10,
        checks=(
            ProportionResult(
                check_id="x",
                kind="reachable",
                desc="<script>alert(1)</script>",
                event_label="도달",
                successes=5,
                n=10,
                p_hat=0.5,
                ci=(0.2, 0.8),
                rule_of_three=None,
                example=None,
            ),
        ),
    )
    report = SimReport(samples=10, horizon=5, seed=0, configs=(malicious,), skipped=())
    html = render_sim_html(report)
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_meanci_chart_for_overflow_distribution() -> None:
    # 히스토그램이 없는(연속/넓은) 분포도 평균±CI 막대(SVG)로 그려진다.
    cfg = ConfigResult(
        config={},
        n_samples=100,
        truncated=0,
        terminated=100,
        checks=(
            DistributionResult(
                check_id="cont",
                desc=None,
                n=100,
                mean=1.5,
                stddev=0.3,
                ci=(1.44, 1.56),
                vmin=0.8,
                vmax=2.4,
                percentiles=None,
                histogram=None,
            ),
        ),
    )
    report = SimReport(samples=100, horizon=10, seed=0, configs=(cfg,), skipped=())
    html = render_sim_html(report)
    assert "<svg" in html
    assert "백분위: (distinct 값이 많아 생략" in html


def test_cli_sim_writes_html(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    result = CliRunner().invoke(
        app,
        ["sim", str(EXAMPLES / "dungeon.lf"), "--samples", "100", "--html", str(out)],
    )
    assert result.exit_code == 0
    assert "HTML 리포트를 저장했습니다" in result.output
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert "Monte Carlo 추정 결과 (sim)" in content
