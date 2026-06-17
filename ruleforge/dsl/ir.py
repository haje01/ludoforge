"""중간표현(IR): DSL 텍스트와 Z3 번역 사이의 불변 자료구조.

설계 원칙(CLAUDE.md §7): IR은 frozen 데이터클래스. 순수 데이터만 담고 IO는 없다.
1차 범위(D1)는 LIA 수치 변수(int)와 enum 변수, `when`/`then` 룰만 표현했고,
2차에서 불리언 상태 변수(bool, D6)와 실수 변수(real, LRA, D7)를 추가했다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

VariableType = Literal["int", "enum", "bool", "real"]


@dataclass(frozen=True)
class Variable:
    """도메인 변수.

    - int: `min`/`max`로 선언 범위를 둔다(없으면 None = 무한).
    - enum: `values`에 허용 값 목록을 둔다.
    - bool: 추가 필드 없음. True/False 두 상태를 자유롭게 가진다(상호 배제 등, D6).
    - real: `min`/`max`로 실수 범위를 둔다(LRA, D7). int 경계는 정수, real 경계는 실수.
    """

    name: str
    type: VariableType
    min: float | None = None
    max: float | None = None
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    """단일 룰. `when`이 있으면 `Implies(when, then)`로 번역된다(CLAUDE.md §4).

    `source`는 룰이 정의된 .rule 파일명이다. 디렉토리 병합 시 어느 파일의 룰이 모순의
    범인인지 리포트에서 짚기 위함이다. 직접 생성한 IR(테스트 등)에서는 None일 수 있다.
    """

    id: str
    then: str
    when: str | None = None
    author: str | None = None
    desc: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Expect:
    """명시적 도달성 단언(D10): `that` 조건이 룰 하에서 도달 가능해야 한다.

    `rules ∧ that`가 SAT이면 충족, UNSAT이면 미충족(룰이 봉쇄)으로 본다.
    자동 도달성 추론(D3)의 역방향 — 기획자가 양의 도달성을 직접 선언한다.
    """

    id: str
    that: str
    desc: str | None = None


@dataclass(frozen=True)
class RuleSet:
    """검사 단위: 도메인 변수들과 룰들, 도달성 단언(expects)의 묶음."""

    variables: tuple[Variable, ...] = field(default_factory=tuple)
    rules: tuple[Rule, ...] = field(default_factory=tuple)
    expects: tuple[Expect, ...] = field(default_factory=tuple)

    def variable(self, name: str) -> Variable:
        """이름으로 변수를 찾는다. 없으면 KeyError."""
        for v in self.variables:
            if v.name == name:
                return v
        raise KeyError(name)
