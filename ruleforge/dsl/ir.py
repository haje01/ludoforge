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
    """단일 룰. `when`이 있으면 `Implies(when, then)`로 번역된다(CLAUDE.md §4)."""

    id: str
    then: str
    when: str | None = None
    author: str | None = None
    desc: str | None = None


@dataclass(frozen=True)
class RuleSet:
    """검사 단위: 도메인 변수들과 룰들의 묶음."""

    variables: tuple[Variable, ...] = field(default_factory=tuple)
    rules: tuple[Rule, ...] = field(default_factory=tuple)

    def variable(self, name: str) -> Variable:
        """이름으로 변수를 찾는다. 없으면 KeyError."""
        for v in self.variables:
            if v.name == name:
                return v
        raise KeyError(name)
