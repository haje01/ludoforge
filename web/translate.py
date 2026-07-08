"""LLM 번역 서비스: 산문 기획 → `.lf` — 로더·스키마 오류를 피드백하는 수리 루프 (D32 P3).

역할 경계(원칙 1): LLM은 **번역만** 한다 — 후보 `.lf`는 매번 로더(`parse_rule_text`)와
스키마(`validate`) 게이트를 통과해야 하고, 실패 메시지를 (후보 전문 + 행 번호와 함께)
그대로 되먹여 재시도한다(상한 `max_attempts`). 게이트를 못 넘은 출력은 절대 사용자에게
성공으로 보이지 않는다.

게이트를 통과해도(구문·참조는 맞아도) 산문 의도를 충실히 옮겼는지는 별개다 — 선택적
`review`(충실도 리뷰어)가 산문↔`.lf`를 대조해 누락/환각/의도 미반영을 지적하면 그
피드백을 되먹여 재생성한다. 리뷰는 **번역 충실도만** 본다(모순 판정 아님 — 그건 solver의
몫, 원칙 1). 재생성으로도 못 고치면 최종 안전망은 사람 게이트(규칙서 미리보기)다.

`complete`/`review`는 주입 가능한 순수 함수형 인터페이스라 테스트가 LLM 없이 루프를
검증한다. 실제 클라이언트는 `anthropic_complete`가, 리뷰어는 `make_reviewer`가 만든다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from core.schema import SchemaError, validate
from core.text_loader import TextLoaderError, parse_rule_text

CompleteFn = Callable[[str, list[dict[str, str]]], str]
# (prose, tables_lf, candidate_lf) → None이면 충실 · 문자열이면 재생성용 피드백.
ReviewFn = Callable[[str, str, str], str | None]

_FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)

# LLM 프롬프트는 영어로 작성한다(사용자 전역 규칙). 문법 요약은 CLAUDE.md §4의 압축본 —
# 문법이 바뀌면 이 참조도 함께 갱신한다.
_SYSTEM_PROMPT = """\
You translate Korean/English game design prose into Ludoforge `.lf`, a small
declarative, non-Turing-complete DSL for game numeric/economy systems. A solver
(Z3) and a Monte Carlo simulator consume the result — you only translate; you
never judge consistency yourself.

GRAMMAR SUMMARY
- domain block declares typed state variables:
    domain {
        level: int 1..100          // int with optional bounds (0.. open max)
        rate:  real 0..1
        flag:  bool
        role:  enum { warrior, mage }
    }
- Static rules (same-state predicates use `==`):
    constraint cap_rule:
        desc "설명(Korean ok)"
        when role == warrior       // optional guard
        then hp == level * 100     // predicate over the same state
- Reachability intents (write these to capture the designer's stated intent):
    expect max_level: role == warrior and level == 100
- Optional dynamics (only when the prose describes accumulation/turns):
    init: gold == 0 and status == playing
    transition earn:
        when status == playing and gold < 30
        then gold = min(gold + 2, 30)      // effects use `=` assignment; `;` for parallel
    transition fight:
        outcomes:                          // probabilistic branches (weights)
            0.7 -> gold = gold + 5
            0.3 -> status = dead
    check winnable  reachable: gold >= 30  // kind keyword REQUIRED before the colon
    check gold_ok   invariant: gold >= 0
    check no_stuck  no_deadlock
    check gold_dist distribution: gold     // numeric expr, sim only
- Tables (shared data), indexed by `for` loop variables:
    table reward { goblin: 2, dragon: 10 }
    for mon in [goblin, dragon]:
        transition "hunt_${mon}":
            when monster == mon
            then gold = gold + reward[mon]
- Arrays over a finite index set — declare ONCE, expands to one scalar per index.
  Use this whenever the prose has several same-shaped entities (parameters,
  players, units) instead of copy-pasting near-identical variables/rules.
  The index set inside `[...]` is the LITERAL list of CONCRETE member names —
  normally the SAME keys as your imported tables. NEVER a placeholder concept or
  a spreadsheet column header:
    domain {
        level[temp, oxy, ocean]: int 0..19    // ✓ concrete keys (== table keys)
        // level[param]: ...                   // ✗ WRONG: one scalar named "param";
        //                                      //   then level[temp] fails — no such index
    }
    for p in [temp, oxy, ocean]:              // index with the loop variable
        transition "raise_${p}":
            when level[p] < cap[p]            // tables may be indexed the same way
            then level[p] = level[p] + 1      // effect LHS may use a STATIC index
    check leader reachable: level[oxy] >= 14  // enum-var index is READ-ONLY
- Multiple effects in ONE transition: wrap in braces, separate with `;`:
    then { level[p] = level[p] + 1; tr = tr + 1; mc = min(mc + tr, 3000) }
- `pref` = player policy weight (sim samples among co-enabled transitions):
    transition dig: when status == playing pref policy[p] then ...
- `ghost` = narrative counter, sim-only, excluded from logic checks:
    domain { ghost gens: int 0.. }            // pin in init; read only in RHS/distribution

HARD RULES
1. `=` only in effects (transition then/outcomes); `==` in all predicates
   (when/init/constraint/expect/check). Mixing them is a syntax error.
2. Every variable you reference must be declared in `domain`.
3. min()/max() only inside effect right-hand sides (saturation), never in predicates.
4. No division by variables; constant denominators only.
5. Identifiers are ASCII [A-Za-z_][A-Za-z0-9_]*; Korean goes in desc/note strings.
6. If tables are provided by the user, reference them by name — do NOT redefine
   or invent data. Do not invent numbers absent from the prose; if a number is
   missing, declare the variable with bounds and add a `desc` noting the gap.
7. Always add `expect` assertions for states the prose says should be possible,
   and `check` items for properties it promises — they are how the solver
   verifies the designer's intent.
8. Add `desc "..."` (Korean) to constraints/transitions/checks so a generated
   rulebook stays readable.
9. `check` syntax is `check <id> <kind>: <predicate>` — the kind keyword
   (reachable | invariant | no_deadlock | distribution) is REQUIRED between the
   id and the colon. `check <id>: <predicate>` is a syntax error.
10. `init`/`transition`/`check` are for DYNAMIC models only (state that changes
    over turns). For a purely static model (constraints over one snapshot),
    express every "should be possible" intent with `expect`, never `check`.
11. Arrays: `name[a, b, c]: <type>` = one scalar per index. The `[a, b, c]` must
    be the LITERAL concrete member names (match your table keys / your `for`
    lists) — NOT an abstract placeholder or a CSV column header. `level[param]`
    is wrong: it declares a single scalar "param", so `level[temp]` then fails.
    Index with a `for` loop variable or a literal. An effect left-hand side may
    use a STATIC index (`level[p]`, p a loop var); a dynamic index (`x[enumVar]`)
    is READ-ONLY, and the index enum's value set must cover the array's index set.
12. Two or more effects MUST be `then { a = …; b = … }` (braces, `;`-separated).
    Newline-separated bare effects are a syntax error.
13. No dead ends (or `no_deadlock` fails): EVERY reachable state must have at
    least one enabled transition. A terminal/goal state (e.g. `status == done`)
    needs an ABSORBING self-loop — `transition end: when status == done then
    status = done`. Also give the player an always-available fallback (e.g. a
    `save_up` that only receives income) so no mid-game state can get stuck.

EXAMPLE — a COMPLETE, deadlock-free numeric/economy model. Use it as a TEMPLATE:
arrays with concrete keys, tables, a for-template with `pref` + `ghost` +
multi-effect braces, an always-available fallback action, and an ABSORBING
terminal self-loop. Translate the user's prose into this SHAPE (do not copy these
numbers):
    domain {
        level[temp, oxy, ocean]: int 0..19
        tr: int 20..62
        mc: int 0..3000
        status: enum { playing, done }
        ghost gens: int 0..
    }
    table cap { temp: 19, oxy: 14, ocean: 9 }
    table cost { temp: 14, oxy: 23, ocean: 18 }
    table policy { temp: 4, oxy: 2, ocean: 3 }
    init: level[temp] == 0 and level[oxy] == 0 and level[ocean] == 0
        and tr == 20 and mc == 40 and status == playing and gens == 0
    for p in [temp, oxy, ocean]:
        transition "raise_${p}":
            desc "표준 프로젝트 — 파라미터 1단계 상승, TR +1"
            when status == playing and level[p] < cap[p] and mc + tr >= cost[p]
            pref policy[p]
            then { level[p] = level[p] + 1; tr = tr + 1;
                   mc = min(mc + tr - cost[p], 3000); gens = gens + 1 }
    transition save_up:                     // always enabled while playing → no stuck state
        desc "저축 — 소득만 받고 세대를 넘긴다(막다른 상태 방지)"
        when status == playing
            and not (level[temp] == 19 and level[oxy] == 14 and level[ocean] == 9)
        pref 1
        then { mc = min(mc + tr, 3000); gens = gens + 1 }
    transition finish:
        when status == playing
            and level[temp] == 19 and level[oxy] == 14 and level[ocean] == 9
        then status = done
    transition done_absorb:                 // ABSORBING self-loop → terminal is not a deadlock
        when status == done
        then status = done
    check terraformed reachable: status == done
    check tr_floor     invariant: tr >= 20
    check mc_nonneg    invariant: mc >= 0
    check no_stuck     no_deadlock
    check length       distribution: gens

OUTPUT: return ONLY the `.lf` source, in a single fenced code block.
"""

_REPAIR_PROMPT = """\
Your `.lf` failed the loader/schema gate.

ERROR:
{error}

YOUR `.lf` SO FAR (line numbers added — the error above refers to these lines;
note the imported tables occupy the first lines):
{numbered}

Return the FULL corrected `.lf` source in one fenced code block. Keep the
declarations that were already correct.
"""

# 게이트는 통과했으나(구문 OK) 산문 의도를 충실히 못 옮긴 경우의 재생성 프롬프트.
_REVIEW_REPAIR_PROMPT = """\
Your `.lf` is syntactically valid, but a translation review found it does not
faithfully match the design prose:

{feedback}

Revise the `.lf` to address every point and return the FULL corrected source in
one fenced code block. Do not invent numbers absent from the prose — if a value
is truly unspecified, declare the variable with bounds and note the gap in `desc`.
"""

# 충실도 리뷰어의 시스템 프롬프트. 원칙 1 경계: 논리 모순은 판정하지 않는다(solver 몫) —
# "산문에 있는 것을 빠짐없이/지어내지 않고/올바른 형태로 옮겼는가"만 본다.
_REVIEW_SYSTEM_PROMPT = """\
You review Ludoforge translations. You are given the designer's PROSE (plus any
imported tables) and a candidate `.lf` model that ALREADY passes the loader and
schema. Judge ONLY translation faithfulness — you do NOT judge logical
consistency (a Z3 solver does that separately). Check:
- Every quantity, rule, and bound stated in the prose is represented.
- No invented numbers or rules that are absent from the prose.
- Each "should be possible" is an `expect` (static) or a `reachable` check; each
  promised property is a `check` (invariant / no_deadlock / distribution).
- Imported tables are referenced by name, not redefined or altered.

If the translation is faithful, reply with exactly one line:
FAITHFUL
Otherwise reply with `PROBLEMS:` on the first line, then a numbered list of
concrete, actionable issues (what is missing / invented / misplaced). Be specific.
"""


def _numbered(text: str) -> str:
    """후보 전문을 행 번호와 함께 렌더한다 — 오류가 짚는 줄과 실제 원인 줄이 달라도(예:
    앞선 `then {` 누락으로 뒤 줄에서 터질 때) 모델이 전체 맥락을 번호로 보고 고치게 한다.
    (단일 줄 인용은 위치만 줘 같은 실수를 반복시킨 회귀가 있었다 — 2026-07-07.)"""
    lines = text.splitlines()
    width = len(str(len(lines))) if lines else 1
    return "\n".join(f"{i:>{width}} | {line}" for i, line in enumerate(lines, 1))


@dataclass(frozen=True)
class TranslateAttempt:
    """한 번의 LLM 시도 — 후보 `.lf`와 실패 사유. error=None이면 게이트+충실도 통과.
    error는 게이트 오류(구문·스키마) 또는 충실도 리뷰 피드백을 담는다."""

    lf_text: str
    error: str | None


@dataclass(frozen=True)
class TranslateResult:
    """번역 결과. ok=False면 lf_text는 마지막(실패) 후보다 — 성공으로 쓰면 안 된다."""

    ok: bool
    lf_text: str
    attempts: tuple[TranslateAttempt, ...]


def translate_prose(
    prose: str,
    *,
    tables_lf: str = "",
    complete: CompleteFn,
    review: ReviewFn | None = None,
    max_attempts: int = 3,
) -> TranslateResult:
    """산문을 `.lf`로 번역한다 — 게이트(구문·스키마) 실패 시 오류를 (후보 전문+행 번호와
    함께) 되먹이고, 통과 시 review가 있으면 충실도까지 확인해 문제가 있으면 재생성한다.
    최대 max_attempts회 시도(각 시도 = 생성 1회; 충실도 리뷰 호출은 별도로 세지 않는다)."""
    user_content = prose.strip()
    if tables_lf.strip():
        user_content += (
            "\n\nThe following tables were imported from the designer's spreadsheet."
            " Reference them by name; do not redefine them (they are prepended"
            " automatically):\n```\n" + tables_lf.strip() + "\n```"
        )
    messages: list[dict[str, str]] = [{"role": "user", "content": user_content}]

    attempts: list[TranslateAttempt] = []
    candidate = ""
    for _ in range(max_attempts):
        response = complete(_SYSTEM_PROMPT, messages)
        candidate = _combine(tables_lf, _extract_lf(response))
        error = _gate(candidate)
        # 게이트 통과 후에만 충실도 리뷰 — 구문·참조가 맞아야 의미 대조가 뜻이 있다.
        faithfulness = error is None and review is not None
        if faithfulness:
            error = review(prose, tables_lf, candidate)  # type: ignore[misc]
        attempts.append(TranslateAttempt(lf_text=candidate, error=error))
        if error is None:
            return TranslateResult(ok=True, lf_text=candidate, attempts=tuple(attempts))
        messages.append({"role": "assistant", "content": response})
        if faithfulness:  # error는 충실도 피드백
            repair = _REVIEW_REPAIR_PROMPT.format(feedback=error)
        else:  # error는 게이트(구문·스키마) 오류
            repair = _REPAIR_PROMPT.format(error=error, numbered=_numbered(candidate))
        messages.append({"role": "user", "content": repair})

    return TranslateResult(ok=False, lf_text=candidate, attempts=tuple(attempts))


def make_reviewer(complete: CompleteFn) -> ReviewFn:
    """번역 CompleteFn을 재사용해 충실도 리뷰어를 만든다 — 같은 LLM, 다른 시스템 프롬프트.
    원칙 1 경계: 리뷰는 산문↔`.lf` 충실도만 본다(모순 판정 아님)."""

    def review(prose: str, tables_lf: str, candidate: str) -> str | None:
        response = complete(
            _REVIEW_SYSTEM_PROMPT,
            [{"role": "user", "content": _review_user_content(prose, tables_lf, candidate)}],
        )
        return _parse_review(response)

    return review


def _review_user_content(prose: str, tables_lf: str, candidate: str) -> str:
    parts = ["DESIGN PROSE:\n" + prose.strip()]
    if tables_lf.strip():
        parts.append("IMPORTED TABLES:\n" + tables_lf.strip())
    parts.append("CANDIDATE `.lf` (already passes loader + schema):\n" + candidate.strip())
    return "\n\n".join(parts)


def _parse_review(response: str) -> str | None:
    """리뷰 응답 해석 — 첫 비어있지 않은 줄이 PROBLEMS로 시작하면 그 피드백을, 아니면 None.
    애매/빈 응답은 '충실'로 본다 — 불필요한 재생성으로 멀쩡한 번역을 버리지 않기 위함이며,
    최종 안전망은 사람 게이트다(리뷰어는 확신할 때만 거부)."""
    for line in response.strip().splitlines():
        if line.strip():
            if line.strip().upper().startswith("PROBLEMS"):
                return response.strip()
            return None
    return None


def _extract_lf(response: str) -> str:
    """응답에서 `.lf` 후보를 뽑는다 — 펜스 코드 블록 우선, 없으면 전문."""
    m = _FENCE.search(response)
    return (m.group(1) if m else response).strip()


def _combine(tables_lf: str, body: str) -> str:
    if tables_lf.strip():
        return tables_lf.strip() + "\n\n" + body
    return body


def _gate(candidate: str) -> str | None:
    """로더·스키마 게이트 — 통과하면 None, 실패하면 오류 메시지(그대로 되먹임)."""
    try:
        rs = parse_rule_text(candidate, source="web-input.lf")
        validate(rs)
    except (TextLoaderError, SchemaError) as e:
        return str(e)
    return None


def anthropic_complete(model: str, *, max_tokens: int = 4096) -> CompleteFn:
    """실제 Claude API 클라이언트 — `ANTHROPIC_API_KEY` 환경변수를 쓴다.

    지연 import: 웹 서버를 띄우지 않는 경로(테스트·CLI 검증)는 SDK 없이도 동작한다.
    키 부재는 여기서 즉시 실패시킨다 — SDK는 요청 시점에야 던져 수리 루프 밖에서 터진다.
    """
    import os

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다")
    client = anthropic.Anthropic()

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        params: list[anthropic.types.MessageParam] = [
            {"role": "assistant" if m["role"] == "assistant" else "user", "content": m["content"]}
            for m in messages
        ]
        response = client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=params
        )
        return "".join(block.text for block in response.content if block.type == "text")

    return complete
