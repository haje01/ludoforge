# CLAUDE.md

> 이 문서는 코딩 AI 에이전트(Claude Code 등)가 본 프로젝트를 작업할 때 따라야 할
> 단일 진실 원천(SSOT)이다. 아키텍처 결정, 코딩 규약, 도메인 개념을 담는다.
> 코드와 충돌이 생기면 **이 문서를 먼저 갱신**한 뒤 코드를 바꾼다.

---

## 1. 프로젝트 개요

**이름(가칭):** RuleForge — MMORPG 룰 정합성 검증기

**한 줄 정의:** 여러 기획자가 작성한 MMORPG 게임 룰을 사람이 읽는 산문 대신
**기계 검증 가능한 DSL**로 작성하게 하고, 이를 **SMT solver(Z3)** 로 번역해
룰 사이의 **논리적 모순을 결정론적으로 탐지**하는 도구.

**해결하는 문제:**
- 기획자가 여럿일 때 각자 합리적으로 쓴 룰이 함께 두면 모순되는 일이 잦다
  (예: "전사 HP = 레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순).
- D&D SRD를 일관성 있게 형식화하려는 문제와 동형(同型)이다.
- 시뮬레이션 도구(Machinations 등)는 *반례를 우연히 만나야* 잡지만,
  본 도구는 모순의 **존재 자체를 증명**한다 (unsat core).

**명시적 비목표(Non-goals):**
- 밸런스의 "재미" 평가(연속적·통계적 품질)는 다루지 않는다. 그건 시뮬레이션 영역.
- 런타임 게임 서버 검증이 아니다. **기획 단계 정적 검증** 도구다.
- 게임 엔진/에디터가 아니다.

---

## 2. 핵심 설계 원칙

1. **결정론적 검증을 LLM에 맡기지 않는다.** 모순 판정은 항상 Z3가 한다.
   LLM/AI 에이전트는 (a) 산문→DSL 번역 보조, (b) unsat core를 사람 말로 설명,
   (c) 신규 룰의 잠재 충돌 후보 제시 — 이 세 가지 *보조* 역할만.
   판정 자체를 LLM이 하면 거짓 일관성을 환각할 수 있다.

2. **DSL이 SSOT다.** 룰은 산문이 아니라 구조화된 DSL로만 작성한다.
   형식화 행위 자체가 암묵 가정을 드러낸다.

3. **두 종류 검사를 분리한다.**
   - *형식/참조 무결성*: 스키마 검증(존재하지 않는 상태 참조, 순환 의존 등).
   - *논리 모순*: Z3 SMT 검사. 전자가 통과해야 후자로 넘어간다.

4. **모순 리포트는 사람이 읽을 수 있어야 한다.** unsat core(범인 룰)와
   반례 모델(깨지는 입력)을 함께 제시한다. 둘 다 디버깅에 필요하다.

5. **점진적 형식화.** 모든 룰을 한 번에 형식화하지 않는다. 충돌이 잦은
   룰부터 DSL로 옮기고 검사 범위를 넓힌다.

---

## 3. 검증 파이프라인 (목표 아키텍처)

```
기획 DSL (.rule 파일, git 관리, SSOT)
        │
        ▼
  [1] 파서/로더        rule 파일 → 내부 IR(중간표현)
        │
        ▼
  [2] 스키마·참조 검증  형식 오류, 미정의 심볼 참조, 순환 의존
        │              (실패 시 여기서 중단, Z3까지 안 감)
        ▼
  [3] Z3 번역기        IR → Z3 제약식 (assert_and_track 로 named)
        │
        ▼
  [4] 검사 실행
        ├─ 모순 검사:   여러 룰 동시 assert → unsat 이면 모순,
        │               s.unsat_core() 로 범인 룰 집합 추출
        ├─ 도달성 검사: "위반 상태가 존재하는가?" → sat 이면 반례 모델
        └─ 경계 검사:   Optimize 로 이론적 최대/최소값 vs 기획 의도 상한
        │
        ▼
  [5] 리포터          unsat core + 반례를 사람 말 리포트로 변환
        │             (CI에서 PR 코멘트로 출력)
        ▼
  [6] CI 통합         PR마다 자동 실행, 모순 시 fail
```

---

## 4. DSL 설계 방향 (초안 — 변경 가능)

목표: **기획자가 쓰기 쉬우면서 Z3로 깔끔히 번역**되는 선언적 문법.
초기엔 YAML 기반으로 시작(파서 비용 최소화), 필요해지면 자체 문법으로 승격.

```yaml
# 예시: warrior_hp.rule
domain:
  variables:
    level: { type: int, min: 1, max: 100 }
    hp:    { type: int, min: 0 }
    role:  { type: enum, values: [warrior, mage, archer] }

rules:
  - id: warrior_hp_formula
    author: planner_A
    desc: "전사 최대 HP는 레벨당 100"
    when:  "role == warrior"
    then:  "hp == level * 100"

  - id: global_hp_cap
    author: planner_B
    desc: "모든 캐릭터 HP는 5000을 넘지 않는다"
    then:  "hp <= 5000"
```

번역 규칙:
- `when` → `Implies(when_expr, then_expr)`.
- 각 rule은 `assert_and_track(constraint, id)` 로 등록 → unsat core가 `id`를 반환.
- enum은 Z3 정수 인코딩 또는 `Datatype` 사용. 비율/확률은 정수 분수 회피 위해
  스케일링(예: 1.2배 → `*12/10`)하거나 `Real` 사용.

표현 가능해야 할 룰 패턴:
- 수치 공식(LIA): 스탯/데미지/비용.
- 조건부 효과: `Implies` (버프 활성 시 ...).
- 상호 배제 상태: `Not(And(stealthed, attacking))`.
- 비율/확률(LRA): 확률 합 = 1 등.

**주의:** 비선형 산술(변수×변수, 예 `atk * crit_mult`)은 NIA라 느리거나
결정 불가. 가능하면 한쪽 상수화 또는 구간 분할.

---

## 5. 기술 스택 / 환경

- **언어:** Python 3.11+
- **패키지 관리자: **uv**
- **SMT:** `z3-solver` (Z3, Microsoft Research)
- **DSL 파싱:** 초기 PyYAML, 향후 필요 시 Lark(자체 문법)
- **CLI:** `typer` 또는 `click`
- **테스트:** `pytest`
- **린트/포맷:** `ruff` + `ruff format`
- **타입:** `mypy` (strict 지향)
- 패키지 설치 시 `pip install <pkg> --break-system-packages`

향후 확장(현 단계 비목표): 규칙 상호작용용 ASP(clingo), 온톨로지 일관성(OWL/HermiT).
이들은 Z3로 표현이 어색한 비단조 추론·분류 모순이 실제 병목이 될 때만 도입.

---

## 6. 권장 디렉터리 구조

```
ruleforge/
  __init__.py
  dsl/
    schema.py        # DSL 스키마 정의·검증 (참조 무결성, 순환 의존)
    loader.py        # .rule 파일 → 내부 IR
    ir.py            # 중간표현 데이터클래스
  solver/
    translator.py    # IR → Z3 제약식
    checks.py        # 모순/도달성/경계 검사 로직
    report.py        # unsat core·반례 → 사람용 리포트
  cli.py             # 진입점
rules/               # 실제 기획 룰 (.rule), git SSOT
tests/
  test_schema.py
  test_translator.py
  test_checks.py     # 알려진 모순 케이스가 반드시 unsat 나오는지
docs/
CLAUDE.md
pyproject.toml
```

---

## 7. 코딩 규약

- IR은 불변(frozen) 데이터클래스 우선. 함수형 코어 / 명령형 셸 분리
  (번역·검사 로직은 순수 함수, IO/CLI는 바깥 셸).
- Z3 제약은 반드시 `assert_and_track(expr, rule_id)` 로 등록한다.
  unsat core 추적이 본 프로젝트의 존재 이유다 — 익명 assert 금지.
- 모든 공개 함수에 타입 힌트. mypy strict 통과.
- 사용자 노출 메시지(리포트)는 한국어 우선, 코드/주석/식별자는 영어.
- 예외를 삼키지 말 것. DSL 검증 실패는 어떤 룰/필드가 문제인지 명시.

---

## 8. 테스트 전략 (중요)

검증기의 신뢰성이 곧 제품 가치다. 다음을 반드시 지킨다:

- **알려진 모순 코퍼스:** `tests/fixtures/` 에 *의도적으로 모순인* 룰셋을 두고,
  검사기가 정확히 그 룰들을 unsat core로 짚는지 검증.
- **알려진 정합 코퍼스:** 모순이 없어야 하는 룰셋이 sat(또는 모델 존재)인지 검증.
- **거짓 양성/음성 회귀:** 한 번 잘못 잡은 케이스는 영구 회귀 테스트로 고정.
- Z3 결과(`sat`/`unsat`)에 대한 단정은 명시적으로, `unknown` 반환 시
  (타임아웃·비선형 등) 별도 경로로 보고 — 절대 sat/unsat으로 뭉개지 않는다.

---

## 9. 작업 시작 순서 (에이전트용 로드맵)

처음 작업한다면 이 순서로 진행한다:

1. `pyproject.toml` + 의존성(z3-solver, pyyaml, typer, pytest, ruff, mypy).
2. `ir.py`: 최소 IR(Variable, Rule) 데이터클래스.
3. `loader.py`: 4장 예시 YAML 1개를 파싱해 IR 생성.
4. `translator.py`: IR → Z3, `assert_and_track` 사용.
5. `checks.py`: 모순 검사(`unsat` + `unsat_core`)와 도달성 검사(`sat` + model).
6. `report.py`: core/모델을 한국어 리포트로.
7. `cli.py`: `ruleforge check rules/` 한 줄로 위 파이프라인 실행.
8. 4장의 warrior_hp 예시를 **모순 케이스**로 만들어
   (레벨 상한 룰 추가) 검사기가 세 룰을 정확히 짚는지 테스트.

각 단계는 작은 PR로. 단계마다 테스트 먼저(혹은 동시).

---

## 10. 에이전트 행동 지침

- **추측하지 말고 형식화하라.** 룰의 의미가 모호하면 임의 가정으로
  코드를 짜지 말고, 어떤 해석들이 가능한지 짚고 확인을 요청한다.
- **결정론 경계를 지켜라.** "이 룰들은 모순 같다"는 식의 LLM 직관으로
  결론짓지 말 것. 반드시 Z3에 넣어 `unsat`을 받아 근거로 삼는다.
- **unsat core가 비어 있거나 너무 크면** 의심하라 — 제약 등록이 잘못됐을
  신호다. 익명 assert가 섞였는지 먼저 확인.
- DSL 문법을 바꾸면 이 문서 4장과 로더/번역기 테스트를 함께 갱신한다.
- 비선형으로 빠지는 룰을 만나면, 우회(상수화·구간분할)를 제안하고
  그 한계를 리포트에 명시한다. 조용히 `unknown`을 숨기지 않는다.

