# CLAUDE.md

> 이 문서는 코딩 AI 에이전트(Claude Code 등)가 본 프로젝트를 작업할 때 따라야 할
> 단일 진실 원천(SSOT)이다. 아키텍처 결정, 코딩 규약, 도메인 개념을 담는다.
> 코드와 충돌이 생기면 **이 문서를 먼저 갱신**한 뒤 코드를 바꾼다.

---

## 1. 프로젝트 개요

**이름:** Ludoforge — **게임 수치·경제 시스템 검증기**(D32). (논리 백엔드 `logic/`·Z3·BMC,
확률 추정 백엔드 `sim/`·Monte Carlo, 확률 증명 오라클 `prob/`·PRISM, 공유 프론트엔드
`core/`. 모두 우산 CLI `ludoforge`의 서브명령으로 노출된다.)

**한 줄 정의:** 게임의 **수치·경제 시스템**(성장 공식, 드랍률, 재화 싱크/소스, 상한 규칙,
자원 동역학)을 산문 대신 **기계 검증 가능한 DSL**(`.lf`)로 형식화하고, 하나의 공유 IR을
여러 백엔드로 검증한다 — **논리적 모순·도달성·불변식은 Z3/BMC로 증명**하고, **기대값·
분포 등 정량 속성은 Monte Carlo 시뮬레이션으로 추정**한다(소형 모델은 PRISM으로 교차검증).
핵심은 *존재·건전성은 결정론적 증명*(LLM 아닌 solver가 판정)이고, *정량 크기는 정직한
추정*(신뢰구간·"증명 아님" 라벨)이라는 **증명/추정 분업**이다(D19).

**해결하는 문제:**
- 기획자가 여럿일 때 각자 합리적으로 쓴 수치 룰이 함께 두면 모순되는 일이 잦다
  (예: "전사 HP = 레벨×100" + "HP 상한 5000" + "레벨 상한 100" → 레벨 51부터 모순).
- 시뮬레이션 도구(Machinations 등)는 *반례를 우연히 만나야* 잡지만,
  본 도구는 모순의 **존재 자체를 증명**한다 (unsat core).
- 경제 동역학(누적·소모·확률 보상)의 건전성("재화가 음수가 될 수 없다", "상한 도달
  가능")과 분포("기대 수익", "파산 확률")를 기획 단계에서 기계로 확인한다.

**명시적 비목표(Non-goals):**
- **게임 전체를 기술하는 기획 언어가 아니다(D32).** 카드별 고유 메커니즘(테라포밍
  마즈류)·서사·연출은 범위 밖 — 그걸 담으려면 DSL이 튜링완전해져 검증 가능성이 무너진다.
  본 DSL의 확장 축은 *구조는 같고 데이터만 다른* 조합(표 D18·배열 D28)이며, 검증은
  "치명적 부분계"(수치·경제)에 집중한다. 보드게임 통합 예제(dungeon 등)는 전 기능
  시연·테스트 픽스처로 유지한다.
- 밸런스 *튜닝*을 **증명으로** 다루지 않는다 — 분포 같은 연속적 품질은 *증명* 백엔드
  (Z3/BMC·PRISM)의 영역이 아니다. **단, D19로 튜닝은 *추정* 백엔드(`sim`, Monte Carlo)의
  목표가 되었다**("증명 아님 · 표집 추정" 라벨·신뢰구간과 함께). "상한 도달 가능한가 ·
  확률적 데드락이 없는가" 같은 정량 *건전성*은 여전히 증명 백엔드 목표다(D13~D14,
  **D19로 갱신/개정**).
- 런타임 게임 서버 검증이 아니다. **기획 단계 검증** 도구다 — 단일 스냅샷에 더해 전이
  시스템(BMC)·확률 모델검사를 포함하나, 모두 설계 시점 정적 분석이다(D11~D12).
- 게임 엔진/에디터가 아니다.

**인터페이스 방향(D32, 웹 MVP):** 기획자가 DSL을 직접 배우는 대신, **산문/시트 입력 →
LLM 번역(로더·스키마 오류를 피드백하는 수리 루프) → 사람 게이트(생성 `.lf` + docgen
규칙서 병렬 확인) → bmc/sim 실행**의 웹 인터페이스를 둔다. 시트→`table` 절은 LLM 없이
결정론 변환. 판정은 항상 solver(원칙 1) — LLM은 번역과 설명만 한다.

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
> 그 위에 **논리 증명 백엔드(`logic/`·Z3·BMC, `ludoforge bmc`)** 와 **추정 백엔드
> (`sim/`·Monte Carlo, `ludoforge sim`)** 를 사용자 백엔드로 둔다. **PRISM(`prob/`)은 D23으로
> 사용자 표면에서 내려, 소형 모델에서 sim을 검정하는 *테스트 전용 교차검증 오라클*로만 남는다.**
> 전이 시스템(§4.1)을 모델로 공유하고 질의 dialect는 백엔드별로 가른다. 배경·용어는
> [docs/concepts.md §8](docs/concepts.md).

```
기획 DSL (.lf 파일, git 관리, SSOT)
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
초기 YAML(`.rule`)에서 자체 문법(`.lf`, Lark)으로 승격했고(D21·6차 마일스톤), YAML
프론트엔드는 D32에서 제거해 표면 언어는 `.lf` 하나다. 문법 명세는 PLAN.md 6차 §3,
구현은 `core/text_loader.py`.

> **표면 언어 = 외부 DSL `.lf` (D21 도입 → D32 단일화):** YAML에 문자열로 박힌
> 미니언어 2겹(표현식 D2 + 템플릿 D18)을 **하나의 비-튜링완전 외부 DSL(`.lf`)**로 통합했다
> (`core/text_loader.py`, Lark). 로더 진입점(`load_rule_file`/`load_rules`)은 `.lf`만
> 받고 `.rule`/`.yaml`은 안내와 함께 거부한다(D32). 핵심 의미 = **`=`(대입) vs `==`(비교)
> 분리**: 다음상태 효과는 *이미* 대입+프레임이므로(전이 `then` → `next.X` 배정·미언급 변수
> 유지, D15·§4.1) 효과(`then`/`outcomes`)엔 `=`(대입; `then` 문맥이 곧 다음상태), 같은상태
> 술어(`when`·`init`·정적 `constraint`·`check`)엔 `==`. (다음상태 마커 프라임 `var'`은
> D22로 제거 — `then` 문맥이 잉여로 만듦.) 다중 효과는 `and`가 아니라 `;`(병렬 대입).
> 표 색인은 1급 식(`win[mon][cls]`), `${}`는 id 이름 보간에만. IR은 불변(AST→기존 IR
> lowering) → 백엔드·결정론 경계 무회귀. **참조 예제: `examples/dungeon.lf`.**
> 명세는 PLAN.md 6차 §3, 근거는 decisions.md D21·D32.

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
- `min(a, b, …)` · `max(a, b, …)` 함수(위치 인자 ≥2, 좌측 fold)는 **포화/클램프**용으로
  허용하되 **효과(전이 `then`/`outcomes`)와 요율 식(`pref`/`weight`, D26)에서만** 쓴다 —
  가드·constraint·init·expect·check 같은 술어에서 쓰면 schema가 거부한다(요율은 Z3에
  가지 않으므로 안전 — 예: 욕심 `pref max(win_gold - gold, 0)`). 누적 변수의 오버플로를 가드 없이 상한에서
  포화시키는 데 쓴다(예: `next.gold == min(gold + reward, 30)` — 보상·몬스터·상태를 가드로
  엮지 않음, 오버플로 회피는 갱신식의 책임). 번역: Z3는 `If`로 fold(`min(a,b)=If(a<=b,a,b)`),
  sim은 파이썬 내장, PRISM은 내장 `min`/`max`로 그대로. 그 외 함수(`abs` 등)는 비지원이라 거부.
  문법(`.lf`)은 호출을 어디서나 파싱하고 효과 전용 제한은 schema가 강제한다(generic + gate).

표현 가능해야 할 룰 패턴:
- 수치 공식(LIA): 스탯/데미지/비용.
- 조건부 효과: `Implies` (버프 활성 시 ...).
- 상호 배제 상태: `Not(And(stealthed, attacking))`. **(구현됨, D6)**
- 비율/확률(LRA): 확률 합 = 1 등. **(구현됨, D7 — 피저빌리티/상수 분모)**

**주의:** 비선형 산술(변수×변수, 예 `atk * crit_mult`)은 NIA라 느리거나
결정 불가. 가능하면 한쪽 상수화 또는 구간 분할.

### 4.1 전이 시스템 확장 (다중 백엔드, D11~D14)

정적 스냅샷(위)에 더해, 턴·이동·누적이 있는 **동역학**을 위한 전이 시스템 구문을 둔다.
공유 IR(`core`)이 이를 표현하고, 논리 백엔드(Z3/BMC)와 추정 백엔드(sim/Monte Carlo)가 같은
모델을 다르게 해석한다(`ludoforge bmc`/`sim`). PRISM(`prob/`)은 테스트 전용 교차검증 오라클이다(D23).

```text
init: gold == 0 and room == center      // 초기 상태 술어(선택)

// 상태 → 다음 상태. 효과는 var = … 대입(다음 상태), 가드는 == 비교(D21)
transition descend:
    when room == l1                     // 가드(선택)
    then room = l2                     // 결정적 — weight=1.0 단일 outcome으로 정규화
transition fight:
    when room == l2
    outcomes:                           // 확률 분기. weight는 확률 백엔드용 주석
        0.7 -> gold = gold + 500
        0.3 -> gold = gold
// 플레이어 선택(pref, D20): 아래 둘은 room==l2에서 동시 enabled → sim이 pref로 표집.
transition dive:  when room == l2  pref 0.3  then room = l3      // 욕심
transition leave: when room == l2  pref 0.7  then room = center  // 안전

// 질의. kind로 백엔드 공통 의미 표현
check winnable  reachable: gold >= 10000 and room == center
check gold_ok   invariant: gold >= 0
check gold_dist distribution: gold                        // sim 전용 — 종료 상태 분포 추정(D19)
```

규칙:
- 다음 상태 효과는 자체 문법에서 **`var = expr`**(대입; `then`/`outcomes` 문맥이 곧 다음상태)로
  쓰고, IR에선 **`next.<var> == expr`** 문자열로 lowering된다. `=`(효과)·`==`(술어) 판별은
  문맥+연산자가 강제한다 — 효과에 `==`(비교)를 쓰거나 가드(`when`)·init·expects·check에 `=`(대입)를
  쓰면 **구문 오류**(D22). 다중 효과는 `{ a = …; b = … }`(병렬 대입 집합 → IR에선 `and` 결합).
  다음상태 참조는 효과의 LHS에서만 가능하다(우변·가드는 현재 상태). 프라임 표기는 제거됨(D22).
- **constraint 등식으로 핀되는 변수(`then var == 값`)는 transition 효과로 갱신 금지(D24).**
  그런 변수는 *모든 상태 불변*인 파생 상수(예: 던전!의 `win_gold` = role의 함수)다. bmc는
  이 constraint를 **매 스텝 불변식**으로 강제하지만(D15) sim은 **init 파생에만** 쓴다(dialect
  분리 D11) → 효과가 핀 변수를 갱신하면 두 백엔드 의미가 갈라진다(bmc는 후속 상태를 불변식
  위반으로 UNSAT 가지치기 → 전이 발화 불가·데드락 오탐, sim은 멀쩡히 변경 → 판별 기준선이
  게임 중 이동). 이 조용한 불일치를 `schema.validate()`가 정적으로 거부한다(`_check_constraint_
  pinned_not_mutated`). **좁게만** 막는다: `<=`/`>=` 류 **관계형** constraint는 변수를 특정값으로
  핀하지 않으므로(=핀 대상 아님) 갱신과 공존 합법 — 등식 핀만 충돌한다. 게임 중 변해야 할
  목표값이면 constraint로 파생하지 말고 init에서 고정한 **순수 상태 변수**로 둔다.
- 확률 `weight`는 골격 위 **주석**이다(D12): 논리 백엔드는 지우고(weight-erasure) 분기를
  비결정으로, 확률 백엔드는 가중치를 살려 본다. 정성(논리) 모델은 정량 모델의 건전한 추상.
  - **상태 의존 weight(D26):** 상수 대신 **현재 상태의 식**을 쓸 수 있다(예: 비복원 추출
    `l2_goblins / (l2_goblins + l2_dragons)`). 전이 직전 상태에서 평가해 정규화 표집하며,
    음수/합0은 sim이 런타임 거부 — **weight 합이 0이 될 수 있는 상태(덱 소진 등)는 가드로
    배제**한다(enabledness는 가드 단독, 백엔드 공통 규율). PRISM 오라클은 비율형
    `(w_i)/(Σw)`로 렌더. **BMC 과근사 주의:** erasure는 식이어도 지우므로 weight가 0인
    분기도 "가능"으로 탐색한다(reachable 증인이 확률 0 분기를 밟을 수 있음 — 불변식/
    데드락엔 건전). 단, 덱 카운터처럼 도메인 하한이 소진 분기를 막으면 과근사가 정확해진다.
- 전이 `pref`는 **플레이어 선택**의 상대 가중치다(sim 전용, D20). 한 상태에서 여러 전이가
  동시에 enabled일 때 sim은 매 스텝 **2단 표집**한다: ① enabled 전이를 `pref`로 골라(정책)
  → ② 그 전이의 outcome을 `weight`로 고른다(환경 우연). `weight`(D12, 우연)와 의미가 다른
  별도 키워드다 — **BMC·PRISM은 `pref`를 무시**한다(weight-erasure와 일관, dialect 분리 D11).
  - **상태 의존 pref(D26):** 상수 대신 현재 상태의 식으로 **적응적 정책**을 표현한다
    (예: 욕심이 남은 목표액에 비례 `pref max(win_gold - gold, 0)` — 목표 달성 시 0이 되어
    귀환). co-enabled 정규화·opt-in 안전망·enabled 1개 rng 미소비 등 D20 의미는 전부
    불변이며, co-enabled 합이 0이 되지 않게 상수 기준선을 하나 두는 것이 안전하다.
  - **주사위 닫힌형 `chance`/`rest`(D30, `.lf` 전용):** outcome weight 자리에
    `chance(2d6 >= beat[mon][cls])`(dice 원자 `NdM` 1개 — n≥1·m≥2·n×m≤10000, 목표값은
    desugar 후 **상수** — 리터럴·표 색인·loop 변수)와 잔여 `rest`(블록당 1회 = 1 − 나머지
    상수 가중치 합)를 쓴다. 로더가 `Fraction`으로 정확 계산해 기존 **float weight로
    lowering** — IR·세 백엔드 불변(D18 계보 순수 desugar). 룰북 원형(격파 목표값)이 SSOT에
    남고 승률 매직 넘버 표가 사라진다(예: dungeon.lf `beat`/`fumble` 표). 상태 의존 확률은
    D26 식 weight의 몫이며, chance/rest는 **상수 가중치와만** 혼합(합>1·rest 중복·상태 의존
    목표는 거부). `pref`엔 불허(정책은 주사위가 아님 — 문법 차원 거부).
- 전이 `player`는 **소유 선언**이다(D27, 다인 게임 — `.lf` 전용). `player p1`처럼 선언된
  enum 값(관례상 `turn` enum)을 달며, 생략 시 무소속(환경 전이). **태그는 스케줄러가
  아니다** — 누구 턴인지는 여전히 `turn` enum + 가드/효과의 몫이고 전이 시스템 의미는
  불변. sim은 co-enabled 선택 집합의 소유가 **혼성**(플레이어 간, 또는 태그+무소속)이면
  가드 실수로 보고 명시 거부한다(동시 수 게임은 비지원). BMC/PRISM은 태그를 무시한다
  (weight-erasure·pref 무시와 같은 계보). 정책 라벨에 플레이어를 명시한다. 예제:
  `examples/dungeon_race.lf`(2인 레이스 — 턴 교대·공유 덱·비대칭 정책).
  - 미선언(`pref` 없음)은 **None**으로, "1.0 선언"과 구분한다(opt-in 안전망, §2·D20):
    co-enabled 집합에 하나라도 미선언이 섞이면 sim은 의도치 않은 가드 중첩으로 보고 거부한다
    (`DtmcViolation`). 균등 선택은 같은 `pref`를 명시해 얻는다. enabled가 1개면 선택이 없어
    `pref`는 무시되고 rng도 소비하지 않는다(기존 DTMC 모델의 재현성·비트 동일 보존).
  - 결과는 **"주어진 정책 하의 추정 · Pmax 아님"**으로 라벨한다 — 고정 정책의 값은 Pmax의
    하한이다(정책이 우연히 최적일 때만 일치). 예제: `examples/dungeon.lf`(욕심 vs 안전 pref).
- `checks`의 `kind` ∈ {`reachable`, `invariant`, `no_deadlock`, `distribution`}.
  `reachable`/`invariant`는 `that`(상태 술어), `distribution`은 `expr`(수치식, **sim 전용** —
  평균·CI·백분위·히스토그램으로 추정, D19)을 둔다. 질의 dialect는 백엔드별로 가른다(D11).
  (PCTL `kind: prob`은 D23으로 사용자 표면에서 제거 — PRISM 오라클은 reachable→Pmax로 충분.)
  bmc는 base가 k까지 통과한 속성을 **k-귀납으로 무한 지평 증명 승격** 시도한다(D25):
  `invariant`→`holds`·`no_deadlock`→증명·`reachable` 미도달→`unreachable`(도달 불가 확정,
  종료코드 1). 비귀납/unknown은 유계 결과로 정직하게 남긴다.
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
            win[mon][cls] -> gold = gold + reward[mon]   // 표 색인도 1급 식
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
- **잔여 계산은 D30으로 해소:** `${1 - win - death}` 같은 **산술 계산식**은 부동소수
  정밀도 문제로 보류였으나, 주사위 닫힌형에서는 `rest`(유리수 잔여, §4.1 D30)가 정확히
  대체한다. 일반 산술 보간은 계속 미도입.

### 4.3 배열/인덱스 변수 — 유한 색인 스칼라 가족 (D28)

플레이어·유닛처럼 구조가 같은 개체별 상태를 위해 **유한 색인 배열**을 선언한다.
구현은 D18 계보의 **순수 desugar** — 로더가 스칼라 가족으로 펼치므로 IR·세 백엔드·
결정론 경계가 불변이다.

```text
domain {
    turn: enum { p1, p2 }
    gold[p1, p2]: int 0..30        // → 스칼라 gold_p1·gold_p2로 펼침(선언 순서 유지)
}
for p in [p1, p2]:
    transition "earn_${p}":
        when turn == p and gold[p] < 30      // 정적 색인(loop 변수) → gold_p1 등으로 해소
        player p
        then gold[p] = gold[p] + 1
check leader reachable: gold[turn] >= 10     // 동적 색인(enum 변수) — 읽기 전용
```

- **정적 색인**(리터럴·`for` loop 변수)은 선언·식·효과 LHS 모두 허용 — 스칼라 이름으로
  치환된다. 배열 × `for` 템플릿 × 표(D18)의 결합이 다인 게임의 수동 복제를 접는다
  (`examples/dungeon_race.lf` — 수동판과의 IR 등가는 `tests/fixtures/race_manual.lf`
  골든이 영구 증명).
- **동적 색인**(`gold[turn]` — 색인이 enum 변수)은 **읽기 전용**(술어·효과 RHS·요율 식).
  desugar가 유한 case-분기 IfExp(`gold_p1 if turn == p1 else gold_p2`)로 lowering하고
  sim(평가)·Z3(`If`)·PRISM(ternary)이 지원한다. **IfExp는 desugar 산출물로만 존재** —
  문법에 삼항이 없어 사용자 표면은 비-튜링완전 그대로. 색인 enum의 값 집합은 배열 색인
  집합에 덮여야 한다(아니면 거부 — 조용한 잘못 매핑 방지).
- **효과 LHS 동적 색인(`gold[turn] = …`)은 보류·거부** — 프레임(D15)이 "모든 원소 조건부
  갱신"이 되어 세 백엔드 수술 필요. 턴제의 "현재 플레이어" 갱신은 플레이어별 전이(가드
  `turn == p`) + 정적 색인이 관례.
- **경계(비도입):** 가변 길이 시퀀스·삽입/삭제·손패 연산 없음 — 카운트 멀티셋(D26 비복원
  추출)이 덱/자원의 지원 표현. 펼친 이름(`gold_p1`)이 리포트에 그대로 보이며(추적 가능,
  원칙 4), 기존 변수와 충돌하면 로드 거부. **펼치기는 소스만 줄인다** — 검증 모델
  크기(상태공간)는 그대로다(§4.2 주의와 동일).

### 4.4 문서 메타데이터 — 규칙서 SSOT (D29)

`.lf`를 검증 모델이자 **사람이 읽는 게임 규칙서의 SSOT**로 쓰기 위한 문서 절(`.lf` 전용,
12차). 세 백엔드는 전부 무시한다 — D12 weight-erasure·D20 pref·D27 player와 같은
**"지워지는 주석" 계보**라 검증·추정 의미와 부하가 불변이다.

```text
section "경제 규칙"                            // 문서 목차 절(최상위) — IR 미탑재
domain { gold: int 0..30 desc "보유 보물" }    // 변수 desc → 규칙서 용어집
table reward desc "처치 보상" { goblin: 2 }    // 표 desc — IR 미탑재(문서 전용)
constraint cap:
    desc "보물 상한"
    note "보상이 상한([[gold]] 선언 max)을 넘으면 버려진다(포화)."  // 산문 — 반복 선언 가능
    ref "던전! 2012판 룰북 p.12"               // 출처 — 외부 참조라 무결성 검사 제외
    tag economy, balance                       // 분류 라벨
    then gold <= 30
```

- **IR passthrough:** `note`/`ref`/`tag`는 frozen `Doc(notes, ref, tags)`으로 각 선언 IR
  (`Constraint/Transition/Check/Expect.doc`)에, 변수 `desc`는 `Variable.desc`에 실린다 —
  기본 None이라 골든 IR 등가 무회귀. `section`·table desc는 IR 미탑재(문서 전용 —
  docgen이 desugar 전 파스 트리에서 소비).
- **`[[이름]]` 상호참조(드리프트 억제):** note/desc 본문의 `[[이름]]`은 변수·enum 값·선언
  id·table 이름을 가리켜야 하며 미정의면 **로드 거부** — 존재하지 않는 것을 서술하는 문서
  부패를 기계가 잡는다. 한계: 존재만 검사(산문 *내용* 불일치는 못 잡음 — 규칙서가 형식부를
  산문 옆에 병기해 사람이 대조). `for` 템플릿 안 note의 `${}`는 id처럼 보간된다.
- **규칙서 생성:** `ludoforge doc <path.lf> [-o 출력] [--md]`(`core/docgen.py`) — desugar
  *전* 트리 기반이라 for 템플릿·표가 저자가 쓴 **접힌 형태**로 렌더된다(전투 8종 → 템플릿
  1개 + 표). check들은 맨 끝 "검증·추정 성질" 절로 모인다(산문 약속이 아니라 bmc 증명·sim
  추정으로 기계 확인 — 일반 규칙서와의 차별점). 생성 전 로드·스키마·참조 게이트 통과 요구
  (깨진 모델의 규칙서는 안 만든다). 자체 완결 HTML(외부 의존 0)·결정론·단방향 파생 뷰
  (수정은 항상 원본 `.lf`). 참조 예제: `examples/dungeon.lf`·`dungeon_race.lf`(저술 완료).

### 4.5 ghost 서술 변수 — 검증 제외 상태 (D31)

"게임당 전투 횟수" 같은 **서술적 정량**을 상태 변수로 넣으면 BMC/PRISM 상태공간이 곱으로
커진다. `ghost` 수식어(`.lf` 전용, 14차)는 이 트레이드오프를 끊는다 — **sim만 실행**하고
**bmc/PRISM 오라클은 소비 전에 `erase_ghosts`(core/ghost.py)로 상태공간에서 완전 제거**한다
(k-귀납 증명 지위 불변, 리포트 각주로 제거를 명시).

```text
domain { ghost fights: int 0.. }        // 무한 int여도 무방 — erase 후 소비라 PRISM 게이트 무해
init: … and fights == 0                 // ghost는 init 상수 고정 필수(자유 sweep·파생 금지)
transition fight:
    …
    then { gold = gold + 2; fights = fights + 1 }   // ghost 대입은 실제 효과에 병기
check fight_count distribution: fights  // sim 전용 — "서술 변수(논리 검증 제외)" 라벨
```

- **단방향 의존(핵심 불변식): "ghost 전부 제거 시 비-ghost 궤적 비트 동일."** ghost를 읽을
  수 있는 곳 = ghost 대입의 RHS·`distribution` expr·문서 절뿐. **가드·constraint·expects·
  reachable/invariant that·pref/weight·비-ghost 효과 RHS의 ghost 참조는 schema가 거부**
  (`_check_ghost_one_way` — D24 계보의 조용한 백엔드 분기 차단). 게임에 영향을 줘야 하는
  값이면 ghost를 떼라(거부 메시지가 안내).
- ghost 대입은 rng를 소비하지 않아 sim의 비-ghost 추정이 **비트 동일**하게 보존된다. 배열
  (D28)과 결합 가능(`ghost visits[p1, p2]: …` — 원소 전부 승계). `check_finite_state`는
  ghost를 건너뛴다(erase 후 기준). 효과가 전부 ghost인 분기는 erase 후 `True`(항등 효과 —
  분기 구조 보존). 참조 예제: `examples/dungeon.lf`의 `fights`.

---

## 5. 기술 스택 / 환경

- **언어:** Python 3.11+
- **패키지 관리자: **uv**
- **SMT:** `z3-solver` (Z3, Microsoft Research)
- **DSL 파싱:** **Lark 기반 외부 DSL(`.lf`)** — `core/text_loader.py`(자체 문법·`=`/`==`
  분리, D21·PLAN.md 6차). 진입점 `load_rule_file`/`load_rules`는 `core/loader.py`
  (IO·디렉토리 병합)이며 `.lf`만 받는다 — 초기 YAML 프론트엔드는 D32로 제거.
  런타임 evaluator(§7, sim)는 잔존.
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
  loader.py          # 로드 진입점(.lf 파일/디렉토리 병합) — 파싱은 text_loader
  text_loader.py     # 자체 문법(.lf, Lark) → 내부 IR (D21)
  schema.py          # 스키마·참조 검증 + check_finite_state(PRISM 게이트) + check_dtmc(sim 게이트)
  htmlviz.py         # HTML 리포트 인터랙션(의존성 없는 호버 툴팁 CSS·JS) — sim --html 전용(bmc는 값을 인라인 노출해 미사용)
  docgen.py          # .lf → 규칙서(HTML/MD) 생성 — desugar 전 트리 기반(D29), ludoforge doc
  ghost.py           # ghost 서술 변수 제거(D31) — bmc/PRISM 소비 전 순수 IR→IR 변환(sim은 원본)
ludoforge/           # 우산: 통합 CLI 진입점·프로젝트 버전
  cli.py             # ludoforge check / bmc / sim / doc / web  (PRISM은 테스트 오라클, CLI 미노출/D23)
web/             # 웹 인터페이스 (D32 P3) — 산문/시트 → LLM 번역 → 사람 게이트 → 실행
  sheet_import.py    # CSV → table 절 결정론 변환(LLM 불개입)
  translate.py       # 산문 → .lf LLM 번역 — 로더·스키마 오류 되먹임 수리 루프(판정은 solver, 원칙 1)
  runs.py            # check/bmc/sim 실행 함수형 코어(CLI와 같은 파이프라인)
  jobs.py            # 인메모리 잡(스레드) — bmc/sim 폴링
  app.py             # FastAPI 셸 + web/static/index.html(단일 페이지, 규칙서 병렬 확인)
  config.py          # configs/web.yaml 로드(모델·수리 루프·자원 상한 클램프)
logic/           # 논리 증명 백엔드 (Z3/BMC)
  solver/
    translator.py    # IR → Z3 제약식
    checks.py        # 정적 모순/도달성 검사
    bmc.py           # 전이 시스템 BMC (k 언롤링·도달성·불변식·데드락)
    report.py        # unsat core·반례 → 사람용 리포트
    html_report.py   # BmcReport → 자체 완결형 HTML(경로·반례 시각화, 의존성 없음) — bmc --html
sim/             # 확률 추정 백엔드 (Monte Carlo, 주 정량 경로 — D19)
  engine.py          # IR 전이 시스템 인터프리터·DTMC 게이트·1 run 표집
  aggregate.py       # 결합가능 집계(Welford·히스토그램·rule-of-three)
  runner.py          # multiprocessing 분배·SeedSequence.spawn(분산 구조는 후속)
  report.py          # 추정+CI·절단 비율 한국어 리포트("증명 아님" 라벨)
  html_report.py     # SimReport → 자체 완결형 HTML(인라인 CSS·SVG, 의존성 없음) — sim --html
prob/           # 확률 증명 오라클 (PRISM — 소형 모델 교차검증, D19)
  prism_gen.py       # IR → PRISM 모델·속성
  runner.py          # prism 실행·결과 파싱(미설치 시 graceful)
rules/               # 실제 기획 룰 (.lf), git SSOT
examples/            # 모순/정합/전이 시스템 예제 (.lf)
tests/               # 단위 + 모순/정합 코퍼스 + BMC/sim/PRISM
configs/             # 설정 yaml (web.yaml — 웹 모델·자원 상한)
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

