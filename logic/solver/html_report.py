"""BMC HTML 리포트(D15): BmcReport를 자체 완결형(self-contained) HTML로 시각화한다.

텍스트 리포트(`format_bmc_report`)와 같은 내용을 더 보기 쉽게 보여주는 용도다 — 속성마다
상태 배지(도달/위반/데드락/미확인)를 색으로, 반례·도달 **경로(trace)**를 상태 카드 + 전이
화살표로 그린다(스텝 간 바뀐 변수는 강조). 외부 의존성·CDN 없이 인라인 CSS와 작은 인라인
JS(상태 카드 호버 시 전체 상태 툴팁, core.htmlviz)만 쓴다(오프라인에서 그대로 열림).
결정론을 위해 타임스탬프 등 비결정 요소는 넣지 않는다.

"k까지 유지/미도달"은 증명이 아니라 **유계 결과**라는 k-bound 정직성을 머리에 라벨로 박는다.
"""

from __future__ import annotations

import html

from core.htmlviz import TOOLTIP_CSS, TOOLTIP_JS
from logic.solver.bmc import _LABEL, BmcReport, PropertyResult, Trace

# 상태 → 의미 분류(배지 색). 나머지(미도달·unknown)는 경고.
_GOOD = {"reachable", "holds_up_to_k", "no_deadlock_up_to_k"}
_BAD = {"violated", "deadlock"}

_BOUND_LABEL = (
    "⚠️ 유계(bounded) 검사 — k 스텝까지만 봅니다. '위반 없음 · 데드락 없음 · 미도달'은 "
    "그 깊이까지의 결과일 뿐 무한 지평 증명이 아닙니다."
)

_KBOUND_NOTE: dict[str, str] = {
    "unreachable_within_k": "k 한계 — 더 깊은 곳은 미검증. 진짜 도달 불가 증명 아님.",
    "holds_up_to_k": "k 한계 — k 스텝까지만 보장. 무한 지평 증명 아님.",
    "no_deadlock_up_to_k": "k 한계 — k 스텝까지만 보장.",
}

_CSS = """
:root {
  --bg: #0d1117; --panel: #161b22; --border: #30363d; --fg: #e6edf3;
  --muted: #8b949e; --accent: #58a6ff; --ok: #3fb950; --bad: #f85149;
  --warn: #d29922; --chip: #21262d; --chip-hi: #1f6feb;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0; padding: 2rem;
  font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif; line-height: 1.5; }
.wrap { max-width: 900px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .5rem; }
.label { background: var(--panel); border: 1px solid var(--border);
  border-left: 3px solid var(--warn); border-radius: 6px; padding: .5rem .75rem;
  margin: .4rem 0; color: var(--muted); font-size: .85rem; }
.meta { color: var(--muted); font-size: .85rem; margin: .5rem 0 1.5rem; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 1.1rem 1.25rem; margin: 0 0 1.25rem; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.title { font-weight: 600; }
.title .kind { color: var(--muted); font-weight: 400; font-size: .8rem; }
.badge { font-size: .8rem; font-weight: 600; padding: .15rem .55rem; border-radius: 999px;
  white-space: nowrap; border: 1px solid transparent; }
.badge.ok { color: var(--ok); border-color: var(--ok); }
.badge.bad { color: var(--bad); border-color: var(--bad); }
.badge.warn { color: var(--warn); border-color: var(--warn); }
.desc { color: var(--muted); font-size: .85rem; margin: .25rem 0 .5rem; }
.note { color: var(--warn); font-size: .8rem; margin: .35rem 0; }
.detail { color: var(--muted); font-size: .85rem; margin: .35rem 0; }
.depth { color: var(--accent); font-size: .82rem; margin: .2rem 0 .6rem; }
.trace { margin-top: .75rem; }
.step { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem;
  background: #0d1117; border: 1px solid var(--border); border-radius: 6px;
  padding: .45rem .6rem; }
.slabel { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums;
  margin-right: .3rem; }
.svar { background: var(--chip); border-radius: 4px; padding: .1rem .4rem; font-size: .82rem;
  font-variant-numeric: tabular-nums; color: var(--muted); }
.svar.changed { background: var(--chip-hi); color: #fff; }
.action { color: var(--fg); font-size: .8rem; margin: .25rem 0 .25rem 1rem;
  padding-left: .8rem; border-left: 2px solid var(--accent); }
.action .arrow { color: var(--accent); }
.skipped { color: var(--muted); font-size: .85rem; margin-top: 1rem; }
.foot { color: var(--muted); font-size: .75rem; margin-top: 2rem; text-align: center; }
"""


def render_bmc_html(report: BmcReport) -> str:
    """BmcReport를 자체 완결형 HTML 문자열로 렌더한다(외부 의존성 없음)."""
    parts: list[str] = [f'<div class="label">{_esc(_BOUND_LABEL)}</div>']
    parts.append(f'<div class="meta">깊이 한계 k={report.k}</div>')

    if not report.results and not report.skipped_other:
        parts.append('<div class="card">검사할 항목(checks)이 없습니다.</div>')
    for i, r in enumerate(report.results, start=1):
        parts.append(_render_result(i, r))
    if report.skipped_other:
        parts.append(
            '<div class="skipped">ℹ️ 다른 백엔드 전용 검사라 건너뜀(distribution=sim): '
            + _esc(", ".join(report.skipped_other))
            + "</div>"
        )

    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Ludoforge BMC 검사 리포트</title>\n"
        f"<style>{_CSS}{TOOLTIP_CSS}</style></head>\n"
        '<body><div class="wrap">\n'
        "<h1>BMC 검사 결과</h1>\n"
        f"{body}\n"
        '<div class="foot">Ludoforge · 논리 백엔드 (Z3 · BMC)</div>\n'
        f"</div>{TOOLTIP_JS}</body></html>\n"
    )


def _render_result(index: int, r: PropertyResult) -> str:
    cls = "ok" if r.status in _GOOD else "bad" if r.status in _BAD else "warn"
    badge = _esc(_LABEL.get(r.status, r.status))
    rows = ['<div class="card">']
    rows.append(
        f'<div class="head"><span class="title">[{index}] {_esc(r.prop_id)} '
        f'<span class="kind">({_esc(r.kind)})</span></span>'
        f'<span class="badge {cls}">{badge}</span></div>'
    )
    if r.desc:
        rows.append(f'<div class="desc">{_esc(r.desc)}</div>')
    if r.depth is not None:
        rows.append(f'<div class="depth">깊이 {r.depth}</div>')
    if r.status in _KBOUND_NOTE:
        rows.append(f'<div class="note">{_esc(_KBOUND_NOTE[r.status])}</div>')
    if r.detail:
        rows.append(f'<div class="detail">{_esc(r.detail)}</div>')
    if r.trace is not None:
        rows.append(_render_trace(r.trace))
    rows.append("</div>")
    return "\n".join(rows)


def _render_trace(trace: Trace) -> str:
    """상태 카드 + 전이 화살표로 경로를 그린다. 직전 스텝 대비 바뀐 변수를 강조한다."""
    rows = ['<div class="trace">']
    prev: dict[str, str] = {}
    for i, step in enumerate(trace.steps):
        chips = [f'<span class="slabel">s{i}</span>']
        for name, value in step.values.items():
            changed = " changed" if i > 0 and prev.get(name) != value else ""
            chips.append(f'<span class="svar{changed}">{_esc(name)}={_esc(value)}</span>')
        state = " · ".join(f"{n}={v}" for n, v in step.values.items())
        tip = _esc(f"s{i} · {state}")
        rows.append(f'<div class="step" data-tip="{tip}">' + "".join(chips) + "</div>")
        if i < len(trace.actions):
            rows.append(
                f'<div class="action"><span class="arrow">▼</span> {_esc(trace.actions[i])}</div>'
            )
        prev = step.values
    rows.append("</div>")
    return "\n".join(rows)


def _esc(s: str) -> str:
    return html.escape(s, quote=True)
