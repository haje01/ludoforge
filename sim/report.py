"""sim 리포트(Phase 2, D19): SimReport를 한국어 리포트로 변환한다.

증명이 아니라 추정이라는 점을 **모든 출력 머리에 라벨**로 박는다(D19 정직성). 비율은
신뢰구간과 함께, 0/N 사건은 rule-of-three 상한으로(불가능이라 하지 않음), 분포는 평균±CI·
백분위로, 그리고 지평 H에 걸린 절단 비율을 보고한다.
"""

from __future__ import annotations

from sim.aggregate import (
    ConfigResult,
    DistributionResult,
    ProportionResult,
    SimReport,
)
from sim.engine import RunResult

_LABEL = "⚠️ 증명 아님 · 표집 추정(Monte Carlo) — 정확값 보장 아님, 신뢰구간으로 읽으세요."
_POLICY_LABEL = (
    "📐 주어진 정책(pref) 하의 추정 — 최적(Pmax) 아님. 이 값은 *이 정책*의 결과이며 "
    "Pmax의 하한입니다(정책이 우연히 최적일 때만 일치)."
)


def format_sim_report(report: SimReport) -> str:
    lines: list[str] = ["Monte Carlo 추정 결과 (sim)", _LABEL]
    if report.uses_policy:
        label = _POLICY_LABEL
        if report.policy_players:
            label += f" (플레이어 {', '.join(report.policy_players)}의 정책, D27)"
        lines.append(label)
    lines += [
        f"표본 N={report.samples} · 지평 H={report.horizon} · seed={report.seed}",
        "",
    ]
    for cfg in report.configs:
        lines.extend(_format_config(cfg))
        lines.append("")
    if report.skipped:
        lines.append(
            "ℹ️ sim이 다루지 않는 체크(건너뜀): "
            + ", ".join(report.skipped)
            + " — no_deadlock은 BMC(ludoforge bmc) 몫."
        )
    return "\n".join(lines).rstrip() + "\n"


def _format_config(cfg: ConfigResult) -> list[str]:
    lines: list[str] = []
    if cfg.config:
        label = ", ".join(f"{k}={v}" for k, v in cfg.config.items())
        lines.append(f"[설정] {label}")
    trunc_pct = 100 * cfg.truncated / cfg.n_samples if cfg.n_samples else 0.0
    note = "  ⚠️ 절단 높음 — 지평 H를 늘려 수렴을 확인하세요." if trunc_pct >= 5 else ""
    lines.append(
        f"  절단(지평 H 미종료): {cfg.truncated}/{cfg.n_samples} ({trunc_pct:.1f}%)"
        f" · 자연종료 {cfg.terminated}/{cfg.n_samples}{note}"
    )
    for i, result in enumerate(cfg.checks, start=1):
        if isinstance(result, ProportionResult):
            lines.extend(_format_proportion(i, result))
        elif isinstance(result, DistributionResult):
            lines.extend(_format_distribution(i, result))
    return lines


def _format_proportion(index: int, r: ProportionResult) -> list[str]:
    desc = f" — {r.desc}" if r.desc else ""
    head = f"  [{index}] '{r.check_id}' ({r.kind}){desc}"
    if r.rule_of_three is not None:
        # 한 번도 관측되지 않음 → 불가능이 아니라 상한으로 보고(D19).
        body = (
            f"      {r.event_label} 미관측(0/{r.n}) — 상한 P({r.event_label}) ≲ "
            f"{r.rule_of_three:.2g} (rule of three). 관측 안 됨 ≠ 불가능 — 존재 증명은 "
            f"ludoforge bmc."
        )
        return [head, body]
    lo, hi = r.ci
    body = (
        f"      {r.event_label} P̂ = {r.p_hat:.4f}  95% CI [{lo:.4f}, {hi:.4f}]  "
        f"({r.successes}/{r.n})"
    )
    out = [head, body]
    if r.kind == "invariant" and r.example is not None:
        out.append(f"      위반 예시 경로(표집): {_format_trace(r.example)}")
    return out


def _format_distribution(index: int, r: DistributionResult) -> list[str]:
    desc = f" — {r.desc}" if r.desc else ""
    # ghost 서술 변수(D31)의 분포는 sim만 본다 — 논리 검증(bmc)에서 제거됐음을 명시.
    ghost = " · 서술 변수(ghost — 논리 검증 제외)" if r.ghost_expr else ""
    lo, hi = r.ci
    lines = [
        f"  [{index}] '{r.check_id}' (distribution){desc}{ghost}",
        f"      평균 = {r.mean:.4f}  95% CI [{lo:.4f}, {hi:.4f}]  "
        f"(σ={r.stddev:.4f}, 범위=[{_num(r.vmin)}, {_num(r.vmax)}], n={r.n})",
    ]
    if r.percentiles is not None:
        pct = "  ".join(f"p{p}={_num(v)}" for p, v in sorted(r.percentiles.items()))
        lines.append(f"      백분위: {pct}")
    else:
        lines.append("      백분위: (distinct 값이 많아 생략 — 평균/CI만)")
    return lines


def _format_trace(run: RunResult) -> str:
    """위반 경로를 간결히(상태열 + 전이 id). 너무 길면 앞뒤만."""
    states = [", ".join(f"{k}={v}" for k, v in s.items()) for s in run.states]
    if len(states) <= 4:
        path = " → ".join(f"({s})" for s in states)
    else:
        path = f"({states[0]}) → … → ({states[-1]})  [{len(states)}상태]"
    return path


def _num(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:.4f}"
