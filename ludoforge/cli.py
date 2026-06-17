"""Ludoforge 통합 CLI 진입점.

서브커맨드로 백엔드를 호출한다:
  ludoforge check <path>   정적 모순 검사 (논리 백엔드/Z3)
  ludoforge bmc   <path>   전이 시스템 BMC (논리 백엔드/Z3·BMC)
  ludoforge prob  <path>   확률 검사 (확률 백엔드(PRISM))

공통 파이프라인: 로드 → 스키마·참조 검증 → 백엔드 번역·검사 → 한국어 리포트.
종료코드: 0=정합/정상, 1=모순/증명된 위반, 2=로드/검증/번역 오류, 3=unknown/미확인.
"""

from __future__ import annotations

from pathlib import Path

import typer

from core.loader import LoaderError, load_rules
from core.schema import SchemaError, validate
from logic.solver.bmc import format_bmc_report, run_bmc
from logic.solver.checks import check as run_checks
from logic.solver.report import format_report
from logic.solver.translator import TranslationError, translate
from prob.prism_gen import ProbError, generate
from prob.runner import format_prob_report, run_prism

app = typer.Typer(help="Ludoforge — 게임 기획 검증 툴킷 (논리·확률 백엔드)")

_EXIT_OK = 0
_EXIT_CONTRADICTION = 1
_EXIT_ERROR = 2
_EXIT_UNKNOWN = 3


@app.callback()
def main() -> None:
    """MMORPG 룰 정합성 검증기. 하위 명령으로 동작한다."""


@app.command()
def check(path: str = typer.Argument(..., help="검사할 .rule 파일 또는 디렉토리")) -> None:
    """룰셋의 정합성을 검사한다. 디렉토리면 모든 .rule을 병합해 함께 검사한다."""
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
        translation = translate(ruleset)
    except (LoaderError, SchemaError, TranslationError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    report = run_checks(ruleset, translation)
    rule_sources = {r.id: r.source for r in ruleset.rules if r.source}
    typer.echo(format_report(report, rule_sources))

    if report.has_contradiction:
        raise typer.Exit(_EXIT_CONTRADICTION)
    if report.unknowns:
        raise typer.Exit(_EXIT_UNKNOWN)
    raise typer.Exit(_EXIT_OK)


@app.command()
def bmc(
    path: str = typer.Argument(..., help="검사할 .rule 파일 또는 디렉토리"),
    k: int = typer.Option(10, "--k", help="BMC 언롤링 깊이 상한"),
) -> None:
    """전이 시스템(init/transitions/properties)을 깊이 k까지 BMC로 검사한다(D15).

    종료코드: 0=정상, 1=증명된 위반(불변식/데드락), 2=로드/검증 오류, 3=k 한계 미확인.
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

    if report.has_violation:
        raise typer.Exit(_EXIT_CONTRADICTION)
    if report.has_unconfirmed:
        raise typer.Exit(_EXIT_UNKNOWN)
    raise typer.Exit(_EXIT_OK)


@app.command()
def prob(
    path: str = typer.Argument(..., help="검사할 .rule 파일 또는 디렉토리"),
    show_model: bool = typer.Option(False, "--show-model", help="생성된 PRISM 모델도 출력"),
) -> None:
    """전이 시스템을 PRISM 확률 모델로 번역해 검사한다(확률 백엔드, D16).

    유한 상태가 전제다. `prism` 바이너리가 없으면 모델만 생성·출력한다(graceful).
    종료코드: 0=정상 · 2=로드/검증/번역 오류 · 3=PRISM 미설치(미계산).
    """
    try:
        ruleset = load_rules(Path(path))
        validate(ruleset)
    except (LoaderError, SchemaError) as e:
        typer.echo(f"검사를 진행할 수 없습니다:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    if not ruleset.transitions:
        typer.echo("전이(transitions)가 없어 확률 백엔드 대상이 아닙니다.", err=True)
        raise typer.Exit(_EXIT_ERROR)

    try:
        program = generate(ruleset)  # 유한 상태 게이트(D13) 포함
    except (SchemaError, ProbError) as e:
        typer.echo(f"PRISM 모델 생성 실패:\n{e}", err=True)
        raise typer.Exit(_EXIT_ERROR) from e

    report = run_prism(program)
    typer.echo(format_prob_report(report))
    if show_model and report.available:
        typer.echo("")
        typer.echo(program.model)

    if not report.available:
        raise typer.Exit(_EXIT_UNKNOWN)  # 미설치 — 계산 미수행
    raise typer.Exit(_EXIT_OK)


if __name__ == "__main__":
    app()
