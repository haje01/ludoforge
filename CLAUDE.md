# CLAUDE.md

> 이 문서는 코딩 AI 에이전트(Claude Code 등)가 본 프로젝트를 작업할 때 따라야 할
> 단일 진실 원천(SSOT)이다. 아키텍처 결정, 코딩 규약, 도메인 개념을 담는다.
> 코드와 충돌이 생기면 **이 문서를 먼저 갱신**한 뒤 코드를 바꾼다.

---

## 1. 프로젝트 개요

**이름:** Ludoforge — 게임 기획 검증 툴킷. (논리 백엔드 `logic/`·Z3·BMC, 확률 추정
백엔드 `sim/`·Monte Carlo, 확률 증명 오라클 `prob/`·PRISM, 공유 프론트엔드 `core/`.
모두 우산 CLI `ludoforge`의 서브명령으로 노출된다.)

**한 줄 정의:** 여러 기획자가 작성한 게임 룰·전이 시스템을 사람이 읽는 산문 대신
**기계 검증 가능한 DSL**로 작성하게 하고, 하나의 공유 IR을 여러 백엔드로 검증한다 —
**논리적 모순·도달성·불변식은 Z3/BMC로 증명**하고, **승리 확률·기대 길이·직업별 분포 등
정량 속성은 Monte Carlo 시뮬레이션으로 추정**한다(소형 모델은 PRISM으로 교차검증). 핵심은
*존재·건전성은 결정론적 증명*(LLM 아닌 solver가 판정)이고, *정량 크기는 정직한 추정*
(신뢰구간·"증명 아님" 라벨)이라는 **증명/추정 분업**이다(D19).

**해결하는 문제:**
- 기획자가 여럿일 때 각자 합리적으로 쓴 룰이 함께 두면 모순되는 일이 잦다
  (예: "전사 HP = 레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순).
- D&D SRD를 일관성 있게 형식화하려는 문제와 동형(同型)이다.
- 시뮬레이션 도구(Machinations 등)는 *반례를 우연히 만나야* 잡지만,
  본 도구는 모순의 **존재 자체를 증명**한다 (unsat core).

**명시적 비목표(Non-goals):**
- 밸런스 *튜닝*을 **증명으로** 다루지 않는다 — 직업별 승률·분포 같은 연속적 품질은
  *증명* 백엔드(Z3/BMC·PRISM)의 영역이 아니다. **단, D19로 튜닝은 *추정* 백엔드(`sim`,
  Monte Carlo)의 목표가 되었다**("증명 아님 · 표집 추정" 라벨·신뢰구간과 함께). 즉
  "A직업 승률이 B와 5% 이내인가"는 이제 sim이 추정으로 답한다 — 증명이 아닐 뿐. "승리
  가능한가 · 확률적 데드락이 없는가 · 기대 게임 길이가 유한한가" 같은 정량 *건전성*은
  여전히 증명 백엔드 목표다(decisions.md D13~D14, **D19로 갱신/개정**).
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
> (단일 스냅샷) 경로다. 이에 더해 로더·스키마·IR을 공유 라이브러리 `core`로 두고,
> 그 위에 **논리 증명 백엔드(`logic/`·Z3·BMC, `ludoforge bmc`)** 와 **확률 증명 백엔드
> (`prob/`·PRISM, `ludoforge prob`)** 를 나란히 둔다. 전이 시스템(§4.1)을 모델로 공유
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

## 4. DSL 설계 (자체 문법 `.lf` — 구현됨, D21)

목표: **기획자가 쓰기 쉬우면서 Z3로 깔끔히 번역**되는 선언적·비-튜링완전 문법.
초기 YAML(`.rule`)에서 자체 문법(`.lf`, Lark)으로 승격했다(D21·6차 마일스톤). 문법 명세는
PLAN.md 6차 §3, 구현은 `core/text_loader.py`.

> **표면 언어 = 외부 DSL `.lf` (D21, PLAN.md 6차 — ✅ 구현 완료):** YAML에 문자열로 박힌
> 미니언어 2겹(표현식 D2 + 템플릿 D18)을 **하나의 비-튜링완전 외부 DSL(`.lf`)**로 통합했다
> (`core/text_loader.py`, Lark). 로더가 확장자로 디스패치(`load_rule_file`: `.lf`→자체 문법,
> `.rule`→YAML·**디프리케이트**). 핵심 의미 = **`=`(대입) vs `==`(비교) 분리**: 다음상태 효과는
> *이미* 대입+프레임이므로(전이 `then` → `next.X` 배정·미언급 변수 유지, D15·§4.1) 프라임
> `gold'`엔 `=`(전이 효과 전용), 같은상태 술어(`when`·`init`·정적 `constraint`·`check`)엔 `==`.
> 다중 효과는 `and`가 아니라 `;`(병렬 대입). 표 색인은 1급 식(`win[mon][cls]`), `${}`는 id
> 이름 보간에만. IR은 불변(AST→기존 IR lowering) → 백엔드·결정론 경계 무회귀. **참조 예제:
> `examples/dungeon.lf`. 아래 예시는 자체 문법(`.lf`) 기준이다** — YAML `.rule`은 같은 IR을
> 내며 하위 호환으로 로드된다(디프리케이트). 명세는 PLAN.md 6차 §3, 근거는 decisions.md D21.

```text
// 예시: warrior_hp.lf
domain {
    level:     int 1..100
    hp:        int 0..
    role:      enum { warrior, mage, archer }
    stealthed: bool                 // 불리언 상태(D6) — 추가 필드 없음
    drop_rate: real 0..1            // 실수 변수(LRA, D7)
}

constraint warrior_hp_formula:
    author "planner_A"
    desc "전사 최대 HP는 레벨당 100"
    when role == warrior            // == 비교(같은 상태)
    then hp == level * 100
constraint global_hp_cap:
    author "planner_B"
    desc "모든 캐릭터 HP는 5000을 넘지 않는다"
    then hp <= 5000

// 명시적 도달성 단언(D10, 선택)
expect warrior_can_max_level:
    desc "전사는 레벨 100까지 성장할 수 있어야 한다"
    role == warrior and level == 100   // 이 상태가 도달 가능해야 함
```

번역 규칙:
- `when` → `Implies(when_expr, then_expr)`.
- 각 제약(constraint)은 `assert_and_track(constraint, id)` 로 등록 → unsat core가 `id`를 반환.
- enum은 Z3 `EnumSort`(변수=Const, 값=sort 상수, D8). 서로 다른 enum이 같은 값 이름을
  써도 안전하며, `role == warrior`의 값은 비교 상대 변수의 sort로 해석한다(문맥 기반).
  enum 도달성은 **값 단위 투영**으로 본다: 각 변수의 각 값이 *어떤* 배정으로든 도달
  가능한지(`domain ∧ constraints ∧ var==value` sat)만 검사한다. 조건부 룰이 일부 조인트 조합을
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
- `expects:`의 각 `that`는 "도달 가능해야 하는 조건"이다(D10). `domain ∧ constraints ∧ that`가
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
공유 IR(`core`)이 이를 표현하고, 논리 백엔드(Z3/BMC)와 확률 백엔드(PRISM), 추정 백엔드
(sim/Monte Carlo)가 같은 모델을 다르게 해석한다(모두 구현됨 — `ludoforge bmc`/`prob`/`sim`).

```text
init: gold == 0 and room == center      // 초기 상태 술어(선택)

// 상태 → 다음 상태. 효과는 var' = … 대입(다음 상태), 가드는 == 비교(D21)
transition descend:
    when room == l1                     // 가드(선택)
    then room' = l2                     // 결정적 — weight=1.0 단일 outcome으로 정규화
transition fight:
    when room == l2
    outcomes:                           // 확률 분기. weight는 확률 백엔드용 주석
        0.7 -> gold' = gold + 500
        0.3 -> gold' = gold
// 플레이어 선택(pref, D20): 아래 둘은 room==l2에서 동시 enabled → sim이 pref로 표집.
transition dive:  when room == l2  pref 0.3  then room' = l3      // 욕심
transition leave: when room == l2  pref 0.7  then room' = center  // 안전

// 질의. kind로 백엔드 공통 의미 표현
check winnable  reachable: gold >= 10000 and room == center
check gold_ok   invariant: gold >= 0
check likely    prob: "P>=0.95 [ F (room == center) ]"   // 확률 백엔드 전용
check gold_dist distribution: gold                        // sim 전용 — 종료 상태 분포 추정(D19)
```

규칙:
- 다음 상태 효과는 자체 문법에서 **`var' = expr`**(프라임 LHS + `=` 대입)로 쓰고, IR에선
  **`next.<var> == expr`** 문자열로 lowering된다(전이 효과에서만 — 가드·init·expects·check엔
  프라임 불가, 스키마 오류). 효과에 `==`(비교)를 쓰거나 프라임 없는 LHS는 **구문 오류**(D21
  판별). 다중 효과는 `{ a' = …; b' = … }`(병렬 대입 집합 → IR에선 `and` 결합).
- 확률 `weight`는 골격 위 **주석**이다(D12): 논리 백엔드는 지우고(weight-erasure) 분기를
  비결정으로, 확률 백엔드는 가중치를 살려 본다. 정성(논리) 모델은 정량 모델의 건전한 추상.
- 전이 `pref`는 **플레이어 선택**의 상대 가중치다(sim 전용, D20). 한 상태에서 여러 전이가
  동시에 enabled일 때 sim은 매 스텝 **2단 표집**한다: ① enabled 전이를 `pref`로 골라(정책)
  → ② 그 전이의 outcome을 `weight`로 고른다(환경 우연). `weight`(D12, 우연)와 의미가 다른
  별도 키워드다 — **BMC·PRISM은 `pref`를 무시**한다(weight-erasure와 일관, dialect 분리 D11).
  - 미선언(`pref` 없음)은 **None**으로, "1.0 선언"과 구분한다(opt-in 안전망, §2·D20):
    co-enabled 집합에 하나라도 미선언이 섞이면 sim은 의도치 않은 가드 중첩으로 보고 거부한다
    (`DtmcViolation`). 균등 선택은 같은 `pref`를 명시해 얻는다. enabled가 1개면 선택이 없어
    `pref`는 무시되고 rng도 소비하지 않는다(기존 DTMC 모델의 재현성·비트 동일 보존).
  - 결과는 **"주어진 정책 하의 추정 · Pmax 아님"**으로 라벨한다 — 고정 정책의 값은 Pmax의
    하한이다(정책이 우연히 최적일 때만 일치). 예제: `examples/dungeon_policy.lf`(욕심 vs 안전).
- `checks`의 `kind` ∈ {`reachable`, `invariant`, `prob`, `no_deadlock`, `distribution`}.
  `reachable`/`invariant`는 `that`(상태 술어), `prob`는 `spec`(PCTL 문자열, 확률 백엔드
  전용 — core는 구문 검사 안 함), `distribution`은 `expr`(수치식, **sim 전용** — 평균·CI·
  백분위·히스토그램으로 추정, D19)을 둔다. 질의 dialect는 백엔드별로 가른다(D11).
- 유한 상태(PRISM 오라클 전제, D13)는 `validate()`와 분리된 `check_finite_state()`가
  검사한다 — int에 min·max 강제, real은 이산화 필요로 거부. Z3·**sim은 무한·real을
  허용**하므로 공유 `validate()`엔 넣지 않는다. sim은 대신 지평 H를 요구하고, 도달 상태의
  비결정을 **무작위 정책(`pref`)으로 해소**한다(D20): co-enabled가 모두 `pref`를 명시하면
  표집, 아니면 거부(D19의 "enabled ≤1만 허용"을 조건부로 완화).

### 4.2 템플릿 확장 — `for:` / `${expr}` / `tables:` (D18)

클래스×몬스터처럼 구조가 같고 데이터만 다른 항목이 곱으로 늘어나는 걸 막기 위해,
`constraint`/`transition`/`check`를 `for` 템플릿으로 쓸 수 있고, 공통 데이터는 최상위 `table`로
둔다. **로더가 파싱 직후 구체 항목으로 펼친다(desugar, 트리 확장 패스)** — IR·번역기·BMC·PRISM·
sim은 그대로 구체 항목만 본다. 펼치기는 순수 구문 변환이라 결정론 경계를 건드리지 않는다(§2).

```text
// 공통 데이터 표(desugar 시점에 소비, IR엔 안 들어감)
table reward { goblin: 2, dragon: 10 }
table win {                              // win[mon][cls]
    goblin: { fighter: 0.92, rogue: 0.72 }
    dragon: { fighter: 0.58, rogue: 0.08 }
}
// 데카르트 곱. loop 변수는 도메인 변수와 동명 금지(monster→mon; 동명이면 거부)
for mon in [goblin, dragon], cls in [fighter, rogue]:
    transition "fight_${mon}_${cls}":
        when role == cls and monster == mon       // loop 변수는 1급 식으로 치환
        outcomes:
            win[mon][cls] -> gold' = gold + reward[mon]   // 표 색인도 1급 식
```

- `for p in [값들], q in [값들]: <항목>` — 값 리스트들의 **데카르트 곱**(키 순서대로). 한
  `for`는 **항목 1개**를 템플릿한다(YAML의 per-item `for`와 동형). 레코드-리스트 형태·중첩
  `for`는 미도입(후속).
- **loop 변수·표 색인은 1급 식**이다 — `cls`(=`role == cls`)·`cap[mon]`·`win[mon][cls]`처럼
  표현식에 직접 쓰며 desugar가 바인딩 값/표 값으로 치환한다(외부 DSL의 단순화 — YAML의 `${}`
  문자열 보간이 사라짐). 색인 평가는 화이트리스트(Name·Subscript·Constant, `eval` 없음, §7).
  미정의 이름·색인 실패는 위치와 함께 `TextLoaderError`.
- **`${expr}`는 id 이름 문자열 보간에만** 남는다(`"fight_${mon}_${cls}"`). 생성 항목의 `id`는
  템플릿대로 결정적·추적 가능해야 한다(`fight_dragon_rogue`) — unsat core·BMC 반례 리포트가
  여전히 사람이 읽는 범인을 짚게 하기 위함(원칙 4).
- loop 변수가 도메인 변수와 같은 이름이면 **거부**한다(조용한 shadowing 방지, §2·실패는 크게).
- **주의:** 펼치기는 *소스*를 줄일 뿐 *검증 모델*은 줄이지 않는다 — PRISM/Z3엔 여전히
  N·M개 명령이 간다(상태기계 본질). 데이터(N·M개 수치)도 그대로 남는다.
- **미도입(후속):** `${1 - win - death}` 같은 **산술 계산식**은 부동소수 정밀도 문제로
  보류(`miss`는 표에 명시). 필요해지면 Tier 2.5로.

---

## 5. 기술 스택 / 환경

- **언어:** Python 3.11+
- **패키지 관리자: **uv**
- **SMT:** `z3-solver` (Z3, Microsoft Research)
- **DSL 파싱:** **Lark 기반 외부 DSL(`.lf`)** — `core/text_loader.py`(자체 문법·`=`/`==`
  분리, D21·PLAN.md 6차). `load_rule_file`이 확장자로 디스패치: `.lf`→자체 문법, `.rule`/
  `.yaml`→PyYAML(+ast 화이트리스트, D2 — **디프리케이트**, 1회 경고). 두 프론트엔드가 같은
  IR을 내므로 백엔드·결정론 경계 무회귀. 런타임 evaluator(§7, sim)는 잔존.
- **CLI:** `typer` 또는 `click`
- **테스트:** `pytest`
- **린트/포맷:** `ruff` + `ruff format`
- **타입:** `mypy` (strict 지향)
- 패키지 설치 시 `pip install <pkg> --break-system-packages`

향후 확장(현 단계 비목표): 규칙 상호작용용 ASP(clingo), 온톨로지 일관성(OWL/HermiT).
이들은 Z3로 표현이 어색한 비단조 추론·분류 모순이 실제 병목이 될 때만 도입.

---

## 6. 디렉터리 구조 (다중 백엔드, D11·D19)

```
core/          # 공유 DSL 프론트엔드(SSOT) — 세 백엔드가 같은 IR을 소비
  ir.py              # 중간표현 데이터클래스 (전이 시스템 포함)
  loader.py          # .rule 파일 → 내부 IR
  schema.py          # 스키마·참조 검증 + check_finite_state(PRISM 게이트) + check_dtmc(sim 게이트)
ludoforge/           # 우산: 통합 CLI 진입점·프로젝트 버전
  cli.py             # ludoforge check / bmc / prob / sim
logic/           # 논리 증명 백엔드 (Z3/BMC)
  solver/
    translator.py    # IR → Z3 제약식
    checks.py        # 정적 모순/도달성 검사
    bmc.py           # 전이 시스템 BMC (k 언롤링·도달성·불변식·데드락)
    report.py        # unsat core·반례 → 사람용 리포트
sim/             # 확률 추정 백엔드 (Monte Carlo, 주 정량 경로 — D19)
  engine.py          # IR 전이 시스템 인터프리터·DTMC 게이트·1 run 표집
  aggregate.py       # 결합가능 집계(Welford·히스토그램·rule-of-three)
  runner.py          # multiprocessing 분배·SeedSequence.spawn(분산 구조는 후속)
  report.py          # 추정+CI·절단 비율 한국어 리포트("증명 아님" 라벨)
prob/           # 확률 증명 오라클 (PRISM — 소형 모델 교차검증, D19)
  prism_gen.py       # IR → PRISM 모델·속성
  runner.py          # prism 실행·결과 파싱(미설치 시 graceful)
rules/               # 실제 기획 룰 (.rule), git SSOT
examples/            # 모순/정합/전이 시스템 예제 (.rule)
tests/               # 단위 + 모순/정합 코퍼스 + BMC/sim/PRISM
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

