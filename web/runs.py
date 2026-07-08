"""백엔드 실행(check/bmc/sim)의 함수형 코어 — CLI(`ludoforge/cli.py`)와 같은 파이프라인.

`.lf` 텍스트를 받아 로드 → 스키마 → 백엔드 → 리포트(텍스트 + 있으면 자체 완결 HTML)로
변환한다. 종료코드 의미는 CLI와 동일: 0=정합/정상, 1=모순/증명된 위반, 2=오류, 3=unknown.
IO가 없어 잡 스레드·테스트가 그대로 부른다(함수형 코어/명령형 셸, §7).
"""

from __future__ import annotations

from typing import Any

from core.ir import RuleSet
from core.schema import SchemaError, validate
from core.text_loader import TextLoaderError, parse_rule_text
from logic.solver.bmc import format_bmc_report, run_bmc
from logic.solver.checks import check as run_checks
from logic.solver.html_report import render_bmc_html
from logic.solver.report import format_report
from logic.solver.translator import TranslationError, translate
from sim.engine import SimError
from sim.html_report import render_sim_html
from sim.report import format_sim_report
from sim.runner import run_sim

_SOURCE = "web-input.lf"


def _load(lf_text: str) -> RuleSet | dict[str, Any]:
    """공통 게이트 — 실패 시 exit=2 결과 dict를 돌려준다(예외를 삼키지 않되 형태는 통일)."""
    try:
        rs = parse_rule_text(lf_text, source=_SOURCE)
        validate(rs)
    except (TextLoaderError, SchemaError) as e:
        return {"exit": 2, "text": f"검사를 진행할 수 없습니다:\n{e}", "html": None}
    return rs


def run_check_text(lf_text: str) -> dict[str, Any]:
    """정적 모순 검사 — `ludoforge check`와 동일 파이프라인."""
    rs = _load(lf_text)
    if isinstance(rs, dict):
        return rs
    try:
        translation = translate(rs)
    except TranslationError as e:
        return {"exit": 2, "text": f"번역 오류:\n{e}", "html": None}
    report = run_checks(rs, translation)
    sources = {c.id: c.source for c in rs.constraints if c.source}
    exit_code = 1 if report.has_contradiction else (3 if report.unknowns else 0)
    return {"exit": exit_code, "text": format_report(report, sources), "html": None}


def run_bmc_text(lf_text: str, k: int) -> dict[str, Any]:
    """전이 시스템 BMC — `ludoforge bmc`와 동일 파이프라인."""
    rs = _load(lf_text)
    if isinstance(rs, dict):
        return rs
    if not rs.transitions:
        return {
            "exit": 2,
            "text": "전이(transitions)가 없어 BMC 대상이 아닙니다. 정적 검사(check)를 쓰세요.",
            "html": None,
        }
    try:
        report = run_bmc(rs, k)
    except TranslationError as e:
        return {"exit": 2, "text": f"번역 오류:\n{e}", "html": None}
    exit_code = 1 if report.has_violation else (3 if report.has_unconfirmed else 0)
    return {
        "exit": exit_code,
        "text": format_bmc_report(report),
        "html": render_bmc_html(report),
        "summary": _bmc_summary(report.counts()),
    }


def _bmc_summary(counts: dict[str, int]) -> str:
    """개수 요약 라벨 — 0인 항목은 생략(예: '증명 4 · 미확인 1 · 건너뜀 2'). 요약 라벨이
    종료코드 한 글자보다 많은 맥락을 준다(k 한계로 인한 정상적 미확인을 덜 놀랍게)."""
    order = [
        ("proven", "증명"),
        ("violated", "위반"),
        ("unconfirmed", "미확인"),
        ("skipped", "건너뜀"),
    ]
    return " · ".join(f"{label} {counts[key]}" for key, label in order if counts[key])


def run_sim_text(
    lf_text: str, samples: int, horizon: int, seed: int, workers: int
) -> dict[str, Any]:
    """Monte Carlo 추정 — `ludoforge sim`과 동일 파이프라인(증명 아님 라벨 포함)."""
    rs = _load(lf_text)
    if isinstance(rs, dict):
        return rs
    if not rs.transitions:
        return {"exit": 2, "text": "전이(transitions)가 없어 sim 대상이 아닙니다.", "html": None}
    try:
        report = run_sim(rs, samples=samples, horizon=horizon, seed=seed, workers=workers)
    except SimError as e:
        return {"exit": 2, "text": f"sim 실행 실패:\n{e}", "html": None}
    return {"exit": 0, "text": format_sim_report(report), "html": render_sim_html(report)}
