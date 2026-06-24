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
class Constraint:
    """단일 정적 제약(DSL의 `constraints` 섹션 항목). 모든 상태에 적용되는 불변식이며,
    `when`이 있으면 `Implies(when, then)`로 번역된다(CLAUDE.md §4).

    `source`는 제약이 정의된 .rule 파일명이다. 디렉토리 병합 시 어느 파일의 제약이 모순의
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
class Outcome:
    """전이의 한 분기(D12). `then`은 `next.<var>`로 다음 상태를 제약한다.

    `weight`는 확률(PRISM) 백엔드용 확률 가중치다. 논리 백엔드는 이를 **무시하고**(weight-
    erasure) 분기를 비결정으로 본다(decisions.md D12). 결정적 전이는 weight=1.0인 단일
    Outcome으로 정규화한다.
    """

    then: str
    weight: float = 1.0


@dataclass(frozen=True)
class Transition:
    """상태 → 다음 상태 전이(D12). `when` 가드가 참인 상태에서 발생한다.

    `outcomes`는 항상 1개 이상이다 — DSL의 bare `then`은 로더가 단일 Outcome(weight=1.0)으로
    정규화한다. 여러 개면 확률 분기(가중치 합은 보통 1, 검증은 확률 백엔드 몫).
    `source`는 정의 파일명(병합 시 범인 추적용).
    """

    id: str
    outcomes: tuple[Outcome, ...]
    when: str | None = None
    desc: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Check:
    """검증 질의(DSL의 `checks` 섹션 항목, D12). `kind`로 백엔드 공통 의미를 표현한다.

    - `reachable`/`invariant`: `that`(현재 상태 술어)를 둔다. 논리 백엔드가 BMC로,
      확률 백엔드가 P>0 / P=1로 해석한다.
    - `prob`: `spec`(PCTL 문자열)을 둔다 — **확률(PRISM) 백엔드 전용**, 그 외는 무시한다.
    - `distribution`: `expr`(수치식)을 둔다 — **sim 백엔드 전용**(D19). 표집 종료 상태에서
      `expr` 값을 모아 평균·신뢰구간·백분위·히스토그램으로 *추정*한다(증명 아님).
    - `no_deadlock`: 추가 필드 없음.

    모델은 공유하되 질의 dialect는 백엔드별이다(D11) — `spec`은 Python 식이 아니라
    PCTL이라 forge-core는 구문 검사하지 않는다(PRISM이 해석). `expr`는 Python 식이라
    참조 무결성을 검사한다(`next.*` 불가 — 현재 상태 식이다).
    """

    id: str
    kind: str
    that: str | None = None
    spec: str | None = None
    expr: str | None = None  # distribution 전용 수치식(sim 백엔드, D19)
    desc: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class RuleSet:
    """검사 단위: 도메인 변수·정적 제약(constraints)·도달성 단언(expects)과 전이 시스템
    (init/transitions/checks, D12)의 묶음. 전이 필드는 비어 있을 수 있다(정적 룰셋과 하위 호환)."""

    variables: tuple[Variable, ...] = field(default_factory=tuple)
    constraints: tuple[Constraint, ...] = field(default_factory=tuple)
    expects: tuple[Expect, ...] = field(default_factory=tuple)
    init: str | None = None
    transitions: tuple[Transition, ...] = field(default_factory=tuple)
    checks: tuple[Check, ...] = field(default_factory=tuple)

    def variable(self, name: str) -> Variable:
        """이름으로 변수를 찾는다. 없으면 KeyError."""
        for v in self.variables:
            if v.name == name:
                return v
        raise KeyError(name)
