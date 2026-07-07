"""Phase 2: 전이 시스템(D12) 프론트엔드 테스트 — 로더·스키마 검증.

core가 init/transitions/checks를 IR로 파싱하고, next.* 참조 무결성과
유한 상태(확률 백엔드 게이트, D13)를 검사하는지 본다. BMC/PRISM 검사는 Phase 3/4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ir import Check, Constraint, Outcome, RuleSet, Transition, Variable
from core.loader import LoaderError, load_rule_file
from core.schema import SchemaError, check_finite_state, validate

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"
_DOM = "domain { g: int 0..9 }\n"


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "t.lf"
    p.write_text(body, encoding="utf-8")
    return p


# ---------- 로더: 던전 픽스처 ----------


def test_loads_dungeon_transition_system() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.lf")

    assert rs.init == (
        "gold == 0 and room == hall and monster == none and status == exploring "
        "and l2_goblins == 2 and l2_dragons == 2 and fights == 0"
    )

    tids = [t.id for t in rs.transitions]
    assert tids == [
        "claim_victory",
        "enter_l1",
        "descend_l2",
        "descend_l3",
        "go_home",
        "fight_goblin_fighter",
        "fight_goblin_cleric",
        "fight_goblin_rogue",
        "fight_goblin_wizard",
        "fight_dragon_fighter",
        "fight_dragon_cleric",
        "fight_dragon_rogue",
        "fight_dragon_wizard",
        "won_absorb",
        "dead_absorb",
    ]

    # 결정적 전이(bare then, 다중 대입) → weight=1.0 단일 Outcome으로 정규화
    enter = next(t for t in rs.transitions if t.id == "enter_l1")
    assert enter.outcomes == (
        Outcome(then="next.room == l1 and next.monster == goblin", weight=1.0),
    )

    # 플레이어 선택(pref, D20·D26) — descend_l2는 적응적 욕심(남은 목표액 비례)을 단다
    descend = next(t for t in rs.transitions if t.id == "descend_l2")
    assert descend.pref == "max(win_gold - gold, 0)"

    # 확률 전이(fight_goblin_fighter) → 3-way: 승리/사망/무소득(rest).
    # 가중치는 chance/rest(D30)의 닫힌형 — fighter는 goblin 격파 목표값 4(P(2d6>=4)=33/36),
    # 치명 문턱 2(P(2d6<=2)=1/36), 잔여 무소득 2/36. 유리수 정확 계산 후 float lowering.
    fight = next(t for t in rs.transitions if t.id == "fight_goblin_fighter")
    assert len(fight.outcomes) == 3
    # 보상은 상한(30)에서 포화(min) — 가드 없이 오버플로 회피.
    assert (fight.outcomes[0].weight, fight.outcomes[0].then) == (
        33 / 36,
        "next.gold == min(gold + 2, 30) and next.monster == none and next.fights == fights + 1",
    )
    assert fight.outcomes[1].weight == 1 / 36
    assert fight.outcomes[2].weight == 2 / 36


def test_loads_dungeon_properties() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    by_id = {p.id: p for p in rs.checks}

    assert by_id["winnable"].kind == "reachable"
    assert by_id["winnable"].that == "status == won"
    assert by_id["gold_nonneg"].kind == "invariant"


def test_transition_source_is_filename() -> None:
    rs = load_rule_file(EXAMPLES / "dungeon.lf")
    assert all(t.source == "dungeon.lf" for t in rs.transitions)


# ---------- 로더: 구조 오류 ----------


def test_transition_with_both_then_and_outcomes_rejected(tmp_path: Path) -> None:
    # 전이 효과는 then 또는 outcomes 중 하나 — 문법이 둘의 병기를 거부한다.
    body = _DOM + "transition t:\n    then g = 0\n    outcomes:\n        1 -> g = 1\n"
    with pytest.raises(LoaderError):
        load_rule_file(_write(tmp_path, body))


def test_transition_with_neither_then_nor_outcomes_rejected(tmp_path: Path) -> None:
    body = _DOM + "transition t:\n"
    with pytest.raises(LoaderError):
        load_rule_file(_write(tmp_path, body))


def test_negative_weight_rejected_by_schema(tmp_path: Path) -> None:
    # 음수는 문법이 아니라 스키마가 거부한다(D26 상태 식 weight 허용으로 파서는 식만 본다).
    body = _DOM + "init: g == 0\ntransition t:\n    outcomes:\n        -0.5 -> g = 0\n"
    with pytest.raises(SchemaError, match="음수"):
        validate(load_rule_file(_write(tmp_path, body)))


# ---------- 로더: 전이 선호도 pref (D20, 무작위 정책) ----------


def test_transition_pref_defaults_to_none(tmp_path: Path) -> None:
    """pref 미선언 전이는 None(=미선언, D20) — co-enabled에 섞이면 sim이 거부한다."""
    body = _DOM + "transition t:\n    then g = 1\n"
    rs = load_rule_file(_write(tmp_path, body))
    assert rs.transitions[0].pref is None


def test_transition_pref_parsed(tmp_path: Path) -> None:
    """pref가 IR에 실린다 — 플레이어 선택의 상대 가중치(D20)."""
    body = (
        _DOM
        + "transition a:\n    pref 0.3\n    then g = 1\n"
        + "transition b:\n    pref 0.7\n    then g = 2\n"
    )
    rs = load_rule_file(_write(tmp_path, body))
    assert (rs.transitions[0].pref, rs.transitions[1].pref) == (0.3, 0.7)


def test_negative_pref_rejected_by_schema(tmp_path: Path) -> None:
    # 음수는 스키마가 거부한다(D26 상태 식 pref 허용으로 파서는 식만 본다).
    body = _DOM + "init: g == 0\ntransition t:\n    pref -1\n    then g = 0\n"
    with pytest.raises(SchemaError, match="음수"):
        validate(load_rule_file(_write(tmp_path, body)))


def test_pref_from_table_stays_float(tmp_path: Path) -> None:
    """표 색인 pref는 desugar가 수치로 해소한다(D18) — 표에서 정책을 끌어올 수 있다."""
    body = (
        _DOM
        + "table policy { go: 0.4 }\n"
        + 'for k in [go]:\n    transition "t_${k}":\n        pref policy[k]\n        then g = 1\n'
    )
    rs = load_rule_file(_write(tmp_path, body))
    assert rs.transitions[0].pref == 0.4


def test_schema_rejects_negative_pref() -> None:
    """IR을 직접 만들어도 음수 pref는 스키마가 거부(방어적 검증, D20)."""
    rs = RuleSet(
        variables=(Variable(name="g", type="int", min=0, max=9),),
        transitions=(Transition(id="t", pref=-0.5, outcomes=(Outcome(then="next.g == 0"),)),),
    )
    with pytest.raises(SchemaError, match="pref"):
        validate(rs)


def test_property_invalid_kind_rejected(tmp_path: Path) -> None:
    # kind 어휘는 문법이 고정한다(reachable/invariant/no_deadlock/distribution).
    body = _DOM + "check p bogus: g == 0\n"
    with pytest.raises(LoaderError):
        load_rule_file(_write(tmp_path, body))


def test_reachable_property_requires_that(tmp_path: Path) -> None:
    body = _DOM + "check p reachable:\n"
    with pytest.raises(LoaderError):
        load_rule_file(_write(tmp_path, body))


# ---------- 스키마: next.* 참조 무결성 ----------


def test_dungeon_fixture_validates() -> None:
    validate(load_rule_file(EXAMPLES / "dungeon.lf"))  # 예외 없으면 통과


def test_next_in_rule_then_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("gold", "int", 0, 100),),
        constraints=(Constraint(id="r", then="next.gold == 0"),),
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
        checks=(Check(id="p", kind="reachable", that="hp == 0"),),
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
        checks=(
            Check(id="p", kind="invariant", that="gold >= 0"),
            Check(id="p", kind="invariant", that="gold <= 100"),
        ),
    )
    with pytest.raises(SchemaError, match="중복된 check id"):
        validate(rs)


def test_existing_static_fixture_still_validates() -> None:
    # 하위 호환: 전이 시스템이 없는 기존 정적 룰셋은 그대로 통과해야 한다.
    validate(load_rule_file(FIXTURES / "warrior_hp.lf"))


# ---------- 유한 상태(확률 백엔드 게이트, D13) ----------


def test_check_finite_state_passes_for_dungeon() -> None:
    check_finite_state(load_rule_file(EXAMPLES / "dungeon.lf"))  # 모두 유한 → 통과


def test_check_finite_state_rejects_unbounded_int() -> None:
    rs = RuleSet(variables=(Variable("hp", "int", 0, None),))
    with pytest.raises(SchemaError, match="hp"):
        check_finite_state(rs)


def test_check_finite_state_rejects_real() -> None:
    rs = RuleSet(variables=(Variable("p", "real", 0.0, 1.0),))
    with pytest.raises(SchemaError, match="실수"):
        check_finite_state(rs)
