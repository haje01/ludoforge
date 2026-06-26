"""sim HTML 리포트(D19): SimReport를 자체 완결형(self-contained) HTML로 시각화한다.

텍스트 리포트(`sim.report`)와 같은 내용을 더 보기 쉽게 보여주는 용도다 — 비율은 95% CI를
얹은 0..1 막대로, 분포는 히스토그램(가능할 때)·평균/CI/백분위 마커로 그린다. 외부 의존성·
CDN 없이 인라인 CSS·SVG와 작은 인라인 JS(커서 위치 값 호버 툴팁, core.htmlviz)만 쓴다
(오프라인에서 그대로 열림). 결정론을 위해 타임스탬프 등 비결정 요소는 넣지 않는다 — 같은
SimReport는 같은 HTML을 낸다.

증명이 아니라 추정이라는 라벨(D19 정직성)은 텍스트 리포트와 동일하게 머리에 박는다.
"""

from __future__ import annotations

import html

from core.htmlviz import TOOLTIP_CSS, TOOLTIP_JS
from sim.aggregate import (
    ConfigResult,
    DistributionResult,
    ProportionResult,
    SimReport,
)
from sim.report import _num  # 숫자 포맷(정수면 정수, 아니면 4자리) 일관 재사용

_LABEL = "⚠️ 증명 아님 · 표집 추정(Monte Carlo) — 정확값 보장 아님, 신뢰구간으로 읽으세요."
_POLICY_LABEL = (
    "📐 주어진 정책(pref) 하의 추정 — 최적(Pmax) 아님. 이 값은 이 정책의 결과이며 "
    "Pmax의 하한입니다(정책이 우연히 최적일 때만 일치)."
)

# 히스토그램 막대 최대 개수. distinct 값이 이보다 많으면 [vmin,vmax]를 균등 구간으로 묶는다.
_MAX_BARS = 30

_CSS = """
:root {
  --bg: #0d1117; --panel: #161b22; --border: #30363d; --fg: #e6edf3;
  --muted: #8b949e; --accent: #58a6ff; --ok: #3fb950; --warn: #d29922;
  --track: #21262d; --bar: #1f6feb;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0; padding: 2rem;
  font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif; line-height: 1.5; }
.wrap { max-width: 900px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .5rem; }
h2 { font-size: 1.05rem; margin: 0 0 .75rem; color: var(--accent); }
.label { background: var(--panel); border: 1px solid var(--border);
  border-left: 3px solid var(--warn); border-radius: 6px; padding: .5rem .75rem;
  margin: .4rem 0; color: var(--muted); font-size: .85rem; }
.label.policy { border-left-color: var(--accent); }
.meta { color: var(--muted); font-size: .85rem; margin: .5rem 0 1.5rem; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 1.1rem 1.25rem; margin: 0 0 1.25rem; }
.cfg { font-size: .9rem; color: var(--accent); margin-bottom: .5rem; }
.trunc { font-size: .8rem; color: var(--muted); margin-bottom: 1rem; }
.trunc.high { color: var(--warn); }
.check { margin: 1rem 0; padding-top: .9rem; border-top: 1px dashed var(--border); }
.check:first-of-type { border-top: none; padding-top: 0; }
.check .name { font-weight: 600; }
.check .kind { color: var(--muted); font-weight: 400; font-size: .8rem; }
.check .desc { color: var(--muted); font-size: .85rem; margin: .15rem 0 .5rem; }
.stat { font-variant-numeric: tabular-nums; font-size: .9rem; margin: .35rem 0; }
.stat .hi { color: var(--fg); font-weight: 600; }
.note { color: var(--warn); font-size: .82rem; }
svg { display: block; margin: .4rem 0; width: 100%; height: auto; }
.skipped { color: var(--muted); font-size: .85rem; margin-top: 1rem; }
.foot { color: var(--muted); font-size: .75rem; margin-top: 2rem; text-align: center; }
"""


def render_sim_html(report: SimReport) -> str:
    """SimReport를 자체 완결형 HTML 문자열로 렌더한다(외부 의존성 없음)."""
    parts: list[str] = []
    parts.append('<div class="label">' + _esc(_LABEL) + "</div>")
    if report.uses_policy:
        parts.append('<div class="label policy">' + _esc(_POLICY_LABEL) + "</div>")
    parts.append(
        f'<div class="meta">표본 N={report.samples} · 지평 H={report.horizon} · '
        f"seed={report.seed}</div>"
    )
    for cfg in report.configs:
        parts.append(_render_config(cfg))
    if report.skipped:
        parts.append(
            '<div class="skipped">ℹ️ sim이 다루지 않는 체크(건너뜀): '
            + _esc(", ".join(report.skipped))
            + " — no_deadlock은 BMC(ludoforge bmc) 몫.</div>"
        )

    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Ludoforge sim 추정 리포트</title>\n"
        f"<style>{_CSS}{TOOLTIP_CSS}</style></head>\n"
        '<body><div class="wrap">\n'
        "<h1>Monte Carlo 추정 결과 (sim)</h1>\n"
        f"{body}\n"
        '<div class="foot">Ludoforge · sim 백엔드 (Monte Carlo 추정)</div>\n'
        f"</div>{TOOLTIP_JS}</body></html>\n"
    )


def _render_config(cfg: ConfigResult) -> str:
    rows: list[str] = ['<div class="card">']
    if cfg.config:
        label = ", ".join(f"{k}={v}" for k, v in cfg.config.items())
        rows.append(f'<div class="cfg">[설정] {_esc(label)}</div>')
    trunc_pct = 100 * cfg.truncated / cfg.n_samples if cfg.n_samples else 0.0
    high = " high" if trunc_pct >= 5 else ""
    note = " ⚠️ 절단 높음 — 지평 H를 늘려 수렴을 확인하세요." if trunc_pct >= 5 else ""
    rows.append(
        f'<div class="trunc{high}">절단(지평 H 미종료): {cfg.truncated}/{cfg.n_samples} '
        f"({trunc_pct:.1f}%) · 자연종료 {cfg.terminated}/{cfg.n_samples}{_esc(note)}</div>"
    )
    for i, result in enumerate(cfg.checks, start=1):
        if isinstance(result, ProportionResult):
            rows.append(_render_proportion(i, result))
        elif isinstance(result, DistributionResult):
            rows.append(_render_distribution(i, result))
    rows.append("</div>")
    return "\n".join(rows)


def _render_proportion(index: int, r: ProportionResult) -> str:
    head = (
        f'<div class="check"><div class="name">[{index}] {_esc(r.check_id)} '
        f'<span class="kind">({_esc(r.kind)})</span></div>'
    )
    if r.desc:
        head += f'<div class="desc">{_esc(r.desc)}</div>'
    if r.rule_of_three is not None:
        tip = f"{r.event_label} 미관측 0/{r.n} · 상한 P ≲ {r.rule_of_three:.2g}"
        bar = _bar_svg([(0.0, r.rule_of_three, "var(--warn)")], marks=[], tip=tip)
        body = (
            f'<div class="stat">{_esc(r.event_label)} 미관측 (0/{r.n}) — '
            f'상한 P ≲ <span class="hi">{r.rule_of_three:.2g}</span> (rule of three)</div>'
            f"{bar}"
            '<div class="note">관측 안 됨 ≠ 불가능 — 존재 증명은 ludoforge bmc.</div>'
        )
        return head + body + "</div>"
    lo, hi = r.ci
    tip = f"{r.event_label} P̂={r.p_hat:.4f} · 95% CI [{lo:.4f}, {hi:.4f}] · {r.successes}/{r.n}"
    bar = _bar_svg([(lo, hi, "var(--bar)")], marks=[(r.p_hat, "var(--accent)")], tip=tip)
    body = (
        f'<div class="stat">{_esc(r.event_label)} P̂ = <span class="hi">{r.p_hat:.4f}</span>'
        f"  95% CI [{lo:.4f}, {hi:.4f}]  ({r.successes}/{r.n})</div>"
        f"{bar}"
    )
    if r.kind == "invariant" and r.example is not None:
        body += f'<div class="note">위반 예시 경로(표집): {_esc(_trace(r.example))}</div>'
    return head + body + "</div>"


def _render_distribution(index: int, r: DistributionResult) -> str:
    lo, hi = r.ci
    head = (
        f'<div class="check"><div class="name">[{index}] {_esc(r.check_id)} '
        f'<span class="kind">(distribution)</span></div>'
    )
    if r.desc:
        head += f'<div class="desc">{_esc(r.desc)}</div>'
    stat = (
        f'<div class="stat">평균 = <span class="hi">{r.mean:.4f}</span>  95% CI '
        f"[{lo:.4f}, {hi:.4f}]  (σ={r.stddev:.4f}, 범위=[{_num(r.vmin)}, {_num(r.vmax)}], "
        f"n={r.n})</div>"
    )
    chart = _hist_svg(r) if r.histogram else _meanci_svg(r)
    if r.percentiles is not None:
        pct = "  ".join(f"p{p}={_num(v)}" for p, v in sorted(r.percentiles.items()))
        stat_pct = f'<div class="stat">백분위: {_esc(pct)}</div>'
    else:
        stat_pct = '<div class="stat">백분위: (distinct 값이 많아 생략 — 평균/CI만)</div>'
    return head + stat + chart + stat_pct + "</div>"


# ---------- SVG 헬퍼 (인라인, JS·외부 의존성 없음) ----------


def _bar_svg(
    bands: list[tuple[float, float, str]], marks: list[tuple[float, str]], tip: str = ""
) -> str:
    """0..1 스케일 가로 막대. bands=(lo,hi,색) CI 띠, marks=(x,색) 세로 점선(점추정).

    tip을 주면 svg 전체에 호버 툴팁(data-tip)을 단다(커서로 값 확인, core.htmlviz)."""
    w, h = 100.0, 7.0
    attr = f' data-tip="{_esc(tip)}"' if tip else ""
    svg = [
        f'<svg viewBox="0 0 {w:g} {h:g}" preserveAspectRatio="none" role="img"{attr}>',
        f'<rect x="0" y="1.5" width="{w:g}" height="4" rx="1" fill="var(--track)"/>',
    ]
    for lo, hi, color in bands:
        x = max(0.0, lo) * w
        bw = max(0.6, (min(1.0, hi) - max(0.0, lo)) * w)
        svg.append(f'<rect x="{x:.2f}" y="1.5" width="{bw:.2f}" height="4" rx="1" fill="{color}"/>')
    for x, color in marks:
        px = min(1.0, max(0.0, x)) * w
        svg.append(f'<rect x="{px - 0.4:.2f}" y="0.5" width="0.8" height="6" fill="{color}"/>')
    svg.append("</svg>")
    return "".join(svg)


def _hist_svg(r: DistributionResult) -> str:
    """값→빈도 히스토그램 컬럼 차트. distinct가 많으면 균등 구간으로 묶는다. 평균선 표시."""
    assert r.histogram is not None
    bins = _bin_histogram(r.histogram, r.vmin, r.vmax)
    if not bins:
        return ""
    w, h = 100.0, 40.0
    cmax = max(c for _, c in bins) or 1
    n = len(bins)
    bw = w / n
    svg = [f'<svg viewBox="0 0 {w:g} {h:g}" preserveAspectRatio="none" role="img">']
    for i, (v, c) in enumerate(bins):
        bh = (c / cmax) * (h - 2)
        x = i * bw
        pct = f" ({100 * c / r.n:.1f}%)" if r.n else ""
        tip = _esc(f"값 {_num(v)} · 빈도 {c}{pct}")
        svg.append(
            f'<rect x="{x + bw * 0.1:.2f}" y="{h - bh:.2f}" width="{bw * 0.8:.2f}" '
            f'height="{bh:.2f}" fill="var(--bar)" data-tip="{tip}"/>'
        )
    span = r.vmax - r.vmin
    if span > 0:
        mx = (r.mean - r.vmin) / span * w
        mtip = _esc(f"평균 {r.mean:.4f}")
        svg.append(
            f'<rect x="{mx - 0.3:.2f}" y="0" width="0.6" height="{h:g}" '
            f'fill="var(--ok)" data-tip="{mtip}"/>'
        )
    svg.append("</svg>")
    return "".join(svg)


def _meanci_svg(r: DistributionResult) -> str:
    """히스토그램이 없을 때(연속/넓은 범위) [vmin,vmax] 위 평균±CI 띠 + 백분위 마커."""
    span = r.vmax - r.vmin
    if span <= 0:
        return ""

    def pos(v: float) -> float:
        return (v - r.vmin) / span * 100.0

    lo, hi = r.ci
    bands = [(pos(lo) / 100.0, pos(hi) / 100.0, "var(--bar)")]
    marks = [(pos(r.mean) / 100.0, "var(--ok)")]
    if r.percentiles is not None:
        for v in r.percentiles.values():
            marks.append((pos(v) / 100.0, "var(--muted)"))
    tip = f"평균 {r.mean:.4f} · 95% CI [{lo:.4f}, {hi:.4f}] · 범위 [{_num(r.vmin)}, {_num(r.vmax)}]"
    return _bar_svg(bands, marks, tip=tip)


def _bin_histogram(hist: dict[float, int], vmin: float, vmax: float) -> list[tuple[float, int]]:
    """distinct 값이 적으면 값별 막대, 많으면 [vmin,vmax]를 _MAX_BARS 구간으로 묶는다."""
    items = sorted(hist.items())
    if len(items) <= _MAX_BARS:
        return items
    span = vmax - vmin
    if span <= 0:
        return items
    buckets = [0] * _MAX_BARS
    for v, c in items:
        idx = min(_MAX_BARS - 1, int((v - vmin) / span * _MAX_BARS))
        buckets[idx] += c
    return [(vmin + (i + 0.5) * span / _MAX_BARS, c) for i, c in enumerate(buckets)]


def _trace(run: object) -> str:
    """위반 경로 요약(텍스트 리포트와 동일 형식)."""
    from sim.report import _format_trace

    return _format_trace(run)  # type: ignore[arg-type]


def _esc(s: str) -> str:
    return html.escape(s, quote=True)
