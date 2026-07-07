"""LLM 번역 서비스: 산문 기획 → `.lf` — 로더·스키마 오류를 피드백하는 수리 루프 (D32 P3).

역할 경계(원칙 1): LLM은 **번역만** 한다 — 후보 `.lf`는 매번 로더(`parse_rule_text`)와
스키마(`validate`) 게이트를 통과해야 하고, 실패 메시지를 그대로 되먹여 재시도한다
(상한 `max_attempts`). 게이트를 못 넘은 출력은 절대 사용자에게 성공으로 보이지 않는다.

`complete`는 주입 가능한 순수 함수형 인터페이스(system, messages → text)라 테스트가
LLM 없이 루프를 검증한다. 실제 클라이언트는 `anthropic_complete`가 만든다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from core.schema import SchemaError, validate
from core.text_loader import TextLoaderError, parse_rule_text

CompleteFn = Callable[[str, list[dict[str, str]]], str]

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
    check winnable  reachable: gold >= 30
    check gold_ok   invariant: gold >= 0
    check no_stuck  no_deadlock
    check gold_dist distribution: gold     // numeric expr, sim only
- Tables (shared data), indexed by `for` loop variables:
    table reward { goblin: 2, dragon: 10 }
    for mon in [goblin, dragon]:
        transition "hunt_${mon}":
            when monster == mon
            then gold = gold + reward[mon]

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

OUTPUT: return ONLY the `.lf` source, in a single fenced code block.
"""

_REPAIR_PROMPT = """\
Your `.lf` failed the loader/schema gate with this error:

{error}

Fix the model and return the FULL corrected `.lf` source in one fenced code
block. Do not drop declarations that were correct.
"""


@dataclass(frozen=True)
class TranslateAttempt:
    """한 번의 LLM 시도 — 후보 `.lf`와 게이트 오류(None이면 통과)."""

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
    max_attempts: int = 3,
) -> TranslateResult:
    """산문을 `.lf`로 번역한다 — 게이트 실패 시 오류를 되먹여 최대 max_attempts회 시도."""
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
        attempts.append(TranslateAttempt(lf_text=candidate, error=error))
        if error is None:
            return TranslateResult(ok=True, lf_text=candidate, attempts=tuple(attempts))
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": _REPAIR_PROMPT.format(error=error)})

    return TranslateResult(ok=False, lf_text=candidate, attempts=tuple(attempts))


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
