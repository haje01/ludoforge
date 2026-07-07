"""Ludoforge 통합 CLI 진입점.

서브커맨드로 백엔드를 호출한다:
  ludoforge check <path>   정적 모순 검사 (논리 백엔드/Z3)
  ludoforge bmc   <path>   전이 시스템 BMC (논리 백엔드/Z3·BMC)
  ludoforge sim   <path>   Monte Carlo 추정 (sim 백엔드, 주 정량 경로/D19)
  ludoforge doc   <path>   규칙서 생성 (.lf → HTML/Markdown, D29 — 검증 아님·문서 뷰)

(PRISM은 D23으로 사용자 표면에서 내려 테스트 전용 교차검증 오라클로만 남는다.)

공통 파이프라인: 로드 → 스키마·참조 검증 → 백엔드 번역·검사 → 한국어 리포트.
종료코드: 0=정합/정상, 1=모순/증명된 위반, 2=로드/검증/번역 오류, 3=unknown/미확인.
"""

from __future__ import annotations

from pathlib import Path

import typer

from core.docgen import render_doc_html, render_doc_markdown
from core.loader import LoaderError, load_rule_file, load_rules
from core.schema import SchemaError, validate
from core.text_loader import TextLoaderError
from logic.solver.bmc import format_bmc_report, run_bmc
from logic.solver.checks import check as run_checks
from logic.solver.html_report import render_bmc_html
from logic.solver.report import format_report
from logic.solver.translator import TranslationError, translate
from sim.engine import SimError
from sim.html_report import render_sim_html
from sim.report import format_sim_report
from sim.runner import run_sim

app = typer.Typer(help="Ludoforge — 게임 기획 검증 툴킷 (논리·sim 백엔드)")

_EXIT_OK = 0
_EXIT_CONTRADICTION = 1
_EXIT_ERROR = 2
_EXIT_UNKNOWN = 3


@app.callback()
def main() -> None:
    """MMORPG 룰 정합성 검증기. 하위 명령으로 동작한다."""


@app.command()
def check(path: str = typer.Argument(..., help="검사할 .lf 파일 또는 디렉토리")) -> None:
    """룰셋의 정합성을 검사한다. 디렉토리면 모든 .lf를 병합해 함께 검사한다."""
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
        translation = translate(ruleset)
    except (LoaderError, SchemaError, TranslationError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    report = run_checks(ruleset, translation)
    rule_sources = {c.id: c.source for c in ruleset.constraints if c.source}
    typer.echo(format_report(report, rule_sources))

    if report.has_contradiction:
        raise typer.Exit(_EXIT_CONTRADICTION)
    if report.unknowns:
        raise typer.Exit(_EXIT_UNKNOWN)
    raise typer.Exit(_EXIT_OK)


@app.command()
def bmc(
    path: str = typer.Argument(..., help="검사할 .lf 파일 또는 디렉토리"),
    k: int = typer.Option(10, "--k", help="BMC 언롤링 깊이 상한"),
    html_out: str | None = typer.Option(
        None, "--html", help="결과(경로·반례 포함)를 시각화한 HTML 파일로 저장할 경로"
    ),
) -> None:
    """전이 시스템(init/transitions/checks)을 깊이 k까지 BMC로 검사한다(D15).

    base가 k까지 통과한 속성은 k-귀납(D25)으로 무한 지평 증명을 시도한다. 종료코드:
    0=정상(증명 포함), 1=증명된 위반(불변식/데드락/도달 불가 확정), 2=로드/검증 오류,
    3=k 한계 미확인.
    """
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
    except (LoaderError, SchemaError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    if not ruleset.transitions:
        typer.echo(
            "전이(transitions)가 없어 BMC 대상이 아닙니다. 정적 검사는 'ludoforge check'를 쓰세요.",
            err=True,
        )
        raise typer.Exit(_EXIT_ERROR)

    try:
        report = run_bmc(ruleset, k)
    except TranslationError as e:
        typer.echo(f"번역 오류:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    typer.echo(format_bmc_report(report))
    if html_out is not None:
        out_path = Path(html_out)
        out_path.write_text(render_bmc_html(report), encoding="utf-8")
        typer.echo(f"HTML 리포트를 저장했습니다: {out_path}")

    if report.has_violation:
        raise typer.Exit(_EXIT_CONTRADICTION)
    if report.has_unconfirmed:
        raise typer.Exit(_EXIT_UNKNOWN)
    raise typer.Exit(_EXIT_OK)


@app.command()
def sim(
    path: str = typer.Argument(..., help="검사할 .lf 파일 또는 디렉토리"),
    samples: int = typer.Option(10000, "--samples", "-n", help="설정당 표집 횟수"),
    horizon: int = typer.Option(100, "--horizon", "-H", help="run당 최대 스텝(지평)"),
    seed: int = typer.Option(0, "--seed", "-s", help="난수 시드(재현성)"),
    workers: int = typer.Option(1, "--workers", "-w", help="병렬 워커 수(결과는 워커 수 무관)"),
    html_out: str | None = typer.Option(
        None, "--html", help="결과를 시각화한 HTML 파일로 저장할 경로(예: report.html)"
    ),
) -> None:
    """전이 시스템을 Monte Carlo로 표집해 정량 속성을 *추정*한다(sim 백엔드, D19).

    증명이 아니라 추정이다 — 승률·기대 길이·분포를 신뢰구간과 함께 보고한다. DTMC만
    지원한다(비결정 모델은 BMC/PRISM). 종료코드: 0=정상 · 2=로드/검증/sim 오류.
    """
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
    except (LoaderError, SchemaError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    if not ruleset.transitions:
        typer.echo("전이(transitions)가 없어 sim 대상이 아닙니다.", err=True)
        raise typer.Exit(_EXIT_ERROR)

    try:
        report = run_sim(ruleset, samples=samples, horizon=horizon, seed=seed, workers=workers)
    except SimError as e:
        typer.echo(f"sim 실행 실패:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    typer.echo(format_sim_report(report))
    if html_out is not None:
        out_path = Path(html_out)
        out_path.write_text(render_sim_html(report), encoding="utf-8")
        typer.echo(f"HTML 리포트를 저장했습니다: {out_path}")
    raise typer.Exit(_EXIT_OK)


@app.command()
def doc(
    path: str = typer.Argument(..., help="규칙서를 만들 .lf 파일"),
    out: str | None = typer.Option(
        None, "--out", "-o", help="출력 경로(기본: <입력>.doc.html 또는 .doc.md)"
    ),
    md: bool = typer.Option(False, "--md", help="HTML 대신 Markdown으로 출력"),
) -> None:
    """`.lf`에서 사람이 읽는 게임 규칙서를 생성한다(D29 — 단방향 파생 뷰).

    검증이 아니라 문서화다. 생성 전에 로드·스키마·`[[이름]]` 참조 게이트를 통과해야
    한다(깨진 모델의 규칙서는 만들지 않는다). 종료코드: 0=생성 · 2=로드/검증 오류.
    """
    in_path = Path(path)
    if in_path.suffix != ".lf":
        typer.echo(
            "규칙서 생성은 자체 문법(.lf) 전용입니다(D32 — YAML 프론트엔드 제거).",
            err=True,
        )
        raise typer.Exit(_EXIT_ERROR)
    try:
        ruleset = load_rule_file(in_path)  # .lf 로드 = 파싱 + [[이름]] 참조 게이트(D29)
        validate(ruleset)
        src = in_path.read_text(encoding="utf-8")
        title = f"{in_path.stem} 규칙서"
        rendered = (
            render_doc_markdown(src, title, source=in_path.name)
            if md
            else render_doc_html(src, title, source=in_path.name)
        )
    except (OSError, LoaderError, SchemaError, TextLoaderError) as e:
        typer.echo(f"규칙서를 생성할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    out_path = Path(out) if out else in_path.with_suffix(".doc.md" if md else ".doc.html")
    out_path.write_text(rendered, encoding="utf-8")
    typer.echo(f"규칙서를 생성했습니다: {out_path}")
    raise typer.Exit(_EXIT_OK)


if __name__ == "__main__":
    app()
