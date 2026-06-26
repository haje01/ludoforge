# PLAN.md — Ludoforge 작업 계획

> 진행 상태는 [PROGRESS.md](PROGRESS.md), 설계 결정의 "왜"는
> [docs/decisions.md](docs/decisions.md), 아키텍처 SSOT는 [CLAUDE.md](CLAUDE.md).
> 완료된 작업의 상세 이력은 git 커밋과 decisions.md에 있다.
>
> **명명 규약 갱신 (2026-06-17):** 디렉토리 `ruleforge/→logic/`, `probforge/→prob/`,
> `forge_core/→core/`; 브랜드명 **RuleForge/ProbForge**는 **'논리 백엔드'/'확률 백엔드'**로
> 통일. 이하 옛 이름·경로는 역사적 표기다.

**기반(완료):** 1차·2차 마일스톤으로 정적 논리 검사기가 end-to-end 동작한다
(`ludoforge check <path>`, LIA/real/enum/bool, 6가지 모순 유형, 테스트 99건).
3차(다중 백엔드)로 전이 시스템·BMC(`ludoforge bmc`)·PRISM(`ludoforge prob`)이 붙었다.
상세는 [PROGRESS.md](PROGRESS.md)와 decisions.md D1~D18 참조.

---

## 4차 마일스톤 — 정량 추정 백엔드 (Monte Carlo `sim/`) — ✅ 완료 (2026-06-24)

> 설계 근거·결정은 **decisions.md D19**(D13·D14 갱신/개정). 한 줄: **정량 백엔드의 무게
> 중심을 망라적 증명(PRISM)에서 표집 추정(Monte Carlo)으로 옮긴다** — PRISM 상태폭발
> 천장을 우회해 고차원·연속(real)·큰 범위를 다루고, 분포를 사람에게 보여 튜닝을 돕는다.
> PRISM은 소형 모델 *교차검증 오라클*로 남는다.

### 1. 동기와 한 줄 목표

PRISM(D16)은 정확하지만 상태폭발이 너무 쉽게 천장에 닿는다(gold·win_gold `[0..30000]`만
으로 ~70억 상태 → 빌드 멈춤). 그런데 **정확값이 필요한 영역이 곧 폭발로 불가능한 영역**
이다. 존재·건전성(승리 가능·데드락·불변식)은 **이미 Z3/BMC가 증명**하므로, 정량 *크기*
(승률·기대 길이·분포)는 **표집 추정**으로 내려 고차원까지 확장하고 분포를 사람이 읽게 한다.

### 2. 4대 구조 결정 (사용자 비준 2026-06-23, D19)

1. **PRISM은 오라클로 유지** — 소형 유한 모델에서 증명기로 시뮬레이터를 교차검증(신뢰 부여).
2. **DTMC만 허용** — 도달 상태마다 enabled 전이 ≤1(분기는 outcome 가중치로만). 비결정은
   거부(BMC/PRISM-mdp 몫). D15 weight-erasure의 대칭 반대: 가중치 살리고 비결정 막는다.
3. **튜닝을 목표로 승격**(D14 개정) — 분포·직업별 승률을 *추정*으로 답한다("증명 아님" 라벨).
4. **로컬 multiprocessing 우선 + 분산 구조 설계** — 결합가능 집계로 transport는 후속 교체.

### 3. 핵심 설계 포인트

- **재사용:** IR은 이미 guarded-command 전이 시스템 → sim은 그 *인터프리터*다. D15 프레임
  (미제약 변수=유지) 의미·ast 화이트리스트 규율(§7, `eval` 없는 *평가기*) 그대로.
- **초기 자유변수 = sweep**(전이 비결정과 구분): `init`이 안 고정한 enum/bool은 설정
  파라미터 → 값별로 분리해 각각 N회 표집·분포 보고(= 직업별 승률 비교).
- **재현성:** numpy `SeedSequence.spawn(N)` — 워커 수·스케줄 무관 동일 결과.
- **정직성(DNA):** 모든 리포트에 N·신뢰구간·지평 H·미종료 비율·미관측 rule-of-three(≈3/N)·
  "증명 아님 · 표집 추정" 라벨. 0/N을 "불가능"이라 하지 않는다(존재 증명은 Z3/BMC).

### 4. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — 범위 합의 & D19 기록** *(행위 변경 없음)* — ✅ 완료 (2026-06-23)
- decisions.md D19 기록, D13·D14 갱신/개정, CLAUDE.md §1 비목표·§4.1·§6 정련. 사용자 비준.

**Phase 1 — sim 엔진 코어 (`sim/engine.py` + 표현식 evaluator)** *(행위적 변경)* — ✅ 완료 (2026-06-23)
- IR 전이 시스템 인터프리터: 상태=변수 dict, 가드 평가→enabled 1개 선택(DTMC 게이트:
  enabled>1이면 거부)→weight로 outcome 표집→next.* 배정+프레임 유지(D15). 지평 H까지/종료까지.
- ast 화이트리스트 **평가기**(Name·BinOp·Compare·BoolOp·UnaryOp·Constant→파이썬 값, `eval` 금지).
- **성공 기준:** DTMC 픽스처(coin) 1 run이 결정적 seed에서 재현, 비결정(enabled>1) 모델
  (nondet)은 친절히 거부. **던전!은 MDP(hall 귀환 시 enter/claim 동시 enabled)+자유 init**
  이라 Phase 1 거부 대상 — 거부 메시지로 경계 문서화(재현 픽스처가 아님). 자유 init sweep은 Phase 2.

**Phase 2 — 집계 & 리포트 (`sim/aggregate.py`, `sim/report.py`)** *(행위적 변경)* — ✅ 완료 (2026-06-24)
- 결합가능 집계: ProportionAggregate(Wilson CI·rule-of-three), DistributionAggregate
  (Welford 평균/분산 + 값→빈도 카운터로 이산 백분위, _HIST_CAP 초과 시 평균만). 둘 다 merge 지원.
  checks kind 매핑: reachable→P̂(도달), invariant→위반분수+예시 trace, distribution→평균·CI·백분위.
- IR/loader/schema에 `kind: distribution`(+`expr` 필드, next.* 불가) 추가. 초기 자유변수
  sweep(enum/bool 데카르트 곱, int/real 자유는 거부). 흡수(fixpoint) 상태 자연 종료 감지로
  절단 지표 정상화. "증명 아님" 라벨·신뢰구간 한국어 리포트.
- **성공 기준:** DTMC 클래스밸런스 픽스처(arena)에서 직업별 승률 추정+CI 출력(fighter 0.73 >
  wizard 0.42 > rogue 0.22 = win³ 일치), 미관측 사건(progress≥4)은 3/N 상한으로 보고. 던전!은
  여전히 MDP+constraints 파생(win_gold)이라 sim 비대상 — DTMC 던전판은 Phase 4 오라클.

**Phase 3 — runner & CLI (`sim/runner.py`, `ludoforge sim`)** *(행위적 변경)* — ✅ 완료 (2026-06-24)
- `multiprocessing.Pool`로 청크 병렬, numpy `SeedSequence([seed,ci]).spawn(청크수)`로 청크별
  독립 스트림. 청크 수는 **워커 수와 무관**(min(samples,64)), 병합은 **청크 순서대로** →
  부동소수까지 결정적. CLI `ludoforge sim <path> [-n samples] [-H horizon] [-s seed] [-w workers]`.
- 분산 심: 집계가 결합 가능(BatchAggregate.merge)·청크 task가 pickle 가능 → transport만 교체하면
  Ray/dask/k8s로 확장(구현은 로컬 multiprocessing). aggregate를 RNG-무관 run_batch로 리팩터.
- **성공 기준:** 워커 1↔4 SimReport가 **비트 단위 동일**(테스트), 청크 병렬로 코어 분산. numpy
  의존성 추가(스텁 호환 위해 <2.2 핀).

**Phase 4 — PRISM 오라클 교차검증** *(검증)* — ✅ 완료 (2026-06-24)
- **DTMC 던전판**(`examples/dungeon_sim.rule`): 전략을 가드에 인코딩(목표 미달이면 싸우고
  달성이면 귀환·승리 — 상호 배타 가드)해 결정적. `win_gold`는 클래스별 constraints로 파생.
- sim에 **constraints 전파**(initial_state) 추가 — role로부터 win_gold 파생(PRISM init 인코딩
  대응). sweep는 constraint 파생 변수를 제외. `distribution`을 BMC·PRISM이 건너뛰도록 수정.
- 같은 DTMC를 role 고정해 PRISM에 넣으면 Pmax=Pmin=정확값 → sim 직업별 승률 추정의 95% CI가
  그 값을 포함(fighter 0.922·rogue 0.834·wizard 0.945, |Δ|<0.0022). PRISM 미설치 시 skip.
- **성공 기준:** sim↔PRISM 일치 회귀 통과(PRISM 4.10.1 실측). 추정기 신뢰 확립 — D13 반론 무력화.

**Phase 5 — real·고차원 시연** *(신규 표현력 시연)* — ✅ 완료 (2026-06-24)
- `examples/market_sim.rule`: 두 자산(gold·silver, **real**)을 30라운드 복리로 굴리는 다변수
  연속 모델. PRISM은 real을 유한상태 게이트(D13)에서 **즉시 거부**, sim은 표집으로 연속 분포를
  추정(평균 2.66 성장·금 2배 84.9%·연속이라 백분위 생략·평균/CI만, 불변식 0위반→rule of three).
- **성공 기준:** PRISM이 거부하는 real 모델을 sim이 분포로 답한다(테스트로 PRISM 거부 + sim
  추정 동시 확인). 연속 데이터의 히스토그램 넘침→평균/CI degradation도 정직하게 시연.

### 5. 위험 & 미해결 질문

- **DTMC 정적 검사:** v1은 런타임(표집 중 enabled>1 발견) 거부. 정적 사전 거부(Z3로 두
  가드 동시 충족 가능성 질의)는 후속 — 도달 불가 상태의 가짜 충돌을 피하려면 정교 필요.
- **초기 자유변수 폭발:** 자유 enum/bool 조합이 곱으로 커질 수 있음 → 상한+절단 보고.
  연속(real) 초기 자유변수의 sweep 의미는 미정(표집? 거부?) — 일단 init가 고정 요구.
- **지평 H 편향:** H 내 미종료 run의 reachable/distribution 해석 — 절단 비율을 항상 보고,
  H를 늘려 수렴 확인하는 가이드.
- **CI 산정:** 비율은 Wilson, 평균은 t-기반 — 표본 독립 가정(SeedSequence가 보장) 명시.
- **distribution kind 변경 범위:** `core/ir.py`·loader·schema에 `expr` 필드/kind 추가 —
  세 백엔드 중 sim 전용임을 스키마가 명확히(다른 백엔드는 무시/거부).

---

## 5차 마일스톤 — sim 선택 확률(무작위 정책) — ✅ 핵심 완료 (2026-06-24, Phase 1~3)

> 설계 근거·결정은 **decisions.md D20**(D19의 "DTMC만 허용"을 *조건부* 완화). 한 줄:
> **플레이어 *선택* 비결정에 확률(`pref`)을 배정해 무작위 정책으로 해소** — 게임 규칙과
> 전략을 분리하고, 최적이 아닌 현실 플레이어의 행동을 모델링/민감도 분석한다.

### 1. 동기와 한 줄 목표

D19 sim은 enabled 전이가 2개 이상이면 거부해, 전략을 가드에 박아넣게 한다
(`examples/dungeon_sim.rule`이 "목표 미달이면 싸우고 채우면 귀환"을 상호배타 가드로 인코딩).
이는 **규칙과 정책을 한 파일에 엉키게** 하고(전략 바꾸려면 `.rule` 복제), PRISM `Pmax`가
주는 *최적 천장*만 볼 수 있게 한다. 현실 플레이어는 최적이 아니다 — **행동 모델링·민감도
분석**(귀환을 70%로 일찍 하면 승률은?)은 Monte Carlo가 잘하는 D19 튜닝 영역인데 표현 불가.
→ **전이 레벨 선호도 `pref`로 플레이어 선택에 확률을 배정**(매 스텝 2단 표집: 정책으로 전이
선택 → weight로 outcome 선택).

### 2. 핵심 설계 (D20)

- **`pref: float = 1.0`(전이 상대 가중치)** — enabled된 것들끼리 **런타임 정규화**(상태 의존).
  `outcomes.weight`(환경 우연, D12)와 **다른 키워드**(플레이어 정책).
- **안전망 = 명시적 opt-in** — enabled>1일 때 *모든* co-enabled가 `pref` 선언 시에만 표집,
  **하나라도 누락/혼재면 `DtmcViolation` 거부**(의도치 않은 가드 중첩을 조용히 덮지 않는다).
- **dialect 분리** — `pref`는 sim 전용. BMC는 erase(weight-erasure 일관), PRISM은 무시·Pmax 유지.
- **정직성** — "주어진 정책 하의 추정 · Pmax 아님" 라벨. 고정 정책 승률은 Pmax의 *하한*.
- **상태 의존 정책** — 가드(후보 좁힘)+`pref`(잔여 해소) 합성. `pref`의 런타임 식(`${state expr}`)은 후속.

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 1 — IR·로더·스키마에 `pref` 도입** *(구조+행위)* — ✅ 완료 (2026-06-24)
- `core/ir.py`: `Transition.pref: float | None = None`(None=미선언 — opt-in 안전망 위해
  "1.0 선언"과 구분, D20 결정3). `core/loader.py`: `_parse_pref`(생략 None·음수·비수 거부),
  `for:`/`${expr}` 템플릿 호환(전체-`${expr}`이면 타입 보존, D18). `core/schema.py`:
  `_check_transition_prefs`(IR 직접 구성 시 음수 방어).
- **성공 기준 충족:** `pref` 있는 `.rule` 로드·음수/비수 거부·템플릿 타입 보존, `pref` 무선언
  기존 파일 None(전체 203 통과·기존 197 무변경 = 하위 호환), BMC/PRISM 무변경. 테스트 6건.

**Phase 2 — sim 엔진 선택 표집** *(행위적 변경, 핵심)* — ✅ 완료 (2026-06-24)
- `sim/engine.py` `run_once`의 `len(enabled) > 1` 분기를 `_select_transition`으로 교체: enabled
  1개면 그대로(rng 미소비 → 기존 DTMC 재현성·비트 동일 보존), 2개+면 모든 전이가 `pref`
  보유 시 정규화 표집(2단 표집: 정책→outcome), 미선언(None) 혼재 시 `DtmcViolation`, 합 0이면
  SimError. 엔진 docstring을 D19→D20으로 갱신.
- **성공 기준 충족:** 골든 픽스처(`tests/fixtures/policy_choice.rule`, pref 0.3/0.7)에서 도달
  분포가 0.3에 수렴(n=4000, |Δ|<0.03), 선택 표집 재현성, 혼재·합0·기존 nondet 모두 거부.
  테스트 5건 추가(전체 207 통과·기존 무변경 = 하위 호환).

**Phase 3 — 리포트 라벨 & 예제** *(행위+문서)* — ✅ 완료 (2026-06-24)
- `sim/engine.py` `uses_policy(ruleset)`(pref 선언 여부) + `SimReport.uses_policy` 플래그
  (두 생성 지점 runner·aggregate에서 채움). `sim/report.py`: 조건부 정책 라벨 "주어진 정책
  (pref) 하의 추정 — 최적(Pmax) 아님 …하한". 선택 없는 순수 DTMC엔 안 띄움(오해 방지).
- 예제 `examples/dungeon_policy.rule`: 던전을 MDP로 두고 "욕심(fight) vs 안전(leave)"을 `pref`
  로 가른 sim 시연(2단 표집). CLAUDE.md §4.1(`pref` 문법·예시·dialect)·concepts.md §9.4.1
  (무작위 정책)·examples/README 갱신.
- **성공 기준 충족:** 정책 라벨 노출(policy_choice·dungeon_policy), 예제 sim/bmc 동작·문서
  링크 일관, arena(pref 무선언) 라벨 미노출 회귀. 테스트 3건(전체 211 통과·기존 무변경).

> **Phase 4(민감도 sweep & PRISM 유도-DTMC 교차검증)는 "보류 중"으로 내림** (2026-06-24).
> 핵심 기능은 Phase 1~3으로 완성됐고, 선택 표집 정확성은 Phase 2 닫힌형 골든 테스트
> (`policy_choice.rule`)로 이미 검증됐다 — Phase 4는 *알려진 구멍*이 아니라 추가 안전벨트·
> 편의라 트리거가 생길 때 착수한다. 상세·트리거는 아래 "보류 중" 참조.

### 4. 위험 & 미해결 질문

- **`pref` 합성 의미:** 가드+`pref`로 상태 의존 정책을 표현할 때, 도달 불가 가드 조합이
  가짜 선택 집합을 만들지 — 골든 코퍼스로 확인.
- **PRISM 유도-DTMC 모드 비용:** `pref`→PRISM 확률 명령 매핑이 기존 Pmax 경로와 충돌 없이
  공존하는지(dialect 게이트). v1은 sim 단독 골든 검증으로 갈음 가능.
- **런타임 식 `pref`(후속):** `${state expr}` 정책은 표현식 evaluator 재사용 가능하나 스코프
  확대 — v1은 상수 `pref`로 한정.

---

## 6차 마일스톤 — 외부 DSL(자체 문법) — ✅ 완료 (2026-06-25)

> **완료:** 자체 문법 `.lf`(Lark) 프론트엔드 — domain·정적식·전이·checks·템플릿·메타데이터를
> 골든 IR 등가로 고정하고 전 예제(14) 이관, YAML(`.rule`)은 디프리케이트(1회 경고). IR 불변
> → 백엔드·결정론 경계 무회귀. 슬라이스(S1~S6) 로그는 [PROGRESS.md](PROGRESS.md).

> 설계 근거는 본 절(착수 시 **decisions.md D21**로 승격). CLAUDE.md §5의 예고
> ("향후 필요 시 Lark/자체 문법")를 실행한다. 한 줄: **YAML에 문자열로 박힌 미니언어
> 2겹(표현식 + D18 템플릿)을 하나의 일관 문법으로 승격**하되, IR은 불변 → 백엔드·결정론
> 경계 무회귀. 표면(프론트엔드)만 교체한다.

### 1. 동기와 한 줄 목표

현재 `.rule`은 순수 YAML이 아니라 **두 겹의 자체 언어를 문자열에 품는다**: ① 표현식
미니언어(`"role == warrior and level == 100"`, loader가 ast-화이트리스트로 파싱, §7),
② 템플릿 미니언어(D18: `for:` 곱·`${win[mon][cls]}` 색인 보간·`tables:`). 이 둘은
*호스트가 공짜로 주는 것을 손으로 재구현*한 자리다(D18의 `${1-win-death}` 산술 보류가 증거).
→ **자체 문법 하나**로 통합하면: `and/or/not`·다음상태·`for`·`table`·색인이 모두 1급
시민이 되고, 파서를 직접 소유해 **line:col·도메인 인지 에러**(§7·원칙4)를 준다. 결정적으로
**비-튜링완전 문법**(while·함수·import·부수효과 없음)이라 "룰=선언적 데이터·결정론 경계"
(§2 원칙1·2)를 *문법 차원에서* 강제한다 — Internal(Python) DSL이 런타임에 막아야 하는 것을
애초에 표현 불가로 만든다.

### 2. 핵심 설계 결정

- **`=`(대입) vs `==`(비교) 분리 — 엔진 의미론을 정직하게 노출.** 전이 효과는 *이미*
  대입+프레임이다(검증: `sim/engine.py:301` `apply_outcome`→`_next_assignment`로 `state[var]=eval(rhs)`;
  `logic/solver/bmc.py:221` `_frame`로 미언급 변수 `next.y==y` 유지, D15). 그래서:
  - **효과(`then`/`outcomes`) ⟺ `=`(대입)** — `then` 문맥이 곧 다음상태. **같은상태 술어
    (`when`·`init`·정적 `constraint`·`check.that`) ⟺ `==`(비교).** 판별자는 문맥+연산자.
  - `when gold = 5`(가드 대입)·`then gold == x`(효과 비교)는 **파스 에러** → 오타 방어.
  - **개정(D22):** 초안의 다음상태 마커 프라임 `var'`은 `then` 문맥이 잉여로 만들어 **제거**했다
    (`gold = gold + 1`). PRISM `(gold'=…)` 동형성은 IR(`next.gold == …`) lowering에서 유지된다.
  - **다중 효과는 `and`가 아니라 `;`** — 병렬 대입 집합(`{ gold = 0; room = hall }`).
    `대입 and 대입`은 타입 에러로 차단. PRISM 병렬 업데이트와 정합.
  - **포기:** BMC의 술어 효과(다음 gold > 현재 gold 같은 비결정)를 막는다(sim은 이미 거부). 비결정은
    `outcomes`/`pref`로만 → 백엔드 의미 일치(D11~D14), 코퍼스 실손실 0.
- **데이터/템플릿 1급화** — `table`·`for ... in [곱]`·`win[mon][cls]` 색인이 문법. D18의
  `${...}` 문자열 보간/"전체-`${expr}` 타입보존" 특례는 **id 이름**(`"fight_${mon}_${cls}"`)에만
  남기고, 표현식 안에선 진짜 색인. 펼치기(desugar)는 순수 구문 변환(결정론 경계 무관, §2).
- **비-튜링완전 불변식(1순위)** — `for`는 *명시적 유한 리스트 위 곱*까지만. 일반 루프·재귀·
  IO·조건분기 없음. 깨지면 최대 장점(결정론 경계)이 무너진다 → 문법에 박는다.
- **IR 불변** — AST→기존 IR lowering. 백엔드 3종·스키마·검사는 그대로 구체 IR만 본다.

### 3. 문법 초안 (Lark/EBNF 스케치)

```ebnf
start         : item*
item          : domain_block | table_decl | init_decl | for_block
              | constraint_decl | transition_decl | check_decl

domain_block  : "domain" "{" var_decl+ "}"
var_decl      : NAME ":" var_type
var_type      : "int" range? | "real" range? | "bool"
              | "enum" "{" NAME ("," NAME)* "}"
range         : NUMBER ".." NUMBER              // 선언 경계(min..max)

table_decl    : "table" NAME "{" (entry ("," entry)* | row+) "}"   // 1단(평탄)/2단(중첩)
row           : NAME ":" "{" entry ("," entry)* "}"
entry         : NAME ":" (NUMBER | NAME)

init_decl     : "init" ":" pred                 // 같은 상태 술어(==)

for_block     : "for" binding ("," binding)* ":" INDENT item+ DEDENT  // 데카르트 곱
binding       : NAME "in" "[" NAME ("," NAME)* "]"   // 명시적 유한 집합만(비-튜링완전)

constraint_decl : "constraint" id ":" ("when" pred)? "then" pred      // 정적 == 술어
transition_decl : "transition" id (inline_body | block_body)
inline_body   : "{" ("when" pred ";")? "then" update "}"
block_body    : ":" INDENT ("when" pred)? ("then" update | outcomes) DEDENT
outcomes      : "outcomes" ":" INDENT (weight "->" update)+ DEDENT
weight        : NUMBER | index                  // 상수 또는 table 색인

check_decl    : "check" NAME check_kind
check_kind    : "reachable" ":" pred  | "invariant" ":" pred  | "no_deadlock"
              | "prob" ":" STRING              // PCTL — 백엔드 전용·불투명(core 구문검사 안 함)
              | "distribution" ":" expr        // sim 전용

// ── 술어(같은 상태) vs 대입(다음 상태) ──
pred          : pred "and" pred | pred "or" pred | "not" pred
              | "(" pred ")" | comparison | BOOL_NAME
comparison    : expr CMP expr                   // == != < <= > >=
update        : assign | "{" assign (";" assign)* "}"   // 병렬 대입 집합
assign        : NAME "=" expr                   // var = expr  (then 문맥=다음 상태, D22)
expr          : expr ("+"|"-"|"*"|"/") expr | "(" expr ")" | NUMBER | NAME | index
index         : NAME ("[" NAME "]")+            // win[mon][cls] — 진짜 색인
id            : NAME | STRING                   // "fight_${mon}_${cls}" — ${} 보간은 id에만

CMP : "==" | "!=" | "<=" | ">=" | "<" | ">"     // '=' 단독은 CMP 아님(대입 전용)
COMMENT : "//" /[^\n]*/                          // 줄 주석
// NAME [a-zA-Z_]\w* · NUMBER int|float · STRING "..." · ".." 범위
```

**파스 후 정적 규칙(판별자·게이트):**
1. `=`(assign)은 전이 효과(`then`/`outcomes`)에서만. 그 외 위치(가드·init·pred) → 에러.
2. `==`/CMP는 pred 위치에서만. `=`/`==`(연산자)가 대입/비교를 가른다 — 프라임 마커 없음(D22).
3. `for` 바인딩은 리터럴 enum 값 리스트만(범위·계산 금지). 미정의 이름/색인 실패는 위치 보고 LoaderError.
4. `${expr}`는 `id` 문자열에서만(파라미터·table 이름·색인). 표현식 안에선 색인 노드.
5. 프레임(D15): 효과가 안 건드린 변수는 다음 상태에서 유지 — 백엔드 공통.

### 4. 예시 (`examples/dungeon.rule` 발췌 — 자체 문법)

```text
domain {
    gold: int 0..30   win_gold: int 0..30
    room: enum { hall, l1, l2, l3 }   role: enum { rogue, cleric, fighter, wizard }
    monster: enum { none, goblin, dragon }   status: enum { exploring, won, dead }
}
table win_target { rogue: 10, cleric: 10, fighter: 20, wizard: 30 }
table reward { goblin: 2, dragon: 10 }   table cap { goblin: 28, dragon: 20 }
table win {
    goblin: { fighter: 0.92, cleric: 0.83, rogue: 0.72, wizard: 0.83 }
    dragon: { fighter: 0.58, cleric: 0.28, rogue: 0.08, wizard: 0.72 }
}   // miss, death 동일 구조

for cls in [rogue, cleric, fighter, wizard]:
    constraint "${cls}_win_target":
        when role == cls               // == 비교(같은 상태)
        then win_gold == win_target[cls]

init: gold == 0 and room == hall and monster == none and status == exploring

transition enter_l1:
    when room == hall and status == exploring and monster == none
    then room = l1                    // =  대입(다음 상태)

for mon in [goblin, dragon], cls in [fighter, cleric, rogue, wizard]:
    transition "fight_${mon}_${cls}":
        when role == cls and monster == mon and status == exploring and gold <= cap[mon]
        outcomes:
            win[mon][cls]   -> { gold = gold + reward[mon]; monster = none }
            miss[mon][cls]  -> monster = none
            death[mon][cls] -> { gold = 0; room = hall; status = dead; monster = none }

check winnable        reachable: status == won
check sound_victory   invariant: status != won or gold >= win_gold
check no_stuck        no_deadlock
check best_win_prob   prob: "Pmax=? [ F (status=won) ]"
```

### 5. 단계별 계획 (작은 PR · TDD · Tidy First · IR 무회귀)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 1 — 문법 확정 + Lark 파서 → AST** *(구조)*
- §3 EBNF를 Lark 문법으로. 토큰(`..`·`//`·`${}`)·우선순위(CMP < and/or, `&` 정밀도
  함정 없음 — 자체 문법이라 `and`가 1급) 확정. 산출=위치 보존 AST. **성공 기준:** 코퍼스 전
  `.rule`(신규 표기)이 파스되고 `=`/`==` 오용·`for` 범위·미정의 색인이 line:col로 거부.

**Phase 2 — AST → 기존 IR lowering(desugar 포함)** *(행위)*
- `for`/`table`/`${}` 펼치기 → 구체 항목, AST 표현식 → 기존 IR 노드(`next.X` 등가). 기존
  YAML 로더는 그대로 둠(병행 프론트엔드). **성공 기준:** 자체 `.rule`이 BMC/sim/PRISM에서
  YAML과 동일 결과.

**Phase 3 — 골든 IR 등가 테스트** *(검증, 핵심 안전망)*
- 코퍼스 각 예제를 *두 포맷*(YAML·자체)으로 두고 **IR이 바이트 동일**한지 고정(§8 회귀).
  여기 통과 = 백엔드·결정론 경계 무회귀 증명. **성공 기준:** 전 예제 IR 동일, 1건이라도
  불일치면 fail.

**Phase 4 — 에러 리포트 정련** *(행위+UX)*
- 도메인 인지 메시지("line 41: enum 'room'에 값 'halll' 없음", "`=`는 전이 효과에서만").
  **성공 기준:** 오류 픽스처 코퍼스가 기대 메시지·위치를 낸다.

**Phase 5 — 이관 & YAML 디프리케이트** *(문서+정리)*
- `examples/`·`rules/` 자체 문법 이관, CLAUDE.md §4 전면 갱신, YAML 로더 디프리케이트 경로.
  **성공 기준:** 문서·예제 일관, YAML 경고 노출.

**Phase 6 — (선택) 도구화** *(확장)*
- 포매터(`ludoforge fmt`)·문법 하이라이트·LSP(자체 파서 소유의 이점). **성공 기준:** fmt
  멱등, round-trip 보존.

### 6. 위험 & 미해결 질문

- **문법=장기 약속:** 키워드 변경이 문법+lowering+테스트+모든 `.rule`+포매터+§4를 함께
  건드린다(작업규약 마지막 줄이 더 무거워짐) — Phase 1에서 토큰/키워드를 신중히 동결.
- **비-튜링완전 유지:** `for`·`${expr}`가 편의상 계산식으로 번지면 결정론 경계가 샌다 —
  화이트리스트 노드만(§7 규율 재사용), 골든 코퍼스로 회귀 고정.
- **마이그레이션 비용:** Phase 3 골든 등가가 통과하기 전엔 YAML을 못 버린다(병행 유지 기간).
- **`prob` PCTL 불투명성 유지:** 자체 문법이 PCTL까지 삼키려 하지 말 것 — 백엔드 전용
  문자열로 남겨 dialect 분리(D11) 보존.
- **부동소수 정밀도:** `${1-win-death}` 산술이 가능해져도 PRISM 합=1 요구와 충돌 가능 —
  표 명시 권장 유지(D18 후속 주의 계승).

---

## 7차 마일스톤 — 구조 단순화(PRISM 격하 + 던전 예제 통합) — ✅ 완료 (2026-06-26, P1~P4)

> 설계 근거·결정은 **decisions.md D23**(D13·D16·D19 위상 갱신). 한 줄: **PRISM을 사용자
> 표면에서 내려 테스트 전용 오라클로 격하하고, 던전 예제 4벌(`.lf`)을 하나의 실전형으로 통합**한다.
> **사용자 비준(2026-06-25):** PRISM=테스트 오라클 격하 · 던전/전이 계열만 통합(정적 예제 유지).
> 6차(외부 DSL) 완료 위에 쌓으며, 통합 대상은 모두 `.lf`. **착수 가능 — Phase 1부터.**

### 1. 동기

D19 이후 PRISM의 위상(소형 모델 교차검증 오라클)과 *사용자 표면*(`ludoforge prob`·DSL
`kind: prob`·외부 prism 의존)이 안 맞고, 던전 예제가 백엔드별 4벌로 비대하다. 둘 다 PRISM의
어정쩡한 위상이 뿌리 — 표면을 걷으면 예제 통합이 자연스러워진다(예제 단순화와 PRISM 격하가
서로를 강화).

### 2. 핵심 설계 (D23)

- **PRISM 표면 제거·오라클 보존:** `ludoforge prob`·`kind: prob`/`spec` 제거. `prob/`·
  `test_sim_oracle`·작은 DTMC 오라클 픽스처는 보존(증명기가 추정기를 검정 = DNA).
- **오라클은 reachable로 충분:** prism_gen `reachable`→`Pmax=? [F]` 매핑이라 `kind: prob`
  없이 오라클이 돈다. prism_gen의 prob(spec) 분기는 사문화 → 제거.
- **던전 통합:** 단일 MDP+pref `dungeon.lf`(클래스 밸런스 + 욕심/안전 pref) — bmc로 건전성,
  sim으로 정책 추정. 하나의 모델, 두 질문(dialect 분리).
- **정적 모순 예제 유지**(창립 가치). 통합 대상은 던전/전이 계열뿐.

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).
> 구조 변경(이동·삭제)과 행위 변경(통합 모델)을 PR로 분리(Tidy First).

**Phase 1 — DSL/CLI에서 PRISM 사용자 표면 제거** *(행위적 변경)*
- `core`: `Check.spec` 필드·`kind: prob` 파싱/검증 제거(`ir.py`·`loader.py`·`schema.py`),
  `kind`를 {`reachable`,`invariant`,`no_deadlock`,`distribution`}로 축소. `kind: prob` 쓴
  파일은 친절히 거부. `ludoforge/cli.py`에서 `prob` 서브명령 제거.
- `prob/prism_gen`: `prob`(spec) 분기 제거(reachable/invariant→PCTL 매핑만 유지).
- **성공 기준:** CLI는 check·bmc·sim만. `kind: prob` 거부 테스트. 기존 reachable/invariant
  검사·bmc·sim 무변경. `test_probforge`는 오라클 매핑만 남겨 축소.

**Phase 2 — 오라클 DTMC를 픽스처로 이동** *(구조적 변경, 행위 불변)*
- `examples/dungeon_sim.lf`(+골든 `.rule`) → `tests/fixtures/oracle_dungeon.lf`(이름 명확화).
  prob 검사가 있으면 reachable로 정리. `test_sim_oracle`·`test_sim_scale` 경로 갱신.
- **성공 기준:** 오라클 회귀(PRISM 정확값 ∈ sim CI) 픽스처 경로로 통과(설치 시)·미설치 skip.
  예제 디렉토리에서 오라클 전용 파일이 빠짐.

**Phase 3 — 던전 예제 통합** *(행위적 변경, 핵심)*
- 단일 `examples/dungeon.lf` 작성: 클래스 밸런스(role sweep·win_gold 파생·전투 tables) +
  "욕심(dive/fight) vs 안전(return)" `pref` 선택. checks: bmc용(클래스별 winnable·no_deadlock·
  불변식) + sim용(직업별 승률 reachable·gold `distribution`). `dungeon_policy`는 통합 흡수 후
  제거. **`market_sim`은 real·연속 능력 시연용으로 최소 보존**(사용자 결정 2026-06-25). 병존
  골든 `.rule`은 통합·디프리케이트와 함께 정리.
- `test_corpus`(EXAMPLE_EXPECTED)·`test_bmc`·예제 README 갱신.
- **성공 기준:** 통합 `dungeon.lf`가 `ludoforge bmc`·`ludoforge sim`로 동작(클래스별 결과·
  정책 라벨). 던전 계열 예제 4→2(통합 `dungeon` + `market_sim` 보존). 통합 모델 동작 회귀 테스트.

**Phase 4 — 문서 정합** *(문서)*
- CLAUDE.md §1(PRISM=테스트 오라클)·§3·§4.1(kind 집합)·§6, concepts.md §8.6/§8.8/§9.6(PCTL·
  오라클 재서술), README, decisions D13·D16·D19 상태 주석, PLAN/PROGRESS.
- **성공 기준:** 문서에 `ludoforge prob`·사용자용 `kind: prob` 잔존 없음. 링크·예제 일관.

### 4. 위험 & 미해결 질문

- **`market_sim`(real) 처리:** ✅ 결정(2026-06-25) — **최소 보존**. 통합 던전은 정수 모델로
  두고, real·연속·고차원 능력(D19) 시연은 `market_sim`이 단독으로 계속 맡는다.
- **bmc가 통합 모델을 감당하나:** MDP+pref+role+constraints 파생을 k 언롤링했을 때 상태/깊이.
  pref는 bmc가 무시하므로 비결정 분기만 늘어남 — 작은 k에서 도달성 시연되게 수치 조정.
- **하위 호환:** `kind: prob` 제거는 비호환 변경 — rules/·examples/·fixtures/에 잔존 사용 일괄 정리.
---

## 다중 백엔드 마일스톤 — ✅ 완료 (2026-06-17)

> **상태: 완료.** Phase 0~4 모두 끝났다(D11~D16). 공유 IR(`forge_core`) 위에 RuleForge
> (Z3/BMC, `ludoforge bmc`)와 ProbForge(PRISM, `ludoforge prob`) 두 백엔드가 동작하며,
> 던전!(WotC)을 논리·확률 양쪽으로 검증해 e2e 확인했다(승리 확률 Pmax [F win]=1.0).
> **Phase 5(저엄밀 Machinations/몬테카를로 export)는 생략**하고 마일스톤을 마감한다.
> 배경·용어는 [docs/concepts.md §8](docs/concepts.md). 상세 이력은 git·PROGRESS·decisions.
>
> 아래는 마감 시점의 계획 내용 보존(동기·결정·DSL·단계). 완료 단계는 PROGRESS 참조.

### 1. 동기와 한 줄 목표

**하나의 DSL을 게임 월드의 SSOT로 쓰되, 그 위에서 논리 증명(RuleForge/Z3)과 확률
증명(ProbForge/PRISM)을 *각각의 수학*으로 수행한다.**

현재 RuleForge는 변수의 **단일 정적 스냅샷**에서 논리적 모순만 본다. 게임처럼 턴·이동·
누적이 있는 동역학, 그리고 주사위·확률은 표현조차 못 한다. 이를 한 엔진으로 다 하려는
건 수학적으로 불가능하다 — 증명(SMT)과 확률(모델검사)은 다른 수학이다. 따라서 **모델은
하나, 백엔드는 둘**로 간다.

### 2. 3대 구조 결정 (이 마일스톤의 전제)

1. **파서/IR은 공유 라이브러리(`forge-core`).** RuleForge와 ProbForge는 *같은 IR을
   소비하는 두 백엔드*다. 각자 loader를 재구현하면 "하나의 SSOT"가 "어긋나는 두 파서"가
   된다 — 이것이 구조의 생사를 가른다.
2. **모델은 공유, 속성(질의) dialect는 각자.** 전이 모델은 둘이 공유하지만, 질의 언어는
   Z3쪽(도달성/불변식/unsat-core)과 PRISM쪽(PCTL/CSL)이 본질적으로 다르다. **질의 언어를
   통일하지 않는다.**
3. **ProbForge = PRISM 기반 *증명기*.** RuleForge(논리 증명)와 대칭. 유한 상태를 강제
   요구하며 상태 폭발이 천장이다. 몬테카를로/Machinations export는 *별도의 저엄밀 경로*로
   명확히 라벨링한다(증명 아님).

### 3. 왜 공유 코어가 억지가 아닌가 (핵심 근거)

공유 코어는 **guarded-command 전이 시스템**이다: `변수 + 가드된 전이 + (선택적) 확률 가중치`.
이 골격을 두 백엔드가 다르게 해석할 뿐이다.

- **RuleForge:** 가중치를 **지우고**(weight-erasure) 비결정 전이 관계로 본 뒤 k 스텝
  언롤링해 Z3로 증명. 주사위 = 적대적 비결정.
- **ProbForge:** 가중치를 **읽어** DTMC/MDP로 PRISM에 넘겨 PCTL 검사.

정성(논리) 모델은 정량(확률) 모델에서 확률을 잊은 **건전한 추상**이다. 둘은 이질적
접합이 아니라 한쪽이 다른 쪽의 정련(refinement)이라, 단일 DSL이 자의적이지 않다.

```
                 forge-core/   ← 진짜 SSOT: loader + schema + IR (단 하나)
                  (전이 시스템: 변수 · init · transitions · checks)
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
      ruleforge/                probforge/
   IR → Z3/BMC (논리 증명)     IR → PRISM (확률 증명)
   도달성 · 불변식 · 데드락     P/E 속성 · a.s. 도달성
   unsat-core · 반례 시퀀스     정확 확률·기댓값 (유한 상태)
          │
          └─(선택, 저엄밀)→ Machinations/몬테카를로 export (증명 아님, 플레이테스트용)
```

> **숨은 의존:** 공유 코어인 전이 시스템(BMC)은 현재 RuleForge엔 아직 없는 신규 차원이다
> (지금은 정적 스냅샷만). Phase 2~3이 사실상 RuleForge 자체의 큰 표현력 확장이고,
> ProbForge(Phase 4)는 그 공유 모델을 두 번째로 소비한다.

### 4. DSL 확장 스케치 (forge-core v2)

기존 `domain`/`constraints`/`expects`는 유지(하위 호환). 전이 시스템을 위해 `init` /
`transitions` / `checks`를 추가한다. **확률 가중치와 PRISM 전용 속성은 RuleForge가
무시하는 주석**이다(레이어드 — 두 백엔드가 *똑같이* 소비하지 않음을 전제).

```yaml
domain:
  variables:
    gold: { type: int, min: 0, max: 30000 }   # ProbForge 위해 유한 max 필수
    room: { type: enum, values: [center, l1, l2, l3] }
    role: { type: enum, values: [fighter, wizard] }
    win_gold: { type: int, min: 0, max: 30000 }

constraints:                                  # 정적 불변/관계 (기존, 유지)
  - id: wizard_win_target
    when: "role == wizard"
    then: "win_gold == 20000"

init: "gold == 0 and room == center"    # 초기 상태 술어 (신규)

transitions:                            # 상태 → 다음 상태 (신규). next.<var>로 다음값 참조
  - id: descend
    when: "room == l1"
    then: "next.room == l2"
  - id: fight_l2
    when: "room == l2"
    outcomes:                           # 가중치 = ProbForge용, RuleForge는 분기로만 해석
      - { weight: 0.7, then: "next.gold == gold + 500" }
      - { weight: 0.3, then: "next.gold == gold" }     # 패배

checks:                             # 백엔드별 dialect, 공통 의미는 kind로
  - id: winnable
    kind: reachable                     # RuleForge: BMC 도달성 / ProbForge: P>0
    that: "gold >= win_gold and room == center"
  - id: gold_nonneg
    kind: invariant                     # RuleForge: 모든 경로에서 불변
    that: "gold >= 0"
  - id: likely_win
    kind: prob                          # ProbForge 전용 (RuleForge 무시)
    spec: "P>=0.95 [ F (gold >= win_gold and room == center) ]"
```

**같은 전이 한 장면, 두 해석:** `fight_l2`를 RuleForge는 "0.7/0.3 가중치를 버리고 두
분기 모두 가능"으로 보고 *모든 주사위열에서 불변식이 성립하는지* 증명한다. ProbForge는
가중치를 살려 *승리 확률 ≥ 0.95* 를 PRISM으로 검사한다.

### 5. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).
> 구조적 변경과 행위적 변경을 분리한다(벡 Tidy First).

**Phase 0 — 범위 합의 & 결정 기록** *(행위 변경 없음)*
- decisions.md에 D11~ 기록: ① 다중 백엔드 계약, ② 전이 시스템 의미, ③ ProbForge 유한
  상태 요구, ④ 비목표 선(밸런스 *튜닝* 제외, *건전성* 속성만 — §7).
- **성공 기준:** CLAUDE.md §1/§3 갱신안 합의, 본 마일스톤 범위 비준.

**Phase 1 — `forge-core` 추출** *(구조적 변경, 행위 불변 — 순수 리팩터)*
- 현재 `ruleforge/dsl/`(loader·schema·ir)를 공유 패키지 `forge-core`로 분리. `ruleforge`는
  그 위 백엔드로 재배치(`solver/` 유지). 기존 99건 테스트 **전부 그대로 통과**.
- **성공 기준:** `ludoforge check` 기존 동작·리포트·테스트가 동일. 행위 변경 0.

**Phase 2 — 전이 시스템 확장 (DSL/IR)** *(행위적 변경)*
- IR에 `init` / `Transition`(when·outcomes·next.* 참조) / `Property`(kind·that·spec) 추가.
  스키마 검증(미정의 심볼, `next.` 참조 무결성, 유한 범위 요구) 확장. 던전! 미니 예제
  (`examples/`)와 파싱 테스트 우선.
- **성공 기준:** §4 예제가 IR로 로드되고 스키마 검증을 통과/거부(경계 누락 시 친절한
  에러). 기존 정적 DSL은 하위 호환.

**Phase 3 — RuleForge BMC 백엔드** *(행위적 변경)*
- IR 전이를 k 스텝 언롤링 → Z3. `assert_and_track` 규율 유지(unsat-core가 존재 이유).
  속성: `reachable`(sat + 도달 경로), `invariant`(unsat이면 안전 증명, 아니면 깨짐 시퀀스),
  `no_deadlock`. 주사위는 비결정으로.
- **성공 기준:** 알려진 코퍼스에서 (a) 도달성 sat 경로, (b) 불변식 위반 시퀀스, (c)
  k-bound 한계를 리포트에 명시(무한 지평 미증명 구간 숨기지 않음).

**Phase 4 — `probforge` 스켈레톤 (PRISM)** *(신규)*
- IR(가중치 보존) → PRISM 모델(guarded commands) 생성, `prism` CLI 호출, 결과 파싱.
  유한 상태 강제: 경계 없는 변수는 ProbForge에서 **명시적 거부**. 속성: `kind: prob`의
  PCTL spec 통과, `reachable`/`invariant`는 P>0 / P=1로 매핑.
- **성공 기준:** §4 예제에서 승리 확률·기대 턴 수가 PRISM으로 계산되고, 상태공간 크기와
  `unknown`/타임아웃을 별도 보고(sat/unsat·수치로 뭉개지 않음).

**Phase 5 — (선택) 저엄밀 export** *(신규, 명확히 비증명)*
- IR → Machinations(단방향 *뷰*, 편집 금지) 또는 내장 몬테카를로 시뮬레이터.
- **성공 기준:** 생성물이 "증명 아님 · 표집 추정 · lossy 투영"임을 출력에 라벨. 역방향
  편집 차단으로 SSOT 드리프트 방지.

### 6. 위험 & 미해결 질문 (착수 전 검증)

- **상태 폭발(ProbForge 1순위 리스크):** `gold×room×hp×class`가 수백만 상태로 폭발 가능.
  추상화/구간화 전략, PRISM 심볼릭 엔진 한계 측정 필요.
- **BMC k-bound:** 긴 지평의 전역 보장은 k-induction/불변식이 필요. 어디까지를 "증명"으로
  주장할지 경계 명시.
- **공유 IR이 두 백엔드 요구를 다 수용하는가:** Z3는 무한/정확 산술, PRISM은 유한·비선형
  OK — sweet spot이 상보적이라 IR이 양쪽 제약을 어떻게 공존시킬지(변수별 "ProbForge 대상"
  표식이 필요할 수 있음).
- **`next.` 참조·outcomes 문법:** 종속/독립 변수 판정(D5 휴리스틱)을 전이 문맥으로 확장
  시 오분류 위험. 코퍼스로 검증.
- **별도 패키지 vs 단일 CLI:** `forge prove` / `forge measure` 서브커맨드 한 프로젝트에
  둘지, 리포지토리를 가를지 — 파서 공유만 깨지지 않으면 패키징 선택.

### 7. 비목표 (scope 경계)

- **밸런스 *튜닝*·재미 평가는 비목표**(CLAUDE.md §1 유지). ProbForge는 *건전성* 속성만:
  "승리 가능한가", "확률적 데드락 없는가", "기대 게임 길이 유한한가". "A직업 승률이 B와
  5% 이내인가" 같은 튜닝은 Machinations 몫.
- **공간 보드의 픽셀 단위 충실 재현은 비목표.** 방=enum, 통로=전이 가드로 *위상*만 표현.
- **질의 언어 통일은 비목표.** 모델만 공유, 속성 dialect는 백엔드별.
- **생성된 Machinations 파일의 양방향 편집은 비목표(금지).** 단방향 파생 뷰만.

---

## 보류 중 (기존 후보 — 다중 백엔드와 별개로 잔존)

- **CI 통합**: PR마다 `ludoforge check` 자동 실행 + 모순을 PR 코멘트로, 모순 시 fail.
- **Real 범위 도달성 — 완전 Optimize(A-ii)**: 정확 달성값·gap·접근(`<`) 구분. D9 후속.
- **경계 검사 확장**: 종속 변수 정보성 리포트 / 기획 의도 상한.
- **sim 민감도 sweep (D20 Phase 4-a)**: `pref` 한 점을 범위로 쓸어(예 0→1) 승률·분포 곡선을
  자동 출력. 핵심 능력(pref+추정)은 5차 마일스톤에 있으니 이건 편의 기능이다.
  - *트리거*: 실제로 `pref`를 반복 튜닝하느라 수동 재실행이 번거로워질 때(점진적, CLAUDE §5).
  - *비용/결정*: 어느 `pref`를·어느 범위로 쓸지 문법, CLI 플래그, 곡선 리포트 포맷.
- **PRISM 유도-DTMC 교차검증 (D20 Phase 4-b)**: PRISM이 `pref`를 살려 유도 DTMC의 `P=?`를
  풀어 sim 다단계 정책 합성을 증명기로 재확인. 단일 선택점은 이미 Phase 2 골든 테스트
  (`policy_choice.rule`)로 검증됨 — 이건 *알려진 구멍*이 아니라 추가 안전벨트.
  - *트리거*: 다단계 `pref` 합성에 의심이 생기거나(현재 위험 낮음), *추정 아닌 증명*으로
    고정 정책 확률을 원할 때(틈새 수요).
  - *비용/결정*: `prism_gen`에 "`pref`→확률 명령 변환 + `P=?` 출력" 모드 신설, 기존 Pmax(MDP)
    경로와 dialect 게이트로 공존(D11). v1은 sim 단독 골든 검증으로 갈음.

## 남은 열린 질문 (검증 필요)

- **unsat core 정밀도**: Optimize gap → 경계값 재-assert로 범인 룰을 뽑는 방식이 코어를
  적정 크기로 잡는지 — 더 복잡한 룰셋 코퍼스로 확인.
- **종속 변수 휴리스틱**(D5): `then`의 단일 등식 판정이 `2*hp == ...` 변형에서
  오분류하지 않는지 — 코퍼스로 검증, 필요 시 정교화.

## 작업 규약 (유지)

- 각 단계는 작은 PR. TDD(Red→Green→Refactor), 단계마다 테스트 우선/동시.
- 게이트: `pytest` + `ruff check` + `ruff format` + `mypy`(strict) 통과.
- DSL 문법을 바꾸면 CLAUDE.md §4와 forge-core 로더/스키마/백엔드 번역기/문서를 함께 갱신.
- Z3/PRISM의 `unknown`·타임아웃은 sat/unsat·수치로 뭉개지 않고 별도 경로로 보고.
- 비선형(NIA)은 RuleForge에서 우회(상수화·구간분할) 제안+한계 명시. ProbForge에선 유한
  열거라 허용되나 상태 폭발 비용을 보고.
