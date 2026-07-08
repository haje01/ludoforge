"""웹 MVP: LLM 번역 서비스(산문 → .lf) 수리 루프 테스트 (D32 P3).

LLM은 가짜(complete 주입)로 대체한다 — 여기서 검증하는 건 루프의 기계 부분이다:
후보 추출(펜스), 로더·스키마 게이트 판정, 오류 피드백 재시도, 상한, 표 절 결합.
판정은 항상 로더·스키마(solver 경계)가 한다 — LLM 출력은 절대 그대로 신뢰하지 않는다.
"""

from __future__ import annotations

from web.translate import make_reviewer, translate_prose

_VALID_LF = """domain {
    level: int 1..100
    hp:    int 0..
}
constraint hp_formula:
    then hp == level * 100
expect max_level: level == 100
"""

_BROKEN_LF = "domain { level int 1..100 }\n"  # 콜론 누락 — 구문 오류

_TABLE_LF = "table reward { goblin: 2, dragon: 10 }"

_VALID_WITH_TABLE = """domain {
    gold: int 0..30
    monster: enum { goblin, dragon }
}
init: gold == 0 and monster == goblin
for mon in [goblin, dragon]:
    transition "hunt_${mon}":
        when monster == mon
        then gold = min(gold + reward[mon], 30)
"""


def test_first_try_success() -> None:
    def complete(system: str, messages: list[dict[str, str]]) -> str:
        return f"Here is the model:\n```\n{_VALID_LF}```\n"

    result = translate_prose("전사 HP는 레벨당 100", complete=complete)
    assert result.ok
    assert len(result.attempts) == 1
    assert "constraint hp_formula" in result.lf_text
    assert result.attempts[0].error is None


def test_repair_loop_feeds_error_back() -> None:
    calls: list[list[dict[str, str]]] = []

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        calls.append([dict(m) for m in messages])
        return _BROKEN_LF if len(calls) == 1 else _VALID_LF

    result = translate_prose("전사 HP는 레벨당 100", complete=complete, max_attempts=3)
    assert result.ok
    assert len(result.attempts) == 2
    assert result.attempts[0].error is not None
    # 두 번째 호출의 대화에 첫 시도(assistant)와 오류 피드백(user)이 들어가야 한다.
    second = calls[1]
    assert second[-2]["role"] == "assistant"
    assert second[-1]["role"] == "user"
    assert result.attempts[0].error.splitlines()[0] in second[-1]["content"]


def test_gives_up_after_max_attempts() -> None:
    def complete(system: str, messages: list[dict[str, str]]) -> str:
        return _BROKEN_LF

    result = translate_prose("아무거나", complete=complete, max_attempts=3)
    assert not result.ok
    assert len(result.attempts) == 3
    assert all(a.error is not None for a in result.attempts)


def test_tables_prepended_and_validated_together() -> None:
    def complete(system: str, messages: list[dict[str, str]]) -> str:
        # LLM은 표를 재정의하지 않고 참조만 한다 — 결합은 서비스의 몫.
        return _VALID_WITH_TABLE

    result = translate_prose("사냥 보상 모델", tables_lf=_TABLE_LF, complete=complete)
    assert result.ok
    assert result.lf_text.startswith(_TABLE_LF)
    # 시트 표가 시스템 프롬프트로 전달됐는가(참조하라는 계약).
    assert "reward" in result.lf_text


def test_repair_prompt_quotes_offending_line() -> None:
    """실사용 회귀(2026-07-07): kind 없는 check로 3회 전패 — 수리 피드백이 위치(줄/열)만
    줘서 모델이 같은 실수를 반복했다. 오류가 짚는 줄의 원문을 인용해 되먹여야 한다."""
    bad_check = "domain { hp: int 0..1000 }\ncheck hp_ok: hp <= 1000\n"  # kind 누락(2행)

    calls: list[list[dict[str, str]]] = []

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        calls.append([dict(m) for m in messages])
        return bad_check if len(calls) == 1 else _VALID_LF

    result = translate_prose("HP 상한", complete=complete, max_attempts=2)
    assert result.ok
    repair_msg = calls[1][-1]["content"]
    assert "check hp_ok: hp <= 1000" in repair_msg  # 문제 줄 원문 인용


def test_system_prompt_teaches_check_kind_and_static_expect() -> None:
    """프롬프트 계약 고정(실사용 회귀의 원인 H1·H2): check kind 필수·정적 모델은 expect."""
    captured: list[str] = []

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        captured.append(system)
        return _VALID_LF

    assert translate_prose("아무거나", complete=complete).ok
    system = captured[0]
    assert "check <id> <kind>" in system
    assert "REQUIRED" in system
    assert "expect" in system and "never `check`" in system


def test_schema_error_also_triggers_repair() -> None:
    # 구문은 통과하나 미정의 변수를 참조 — 스키마 게이트가 잡아 재시도로 이어져야 한다.
    bad_schema = "domain { hp: int 0.. }\nconstraint c: then mana <= 100\n"

    calls = 0

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        nonlocal calls
        calls += 1
        return bad_schema if calls == 1 else _VALID_LF

    result = translate_prose("마나 상한", complete=complete, max_attempts=2)
    assert result.ok
    assert len(result.attempts) == 2
    assert result.attempts[0].error is not None and "mana" in result.attempts[0].error


# ── 개선 1: 프롬프트가 배열·색인·다중효과 문법을 가르치는가 ──────────────────


def test_system_prompt_teaches_arrays_and_multi_effect() -> None:
    """개선 1(TM 실패 회귀): 배열 선언·정적 색인·다중효과 브레이스가 프롬프트에 있어야
    한다. 없으면 LLM이 표 키를 스칼라 변수처럼 써 `temp = temp + 1`을 최상위에 흘린다."""
    captured: list[str] = []

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        captured.append(system)
        return _VALID_LF

    assert translate_prose("아무거나", complete=complete).ok
    system = captured[0]
    assert "[temp, oxy, ocean]" in system  # 배열 선언 예시
    assert "level[p]" in system  # 색인 접근/효과 LHS
    assert "then {" in system and ";" in system  # 다중효과 브레이스
    assert "pref" in system and "ghost" in system  # 정책 가중치·서술 변수
    # 색인 집합은 구체적 값(표 키)이어야 한다 — placeholder 오용 방지(실사용 회귀).
    assert "level[param]" in system  # 잘못된 형태를 anti-example로 명시
    assert "table keys" in system


def test_system_prompt_teaches_deadlock_free_terminal() -> None:
    """실사용 회귀(TM no_stuck 깊이 43 데드락): 종료 상태 흡수 전이·always-enabled fallback을
    가르쳐야 완주 후 막다른 상태(데드락)를 피한다. few-shot 예제도 데드락 없는 완전형이어야."""
    captured: list[str] = []

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        captured.append(system)
        return _VALID_LF

    assert translate_prose("아무거나", complete=complete).ok
    system = captured[0]
    assert "ABSORBING" in system  # 종료 상태 흡수 self-loop 규칙(HARD RULE 13)
    assert "no_deadlock` fails" in system  # 데드락 없음 조건의 근거 명시
    # few-shot 예제가 흡수 전이와 always-available fallback을 실제로 포함해야 한다.
    assert "done_absorb" in system and "save_up" in system


# ── 개선 2: 실패 후보 전문 + 행 번호가 되먹여지는가 ──────────────────────────


def test_repair_prompt_includes_full_numbered_source() -> None:
    """개선 2: 오류가 짚는 위치와 진짜 원인 줄이 다를 수 있으므로, 후보 전문을 행 번호와
    함께 되먹인다(단일 줄 인용 대체)."""
    multi = "domain {\n    hp: int 0..1000\n}\ncheck hp_ok: hp <= 1000\n"  # 4행 kind 누락

    calls: list[list[dict[str, str]]] = []

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        calls.append([dict(m) for m in messages])
        return multi if len(calls) == 1 else _VALID_LF

    result = translate_prose("HP 상한", complete=complete, max_attempts=2)
    assert result.ok
    repair = calls[1][-1]["content"]
    # 모든 원본 줄이 행 번호와 함께 들어가야 한다(1..4).
    assert "1 | domain {" in repair
    assert "4 | check hp_ok: hp <= 1000" in repair
    assert result.attempts[0].error.splitlines()[0] in repair  # 에러 메시지도 함께


# ── 개선 3: 게이트 통과 후 충실도 리뷰·재생성 ───────────────────────────────


def test_faithfulness_review_triggers_regeneration() -> None:
    """개선 3: 게이트를 통과해도(구문 OK) 충실도 리뷰가 문제를 짚으면 재생성해야 한다."""
    gen_calls = 0

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        nonlocal gen_calls
        gen_calls += 1
        return _VALID_LF  # 매번 구문상 유효 — 게이트는 통과, 리뷰가 판별

    reviews = 0

    def review(prose: str, tables_lf: str, candidate: str) -> str | None:
        nonlocal reviews
        reviews += 1
        return "PROBLEMS:\n1. 상한 규칙 누락" if reviews == 1 else None

    result = translate_prose("아무거나", complete=complete, review=review, max_attempts=3)
    assert result.ok
    assert len(result.attempts) == 2  # 1차 충실도 실패 → 2차 통과
    assert result.attempts[0].error is not None and "상한 규칙 누락" in result.attempts[0].error
    assert result.attempts[1].error is None


def test_faithful_first_try_no_regeneration() -> None:
    """리뷰가 충실 판정(None)이면 즉시 성공 — 1회로 끝난다."""

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        return _VALID_LF

    def review(prose: str, tables_lf: str, candidate: str) -> str | None:
        return None

    result = translate_prose("아무거나", complete=complete, review=review)
    assert result.ok and len(result.attempts) == 1


def test_review_disabled_by_default() -> None:
    """review 미주입이면 게이트만으로 판정(하위 호환) — 리뷰 없이 1회 통과."""

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        return _VALID_LF

    result = translate_prose("아무거나", complete=complete)
    assert result.ok and len(result.attempts) == 1


def test_make_reviewer_parses_verdict() -> None:
    """make_reviewer: FAITHFUL→None, PROBLEMS→피드백, 애매/빈 응답→None(멀쩡한 번역 보존)."""
    replies = iter(["FAITHFUL\n", "PROBLEMS:\n1. 수치 환각", "(불명확한 잡담)", ""])

    def complete(system: str, messages: list[dict[str, str]]) -> str:
        return next(replies)

    reviewer = make_reviewer(complete)
    assert reviewer("산문", "", _VALID_LF) is None  # FAITHFUL
    fb = reviewer("산문", "", _VALID_LF)
    assert fb is not None and "수치 환각" in fb  # PROBLEMS
    assert reviewer("산문", "", _VALID_LF) is None  # 애매 → 충실
    assert reviewer("산문", "", _VALID_LF) is None  # 빈 응답 → 충실
