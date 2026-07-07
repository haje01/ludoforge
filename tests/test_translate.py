"""웹 MVP: LLM 번역 서비스(산문 → .lf) 수리 루프 테스트 (D32 P3).

LLM은 가짜(complete 주입)로 대체한다 — 여기서 검증하는 건 루프의 기계 부분이다:
후보 추출(펜스), 로더·스키마 게이트 판정, 오류 피드백 재시도, 상한, 표 절 결합.
판정은 항상 로더·스키마(solver 경계)가 한다 — LLM 출력은 절대 그대로 신뢰하지 않는다.
"""

from __future__ import annotations

from web.translate import translate_prose

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
