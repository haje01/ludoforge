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
class Doc:
    """문서 메타데이터(D29, 12차) — 규칙서(`ludoforge doc`)·리포트용 passthrough 주석.

    세 백엔드(bmc/sim/PRISM 오라클)는 전부 무시한다 — D12 weight-erasure·D20 pref·
    D27 player와 같은 "지워지는 주석" 계보라 검증·추정 의미에 영향이 없다.
    `notes`는 절차·연출 산문(반복 선언, 순서 유지), `ref`는 출처(룰북 페이지·URL —
    외부 참조라 `[[이름]]` 무결성 검사 제외), `tags`는 분류 라벨. note/desc 본문의
    `[[이름]]` 상호참조는 로더가 존재를 검사한다(`.lf` 전용, 드리프트 억제).
    """

    notes: tuple[str, ...] = ()
    ref: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Variable:
    """도메인 변수.

    - int: `min`/`max`로 선언 범위를 둔다(없으면 None = 무한).
    - enum: `values`에 허용 값 목록을 둔다.
    - bool: 추가 필드 없음. True/False 두 상태를 자유롭게 가진다(상호 배제 등, D6).
    - real: `min`/`max`로 실수 범위를 둔다(LRA, D7). int 경계는 정수, real 경계는 실수.
    - `desc`는 용어집용 문서 주석(D29, `.lf` 전용) — 백엔드는 무시한다.
    - `ghost`는 서술 전용 상태(D31, `.lf` 전용) — 비-ghost 궤적에 영향 불가(schema 게이트).
      sim만 실행하고 bmc/PRISM은 `erase_ghosts`로 상태공간에서 제거한다.
    """

    name: str
    type: VariableType
    min: float | None = None
    max: float | None = None
    values: tuple[str, ...] = ()
    desc: str | None = None
    ghost: bool = False


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
    doc: Doc | None = None


@dataclass(frozen=True)
class Expect:
    """명시적 도달성 단언(D10): `that` 조건이 룰 하에서 도달 가능해야 한다.

    `rules ∧ that`가 SAT이면 충족, UNSAT이면 미충족(룰이 봉쇄)으로 본다.
    자동 도달성 추론(D3)의 역방향 — 기획자가 양의 도달성을 직접 선언한다.
    """

    id: str
    that: str
    desc: str | None = None
    doc: Doc | None = None


@dataclass(frozen=True)
class Outcome:
    """전이의 한 분기(D12). `then`은 `next.<var>`로 다음 상태를 제약한다.

    `weight`는 확률(PRISM) 백엔드용 확률 가중치다. 논리 백엔드는 이를 **무시하고**(weight-
    erasure) 분기를 비결정으로 본다(decisions.md D12). 결정적 전이는 weight=1.0인 단일
    Outcome으로 정규화한다.

    D26: 상수(float) 대신 **현재 상태의 식(str)**을 둘 수 있다 — 전이 직전 상태에서
    평가해 정규화 표집한다(비복원 추출 등). 음수/합0 평가는 sim이 런타임 거부하며, 그런
    상태는 **가드로 배제**하는 것이 모델러 책임이다(enabledness는 가드 단독). BMC는
    식이어도 erasure로 지우고(0-가중 분기도 "가능"으로 탐색 — 과근사), PRISM 오라클은
    비율형으로 렌더한다.
    """

    then: str
    weight: float | str = 1.0


@dataclass(frozen=True)
class Transition:
    """상태 → 다음 상태 전이(D12). `when` 가드가 참인 상태에서 발생한다.

    `outcomes`는 항상 1개 이상이다 — DSL의 bare `then`은 로더가 단일 Outcome(weight=1.0)으로
    정규화한다. 여러 개면 확률 분기(가중치 합은 보통 1, 검증은 확률 백엔드 몫).
    `source`는 정의 파일명(병합 시 범인 추적용).

    `pref`는 **플레이어 선택**의 상대 가중치다(sim 전용, decisions.md D20). 한 상태에서
    여러 전이가 동시에 enabled일 때 sim이 enabled된 것들끼리 `pref`로 정규화해 무작위
    정책으로 표집한다(매 스텝 2단 표집: 정책으로 전이 선택 → weight로 outcome 선택).
    `None`은 **미선언**이다 — co-enabled 집합에 하나라도 None이 섞이면 sim은 의도치 않은
    가드 중첩으로 보고 거부한다(명시적 opt-in 안전망, D20). 균등 선택은 같은 `pref`를
    명시해 얻는다. `outcomes.weight`(환경 우연, D12)와 의미가 다르다 — BMC/PRISM은 무시한다.

    D26: 상수(float) 대신 **현재 상태의 식(str)**을 둘 수 있다(적응적 정책 — 예: 욕심도가
    남은 목표액에 비례). co-enabled 정규화·opt-in 안전망·enabled 1개 rng 미소비 등 D20
    의미는 전부 불변이며, 상수 자리에 식이 들어갈 뿐이다.

    `player`는 **전이 소유 선언**이다(D27, 다인 게임). None=무소속(환경/자연 전이 —
    흡수·스폰 등). 태그는 스케줄러가 아니다 — 누구 턴인지는 여전히 모델(`turn` enum +
    가드)의 몫이며, 전이 시스템 의미(D12·D15)를 바꾸지 않는다. sim은 co-enabled 선택
    집합의 소유가 혼성이면(가드 실수로 두 플레이어 턴이 겹침) 명시 거부하고,
    BMC/PRISM은 태그를 무시한다(weight-erasure·pref 무시와 같은 계보의 주석).
    이름은 선언된 enum의 값이어야 한다(schema 게이트, 관례상 turn enum).
    """

    id: str
    outcomes: tuple[Outcome, ...]
    when: str | None = None
    desc: str | None = None
    source: str | None = None
    pref: float | str | None = None
    player: str | None = None
    doc: Doc | None = None


@dataclass(frozen=True)
class Check:
    """검증 질의(DSL의 `checks` 섹션 항목, D12). `kind`로 백엔드 공통 의미를 표현한다.

    - `reachable`/`invariant`: `that`(현재 상태 술어)를 둔다. 논리 백엔드가 BMC로,
      PRISM 오라클(테스트 전용)이 P>0 / P=1로 해석한다.
    - `distribution`: `expr`(수치식)을 둔다 — **sim 백엔드 전용**(D19). 표집 종료 상태에서
      `expr` 값을 모아 평균·신뢰구간·백분위·히스토그램으로 *추정*한다(증명 아님).
    - `no_deadlock`: 추가 필드 없음.

    모델은 공유하되 질의 dialect는 백엔드별이다(D11). `expr`는 Python 식이라 참조 무결성을
    검사한다(`next.*` 불가 — 현재 상태 식이다). (PCTL `kind: prob`은 D23으로 사용자 표면에서
    제거 — PRISM은 테스트 오라클로만 남고 reachable→Pmax로 충분하다.)
    """

    id: str
    kind: str
    that: str | None = None
    expr: str | None = None  # distribution 전용 수치식(sim 백엔드, D19)
    desc: str | None = None
    source: str | None = None
    doc: Doc | None = None


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
