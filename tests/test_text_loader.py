"""외부 DSL(자체 문법) 텍스트 로더 테스트 — 6차 마일스톤(D21).

S1: `domain { ... }` 블록 → 기존 Variable 튜플.
S2: `init`·`constraints`·`expects`의 `==` 술어 → 기존 IR 문자열(파이썬-식).
새 프론트엔드의 산출 IR이 YAML 로더와 일치함을 골든 등가로 고정한다(§8). 표현식 문자열은
공백·괄호 차이에 무관하게 **ast 구조**로 비교한다(렌더링 표기는 자유).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.ir import RuleSet, Variable
from core.loader import LoaderError, load_rule_file, load_rules
from core.schema import SchemaError, validate
from core.text_loader import TextLoaderError, parse_rule_text

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
# 디프리케이트된 YAML(.rule) 골든 참조는 old_examples/로 분리(이관 회귀 하니스 전용).
_OLD_EXAMPLES = Path(__file__).resolve().parent.parent / "old_examples"


def _expr_eq(a: str | None, b: str | None) -> bool:
    """두 표현식 문자열이 ast 구조로 동일한가(공백·괄호 무관)."""
    if a is None or b is None:
        return a is b
    return ast.dump(ast.parse(a, mode="eval")) == ast.dump(ast.parse(b, mode="eval"))


def _assert_ir_equiv(native: RuleSet, yaml: RuleSet) -> None:
    """RuleSet 골든 등가: 변수는 바이트 동일, 표현식 문자열은 ast 구조 동일."""
    assert native.variables == yaml.variables
    assert _expr_eq(native.init, yaml.init)
    assert len(native.constraints) == len(yaml.constraints)
    for n, y in zip(native.constraints, yaml.constraints, strict=True):
        assert n.id == y.id
        assert _expr_eq(n.when, y.when)
        assert _expr_eq(n.then, y.then)
        assert n.desc == y.desc
        assert n.author == y.author
    assert len(native.expects) == len(yaml.expects)
    for ne, ye in zip(native.expects, yaml.expects, strict=True):
        assert ne.id == ye.id
        assert _expr_eq(ne.that, ye.that)
        assert ne.desc == ye.desc
    assert len(native.transitions) == len(yaml.transitions)
    for nt, yt in zip(native.transitions, yaml.transitions, strict=True):
        assert nt.id == yt.id
        assert _expr_eq(nt.when, yt.when)
        assert nt.pref == yt.pref
        assert nt.desc == yt.desc
        assert len(nt.outcomes) == len(yt.outcomes)
        for no, yo in zip(nt.outcomes, yt.outcomes, strict=True):
            assert no.weight == yo.weight
            assert _expr_eq(no.then, yo.then)
    assert len(native.checks) == len(yaml.checks)
    for nc, yc in zip(native.checks, yaml.checks, strict=True):
        assert nc.id == yc.id
        assert nc.kind == yc.kind
        assert _expr_eq(nc.that, yc.that)  # reachable/invariant
        assert _expr_eq(nc.expr, yc.expr)  # distribution(sim 수치식)
        assert nc.desc == yc.desc


def test_domain_int_both_bounds() -> None:
    rs = parse_rule_text("domain { gold: int 0..30 }")
    assert rs.variables == (Variable(name="gold", type="int", min=0, max=30),)


def test_domain_int_min_only() -> None:
    # warrior_hp 예제처럼 한쪽 경계만 둘 수 있어야 한다(YAML의 min만 지정과 동형).
    rs = parse_rule_text("domain { hp: int 0.. }")
    assert rs.variables == (Variable(name="hp", type="int", min=0, max=None),)


def test_domain_int_unbounded() -> None:
    rs = parse_rule_text("domain { n: int }")
    assert rs.variables == (Variable(name="n", type="int", min=None, max=None),)


def test_domain_real_bounds_are_floats() -> None:
    rs = parse_rule_text("domain { drop: real 0..1 }")
    (v,) = rs.variables
    assert v == Variable(name="drop", type="real", min=0.0, max=1.0)
    assert isinstance(v.min, float) and isinstance(v.max, float)


def test_domain_bool_has_no_bounds() -> None:
    rs = parse_rule_text("domain { stealthed: bool }")
    assert rs.variables == (Variable(name="stealthed", type="bool"),)


def test_domain_enum_values() -> None:
    rs = parse_rule_text("domain { room: enum { hall, l1, l2 } }")
    assert rs.variables == (Variable(name="room", type="enum", values=("hall", "l1", "l2")),)


def test_domain_multiple_vars_preserve_order() -> None:
    src = """
    domain {
        gold: int 0..30
        room: enum { hall, l1 }
        drop: real 0..1
        flag: bool
    }
    """
    rs = parse_rule_text(src)
    assert [v.name for v in rs.variables] == ["gold", "room", "drop", "flag"]


def test_line_comments_ignored() -> None:
    src = """
    // 던전 도메인
    domain {
        gold: int 0..30   // 보물
    }
    """
    rs = parse_rule_text(src)
    assert rs.variables == (Variable(name="gold", type="int", min=0, max=30),)


def test_int_bound_with_decimal_rejected() -> None:
    # int 경계는 정수여야 한다(_parse_opt_int와 동형).
    with pytest.raises(TextLoaderError):
        parse_rule_text("domain { gold: int 0..3.5 }")


def test_syntax_error_reports_position() -> None:
    with pytest.raises(TextLoaderError) as exc:
        parse_rule_text("domain { gold: int 0..30 ")  # 닫는 중괄호 누락
    # 위치(줄/열)를 포함해 보고한다(파서 직접 소유의 이점, §7).
    assert "1" in str(exc.value)


def test_golden_equivalence_with_yaml_domain(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """같은 도메인을 YAML과 자체 문법으로 두면 IR Variable 튜플이 바이트 동일해야 한다."""
    yaml_src = """
domain:
  variables:
    gold:  { type: int, min: 0, max: 30 }
    room:  { type: enum, values: [hall, l1, l2] }
    drop:  { type: real, min: 0, max: 1 }
    flag:  { type: bool }
"""
    yaml_file = tmp_path / "d.rule"
    yaml_file.write_text(yaml_src, encoding="utf-8")
    yaml_rs = load_rule_file(yaml_file)

    native_src = """
    domain {
        gold: int 0..30
        room: enum { hall, l1, l2 }
        drop: real 0..1
        flag: bool
    }
    """
    native_rs = parse_rule_text(native_src)
    assert native_rs.variables == yaml_rs.variables


# ── S2: 정적 표현식(init·constraints·expects) ──────────────────────────────


def test_init_predicate() -> None:
    rs = parse_rule_text("domain { gold: int 0..30 } init: gold == 0")
    assert _expr_eq(rs.init, "gold == 0")


def test_init_conjunction() -> None:
    rs = parse_rule_text(
        "domain { gold: int 0..9  room: enum { hall, l1 } } init: gold == 0 and room == hall"
    )
    assert _expr_eq(rs.init, "gold == 0 and room == hall")


def test_constraint_when_then() -> None:
    src = """
    domain { level: int 1..100  hp: int 0.. }
    constraint warrior_hp:
        when role == warrior
        then hp == level * 100
    """
    rs = parse_rule_text(src)
    (c,) = rs.constraints
    assert c.id == "warrior_hp"
    assert _expr_eq(c.when, "role == warrior")
    assert _expr_eq(c.then, "hp == level * 100")


def test_constraint_without_when() -> None:
    src = """
    domain { hp: int 0.. }
    constraint global_cap:
        then hp <= 5000
    """
    rs = parse_rule_text(src)
    (c,) = rs.constraints
    assert c.when is None
    assert _expr_eq(c.then, "hp <= 5000")


def test_constraint_quoted_id() -> None:
    rs = parse_rule_text('domain { hp: int 0.. } constraint "cap_rule": then hp <= 10')
    assert rs.constraints[0].id == "cap_rule"


def test_expect_predicate() -> None:
    src = """
    domain { level: int 1..100  role: enum { warrior, mage } }
    expect warrior_max: role == warrior and level == 100
    """
    rs = parse_rule_text(src)
    (e,) = rs.expects
    assert e.id == "warrior_max"
    assert _expr_eq(e.that, "role == warrior and level == 100")


def test_arithmetic_precedence_preserved() -> None:
    # a + b * c → 곱이 먼저(파이썬 동일). ast 구조로 확인.
    rs = parse_rule_text("domain { x: int 0.. } constraint c: then x == 1 + 2 * 3")
    assert _expr_eq(rs.constraints[0].then, "x == 1 + 2 * 3")
    # 잘못된 결합(괄호)으로는 동등하지 않아야 한다(테스트가 무의미하지 않음을 보증).
    assert not _expr_eq(rs.constraints[0].then, "x == (1 + 2) * 3")


def test_paren_grouping() -> None:
    rs = parse_rule_text("domain { a: bool  b: bool  c: bool } constraint c: then (a or b) and c")
    assert _expr_eq(rs.constraints[0].then, "(a or b) and c")


def test_constant_division_kept() -> None:
    # 상수 분모 나눗셈(D7) — 1/3이 유리수로 보존되도록 식 표기 유지.
    rs = parse_rule_text("domain { p: real 0..1 } constraint c: then p == 1 / 3")
    assert _expr_eq(rs.constraints[0].then, "p == 1 / 3")


def test_assignment_equals_rejected_in_predicate() -> None:
    # 단독 `=`는 대입(전이 효과 전용, S3) — 술어 위치에선 구문 오류여야 한다(D21 판별).
    with pytest.raises(TextLoaderError):
        parse_rule_text("domain { gold: int 0..9 } init: gold = 0")


def test_duplicate_init_rejected() -> None:
    with pytest.raises(TextLoaderError):
        parse_rule_text("domain { g: int 0..9 } init: g == 0 init: g == 1")


def test_golden_equivalence_static(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """도메인+init+constraints+expects를 YAML과 자체 문법으로 두면 IR이 등가여야 한다."""
    yaml_src = """
domain:
  variables:
    level: { type: int, min: 1, max: 100 }
    hp:    { type: int, min: 0 }
    role:  { type: enum, values: [warrior, mage] }
init: "hp == 0"
constraints:
  - id: warrior_hp
    when: "role == warrior"
    then: "hp == level * 100"
  - id: global_cap
    then: "hp <= 5000"
expects:
  - id: warrior_max
    that: "role == warrior and level == 100"
"""
    yaml_file = tmp_path / "s.rule"
    yaml_file.write_text(yaml_src, encoding="utf-8")
    yaml_rs = load_rule_file(yaml_file)

    native_src = """
    domain {
        level: int 1..100
        hp:    int 0..
        role:  enum { warrior, mage }
    }
    init: hp == 0
    constraint warrior_hp:
        when role == warrior
        then hp == level * 100
    constraint global_cap:
        then hp <= 5000
    expect warrior_max: role == warrior and level == 100
    """
    native_rs = parse_rule_text(native_src)
    _assert_ir_equiv(native_rs, yaml_rs)


# ── S3: 전이(transitions·outcomes·pref, `=` 대입/`==` 비교 판별) ───────────────


def test_transition_bare_then_is_assignment() -> None:
    src = """
    domain { room: enum { hall, l1 } }
    transition descend:
        when room == hall
        then room = l1
    """
    rs = parse_rule_text(src)
    (t,) = rs.transitions
    assert t.id == "descend"
    assert _expr_eq(t.when, "room == hall")
    assert t.pref is None
    assert len(t.outcomes) == 1
    assert t.outcomes[0].weight == 1.0
    # `room = l1` → 다음 상태 제약 `next.room == l1`로 lowering.
    assert _expr_eq(t.outcomes[0].then, "next.room == l1")


def test_transition_outcomes_weights() -> None:
    src = """
    domain { gold: int 0..9999 room: enum { l2 } }
    transition fight:
        when room == l2
        outcomes:
            0.7 -> gold = gold + 500
            0.3 -> gold = gold
    """
    rs = parse_rule_text(src)
    (t,) = rs.transitions
    assert [o.weight for o in t.outcomes] == [0.7, 0.3]
    assert _expr_eq(t.outcomes[0].then, "next.gold == gold + 500")
    assert _expr_eq(t.outcomes[1].then, "next.gold == gold")


def test_min_call_in_effect_lowers_to_python_expr() -> None:
    # 효과 RHS의 min(...)이 파이썬-식 문자열로 lowering된다(다운스트림 ast가 소비).
    src = """
    domain { g: int 0..30 room: enum { a, b } }
    transition t:
        when room == a
        then { g = min(g + 10, 30); room = b }
    """
    rs = parse_rule_text(src)
    then = rs.transitions[0].outcomes[0].then
    assert _expr_eq(then, "next.g == min(g + 10, 30) and next.room == b")


def test_min_call_with_table_index_arg_desugars() -> None:
    # min 인자 안의 표 색인(reward[mon])도 desugar가 리터럴로 해소한다.
    src = """
    domain { g: int 0..30 monster: enum { goblin, dragon } }
    table reward { goblin: 2, dragon: 10 }
    for mon in [goblin, dragon]:
        transition "hit_${mon}":
            when monster == mon
            then g = min(g + reward[mon], 30)
    """
    rs = parse_rule_text(src)
    by_id = {t.id: t for t in rs.transitions}
    assert _expr_eq(by_id["hit_dragon"].outcomes[0].then, "next.g == min(g + 10, 30)")


def test_transition_multi_assignment() -> None:
    # `{ a = ..; b = .. }` 병렬 대입 → `and` 결합.
    src = """
    domain { gold: int 0..9  room: enum { hall }  status: enum { dead } }
    transition die:
        then { gold = 0; room = hall; status = dead }
    """
    rs = parse_rule_text(src)
    (t,) = rs.transitions
    assert _expr_eq(
        t.outcomes[0].then,
        "next.gold == 0 and next.room == hall and next.status == dead",
    )


def test_transition_pref() -> None:
    src = """
    domain { room: enum { l2, l3 } }
    transition dive:
        when room == l2
        pref 0.3
        then room = l3
    """
    rs = parse_rule_text(src)
    (t,) = rs.transitions
    assert t.pref == 0.3


def test_effect_comparison_rejected() -> None:
    # 효과 위치에서 `==`(비교)는 거부 — 효과는 대입(`=`)이어야 한다(D21·D22).
    src = "domain { room: enum { l1 } } transition t: then room == l1"
    with pytest.raises(TextLoaderError):
        parse_rule_text(src)


def test_guard_assignment_rejected() -> None:
    # 가드(`when`)에서 단독 `=`(대입)는 거부 — 술어는 `==`(같은 상태)여야 한다(D22).
    src = "domain { room: enum { l1 } } transition t: when room = l1 then room = l1"
    with pytest.raises(TextLoaderError):
        parse_rule_text(src)


def test_golden_equivalence_transitions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """전이 시스템을 YAML과 자체 문법으로 두면 IR이 등가여야 한다(가드·outcomes·pref·프레임)."""
    yaml_src = """
domain:
  variables:
    gold:   { type: int, min: 0, max: 30 }
    room:   { type: enum, values: [hall, l1, l2] }
    status: { type: enum, values: [exploring, won, dead] }
init: "gold == 0 and room == hall and status == exploring"
transitions:
  - id: enter_l1
    when: "room == hall and status == exploring"
    then: "next.room == l1"
  - id: fight
    when: "room == l1 and status == exploring"
    outcomes:
      - { weight: 0.7, then: "next.gold == gold + 10" }
      - { weight: 0.3, then: "next.status == dead and next.gold == 0" }
  - id: dive
    when: "room == l1"
    pref: 0.3
    then: "next.room == l2"
checks: []
"""
    yaml_file = tmp_path / "t.rule"
    yaml_file.write_text(yaml_src, encoding="utf-8")
    yaml_rs = load_rule_file(yaml_file)

    native_src = """
    domain {
        gold:   int 0..30
        room:   enum { hall, l1, l2 }
        status: enum { exploring, won, dead }
    }
    init: gold == 0 and room == hall and status == exploring
    transition enter_l1:
        when room == hall and status == exploring
        then room = l1
    transition fight:
        when room == l1 and status == exploring
        outcomes:
            0.7 -> gold = gold + 10
            0.3 -> { status = dead; gold = 0 }
    transition dive:
        when room == l1
        pref 0.3
        then room = l2
    """
    native_rs = parse_rule_text(native_src)
    _assert_ir_equiv(native_rs, yaml_rs)


# ── S4: checks(reachable/invariant/no_deadlock/distribution) ─────────────


def test_check_reachable() -> None:
    rs = parse_rule_text("domain { gold: int 0..9999 } check winnable reachable: gold >= 10000")
    (c,) = rs.checks
    assert c.id == "winnable" and c.kind == "reachable"
    assert _expr_eq(c.that, "gold >= 10000")
    assert c.expr is None


def test_check_invariant() -> None:
    rs = parse_rule_text("domain { gold: int 0.. } check gold_ok invariant: gold >= 0")
    (c,) = rs.checks
    assert c.kind == "invariant"
    assert _expr_eq(c.that, "gold >= 0")


def test_check_no_deadlock() -> None:
    rs = parse_rule_text("domain { g: int 0..9 } check no_stuck no_deadlock")
    (c,) = rs.checks
    assert c.kind == "no_deadlock"
    assert c.that is None and c.expr is None


def test_check_prob_kind_rejected() -> None:
    # PCTL `prob` check은 D23으로 제거 — `.lf` 문법에서 더는 받지 않는다(파싱 오류).
    with pytest.raises(TextLoaderError):
        parse_rule_text(
            'domain { room: enum { center } } check likely prob: "Pmax=? [ F (room=center) ]"'
        )


def test_check_distribution_is_sim_expr() -> None:
    rs = parse_rule_text("domain { gold: int 0..30 } check gold_dist distribution: gold")
    (c,) = rs.checks
    assert c.kind == "distribution"
    assert _expr_eq(c.expr, "gold")
    assert c.that is None


def test_golden_equivalence_checks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """다섯 가지 check kind를 YAML과 자체 문법으로 두면 IR이 등가여야 한다(dialect 보존)."""
    yaml_src = """
domain:
  variables:
    gold: { type: int, min: 0, max: 30 }
    room: { type: enum, values: [hall, center] }
checks:
  - { id: winnable,  kind: reachable, that: "gold >= 20 and room == center" }
  - { id: gold_ok,   kind: invariant, that: "gold >= 0" }
  - { id: no_stuck,  kind: no_deadlock }
  - { id: gold_dist, kind: distribution, expr: "gold" }
"""
    yaml_file = tmp_path / "c.rule"
    yaml_file.write_text(yaml_src, encoding="utf-8")
    yaml_rs = load_rule_file(yaml_file)

    native_src = """
    domain {
        gold: int 0..30
        room: enum { hall, center }
    }
    check winnable  reachable: gold >= 20 and room == center
    check gold_ok   invariant: gold >= 0
    check no_stuck  no_deadlock
    check gold_dist distribution: gold
    """
    native_rs = parse_rule_text(native_src)
    _assert_ir_equiv(native_rs, yaml_rs)


# ── S5: 템플릿(table·for·${} desugar) ─────────────────────────────────────────


def test_for_cartesian_product_order_and_id_interp() -> None:
    # 곱 순서 = 바인딩 선언 순서(로더와 동형), id는 ${}로 보간.
    src = """
    domain {
        monster: enum { goblin, dragon }
        role:    enum { fighter, rogue }
        gold:    int 0..99
    }
    for mon in [goblin, dragon], cls in [fighter, rogue]:
        transition "fight_${mon}_${cls}":
            when role == cls and monster == mon
            then gold = gold
    """
    rs = parse_rule_text(src)
    assert [t.id for t in rs.transitions] == [
        "fight_goblin_fighter",
        "fight_goblin_rogue",
        "fight_dragon_fighter",
        "fight_dragon_rogue",
    ]
    # loop 변수가 식에서 값으로 치환됐는가.
    assert _expr_eq(rs.transitions[0].when, "role == fighter and monster == goblin")


def test_table_index_in_guard_weight_rhs() -> None:
    src = """
    domain { gold: int 0..99  monster: enum { goblin, dragon } }
    table reward { goblin: 2, dragon: 10 }
    table cap    { goblin: 28, dragon: 20 }
    table win {
        goblin: { fighter: 0.9 }
        dragon: { fighter: 0.6 }
    }
    for mon in [goblin, dragon], cls in [fighter]:
        transition "fight_${mon}_${cls}":
            when monster == mon and gold <= cap[mon]
            outcomes:
                win[mon][cls] -> gold = gold + reward[mon]
    """
    rs = parse_rule_text(src)
    t0 = rs.transitions[0]  # goblin/fighter
    assert _expr_eq(t0.when, "monster == goblin and gold <= 28")
    assert t0.outcomes[0].weight == 0.9
    assert _expr_eq(t0.outcomes[0].then, "next.gold == gold + 2")
    t1 = rs.transitions[1]  # dragon/fighter
    assert _expr_eq(t1.when, "monster == dragon and gold <= 20")
    assert t1.outcomes[0].weight == 0.6
    assert _expr_eq(t1.outcomes[0].then, "next.gold == gold + 10")


def test_for_over_constraints() -> None:
    src = """
    domain { win_gold: int 0..99  role: enum { rogue, wizard } }
    table target { rogue: 10, wizard: 30 }
    for cls in [rogue, wizard]:
        constraint "${cls}_target":
            when role == cls
            then win_gold == target[cls]
    """
    rs = parse_rule_text(src)
    assert [c.id for c in rs.constraints] == ["rogue_target", "wizard_target"]
    assert _expr_eq(rs.constraints[0].then, "win_gold == 10")
    assert _expr_eq(rs.constraints[1].then, "win_gold == 30")


def test_undefined_table_rejected() -> None:
    src = """
    domain { gold: int 0..9  m: enum { a } }
    for x in [a]:
        transition t:
            when gold <= cap[x]
            then gold = gold
    """
    with pytest.raises(TextLoaderError):
        parse_rule_text(src)


def test_undefined_index_param_rejected() -> None:
    src = """
    domain { gold: int 0..9 }
    table reward { a: 1 }
    for x in [a]:
        transition t:
            then gold = gold + reward[y]
    """
    with pytest.raises(TextLoaderError):
        parse_rule_text(src)


def test_golden_equivalence_templates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """for/tables/${}를 YAML과 자체 문법으로 두면 펼친 IR이 등가여야 한다(D18 동형)."""
    yaml_src = """
domain:
  variables:
    gold:    { type: int, min: 0, max: 30 }
    monster: { type: enum, values: [goblin, dragon] }
    role:    { type: enum, values: [fighter, rogue] }
    status:  { type: enum, values: [exploring, dead] }
tables:
  reward: { goblin: 2, dragon: 10 }
  cap:    { goblin: 28, dragon: 20 }
  win:
    goblin: { fighter: 0.9, rogue: 0.7 }
    dragon: { fighter: 0.6, rogue: 0.2 }
transitions:
  - id: "fight_${mon}_${cls}"
    for: { mon: [goblin, dragon], cls: [fighter, rogue] }
    when: "role == ${cls} and monster == ${mon} and gold <= ${cap[mon]}"
    outcomes:
      - { weight: "${win[mon][cls]}", then: "next.gold == gold + ${reward[mon]}" }
      - { weight: 0.1, then: "next.status == dead" }
"""
    yaml_file = tmp_path / "tmpl.rule"
    yaml_file.write_text(yaml_src, encoding="utf-8")
    yaml_rs = load_rule_file(yaml_file)

    native_src = """
    domain {
        gold:    int 0..30
        monster: enum { goblin, dragon }
        role:    enum { fighter, rogue }
        status:  enum { exploring, dead }
    }
    table reward { goblin: 2, dragon: 10 }
    table cap    { goblin: 28, dragon: 20 }
    table win {
        goblin: { fighter: 0.9, rogue: 0.7 }
        dragon: { fighter: 0.6, rogue: 0.2 }
    }
    for mon in [goblin, dragon], cls in [fighter, rogue]:
        transition "fight_${mon}_${cls}":
            when role == cls and monster == mon and gold <= cap[mon]
            outcomes:
                win[mon][cls] -> gold = gold + reward[mon]
                0.1 -> status = dead
    """
    native_rs = parse_rule_text(native_src)
    _assert_ir_equiv(native_rs, yaml_rs)


# ── S6: 전체 코퍼스 골든 등가 + loop-var 충돌 감지 ──────────────────────────────


@pytest.mark.parametrize("lf_path", sorted(_EXAMPLES.glob("*.lf")), ids=lambda p: p.stem)
def test_example_lf_matches_yaml(lf_path: Path) -> None:
    """이관된 examples/*.lf는 같은 이름의 *.rule(YAML)과 IR 등가여야 한다(이관 회귀 하니스).

    새 .lf를 추가하면 자동으로 등가가 검증된다. 대응 YAML이 없으면 건너뛴다.
    YAML로 표현 불가한 `.lf` 전용 기능(D26 상태 식 pref/weight)을 쓰도록 진화한 예제는
    old_examples/에 이관 시점 `.lf` 스냅샷을 동결해 그 쌍으로 비교한다(dungeon 사례 —
    test_full_dungeon_golden_equivalence)."""
    frozen = _OLD_EXAMPLES / lf_path.name
    if frozen.exists():
        lf_path = frozen  # 살아있는 예제가 .lf 전용 기능으로 진화 — 동결 스냅샷으로 비교
    yaml_path = _OLD_EXAMPLES / (lf_path.stem + ".rule")
    if not yaml_path.exists():
        pytest.skip(f"대응 YAML 없음: {yaml_path.name}")
    _assert_ir_equiv(load_rule_file(lf_path), load_rule_file(yaml_path))


def test_loop_var_domain_collision_rejected() -> None:
    # loop 변수가 도메인 변수와 동명이면 거부(조용한 shadowing 방지) — dungeon의 monster 사례.
    src = """
    domain { monster: enum { goblin, dragon } }
    for monster in [goblin, dragon]:
        transition t:
            then monster = monster
    """
    with pytest.raises(TextLoaderError, match="도메인 변수와 이름이 같"):
        parse_rule_text(src)


def test_full_dungeon_golden_equivalence() -> None:
    """6차 이관 시점의 dungeon.{rule,lf} 스냅샷이 IR 등가여야 한다(이관 회귀 하니스).

    전 기능을 한 번에 검증: 도메인·정적 constraints·5개 table·init·이동/조우/전투(8-way
    for-template)/흡수 전이·5종 check kind·괄호-or 가드·다중 대입·표 색인 가중치·desc 메타데이터.
    .lf는 로더 디스패치(확장자)로 읽는다.

    D26 이후 examples/dungeon.lf는 YAML로 표현 불가한 상태 의존 pref/weight를 쓰므로
    (`.lf` 전용), 이관 등가는 old_examples/의 동결 스냅샷 쌍으로 고정한다 — 살아있는
    예제는 자유롭게 진화하고, 이관 무회귀 증명은 스냅샷이 계속 지킨다.
    """
    yaml_rs = load_rule_file(_OLD_EXAMPLES / "dungeon.rule")
    native_rs = load_rule_file(_OLD_EXAMPLES / "dungeon.lf")
    _assert_ir_equiv(native_rs, yaml_rs)
    # 자체 IR이 백엔드가 거치는 스키마 게이트(참조 무결성·next.* 규칙·중복 id)를 통과하는가
    # — 골든 등가에 더해 백엔드-준비 상태를 확인(IR 동일 ⇒ BMC/sim/PRISM 동작 동일).
    validate(native_rs)
    # 전투 for-template이 8개로 펼쳐졌는지(순서 포함) 명시 확인.
    fight_ids = [t.id for t in native_rs.transitions if t.id.startswith("fight_")]
    assert fight_ids == [
        "fight_goblin_fighter",
        "fight_goblin_cleric",
        "fight_goblin_rogue",
        "fight_goblin_wizard",
        "fight_dragon_fighter",
        "fight_dragon_cleric",
        "fight_dragon_rogue",
        "fight_dragon_wizard",
    ]


def test_team_example_lf_dir_merge() -> None:
    """team_example/ (.lf 다중 파일)이 병합돼 공유 도메인 + 두 기획자 제약을 구성한다.

    협업 패턴(여러 기획자가 각자 파일에 룰을 쓰고 함께 검사)을 자체 문법으로 시연. 병합 시
    범인 파일 추적(source)이 .lf에서도 동작함을 확인한다(원칙4)."""
    rs = load_rules(_EXAMPLES / "team_example")
    assert [v.name for v in rs.variables] == ["level", "hp", "role"]
    by_id = {c.id: c.source for c in rs.constraints}
    assert by_id == {"warrior_hp_formula": "planner_a.lf", "global_hp_cap": "planner_b.lf"}


def test_metadata_roundtrip() -> None:
    # desc(모든 선언)·author(constraint 전용)가 IR에 보존되는가(S6 이관 충실성).
    src = """
    domain { hp: int 0..  level: int 1..100  role: enum { warrior, mage } }
    constraint warrior_hp:
        desc "전사 HP는 레벨당 100"
        author "planner_A"
        when role == warrior
        then hp == level * 100
    transition grow:
        desc "성장"
        then hp = hp + 1
    check reach desc "도달 가능" reachable: hp == 100
    expect ex: desc "조합 도달" role == warrior and level == 100
    """
    rs = parse_rule_text(src)
    assert rs.constraints[0].desc == "전사 HP는 레벨당 100"
    assert rs.constraints[0].author == "planner_A"
    assert rs.transitions[0].desc == "성장"
    assert rs.checks[0].desc == "도달 가능"
    assert rs.expects[0].desc == "조합 도달"


def test_loader_dispatches_lf_extension(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # load_rule_file이 .lf를 자체 문법으로 디스패치한다(D21).
    f = tmp_path / "d.lf"
    f.write_text("domain { g: int 0..9 }", encoding="utf-8")
    rs = load_rule_file(f)
    assert rs.variables == (Variable(name="g", type="int", min=0, max=9),)


def test_yaml_load_emits_deprecation_warning(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import core.loader as loader_mod

    loader_mod._warned_yaml = False  # 1회-경고 플래그 리셋(프로세스 공유)
    f = tmp_path / "d.rule"
    f.write_text("domain:\n  variables:\n    g: { type: int, min: 0, max: 9 }\n", encoding="utf-8")
    with pytest.warns(DeprecationWarning, match="디프리케이트"):
        loader_mod.load_rule_file(f)


# ---------- 상태 의존 pref/weight (D26) ----------


def test_state_expr_weight_lowered_as_string() -> None:
    rs = load_rule_file(Path("tests/fixtures/urn.lf"))
    draw = rs.transitions[0]
    # 상태 식은 문자열로 보존(전이 직전 상태에서 sim이 평가), 수치가 아니다.
    assert draw.outcomes[0].weight == "red / (red + blue)"
    assert draw.outcomes[1].weight == "blue / (red + blue)"


def test_state_expr_pref_lowered_as_string() -> None:
    rs = load_rule_file(Path("tests/fixtures/policy_adaptive.lf"))
    by = {t.id: t for t in rs.transitions}
    assert by["pick_a"].pref == "x"
    assert by["pick_b"].pref == "10 - x"


def test_numeric_pref_and_weight_stay_float() -> None:
    # 상수는 여전히 float — 기존 골든 IR 등가(하위 호환, D26).
    rs = load_rule_file(Path("examples/dungeon.lf"))
    by = {t.id: t for t in rs.transitions}
    assert isinstance(by["go_home"].pref, float)  # `pref 5` 상수
    # 표 색인 weight는 desugar 후 수치 — float 유지
    assert all(isinstance(oc.weight, float) for oc in by["fight_goblin_fighter"].outcomes)
    # 상태 식 pref/weight(D26)는 문자열 — 던전의 적응 정책·비복원 덱
    assert by["descend_l2"].pref == "max(win_gold - gold, 0)"
    assert by["descend_l2"].outcomes[0].weight == "l2_goblins / (l2_goblins + l2_dragons)"


# ---------- player 태그 (D27) ----------


def test_player_tag_parsed_to_ir() -> None:
    rs = parse_rule_text(
        """
        domain { turn: enum { p1, p2 }  x: int 0..3 }
        init: turn == p1 and x == 0
        transition move: when turn == p1 player p1 pref 1 then { x = 1; turn = p2 }
        transition rest: when turn == p1 player p1 pref 1 then turn = p2
        transition env_tick: when turn == p2 then turn = p1
        """
    )
    by = {t.id: t for t in rs.transitions}
    assert by["move"].player == "p1"
    assert by["env_tick"].player is None  # 무소속(환경 전이) 기본값


def test_player_tag_substituted_in_for_template() -> None:
    rs = parse_rule_text(
        """
        domain { turn: enum { p1, p2 }  x: int 0..3 }
        init: turn == p1 and x == 0
        table other { p1: p2, p2: p1 }
        for p in [p1, p2]:
            transition "move_${p}": when turn == p player p then turn = other[p]
        """
    )
    by = {t.id: t for t in rs.transitions}
    assert by["move_p1"].player == "p1"
    assert by["move_p2"].player == "p2"
    assert by["move_p1"].when == "turn == p1"
    assert by["move_p1"].outcomes[0].then == "next.turn == p2"  # other[p] 표 치환


def test_player_tag_undeclared_enum_value_rejected() -> None:
    rs = parse_rule_text(
        """
        domain { turn: enum { p1, p2 }  x: int 0..3 }
        init: turn == p1 and x == 0
        transition move: player p3 then x = 1
        """
    )
    with pytest.raises(SchemaError, match="player 'p3'.*enum 값이 아닙니다"):
        validate(rs)


def test_player_key_in_yaml_rejected(tmp_path: Path) -> None:
    # player는 .lf 전용(D27) — 디프리케이트 YAML에선 조용한 무시 대신 명확히 거부.
    body = (
        "domain: {variables: {x: {type: int, min: 0, max: 3}}}\n"
        "transitions:\n"
        "  - id: t\n"
        "    player: p1\n"
        "    then: 'next.x == 1'\n"
    )
    f = tmp_path / "t.rule"
    f.write_text(body, encoding="utf-8")
    with pytest.raises(LoaderError, match="player.*자체 문법"):
        load_rule_file(f)


# ---------- 배열/인덱스 변수 (D28) ----------


def test_array_declaration_expands_to_scalar_family() -> None:
    rs = parse_rule_text("domain { gold[p1, p2]: int 0..30  turn: enum { p1, p2 } }")
    assert [v.name for v in rs.variables] == ["gold_p1", "gold_p2", "turn"]
    assert rs.variables[0] == Variable(name="gold_p1", type="int", min=0, max=30)


def test_array_static_index_resolves_everywhere() -> None:
    """리터럴 색인이 init·가드·효과 LHS/RHS·check에서 스칼라 이름으로 해소된다(D28)."""
    rs = parse_rule_text(
        """
        domain { gold[p1, p2]: int 0..30  turn: enum { p1, p2 } }
        init: gold[p1] == 0 and gold[p2] == 0 and turn == p1
        transition give: when turn == p1 and gold[p1] > 0
            then { gold[p1] = gold[p1] - 1; gold[p2] = gold[p2] + 1; turn = p2 }
        check rich reachable: gold[p2] >= 10
        """
    )
    assert _expr_eq(rs.init, "gold_p1 == 0 and gold_p2 == 0 and turn == p1")
    (t,) = rs.transitions
    assert _expr_eq(t.when, "turn == p1 and gold_p1 > 0")
    assert _expr_eq(
        t.outcomes[0].then,
        "next.gold_p1 == gold_p1 - 1 and next.gold_p2 == gold_p2 + 1 and next.turn == p2",
    )
    assert _expr_eq(rs.checks[0].that, "gold_p2 >= 10")


def test_array_index_with_for_loop_var() -> None:
    """for loop 변수 색인 — 배열과 템플릿의 결합이 수동 복제와 같은 IR을 낸다(D28 핵심)."""
    src_array = """
    domain { gold[p1, p2]: int 0..9  turn: enum { p1, p2 } }
    table other { p1: p2, p2: p1 }
    for p in [p1, p2]:
        transition "pass_${p}": when turn == p then { gold[p] = gold[p] + 1; turn = other[p] }
    """
    src_manual = """
    domain { gold_p1: int 0..9  gold_p2: int 0..9  turn: enum { p1, p2 } }
    transition pass_p1: when turn == p1 then { gold_p1 = gold_p1 + 1; turn = p2 }
    transition pass_p2: when turn == p2 then { gold_p2 = gold_p2 + 1; turn = p1 }
    """
    _assert_ir_equiv(parse_rule_text(src_array), parse_rule_text(src_manual))


def test_array_undeclared_index_value_rejected() -> None:
    with pytest.raises(TextLoaderError, match="배열 'gold'에 색인 값 'p3'가 없습니다"):
        parse_rule_text("domain { gold[p1, p2]: int 0..9 } init: gold[p3] == 0")


def test_array_expanded_name_collision_rejected() -> None:
    with pytest.raises(TextLoaderError, match="변수 이름 충돌: 'gold_p1'"):
        parse_rule_text("domain { gold_p1: int 0..9  gold[p1, p2]: int 0..9 }")


def test_array_bare_use_rejected() -> None:
    with pytest.raises(TextLoaderError, match="배열 변수 'gold'는 색인해서만"):
        parse_rule_text("domain { gold[p1, p2]: int 0..9 } init: gold == 0")


def test_array_table_name_overlap_rejected() -> None:
    with pytest.raises(TextLoaderError, match="표.*배열.*이름이 겹칩니다"):
        parse_rule_text("domain { gold[p1, p2]: int 0..9 } table gold { p1: 1, p2: 2 }")


def test_array_two_indices_rejected() -> None:
    with pytest.raises(TextLoaderError, match="색인을 1개만"):
        parse_rule_text("domain { gold[p1, p2]: int 0..9 } init: gold[p1][p2] == 0")
