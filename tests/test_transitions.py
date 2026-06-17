"""Phase 2: 전이 시스템(D12) 프론트엔드 테스트 — 로더·스키마 검증.

forge_core가 init/transitions/properties를 IR로 파싱하고, next.* 참조 무결성과
유한 상태(ProbForge 게이트, D13)를 검사하는지 본다. BMC/PRISM 검사는 Phase 3/4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_core.ir import Outcome, Property, Rule, RuleSet, Transition, Variable
from forge_core.loader import LoaderError, load_rule_file
from forge_core.schema import SchemaError, check_finite_state, validate

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"
_DOM = "domain: {variables: {g: {type: int, min: 0, max: 9}}}\n"


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "t.rule"
    p.write_text(body, encoding="utf-8")
    return p


# ---------- 로더: 던전 픽스처 ----------


def test_loads_dungeon_transition_system() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.rule")

    assert rs.init == "gold == 0 and room == center"

    tids = [t.id for t in rs.transitions]
    assert tids == ["descend_to_l1", "fight_l1", "return_to_center"]

    # 결정적 전이(bare then) → weight=1.0 단일 Outcome으로 정규화
    descend = rs.transitions[0]
    assert descend.when == "room == center"
    assert descend.outcomes == (Outcome(then="next.room == l1", weight=1.0),)

    # 확률 전이 → 가중치 보존
    fight = rs.transitions[1]
    assert len(fight.outcomes) == 2
    assert (fight.outcomes[0].weight, fight.outcomes[0].then) == (0.7, "next.gold == gold + 5")
    assert fight.outcomes[1].weight == 0.3


def test_loads_dungeon_properties() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.rule")
    by_id = {p.id: p for p in rs.properties}

    assert by_id["winnable"].kind == "reachable"
    assert by_id["winnable"].that == "gold >= win_gold and room == center"
    assert by_id["gold_nonneg"].kind == "invariant"
    likely = by_id["likely_win"]
    assert likely.kind == "prob"
    assert likely.spec is not None and likely.spec.startswith("Pmax=?")
    assert likely.that is None


def test_transition_source_is_filename() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.rule")
    assert all(t.source == "dungeon.rule" for t in rs.transitions)


# ---------- 로더: 구조 오류 ----------


def test_transition_with_both_then_and_outcomes_rejected(tmp_path: Path) -> None:
    body = (
        "domain: {variables: {g: {type: int, min: 0, max: 9}}}\n"
        "transitions:\n"
        "  - id: t\n"
        "    then: 'next.g == 0'\n"
        "    outcomes: [{weight: 1, then: 'next.g == 1'}]\n"
    )
    with pytest.raises(LoaderError, match="하나만"):
        load_rule_file(_write(tmp_path, body))


def test_transition_with_neither_then_nor_outcomes_rejected(tmp_path: Path) -> None:
    body = "domain: {variables: {g: {type: int, min: 0, max: 9}}}\ntransitions:\n  - id: t\n"
    with pytest.raises(LoaderError, match="then.*outcomes"):
        load_rule_file(_write(tmp_path, body))


def test_negative_weight_rejected(tmp_path: Path) -> None:
    body = (
        "domain: {variables: {g: {type: int, min: 0, max: 9}}}\n"
        "transitions:\n  - id: t\n    outcomes: [{weight: -0.5, then: 'next.g == 0'}]\n"
    )
    with pytest.raises(LoaderError, match="음수"):
        load_rule_file(_write(tmp_path, body))


def test_property_invalid_kind_rejected(tmp_path: Path) -> None:
    body = _DOM + "properties:\n  - {id: p, kind: bogus}\n"
    with pytest.raises(LoaderError, match="kind"):
        load_rule_file(_write(tmp_path, body))


def test_reachable_property_requires_that(tmp_path: Path) -> None:
    body = _DOM + "properties:\n  - {id: p, kind: reachable}\n"
    with pytest.raises(LoaderError, match="that"):
        load_rule_file(_write(tmp_path, body))


def test_prob_property_requires_spec(tmp_path: Path) -> None:
    body = _DOM + "properties:\n  - {id: p, kind: prob}\n"
    with pytest.raises(LoaderError, match="spec"):
        load_rule_file(_write(tmp_path, body))


# ---------- 스키마: next.* 참조 무결성 ----------


def test_dungeon_fixture_validates() -> None:
    validate(load_rule_file(EXAMPLES / "dungeon.rule"))  # 예외 없으면 통과


def test_next_in_rule_then_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        rules=(Rule(id="r", then="next.gold == 0"),),
    )
    with pytest.raises(SchemaError, match="전이 then에서만"):
        validate(rs)


def test_next_unknown_variable_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        transitions=(Transition(id="t", outcomes=(Outcome(then="next.hp == 0"),)),),
    )
    with pytest.raises(SchemaError, match="다음 상태"):
        validate(rs)


def test_undefined_symbol_in_transition_when_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        transitions=(
            Transition(id="t", when="hp > 0", outcomes=(Outcome(then="next.gold == 0"),)),
        ),
    )
    with pytest.raises(SchemaError, match="'hp'"):
        validate(rs)


def test_undefined_symbol_in_property_that_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        properties=(Property(id="p", kind="reachable", that="hp == 0"),),
    )
    with pytest.raises(SchemaError, match="'hp'"):
        validate(rs)


def test_init_next_reference_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        init="next.gold == 0",
    )
    with pytest.raises(SchemaError, match="전이 then에서만"):
        validate(rs)


def test_duplicate_transition_id_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        transitions=(
            Transition(id="t", outcomes=(Outcome(then="next.gold == 0"),)),
            Transition(id="t", outcomes=(Outcome(then="next.gold == 1"),)),
        ),
    )
    with pytest.raises(SchemaError, match="중복된 transition id"):
        validate(rs)


def test_duplicate_property_id_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        properties=(
            Property(id="p", kind="invariant", that="gold >= 0"),
            Property(id="p", kind="invariant", that="gold <= 100"),
        ),
    )
    with pytest.raises(SchemaError, match="중복된 property id"):
        validate(rs)


def test_existing_static_fixture_still_validates() -> None:
    # 하위 호환: 전이 시스템이 없는 기존 정적 룰셋은 그대로 통과해야 한다.
    validate(load_rule_file(FIXTURES / "warrior_hp.rule"))


# ---------- 유한 상태(ProbForge 게이트, D13) ----------


def test_check_finite_state_passes_for_dungeon() -> None:
    check_finite_state(load_rule_file(EXAMPLES / "dungeon.rule"))  # 모두 유한 → 통과


def test_check_finite_state_rejects_unbounded_int() -> None:
    rs = RuleSet(variables=(Variable("hp", "int", 0, None),))
    with pytest.raises(SchemaError, match="hp"):
        check_finite_state(rs)


def test_check_finite_state_rejects_real() -> None:
    rs = RuleSet(variables=(Variable("p", "real", 0.0, 1.0),))
    with pytest.raises(SchemaError, match="실수"):
        check_finite_state(rs)
