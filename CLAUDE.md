# CLAUDE.md

> 이 문서는 코딩 AI 에이전트(Claude Code 등)가 본 프로젝트를 작업할 때 따라야 할
> 단일 진실 원천(SSOT)이다. 아키텍처 결정, 코딩 규약, 도메인 개념을 담는다.
> 코드와 충돌이 생기면 **이 문서를 먼저 갱신**한 뒤 코드를 바꾼다.

---

## 1. 프로젝트 개요

**이름:** Ludoforge — 게임 기획 검증 툴킷. (논리 백엔드 **RuleForge**/Z3·BMC,
확률 백엔드 **ProbForge**/PRISM, 공유 프론트엔드 **forge_core**.)

**한 줄 정의:** 여러 기획자가 작성한 게임 룰·전이 시스템을 사람이 읽는 산문 대신
**기계 검증 가능한 DSL**로 작성하게 하고, 하나의 공유 IR을 여러 백엔드로 검증한다 —
**논리적 모순·도달성·불변식은 Z3/BMC로 증명**하고, **승리 확률 등 정량 속성은 PRISM으로
계산**한다. 핵심은 *결정론적 증명*(LLM이 아니라 solver가 판정).

**해결하는 문제:**
- 기획자가 여럿일 때 각자 합리적으로 쓴 룰이 함께 두면 모순되는 일이 잦다
  (예: "전사 HP = 레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순).
- D&D SRD를 일관성 있게 형식화하려는 문제와 동형(同型)이다.
- 시뮬레이션 도구(Machinations 등)는 *반례를 우연히 만나야* 잡지만,
  본 도구는 모순의 **존재 자체를 증명**한다 (unsat core).

**명시적 비목표(Non-goals):**
- 밸런스의 *재미·튜닝* 평가(연속적 품질, "A직업 승률이 B와 5% 이내인가" 류)는 다루지
  않는다 — 그건 Machinations 등 시뮬레이션 영역. 단, "승리 가능한가 · 확률적 데드락이
  없는가 · 기대 게임 길이가 유한한가" 같은 정량 *건전성* 속성은 ProbForge 백엔드의
  목표다(decisions.md D13~D14).
- 런타임 게임 서버 검증이 아니다. **기획 단계 검증** 도구다 — 단일 스냅샷에 더해 전이
  시스템(BMC)·확률 모델검사를 포함하나, 모두 설계 시점 정적 분석이다(D11~D12).
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

> **다중 백엔드 — 구현됨(decisions.md D11~D16):** 아래 파이프라인은 정적 모순 검사
> (단일 스냅샷) 경로다. 이에 더해 로더·스키마·IR을 공유 라이브러리 `forge_core`로 두고,
> 그 위에 **논리 증명 백엔드(RuleForge/Z3·BMC, `ludoforge bmc`)** 와 **확률 증명 백엔드
> (ProbForge/PRISM, `ludoforge prob`)** 를 나란히 둔다. 전이 시스템(§4.1)을 모델로 공유
> 하고 질의 dialect는 백엔드별로 가른다. 배경·용어는 [docs/concepts.md §8](docs/concepts.md).

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
    stealthed: { type: bool }   # 불리언 상태(D6) — 추가 필드 없음
    drop_rate: { type: real, min: 0, max: 1 }   # 실수 변수(LRA, D7)

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

expects:                          # 명시적 도달성 단언(D10, 선택)
  - id: warrior_can_max_level
    desc: "전사는 레벨 100까지 성장할 수 있어야 한다"
    that: "role == warrior and level == 100"   # 이 상태가 도달 가능해야 함
```

번역 규칙:
- `when` → `Implies(when_expr, then_expr)`.
- 각 rule은 `assert_and_track(constraint, id)` 로 등록 → unsat core가 `id`를 반환.
- enum은 Z3 `EnumSort`(변수=Const, 값=sort 상수, D8). 서로 다른 enum이 같은 값 이름을
  써도 안전하며, `role == warrior`의 값은 비교 상대 변수의 sort로 해석한다(문맥 기반).
  enum 도달성은 **값 단위 투영**으로 본다: 각 변수의 각 값이 *어떤* 배정으로든 도달
  가능한지(`domain ∧ rules ∧ var==value` sat)만 검사한다. 조건부 룰이 일부 조인트 조합을
  막는 것(`sky==night → lighting==night`이 `(night, day)`를 막음)은 정상이라 보고하지
  않는다 — 조합 단위 도달성 단언은 `expects:`(D10)로 명시한다. 무조건 룰로 한 값에 핀된
  enum은 나머지 값 봉쇄가 정상이라 제외(D5와 동형). enum 조합 고정은 수치/bool 내부 검사의
  문맥일 뿐 셀 자체를 모순으로 보지 않는다.
  bool은 z3.Bool로 번역(도메인 제약 없음). `then`이 bare atom/부정/등식이면 상태 제약이
  된다. 자유 bool의 True/False 각 상태가 도달 가능한지 검사한다(D6).
- real은 z3.Real로 번역(LRA, D7). 선언 min/max는 feasibility 제약. 나눗셈 `/`는
  **상수 분모만** 허용(`1/3` → 정확한 유리수). 변수 분모는 비선형이라 거부. real의 선언
  min/max **끝점** 도달성도 검사한다(D9): `var == 끝점`이 unsat이면 봉쇄로 보고(끝점
  feasibility, 정확한 달성값은 비계산 — Optimize/epsilon 회피).
- `expects:`의 각 `that`는 "도달 가능해야 하는 조건"이다(D10). `domain ∧ rules ∧ that`가
  unsat이면 단언 미충족으로 보고하고 범인 룰을 짚는다. 자동 도달성 추론의 역방향이며,
  변수별 경계로는 안 보이는 **조합 도달성**(예: 두 스탯 동시 최대)을 검증한다.

표현 가능해야 할 룰 패턴:
- 수치 공식(LIA): 스탯/데미지/비용.
- 조건부 효과: `Implies` (버프 활성 시 ...).
- 상호 배제 상태: `Not(And(stealthed, attacking))`. **(구현됨, D6)**
- 비율/확률(LRA): 확률 합 = 1 등. **(구현됨, D7 — 피저빌리티/상수 분모)**

**주의:** 비선형 산술(변수×변수, 예 `atk * crit_mult`)은 NIA라 느리거나
결정 불가. 가능하면 한쪽 상수화 또는 구간 분할.

### 4.1 전이 시스템 확장 (다중 백엔드, D11~D14)

정적 스냅샷(위)에 더해, 턴·이동·누적이 있는 **동역학**을 위한 전이 시스템 구문을 둔다.
공유 IR(`forge_core`)이 이를 표현하고, RuleForge(Z3/BMC)와 ProbForge(PRISM)가 같은
모델을 다르게 해석한다. **현재 구현(Phase 2)은 프론트엔드만** — 로더·스키마 검증까지이며,
BMC 검사는 Phase 3, PRISM은 Phase 4에서 붙는다.

```yaml
init: "gold == 0 and room == center"   # 초기 상태 술어(선택)

transitions:                            # 상태 → 다음 상태. next.<var>로 다음값 참조
  - id: descend
    when: "room == l1"                  # 가드(선택)
    then: "next.room == l2"             # 결정적 — weight=1.0 단일 outcome으로 정규화
  - id: fight
    when: "room == l2"
    outcomes:                           # 확률 분기. weight는 ProbForge용 주석
      - { weight: 0.7, then: "next.gold == gold + 500" }
      - { weight: 0.3, then: "next.gold == gold" }

properties:                             # 질의. kind로 백엔드 공통 의미 표현
  - { id: winnable, kind: reachable, that: "gold >= 10000 and room == center" }
  - { id: gold_ok,  kind: invariant, that: "gold >= 0" }
  - { id: likely,   kind: prob, spec: "P>=0.95 [ F (room == center) ]" }  # ProbForge 전용
```

규칙:
- `next.<var>`(다음 상태 참조)는 **전이 then에서만** 허용. rules·init·expects·property.that
  에서 쓰면 스키마 오류. `next`는 전이 표현식의 예약 식별자다.
- 확률 `weight`는 골격 위 **주석**이다(D12): RuleForge는 지우고(weight-erasure) 분기를
  비결정으로, ProbForge는 가중치를 살려 본다. 정성(논리) 모델은 정량 모델의 건전한 추상.
- `properties.kind` ∈ {`reachable`, `invariant`, `prob`, `no_deadlock`}. `reachable`/
  `invariant`는 `that`(상태 술어), `prob`는 `spec`(PCTL 문자열, ProbForge 전용 — forge-core는
  구문 검사 안 함). 질의 dialect는 백엔드별로 가른다(D11).
- 유한 상태(ProbForge/PRISM 전제, D13)는 `validate()`와 분리된 `check_finite_state()`가
  검사한다 — int에 min·max 강제, real은 이산화 필요로 현 단계 거부. Z3는 무한 정수를
  허용하므로 공유 `validate()`엔 넣지 않는다.

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

## 6. 디렉터리 구조 (다중 백엔드, D11)

```
forge_core/          # 공유 DSL 프론트엔드(SSOT) — 두 백엔드가 같은 IR을 소비
  ir.py              # 중간표현 데이터클래스 (전이 시스템 포함)
  loader.py          # .rule 파일 → 내부 IR
  schema.py          # 스키마·참조 검증 + check_finite_state(ProbForge 게이트)
ludoforge/           # 우산: 통합 CLI 진입점·프로젝트 버전
  cli.py             # ludoforge check / bmc / prob
ruleforge/           # 논리 증명 백엔드 (Z3/BMC)
  solver/
    translator.py    # IR → Z3 제약식
    checks.py        # 정적 모순/도달성 검사
    bmc.py           # 전이 시스템 BMC (k 언롤링·도달성·불변식·데드락)
    report.py        # unsat core·반례 → 사람용 리포트
probforge/           # 확률 증명 백엔드 (PRISM)
  prism_gen.py       # IR → PRISM 모델·속성
  runner.py          # prism 실행·결과 파싱(미설치 시 graceful)
rules/               # 실제 기획 룰 (.rule), git SSOT
examples/            # 모순/정합/전이 시스템 예제 (.rule)
tests/               # 단위 + 모순/정합 코퍼스 + BMC/PRISM
docs/                # concepts.md / decisions.md / 슬라이드
CLAUDE.md  PLAN.md  PROGRESS.md  pyproject.toml
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
7. `cli.py`: `ludoforge check rules/` 한 줄로 위 파이프라인 실행.
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

