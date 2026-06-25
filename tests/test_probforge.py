"""Phase 4: 확률(PRISM) 백엔드 테스트 — IR→PRISM 번역(D16).

모델 생성은 PRISM 없이 검증한다(생성 텍스트 골든 단정). 실제 PRISM 실행은 바이너리가
있을 때만(통합 테스트는 skipif). 유한 상태 게이트·번역 오류·러너 graceful도 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ir import Outcome, RuleSet, Transition, Variable
from core.loader import load_rule_file
from core.schema import SchemaError
from prob.prism_gen import ProbError, generate
from prob.runner import find_prism, format_prob_report, run_prism

EXAMPLES = Path(__file__).parent.parent / "examples"


def _dungeon() -> RuleSet:
    return load_rule_file(EXAMPLES / "dungeon.rule")


# ---------- 모델 생성 ----------


def test_model_header_and_enum_consts() -> None:
    model = generate(_dungeon()).model
    assert model.startswith("mdp")
    assert "const int hall = 0;" in model
    assert "const int l1 = 1;" in model
    # role enum 순서: rogue·cleric·fighter·wizard
    assert "const int rogue = 0;" in model
    assert "const int fighter = 2;" in model
    assert "const int wizard = 3;" in model


def test_variable_declarations() -> None:
    model = generate(_dungeon()).model
    assert "gold : [0..30];" in model
    assert "room : [0..3];" in model
    assert "win_gold : [0..30];" in model


def test_deterministic_and_probabilistic_commands() -> None:
    model = generate(_dungeon()).model
    # 결정적 전이(weight 1.0) — 확률 접두 없음
    assert "[enter_l1]" in model
    assert "(room'=l1)" in model
    # 확률 전이 — 가중치 보존(합=1). fight_goblin_fighter: 승0.92 / 무소득0.07 / 사망0.01.
    assert "0.92:(gold'=(gold + 2))" in model
    assert "0.07:(monster'=none)" in model
    # 사망 분기는 다중 갱신
    assert "0.01:(gold'=0) & (room'=hall) & (status'=dead) & (monster'=none)" in model


def test_init_block_encodes_init_and_rules() -> None:
    model = generate(_dungeon()).model
    assert "init" in model and "endinit" in model
    # init 술어(비교는 공백 포함 렌더: `gold = 0`)
    assert "gold = 0" in model
    assert "room = hall" in model
    # 정적 rules → init 술어(프레임 불변 변수, D16)
    assert "win_gold = 20" in model
    assert "win_gold = 10" in model
    assert "role = wizard" in model


def test_property_mapping() -> None:
    props = {p.prop_id: p for p in generate(_dungeon()).properties}
    assert props["winnable"].pctl.startswith("Pmax=? [ F (")
    assert "status = won" in props["winnable"].pctl
    assert props["gold_nonneg"].pctl.startswith("Pmin=? [ G (")


def test_no_deadlock_property_skipped() -> None:
    rs = load_rule_file(Path(__file__).parent / "fixtures" / "bmc_deadlock.rule")
    program = generate(rs)
    # no_deadlock는 prop으로 생성하지 않는다(PRISM 자동 탐지, D16)
    assert program.properties == ()


# ---------- 번역 오류 ----------


def test_non_assignment_then_rejected() -> None:
    rs = RuleSet(
        variables=(Variable("x", "int", 0, 5),),
        transitions=(Transition(id="t", outcomes=(Outcome(then="next.x > x"),)),),
    )
    with pytest.raises(ProbError, match="배정형"):
        generate(rs)


def test_enum_value_name_collision_rejected() -> None:
    rs = RuleSet(
        variables=(
            Variable("a", "enum", values=("idle", "active")),
            Variable("b", "enum", values=("active", "done")),  # 'active' 중복
        ),
        transitions=(Transition(id="t", outcomes=(Outcome(then="next.a == active"),)),),
    )
    with pytest.raises(ProbError, match="유일"):
        generate(rs)


def test_finite_state_gate_rejects_unbounded_int() -> None:
    rs = RuleSet(
        variables=(Variable("hp", "int", 0, None),),
        transitions=(Transition(id="t", outcomes=(Outcome(then="next.hp == 0"),)),),
    )
    with pytest.raises(SchemaError, match="유한 상태"):
        generate(rs)


# ---------- 러너 ----------


def test_runner_graceful_without_prism(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRISM", raising=False)
    monkeypatch.setattr("prob.runner.shutil.which", lambda _name: None)
    program = generate(_dungeon())
    report = run_prism(program)
    assert report.available is False
    text = format_prob_report(report)
    assert "PRISM 미설치" in text
    assert "mdp" in text  # 생성 모델을 함께 보여준다


@pytest.mark.skipif(find_prism() is None, reason="PRISM 바이너리 미설치")
def test_prism_computes_results_when_available() -> None:
    program = generate(_dungeon())
    report = run_prism(program)
    assert report.available is True
    assert report.error is None
    assert len(report.outcomes) == len(program.properties)
    assert all(o.result is not None for o in report.outcomes)
