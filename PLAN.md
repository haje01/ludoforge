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

## 8차 마일스톤 — BMC k-귀납(무한 지평 증명 승격) — ✅ 완료 (2026-07-02, P0~P4)

> **Phase 0 완료:** 사용자 비준(2026-07-02) — `unreachable`(도달 불가 확정)의 종료코드 1
> 승격 포함. 설계는 **decisions.md D25**로 승격 기록됨.
>
> 설계 근거는 본 절(→ **decisions.md D25**). 한 줄: **BMC의 "k까지 유지"
> 유계 결과를 k-귀납(k-induction)으로 무한 지평 증명으로 승격**한다. IR·DSL·프론트엔드
> 불변 — `logic/solver/bmc.py` 안에서 끝나는 순수 백엔드 확장이라 아크에서 리스크가
> 가장 낮은 첫 타자다.
>
> **아크 문맥(2026-07-02 합의):** 표현력 확장 아크 = 8차 k-귀납 → 9차 상태 의존
> `pref`/`weight` → 10차 플레이어 태그 → 11차 배열/컬렉션. 아크 전체의 **북극성 예제 =
> "Dungeon! 2~4인 레이스판"**(실물 2012 규칙이 가진 다인 레이스·카드 덱 비복원 추출·
> 플레이어별 상태를 마일스톤마다 하나씩 걷어내며 접근; 2d6 판정은 확률 weight로 유지,
> 레벨 3층 축소). 모노폴리는 북극성이 아니라 11차 이후 배열 스트레스 테스트 후보로 강등.
> 8차는 기존 `dungeon.lf` 그대로를 대상으로 한다(북극성 확장은 9차부터).

### 1. 동기와 한 줄 목표

D15가 못박은 대로 현 BMC의 `invariant`/`no_deadlock` "k까지 유지"는 증명이 아니라 **유계
결과**다("무한 지평 보장은 k-induction 필요 — 미해결"). 게임이 커질수록(북극성: 수백 턴
레이스) 이 미증명 구간이 리포트의 대부분이 된다. k-귀납을 붙이면 다수의 불변식이 **깊이와
무관한 진짜 증명**으로 승격되고, `reachable`의 "k까지 미도달"도 **도달 불가 확정**으로
답할 수 있게 된다 — "존재·건전성은 solver가 증명한다"(§2 원칙 1·D19 분업)의 완성이다.

### 2. 핵심 설계 (D25 후보)

- **귀납 스텝 정의:** base(기존 BMC invariant 검사, init 기준)가 j까지 통과한 뒤, **init을
  뗀** 임의 합법 상태열 s_0..s_j(매 스텝 상태 제약 + 전이 관계)에 대해
  `φ(s_0) ∧ … ∧ φ(s_{j-1}) ∧ ¬φ(s_j)`가 **unsat**이면 φ는 모든 깊이에서 성립(증명 완료).
- **귀납 가설에 상태 제약 포함(D15 재사용):** 도메인 min/max와 정적 constraints는 매 스텝
  불변식(D15)이므로 스텝 검사의 모든 s_i에 그대로 건다. 건전성 근거: 도달 가능한 상태는
  항상 합법이므로, 합법 상태로 좁혀 귀납해도 도달 상태를 놓치지 않는다. (이 덕에
  `gold_nonneg`처럼 도메인에서 직접 따라오는 불변식은 즉시 귀납된다.)
- **세 kind 모두 승격 — 같은 꼴 하나로:**
  - `invariant`: 위 정의 그대로 → 새 status **`holds`**(무한 지평 증명).
  - `no_deadlock`: φ = "어떤 가드든 enabled". 전이 관계가 s_0..s_{j-1}의 발화를 이미
    강제하므로 `¬enabled(s_j)` unsat 검사와 동형 → **`no_deadlock`**(증명).
  - `reachable`: k까지 미도달일 때 **¬that을 불변식으로 귀납** — 성공하면
    **`unreachable`**(도달 불가 확정). 자동 도달성·expect류 검사가 "더 깊이 보면 될지도"
    대신 확정 답을 얻는다.
- **반복 심화 재사용:** 스텝 검사를 j=1..k로 시도해 **최소 귀납 깊이 j**를 보고(리포트
  detail: "k-귀납, j=2"). 기존 `_Bmc`의 스텝별 변수·관계 사전 계산을 그대로 쓴다.
- **정직성(무타협):** 스텝 검사가 sat(비귀납)이거나 unknown이면 기존 k-bound status를
  유지하고 사유를 detail로 남긴다 — **절대 증명으로 뭉개지 않는다**(§8). 귀납 반례(CTI)는
  도달 가능성을 보장하지 않으므로 v1은 "귀납 실패(반례 상태는 도달 보장 없음)" 한 줄만,
  CTI trace 노출은 선택 후속.
- **종료코드 의미(✅ 비준 2026-07-02):** 증명된 `holds`/`no_deadlock`은 정상(0).
  **`unreachable`(도달 불가 확정)은 reachable 검사의 실패 확정이므로 `has_violation`
  (종료코드 1)로 승격** — 현행 "미확인(3)"과 의미가 다른 확정 부정이다.
- **기본 활성:** 별도 플래그 없이 항상 시도(base 통과 후에만 추가 solver 호출이라 저비용).
  기존 status 문자열은 유지하고 증명 시에만 새 status로 바뀐다.

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D25 기록 & 비준** *(행위 변경 없음)*
- decisions.md D25(위 핵심 설계 + 종료코드 결정), D15 상태 주석("k-induction은 D25로 해소").
- **성공 기준:** 사용자 비준 — 특히 `unreachable`→종료코드 1 승격 여부.

**Phase 1 — 솔버 구성 매개화** *(구조적 변경, 행위 불변 — 순수 리팩터)*
- `_solver_to_depth(j)`를 init 포함 여부로 매개화(`_solver_span(j, anchored: bool)` 류).
  스텝별 상태 제약·전이 관계 사전 계산은 그대로 재사용.
- **성공 기준:** 기존 BMC 테스트 전부 무변경 통과(행위 변경 0).

**Phase 2 — invariant k-귀납** *(행위적 변경, 핵심)*
- base 통과(j=k까지 위반 없음) 후 스텝 검사 j=1..k → unsat이면 `holds`(+최소 j detail),
  sat/unknown이면 기존 `holds_up_to_k` 유지+사유. `BmcReport.has_unconfirmed`에서 `holds` 제외.
- 픽스처: ① 귀납 성공(예: x+=2 카운터의 "x != 3" — j=2에서 증명), ② 같은 픽스처를 `--k 1`
  로 돌려 귀납 실패 시 k-bound 유지·정직 라벨(한 픽스처로 성공/실패 양면 회귀).
- **성공 기준:** `dungeon.lf`의 `gold_nonneg`·`no_monster_in_hall`·`sound_victory`가
  `holds`(무한 지평 증명)로 승격. 비귀납 케이스는 `holds_up_to_k` + 사유 유지.

**Phase 3 — no_deadlock·reachable 승격** *(행위적 변경)*
- `no_deadlock`: ¬enabled(s_j) 스텝 검사 → 증명 시 `no_deadlock`. `reachable`:
  `unreachable_within_k` 도달 시 ¬that 귀납 → 성공하면 `unreachable`(확정) + 종료코드 반영.
- **성공 기준:** `dungeon.lf`의 `no_stuck`이 증명으로 승격. 도달 불가 확정 픽스처(예:
  가드가 봉쇄한 상태)에서 `unreachable` + 종료코드 1. 기존 reachable-sat 검사(winnable 등
  5건)는 결과·경로 무변경.

**Phase 4 — 리포트·문서 정합** *(행위+문서)*
- 텍스트 리포트(`_LABEL`/`_KBOUND_NOTE`)·HTML(`logic/solver/html_report.py`) 라벨 동기화:
  "✅ 불변식 증명(무한 지평, k-귀납 j=2)" / "❌ 도달 불가 확정". k-bound 각주는 미증명
  항목에만 남긴다. CLAUDE.md §4.1(질의 의미)·concepts.md(BMC 절)·README 갱신.
- **성공 기준:** 리포트에 증명/유계 구분이 명시되고, 문서에 "k까지"가 증명인 양 읽히는
  서술 잔존 없음.

**Phase 5 — (선택·보류) 단순 경로 강화** *(확장)*
- 스텝 상태열에 distinct(s_0..s_j) 제약을 더해 귀납 완전성 향상(유한 상태에서 더 많은
  불변식이 증명됨). *트리거:* 실전 룰셋에서 "참인데 비귀납"이 반복 관측될 때. 그 너머
  (보조 불변식 합성·IC3/PDR)는 별도 마일스톤.

### 4. 위험 & 미해결 질문

- **비귀납 불변식의 비율:** 참이지만 k-귀납으로 안 잡히는 불변식(보조 불변식 필요)이
  실전에서 얼마나 흔한지 — 북극성 예제가 커지며 관측, Phase 5/IC3의 트리거로 삼는다.
- **스텝 검사 비용:** 언롤링 2배(base+step)까지는 아니나 j마다 추가 solver 호출.
  현 규모(k≤20)에선 무시 가능 예상 — 북극성 확장(9차+) 후 재측정.
- **unknown 처리:** 스텝 검사 unknown은 증명도 실패도 아님 — 기존 규약대로 별도 사유로
  보고(§8 "unknown을 sat/unsat으로 뭉개지 않는다").
- **`unreachable` 종료코드 승격의 파급:** CI에서 "아직 k가 작아 미도달"(3)과 "영원히
  불가"(1)가 갈라진다 — 의도된 개선이나 기존 사용 습관과의 충돌 여부 비준에서 확인.

---

## 9차 마일스톤 — 상태 의존 `pref`/`weight`(런타임 식) — ✅ 완료 (2026-07-02, P0~P4)

> **Phase 0 완료:** 사용자 비준(2026-07-02) — enabledness=가드 단독·BMC 과근사 수용·
> `.lf` 전용 포함. 설계는 **decisions.md D26**으로 승격 기록됨.
>
> 설계 근거는 본 절(→ **decisions.md D26**). 한 줄: **`pref`(D20)와
> outcome `weight`(D12)에 상수 대신 현재 상태의 식을 허용**한다 — 적응적 정책("목표에
> 가까우면 귀환 선호")과 상태 의존 우연("남은 카드 수에 비례하는 조우 확률" = **비복원
> 추출**)이 표현된다. 표현력 확장 아크(8차 ✅ → **9차** → 10차 플레이어 태그 → 11차
> 배열/컬렉션)의 두 번째 마일스톤이자 **북극성(Dungeon! 레이스판) 확장의 시작** — 덱을
> "종류별 남은 장수 카운터"(기존 스칼라 int)로 두면 배열(11차) 없이도 몬스터 덱의 비복원
> 조우가 이번 마일스톤만으로 표현된다.

### 1. 동기와 한 줄 목표

D20의 `pref`는 상수라 정책이 상태를 못 본다 — 현실 플레이어는 적응적이다("이미 목표
근접이면 안전 귀환"). D12의 `weight`도 상수라 **비복원 추출**(남은 덱 구성에 의존하는
확률)을 표현할 수 없고, 이는 카드 게임 일반과 실물 Dungeon!(레벨별 몬스터/보물 카드 덱)의
관문이다. 구현 지형은 유리하다: sim 평가기는 이미 변수 나눗셈을 지원하고(`sim/engine.py`
`_BIN_OPS`의 `Div`), sim은 이미 outcome weight를 **정규화**해 표집하며(엔진 docstring),
PRISM 생성기도 이미 **비율형**(`weight/total`, `prism_gen._prob`)으로 렌더한다 — 남은
공사는 "상수만"이라는 게이트를 문법(`t_pref: "pref" NUMBER`·outcome 수치 강제)·IR(float)·
로더에서 여는 것이다.

### 2. 핵심 설계 (D26 후보)

- **IR 타입 확장(하위 호환):** `Outcome.weight: float | str`, `Transition.pref:
  float | str | None`. 수치 리터럴·표 색인(desugar 후 수치)은 지금처럼 **float**로
  lowering — 기존 골든 IR 등가 무회귀. 상태 식일 때만 **str**(표현식 문자열, IR의 기존
  관례)로 보존한다.
- **평가 의미론(현재 상태·전이 전):** 식은 **전이 직전 상태**에서 평가한다(`next.*` 금지).
  - `weight`: 평가값들 중 음수가 있거나 합이 0 이하이면 **런타임 SimError**(실패는 크게).
    합이 양수면 정규화 표집 — 기존 상수 weight 정규화 의미의 자연 확장.
  - `pref`: co-enabled 정규화·opt-in 안전망(하나라도 미선언이면 거부)·enabled 1개면 rng
    미소비 — **D20 의미 전부 불변**, 상수 자리에 식이 들어갈 뿐.
- **enabledness는 가드 단독(백엔드 공통, 핵심 규율):** weight가 0이어도 분기 자체는
  존재한다 — 어떤 백엔드도 weight/pref로 enabled 여부를 바꾸지 않는다. "덱이 비면 조우
  불가" 같은 상태는 **가드로 배제**하라(`when goblin_left + dragon_left > 0`). sim이 합 0
  상태를 만나면 가드 누락으로 보고 에러로 크게 실패한다.
- **dialect 분리 유지(D11):** BMC는 weight-erasure(D15)·pref 무시(D20) 그대로 — 식이어도
  지운다. PRISM 오라클은 weight 식을 **비율형으로 렌더**(`(w_i)/(w_1+…+w_n)`, 기존 `_prob`
  일반화 — 상태 의존이어도 합=1이 구성적으로 보장). pref는 PRISM에서도 계속 무시.
- **BMC 과근사 정직성(문서화 의무):** weight-erasure는 상태 의존 weight에서 **더 거친
  추상**이 된다 — 어떤 상태에서 weight 식이 0으로 평가되는 분기도 BMC는 "가능"으로
  탐색한다(reachable 경로가 확률 0 분기를 밟을 수 있음). 불변식/데드락엔 여전히
  건전(과근사)하나 reachable 증인의 해석에 주의 — 리포트·concepts에 명시한다. weight>0을
  Z3 가드로 결합하는 정련은 비선형(변수 나눗셈) 위험이 있어 후속.
- **`.lf` 전용:** 디프리케이트된 YAML(`.rule`)엔 미도입(수치만 유지). 문법은 `t_pref`를
  expr로, outcome weight의 "desugar 후 수치" 강제를 "수치면 float · 아니면 식 보존"으로
  완화한다.
- **스키마 검증:** weight/pref 식의 참조 무결성(정의된 변수만·`next.*` 금지), 음수 상수는
  로드 시 거부(현행 유지). 식의 실행 시 타입(수치)은 런타임 검사.

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D26 기록 & 비준** *(행위 변경 없음)*
- decisions.md D26(위 핵심 설계), D12·D20 상태 주석. 비준 포인트: ① enabledness=가드 단독
  규율, ② BMC 과근사 수용(정련은 후속), ③ `.lf` 전용.
- **성공 기준:** 사용자 비준.

**Phase 1 — 문법·IR·로더·스키마** *(구조+행위)*
- `core/text_loader.py`: `t_pref: "pref" NUMBER` → expr, outcome weight의 수치 강제 완화
  (수치/표 색인 → float 유지, 상태 식 → 문자열 lowering). `core/ir.py` 타입 확장.
  `core/schema.py`: 식 참조 무결성·`next.*` 금지·(IR 직접 구성 방어) 음수 상수 거부.
- **성공 기준:** 골든 IR 등가 전 예제 무회귀(수치는 여전히 float). 식 pref/weight가 IR에
  문자열로 실리고, 미정의 변수·`next.*` 참조는 위치와 함께 거부. 기존 테스트 전부 통과.

**Phase 2 — sim 엔진 런타임 평가** *(행위적 변경, 핵심)*
- `sim/engine.py`: outcome 표집·`_select_transition`에서 float/str 분기 — str이면 기존
  `evaluate()`로 현재 상태 평가(화이트리스트 재사용, §7). 음수/합0 → SimError(어느 전이·
  어느 상태인지 짚기). enabled 1개 rng 미소비·기존 상수 경로 비트 동일(재현성 회귀).
- 골든 픽스처: **2색 항아리 비복원 추출**(`urn.lf` — 공 카운터 2개, weight = 남은 수 비례,
  뽑을 때마다 감소, 빈 항아리는 가드로 종료). 닫힌형 확률(초기 구성으로 계산)에 수렴 확인.
- **성공 기준:** urn 표집 분포가 닫힌형과 |Δ|<CI로 일치, 상수 모델의 SimReport **비트
  동일**(하위 호환), 합0·음수·미선언 혼재 거부 테스트.

**Phase 3 — PRISM 오라클 교차검증** *(검증)*
- `prob/prism_gen.py`: weight 식을 PRISM 식으로 렌더(비율형 일반화 — 변수명 동일·나눗셈은
  PRISM 실수 나눗셈). 소형 urn DTMC에서 PRISM 정확값 ∈ sim 95% CI(미설치 시 skip).
  BMC는 무변경 확인(weight-erasure 회귀).
- **성공 기준:** 증명기가 추정기를 검정(D19 DNA) — 비복원 추출의 sim 신뢰 확립.

**Phase 4 — 북극성 1단계: 던전 덱 + 적응 정책** *(행위+문서)*
- `examples/dungeon.lf` 확장: ① 레벨별 몬스터 덱 카운터(예: `l2_goblins`·`l2_dragons`) —
  조우 확률을 남은 장수 비례로, 조우 시 감소(비복원), 덱 소진은 가드로 처리. ② 상태 의존
  `pref`(예: 욕심도가 남은 목표액 `win_gold - gold`에 비례). bmc 검사(k 재조정 포함) +
  sim 직업별 승률이 모두 동작.
- 문서: CLAUDE.md §4.1(pref/weight 식·가드 규율·BMC 과근사 주의)·concepts.md·README·
  examples README. PROGRESS 갱신.
- **성공 기준:** 통합 던전이 bmc(증명/유계 구분 유지)·sim(정책 라벨)에서 동작하고, 리포트가
  비복원 조우·적응 정책을 사람이 읽게 보여준다. 문서·예제 일관.

### 4. 위험 & 미해결 질문

- **BMC 과근사의 체감 비용:** 0-가중 분기 탐색이 던전 확장에서 가짜 reachable 증인을
  얼마나 만드는지 — 관측 후, 심하면 "weight 식 > 0을 가드로 명시" 스타일 가이드 또는
  Z3 가드 결합 정련(비선형 우회 필요)을 후속 결정.
- **식 평가 성능:** 매 스텝 `ast` 평가가 늘어난다(현재도 가드가 그렇게 동작) — 표집 규모
  (n=2만)에서 병목이면 컴파일 캐시(`compile` 재사용)를 후속.
- **`uses_policy` 라벨:** pref가 식이어도 "주어진 정책 하의 추정" 라벨 의미는 동일 —
  선언 여부 판정만 유지되는지 회귀.
- **부동소수·PRISM 합=1:** 비율형 렌더로 구성적 보장하나, PRISM 파서의 식 수용 범위
  (나눗셈 중첩)를 소형 오라클로 실측.
- **YAML 경계:** `.rule`에 식을 넣으면 명확히 거부되는지(조용한 float 강제 변환 금지).

---

## 10차 마일스톤 — 플레이어 태그(전이 소유·다인 게임 입구) — ✅ 완료 (2026-07-02, P0~P3)

> **Phase 0 완료:** 사용자 비준(2026-07-02) — 소유 선언(스케줄러 아님)·혼성 co-enabled
> 거부·enum 값 게이트·BMC/PRISM 무시·신규 dungeon_race.lf 포함. 설계는 **decisions.md
> D27**로 승격 기록됨.
>
> 설계 근거는 본 절(→ **decisions.md D27**). 한 줄: **전이에 `player` 소유
> 태그를 달아 다중 플레이어 게임의 선택 구조를 도구가 알게 한다** — sim은 선택 집합의
> 소유 일관성을 검증하고, BMC/PRISM은 태그를 무시한다(주석 — weight-erasure·pref 무시와
> 같은 계보). 표현력 확장 아크(8차 ✅ → 9차 ✅ → **10차** → 11차 배열/컬렉션)의 세 번째
> 마일스톤이자 **북극성 2단계**: 2인 레이스 던전(`dungeon_race.lf`)이 처음 등장한다 —
> "욕심 플레이어와 안전 플레이어가 맞붙으면 누가 이기나"에 sim이 답한다.

### 1. 동기와 한 줄 목표

보드게임의 핵심은 다중 에이전트인데 현재 전이 시스템은 플레이어 개념이 없다 — 턴제
게임을 `turn` enum + 가드로 손으로 인코딩할 수는 있으나(스칼라 수동 복제 + `for` 템플릿),
**도구는 어느 선택이 누구 것인지 모른다**. 그래서 ① 가드 실수로 두 플레이어의 선택이
한 상태에 섞여도(co-enabled) sim이 그냥 pref로 표집해 버리고(조용한 의미 오류 — 턴제
위반), ② 리포트·정책 라벨이 플레이어를 구분하지 못한다. `player` 태그는 이 **소유
선언**을 1급으로 만든다. 가벼운 1단계다: 상태는 여전히 스칼라(플레이어별 복제는 `for`
템플릿 몫, 배열은 11차), 적대적 질의(∃전략 ∀응수)는 후속 — 태그는 그 기반 어휘가 된다.

### 2. 핵심 설계 (D27 후보)

- **`Transition.player: str | None = None`(IR) + `.lf` `player NAME` 절.** None=무소속
  (환경/자연 전이 — 흡수·스폰 등). 문법은 `transition id: … player p1 …`(guard·pref와
  같은 자리의 선택 절). `for` 템플릿 안에서 `player p`처럼 loop 변수를 쓰면 desugar가
  치환한다(`_substitute` 확장 — 태그 NAME도 해소 대상에 포함).
- **태그 = 소유 선언, 스케줄러 아님(경계).** 누구 턴인지는 여전히 모델의 몫이다(`turn`
  enum + 가드 + 효과로 교대). 태그는 "이 선택이 그 플레이어 것"임을 선언해 검증·리포트가
  쓰게 할 뿐, 실행 순서를 만들지 않는다 — 전이 시스템 의미(D12·D15)는 1비트도 안 바뀐다.
- **참조 무결성:** `player`의 이름은 **선언된 enum의 값**이어야 한다(schema — 오타 게이트,
  관례상 `turn: enum { p1, p2 }`의 값). 별도 `players` 선언 형식은 도입하지 않는다(IR
  표면 최소).
- **sim 소유 게이트(핵심 의미):** co-enabled 선택 집합의 태그는 **모두 동일**해야 한다
  (None 포함 — 전부 p1이거나, 전부 None). 혼성(p1+p2, 또는 태그+무소속)이면
  `DtmcViolation` 계보의 오류로 **명시 거부**하고 상태·전이·소유를 짚는다 — 가드 실수로
  두 플레이어의 턴이 겹친 것이므로 조용히 표집하지 않는다(실패는 크게). **동시 수
  (simultaneous move) 게임은 v1 비지원**(비목표로 명시). 단일 소유 집합의 표집 동작은
  기존과 완전 동일(pref 정규화·2단 표집·rng 소비 규칙 불변) → 태그 없는 기존 모델은
  **비트 동일** 하위 호환.
- **BMC/PRISM: 완전 무시.** 태그는 논리·확률 백엔드에 주석이다(D12 weight-erasure·D20
  pref 무시와 일관, dialect 분리 D11). 비결정 탐색은 "모든 플레이어가 한편"인 기존
  과근사 그대로 — 적대적 해석(∃전략 ∀응수)은 별도 마일스톤(진단서 벽 ② 2단계, 소형
  한정 게이트로 후속).
- **리포트:** sim 정책 라벨에 플레이어별 pref 사용을 명시("플레이어 p1·p2의 주어진 정책
  하의 추정"). 승률 자체는 기존 checks로 충분(`check p1_wins reachable: winner == p1`) —
  새 리포트 축은 만들지 않는다.

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D27 기록 & 비준** *(행위 변경 없음)*
- decisions.md D27(위 핵심 설계). 비준 포인트: ① 태그=소유 선언(스케줄러 아님), ② 혼성
  co-enabled 거부·동시 수 비지원, ③ player 이름은 선언된 enum 값(별도 선언 형식 없음),
  ④ BMC/PRISM 무시, ⑤ 북극성은 **신규** `dungeon_race.lf`(1인판 `dungeon.lf`는 기준
  예제로 유지 — 11차에서 레이스판의 수동 복제를 배열로 접는 것이 진화 스토리).
- **성공 기준:** 사용자 비준.

**Phase 1 — IR·문법·스키마** *(구조+행위)*
- `core/ir.py` `Transition.player`, `core/text_loader.py` `t_player: "player" NAME` 절 +
  desugar 치환(템플릿 `for p in [p1, p2]` 호환), `core/schema.py` enum 값 게이트.
  주의: `player`가 문법 키워드가 되므로 동명 도메인 변수와의 충돌 처리(현 코퍼스엔 없음
  — 확인 완료. 충돌 시 line:col 거부).
- **성공 기준:** `player p1` 파싱→IR, 템플릿 치환, 미선언 이름 거부(위치 보고), 태그 없는
  전 코퍼스 골든 IR 무회귀(기본값 None). YAML(`.rule`)은 미도입(D26과 동일한 `.lf` 전용).

**Phase 2 — sim 소유 게이트** *(행위적 변경, 핵심)*
- `sim/engine.py` `_select_transition`: 선택 집합(enabled≥2)의 태그 동일성 검사 — 혼성이면
  상태·전이·소유를 짚는 거부 메시지(기존 `_dtmc_violation` 서식 계승). 정책 라벨(플레이어
  명시)은 `uses_policy` 주변 최소 확장.
- 픽스처: 혼성 co-enabled(가드 실수) 거부 / 단일 소유 표집 무변경 / 태그 전무 모델 비트
  동일 회귀.
- **성공 기준:** 혼성 거부·기존 모델 무회귀(전 테스트 통과), 거부 메시지가 사람이 읽게
  원인(어느 플레이어 전이가 겹쳤나)을 짚는다.

**Phase 3 — 북극성 2단계: 2인 레이스 던전 + 문서** *(행위+문서)*
- `examples/dungeon_race.lf`: 2인 레이스 — `turn` 교대, 플레이어별 상태는 스칼라 수동
  복제(`for p in [p1, p2]` 템플릿), **공유 2층 몬스터 덱**(9차 비복원 — 플레이어 간 자원
  경쟁이 레이스의 커플링), 적응 pref 비대칭(p1=욕심 크게, p2=안전 크게), 먼저 목표 달성
  +귀환 → `winner = p`(흡수). role은 고정해 sweep 폭발 회피(예: 둘 다 fighter — 정책
  차이만 비교).
- 검사: bmc(양쪽 winnable·`invariant: winner 단일성`·no_deadlock — k 재조정: 턴 교대로
  경로가 ~2배), sim(`p1_wins`/`p2_wins` 승률·보물 분포) — **"욕심이 이기는가"에 추정 답**.
- 문서: CLAUDE.md §4.1(`player` 절·소유 게이트·비목표), concepts.md(다인 게임 절 신설
  또는 §8 확장), README·examples README, PROGRESS·PLAN.
- **성공 기준:** `ludoforge bmc/sim examples/dungeon_race.lf` 동작(bmc 건전성 + sim
  매치업 승률), 문서·예제 일관. 1인판 `dungeon.lf` 무변경.

### 4. 위험 & 미해결 질문

- **혼성 co-enabled의 정적 검사:** 두 플레이어 가드의 동시 충족 가능성을 Z3로 사전
  판정하는 것은 도달 불가 상태의 가짜 충돌 문제가 있어(4차 위험 목록의 DTMC 정적 검사와
  같은 계보) v1은 런타임 거부 — 후속.
- **스칼라 수동 복제의 부피:** 레이스판은 플레이어별 변수×2로 커진다 — 11차(배열)의
  동기를 예제 스스로 시연하는 셈. BMC k(~2배 깊이)·sim 지평의 실측 조정 필요.
- **`player` 예약어 충돌:** 기존 모델이 `player`를 변수명으로 썼다면 파스가 깨질 수 있다
  — 현 코퍼스엔 없음(확인). 문법 노트에 예약어 목록 명시.
- **적대적 질의와의 관계:** 태그는 "누구 것"만 선언한다 — "p1이 어떤 전략을 써도 p2가
  이길 수 있는가"(∃∀)는 BMC 의미 확장이 필요한 별도 마일스톤. 태그가 그때의 어휘가 된다.
- **무소속(None) 전이의 위치:** 환경 전이(흡수·스폰)가 플레이어 선택과 co-enabled로 겹치면
  거부되는데, 이것이 과도한 제약인 사례가 나오는지 북극성 예제로 관측.

---

## 11차 마일스톤 — 배열/인덱스 변수(유한 색인 스칼라 가족) — ✅ 완료 (2026-07-02, P0~P4)

> **Phase 0 완료:** 사용자 비준(2026-07-02) — 유한 색인 경계 게이트·순수 desugar·동적
> 색인 읽기 전용·충돌 거부·펼친 이름 노출 포함. 설계는 **decisions.md D28**로 승격 기록됨.
>
> 설계 근거는 본 절(→ **decisions.md D28**). 한 줄: **유한 색인 배열 선언
> (`gold[p1, p2]: int 0..30`)과 색인 식(`gold[p]`)을 문법에 들이되, 구현은 D18 계보의
> 순수 desugar(스칼라 가족 `<base>_<idx>`로 펼침)로 한다** — IR·백엔드·결정론 경계
> 무변경. 표현력 확장 아크(8차 ✅ → 9차 ✅ → 10차 ✅ → **11차**)의 마지막 마일스톤이자
> **북극성 3단계**: 레이스 던전의 플레이어별 수동 복제(변수 8개·전이 12개)가 배열 +
> `for` 템플릿 한 벌로 접힌다 — "플레이어 추가 = 값 목록 한 곳 수정"이 된다.
>
> **경계 게이트(진단 2026-07-02 합의의 이행):** v1은 **고정 크기·유한 색인**(값 목록
> 명시)만이다. 가변 길이 컬렉션(순서 있는 덱·삽입/삭제·손패)은 비도입 — 카운트 멀티셋
> (종류별 남은 수 int, 9차 비복원)이 그 영역의 지원 표현이다. PRISM 때의 도입→격하
> 왕복(D13→D19→D23)을 피하기 위한 사전 게이트.

### 1. 동기와 한 줄 목표

10차 레이스 예제가 스스로 시연했듯, 플레이어별 상태는 지금 **스칼라 수동 복제**다
(`gold_p1`/`gold_p2` + 전이 12개 — 변수 *이름*은 템플릿할 수 없어 `for`로 못 접는다).
개체(플레이어·유닛·슬롯)가 늘수록 소스가 곱으로 는다. 배열 선언과 색인 식을 1급으로
들이면: ① 선언 한 줄(`gold[p1, p2]: int 0..30`), ② `for` 템플릿의 loop 변수와 색인이
결합(`gold[p]` — 전이 한 벌), ③ 색인 오타를 desugar/schema가 위치와 함께 잡는다.
**구현 열쇠는 "펼친 이름을 수동 복제와 동일하게"** 하는 것: `gold[p1]` → 스칼라
`gold_p1`로 펼치면, 접은 레이스 예제의 IR이 **현재 수동 복제판과 바이트 동일**해질 수
있다 — 골든 등가가 곧 무회귀 증명이 된다(6차 이관 하니스와 같은 안전망 구조).

### 2. 핵심 설계 (D28 후보)

- **선언:** `NAME "[" NAME ("," NAME)* "]" ":" var_type` — 색인은 **명시적 유한 값
  목록**(enum 값과 같은 지위, 관례상 turn enum의 값과 일치시킴). 선언은 desugar가
  **스칼라 가족으로 펼친다**: `gold[p1, p2]: int 0..30` → `gold_p1`·`gold_p2`(선언 순서
  유지). 펼친 이름 `<base>_<idx>`가 기존 변수와 충돌하면 로드 거부(조용한 잠식 금지).
- **정적 색인(Tier 1, 핵심):** 식·효과 LHS의 `gold[리터럴]`/`gold[loop변수]`는 desugar가
  스칼라 이름으로 치환한다 — 기존 `index` 노드 해소(D18 표 색인)의 확장이라 **IR·세
  백엔드 완전 무변경**(순수 구문 변환, 결정론 경계 무관). 효과 LHS(`gold[p] = …`)를 위해
  `assign` 규칙의 좌변을 색인 허용으로 확장한다.
- **동적 색인(Tier 2, 읽기 전용):** `gold[turn]`(색인이 enum 변수)은 desugar가 **유한
  case-분기**로 lowering한다 — `(gold_p1 if turn == p1 else gold_p2)`(IfExp). 색인 집합이
  유한하므로 If-체인은 항상 닫힌다. 지원 확장: sim 평가기(IfExp), Z3 번역기(`z3.If`),
  PRISM 렌더(`cond ? a : b`) — 셋 다 기계적. **IfExp는 desugar 산출물로만 등장**한다
  (문법에 삼항 없음 — 사용자 표면은 비-튜링완전 그대로, 화이트리스트는 내부 생성물에만
  열림). 허용 위치: 술어·효과 RHS·요율(pref/weight) 식.
- **효과 LHS 동적 색인은 보류:** `gold[turn] = …`(어느 원소를 쓸지가 상태 의존)는 프레임
  의미(D15)가 "모든 원소를 조건부로 건드림"이 되어 세 백엔드의 효과 처리를 모두 수술해야
  한다 — v1은 명확한 에러로 거부하고 트리거(실전 요구) 시 별도 결정. 턴제의 "현재
  플레이어" 갱신은 플레이어별 전이(가드 `turn == p`) + 정적 색인이 이미 관례다.
- **참조 무결성:** 미선언 색인 값·범위 밖 색인·비-배열에 색인은 desugar/schema가 위치와
  함께 거부. 배열 base 이름은 단독(bare)으로 못 쓴다(원소만 상태 변수).
- **리포트 가독성:** unsat core·trace·sim 리포트에는 펼친 이름(`gold_p1`)이 그대로 보인다
  — 결정적·추적 가능(D18 id 원칙과 동일). 역-표시(`gold[p1]`로 되접기)는 후속 미도입.
- **비도입(경계 재확인):** 가변 길이 시퀀스·삽입/삭제·`hand.push()` 류 연산 없음. 정수
  카운트 멀티셋(9차)이 덱/자원의 지원 표현. 한정자 문법(`all p in …: gold[p] == 0` 류
  init 축약)도 후속 — v1의 init은 원소 나열.

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D28 기록 & 비준** *(행위 변경 없음)*
- decisions.md D28(위 핵심 설계). 비준 포인트: ① v1 = 고정 크기·유한 색인(가변 길이
  컬렉션 비도입 — 경계 게이트), ② 구현 = 순수 desugar(`<base>_<idx>` 스칼라 가족, IR·
  백엔드 불변), ③ 동적 색인은 읽기 전용(효과 LHS는 보류·명시 거부), ④ 이름 충돌 로드
  거부, ⑤ 리포트는 펼친 이름 노출.
- **성공 기준:** 사용자 비준.

**Phase 1 — 선언·정적 색인 desugar** *(구조+행위, 핵심)*
- `core/text_loader.py`: 배열 선언 문법 + 펼치기(스칼라 가족·순서 보존·충돌 거부),
  식/효과 LHS의 정적 색인(리터럴·loop 변수) 해소 — 기존 `index` 해소(`_subst_tree`)와
  `assign` 좌변 확장. 표(table) 색인과 배열 색인의 판별(이름 공간: 표 vs 배열 변수).
- **성공 기준:** 배열 선언·정적 색인이 수동 복제와 **동일한 스칼라 IR**로 펼쳐진다(골든
  등가 픽스처 — 같은 모델의 수동판·배열판 IR 바이트 동일). 미선언 색인 값·이름 충돌은
  위치와 함께 거부. 기존 전 코퍼스 무회귀.

**Phase 2 — 북극성 3단계: 레이스 접기** *(행위 불변 리팩터 — 예제)*
- `examples/dungeon_race.lf`를 배열 + `for p in [p1, p2]` 템플릿 한 벌로 접는다(도메인
  8줄→3줄, 전이 12개→6템플릿; 비대칭 pref는 표 `dive_pref`/`home_pref`, 상대는 표
  `other[p]` — 전부 기존 D18 기능). **접기 전 IR과 바이트 동일**을 커밋 내 테스트로 증명
  후 파일 교체.
- **성공 기준:** 접은 예제의 IR == 수동판 IR(동일성 테스트 통과 후 수동판 제거), bmc/sim
  결과·테스트 전부 무변경. "3~4인 확장 = 값 목록·표 한 곳 수정"을 주석·문서로 시연.

**Phase 3 — 동적 색인(읽기 전용)** *(행위적 변경)*
- desugar: `arr[enum변수]` → IfExp case-분기 lowering. `sim/engine.evaluate`(IfExp),
  `logic/solver/translator`(z3.If), `prob/prism_gen`(ternary) 지원 + schema 참조 검사.
  효과 LHS 동적 색인은 위치를 짚는 명확한 에러.
- 픽스처: "현재 플레이어의 소지금이 목표 이상" 류 술어(`gold[turn] >= 10`)가 세 백엔드에서
  일치(bmc 도달성/sim 추정 + 소형 PRISM 오라클 교차검증 — 9차 urn 패턴 재사용).
- **성공 기준:** 동적 색인 술어·RHS·요율이 동작하고 백엔드 간 일치, LHS 동적 색인은
  친절히 거부. IfExp가 사용자 문법으로는 직접 못 들어옴(비-튜링완전 유지) 확인.

**Phase 4 — 문서 정합 & 아크 마감** *(문서)*
- CLAUDE.md §4(배열 선언·색인·경계)·§4.2(템플릿과의 결합), concepts.md, README,
  examples README, PROGRESS·PLAN. 아크(8~11차) 회고 한 절: 북극성 현황과 다음 후보
  (모노폴리-미니 스트레스 테스트 — 배열 규모 실측, 협상 없는 solo-변형·sim 전용)를
  "보류 중"에 트리거와 함께 기록.
- **성공 기준:** 문서·예제 일관. 아크 종결 상태가 PLAN/PROGRESS에서 한눈에 읽힘.

### 4. 위험 & 미해결 질문

- **펼치기는 소스만 줄인다(D18 주의 계승):** 검증 모델 크기는 그대로다 — 4인 레이스는
  BMC k·sim 지평이 커진다. 배열이 상태폭발을 *해결*하지 않음을 문서에 명시.
- **이름 공간 판별:** `win[mon][cls]`(표)와 `gold[p]`(배열)가 같은 색인 구문을 쓴다 —
  base 이름으로 판별(표 이름 ∩ 배열 이름 = ∅ 강제). 충돌 시 로드 거부.
- **동적 색인의 Z3 비용:** If-체인은 색인 집합 크기에 선형 — 유한·소형(플레이어 수준)
  전제. 큰 색인 집합에서의 비용은 실측 후 가이드.
- **`<base>_<idx>` 충돌 표면:** 사용자가 `gold_p1`을 이미 선언한 경우 — 거부 메시지가
  원인(배열 펼침과 충돌)을 짚는지. 언더스코어 규약 자체가 모호한 사례(색인 값에 `_`)도
  거부 대상인지 P1에서 확정.
- **init 장황함:** 원소 나열 초기화가 개체 수에 비례해 길어진다 — 한정자(`all p in …`)
  문법은 후속 트리거(북극성 4인판에서 불편이 실측되면).

---

## 규칙서 SSOT 아크 (12~14차) — 개요 — ⬜ 계획 수립 (2026-07-06, 비준 대기)

> **진단(2026-07-06 합의):** `.lf`는 검증·추정에 최적화되어 실제 게임 규칙의 서술이 두
> 방식으로 유실된다 — ① **형식화 손실**: 규칙 원형이 DSL 밖에서 손으로 lowering됨(2d6
> 격파 목표값→승률 상수 표, 칸 이동→순간이동), ② **서술 손실**: 검증에 무의미한 절차·
> 연출·출처는 아예 없음. 이 아크는 `.lf`를 **기획자·개발자가 읽는 게임 규칙 SSOT 문서**로
> 승격하되 검증·추정 부하를 0(12·13차)~sim 미미(14차)로 유지한다. 방법론은 기존 두
> 계보의 확장이다: **"지워지는 주석"**(D12 weight-erasure→D20 pref→D27 player)과
> **"순수 desugar"**(D18 템플릿→D28 배열).
>
> - **12차(Tier 0, D29 후보):** 문서 메타데이터(`note`/`ref`/`tag`/`section`) +
>   `ludoforge doc` 규칙서 생성기 — 서술 손실 처방. passthrough 주석이라 백엔드 부하 0.
> - **13차(Tier 1, D30 후보):** 주사위 확률식 `chance(2d6 >= …)`/`rest` desugar —
>   형식화 손실 처방(매직 넘버 승률 표→룰북 원형 수치). 순수 구문 변환이라 부하 0.
> - **14차(Tier 2, D31 후보):** `ghost` 서술 변수 — 상태성 서술(턴 수·최심 도달 층)을
>   sim만 실행하고 bmc/PRISM은 상태공간에서 제거(`erase_ghosts`). 단방향 의존 게이트
>   (D24 계보)가 백엔드 의미 분기를 정적으로 차단.
>
> **기각(진단 시 합의):** 상세/추상 모델 파일 분리(기계 검사 없는 대응 = 형식의 옷을
> 입은 산문 드리프트 재현), Event-B식 정련 증명(체급 초과 — desugar가 곧 기계 보증된
> 추상화), DSL 범용 언어화(비-튜링완전 경계 붕괴 — §1 비목표 그대로). 맵/페이즈
> desugar는 비도입·"보류 중"에 트리거와 함께 기록. 12→13→14 순서를 권장하나 세
> 마일스톤은 상호 독립(어느 것도 다른 것을 전제하지 않음 — docgen의 chance/ghost 표기만
> 후행 연계).

---

## 12차 마일스톤 — 문서 메타데이터 + 규칙서 생성기(`ludoforge doc`) — 🔵 진행중 (P0~P2 ✅)

> **Phase 0 완료:** 사용자 비준(2026-07-06) — 설계는 **decisions.md D29**로 승격 기록됨.
> **Phase 1 완료(2026-07-06):** 문서 절 문법·IR `Doc` passthrough·`[[이름]]` 참조 게이트.
> **Phase 2 완료(2026-07-06):** `core/docgen.py` + `ludoforge doc`(HTML/MD, desugar 전
> 트리 기반 — 접힌 템플릿·표·상호링크·check 모음).
>
> 설계 근거는 본 절(→ **decisions.md D29**). 한 줄: **모든 선언에 구조화된
> 문서 절(`note`/`ref`/`tag`)과 파일 수준 `section`을 허용하고, `.lf` 하나에서 사람이
> 읽는 규칙서(HTML/MD)를 생성한다** — SSOT는 `.lf` 하나, 규칙서는 단방향 파생 뷰.

### 1. 동기와 한 줄 목표

`desc` 한 줄로는 절차·연출·출처를 못 담아, 실제 규칙 설명은 `//` 주석에 산다
(dungeon.lf 헤더 22줄이 증거) — 주석은 구조가 없어 도구(문서 생성·리포트)가 못 쓰고
참조 무결성도 없다. 문서 절을 1급 문법으로 들이면: ① 규칙서 생성이 가능해지고
(`ludoforge doc`), ② `[[이름]]` 상호참조를 로더가 검사해 "존재하지 않는 것을 서술"하는
부패를 기계가 잡고, ③ bmc/sim 리포트가 note를 활용할 수 있다(후속). 산문 드리프트
위험은 남는다(내용 불일치는 기계가 못 잡음 — 한계로 명시). 그래도 형식 룰 *바로 옆*
산문 + 참조 게이트는 별도 위키 대비 질적으로 낫다 — 규칙서가 `.lf`에서 생성되는 한
"문서 따로 모델 따로"의 드리프트는 원천 차단된다.

### 2. 핵심 설계 (D29 후보)

- **문법(`.lf` 전용 — D26·D27 계보):** constraint/transition/check/expect 몸통의 선택
  절로 `note "..."`(반복 허용 — 절차·연출 산문), `ref "..."`(출처 — 룰북 페이지·URL),
  `tag name ("," name)*`(분류). domain 변수 뒤 `desc "..."`(용어집용), `table` 헤더
  `desc`. 최상위 항목 `section "제목"`(이후 선언들이 그 절에 속함 — 문서 목차).
- **IR passthrough:** 새 frozen `Doc(notes, ref, tags)` + 각 선언 IR에 `doc: Doc | None
  = None`, `Variable`에 `desc: str | None = None`. 기본 None → 골든 IR 등가 무회귀.
  세 백엔드는 전부 무시(주석 계보). **`section`은 IR 미탑재** — 문서 전용이라 파스
  트리에만 있으면 된다(아래).
- **doc 생성은 desugar *전* 파스 트리 기반:** 규칙서는 저자가 쓴 접힌 형태(for 템플릿
  1개 + 표)를 보여야지 펼친 전이 8개를 나열하면 안 된다. IR(검증용)과 문서 뷰(표면용)의
  요구가 다르므로 `core/docgen.py`는 text_loader의 desugar 전 트리를 소비한다.
  `.rule`(YAML)은 doc 미지원(디프리케이트 일관).
- **참조 게이트(드리프트 억제):** note/desc 문자열 안 `[[이름]]`은 로드 시 검사 —
  변수·enum 값·선언 id·table 이름 중 하나여야 하며 미정의면 위치와 함께 거부(실패는
  크게). docgen은 상호링크로 렌더.
- **CLI:** `ludoforge doc <path> [-o out]` — 자체 완결 HTML(의존성 없음, html_report
  계보) 기본 + `--md`. 구성: section 목차 → 용어집(domain desc) → 데이터 표(table) →
  규칙(선언별: 가드="언제"·효과="결과"·note·ref) → 검증 성질(check desc — "이 규칙서가
  기계 검증/추정하는 성질"이 일반 규칙서와의 차별점).

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D29 기록 & 비준** *(행위 변경 없음)* — ✅ 완료 (2026-07-06)
- decisions.md D29(위 핵심 설계). 비준 포인트: ① `.lf` 전용, ② IR passthrough(`Doc`)·
  section 미탑재, ③ docgen=desugar 전 트리 기반, ④ `[[이름]]` 참조 게이트(존재만 검사 —
  내용 드리프트는 한계 명시), ⑤ 신규 키워드(note/ref/tag/section) 예약어 충돌 정책.
- **성공 기준 충족:** 사용자 비준(2026-07-06).

**Phase 1 — 문법·IR·참조 게이트** *(구조+행위)* — ✅ 완료 (2026-07-06)
- text_loader에 문서 절 문법 + `Doc` lowering + `[[이름]]` 무결성 검사. 신규 키워드와
  기존 코퍼스 변수명 충돌 사전 확인(충돌 시 line:col 거부).
- **성공 기준 충족:** 문서 절 픽스처 round-trip(IR `doc` 채움·note 반복 순서 유지·for
  템플릿 `${}` 보간), 미정의 `[[..]]`는 선언·필드를 짚어 거부(변수 desc·table desc·
  section 제목 포함), 문서 절 없는 전 코퍼스 골든 IR 무회귀(전체 358 통과), bmc/sim
  e2e 무변경(doc 스모크 포함). 테스트 7건 추가.

**Phase 2 — `core/docgen.py` + `ludoforge doc`** *(행위적 변경, 핵심)* — ✅ 완료 (2026-07-06)
- desugar 전 트리 → 규칙서 HTML/MD 렌더: 접힌 템플릿·표·`[[..]]` 상호링크·check 절.
- **성공 기준 충족:** dungeon.lf 규칙서가 규칙 설명 문서로 읽힘(용어집·표 행렬·8-way
  전투가 접힌 템플릿 1개·검증 성질 절), 자체 완결 HTML(외부 의존 0·결정론)·`--md`,
  깨진 모델(참조 게이트 실패)은 생성 거부(exit 2). `parse_doc_tree` 공개(위치 보존 —
  parse_rule_text와 파싱 공유), 원문 슬라이스 렌더(재포매팅 없음 — 저자 표기 보존).
  본문은 저자 소스 순서(section 절 구분), check만 맨 끝 "검증·추정 성질"로 모음(계획의
  고정 배치를 저자 흐름 보존으로 정련). 테스트 9건(구조 단언 위주). 전체 367 통과.

**Phase 3 — 예제 저술 & 문서 정합** *(문서)*
- dungeon.lf·dungeon_race.lf에 section/note/ref 실제 저술(2012판 룰북 ref — 헤더 `//`
  주석의 산문을 문서 절로 이동), CLAUDE §4 신설 절·README(`ludoforge doc` 빠른시작).
- **성공 기준:** 예제 규칙서 생성물을 사람이 게임 규칙으로 읽을 수 있음, bmc/sim 결과
  무변경(골든 등가·기존 테스트 전부 통과).

### 4. 위험 & 미해결 질문

- **산문 드리프트 잔존:** 참조 게이트는 *존재*만 검사 — 내용 불일치는 못 잡는다. docgen이
  형식부(가드·효과)를 산문 옆에 항상 병기해 사람이 대조하게 하는 것이 완화책.
- **키워드 충돌:** note/ref/tag/section이 변수명으로 쓰인 모델 — **현 코퍼스 확인 완료
  (2026-07-06): 아크 전체 신규 키워드(note/ref/tag/section/chance/rest/ghost) 충돌 없음.**
  예약어 목록은 문법 노트에 문서화(D27 `player` 선례).
- **골든 등가 유지비:** passthrough 필드가 늘수록 `.lf`↔`.rule` 골든 비교가 doc 필드를
  제외해야 함(YAML 미지원이므로) — 비교기에 명시적 제외 목록.
- **doc 테스트 취약성:** HTML 스냅샷 대신 구조(절 수·링크 해소·용어집 항목) 단언 위주.

---

## 13차 마일스톤 — 주사위 확률식(`chance`/`rest` desugar) — ⬜ 비준 대기

> 설계 근거는 본 절(착수 시 **decisions.md D30**로 승격). 한 줄: **outcome weight
> 자리에 주사위 술어의 닫힌형 확률 `chance(2d6 >= beat[mon][cls])`와 잔여 `rest`를
> 허용**하고, desugar가 정확한 유리수(`Fraction`)로 계산해 기존 float weight로
> lowering한다 — IR·백엔드·결정론 경계 불변(D18 계보의 순수 구문 변환).

### 1. 동기와 한 줄 목표

dungeon.lf의 win/miss/death 표 24칸은 실제 규칙("2d6이 격파 목표값 이상이면 승리")을
손으로 환산한 매직 넘버다 — 원형(목표값)은 주석에만 살고, 표를 고칠 때 규칙과 어긋나도
아무도 모른다(형식화 손실의 대표 사례). 주사위 식이 1급이 되면 룰북 수치가 SSOT에 남고
환산은 로더의 몫이 된다 — 규칙서(12차)에도 "2d6 ≥ 9 (10/36)"처럼 원형이 노출된다.
부수 효과: D18이 부동소수 정밀도 문제로 보류한 `${1-win-death}`류 잔여 계산이
`rest`(유리수 잔여)로 근원적으로 해소된다.

### 2. 핵심 설계 (D30 후보)

- **문법:** weight 위치에 `chance(<dice pred>)` | `rest` 추가. dice 원자는 `NdM`
  (정수 리터럴, 예 `2d6` — 전용 토큰 DICE로 렉서 충돌 회피), 술어는 `NdM CMP 상수식`.
  상수식 = 리터럴·표 색인·loop 변수(desugar 후 상수 강제) — **상태 의존 목표값은 거부**
  (상태 의존 확률은 D26 식 weight의 몫, 여기는 닫힌형 전용).
- **desugar:** NdM 분포 콘볼루션(`fractions.Fraction`) → 술어 확률 → float lowering.
  `rest` = 1 − (같은 outcomes 블록의 chance 합, 유리수 정확). 블록당 `rest` 최대 1회,
  chance 합 > 1이면 위치와 함께 거부. IR엔 기존 float weight만 남음 — 백엔드 완전 불변.
- **경계:** v1은 outcome weight 전용(`pref` 불허 — 정책은 주사위가 아님). dice 원자
  1개만(합성 `2d6+1d4`·개별 눈 참조 미지원 — 실전 트리거 시 확장).
- **예제 재저술:** dungeon.lf 전투를 격파 목표값 표(beat) + `chance`/`rest`로 —
  승률 표 3개(win/miss/death)가 목표값 표 1~2개로 줄고 룰북 원형이 남는다. 3분기는
  단일 롤 2문턱으로 모델링: `chance(2d6 >= beat[mon][cls])` 승 ·
  `chance(2d6 <= fumble[mon])` 사망 · `rest` 무소득. **주의: 기존 확률을 정확히 역산할
  수 없어 예제 수치(sim 추정치)가 바뀐다** — 새 닫힌형 골든으로 교체(모델링 결정을
  예제 주석에 명시).

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D30 기록 & 비준** *(행위 변경 없음)*
- decisions.md D30. 비준 포인트: ① `chance`/`rest` 문법·상수 목표값 한정, ② dungeon
  표 교체로 예제 수치 변동 수용, ③ pref 불허·dice 원자 1개 경계.
- **성공 기준:** 사용자 비준.

**Phase 1 — 문법 + desugar** *(구조+행위, 핵심)*
- DICE 토큰·chance/rest 문법, Fraction 콘볼루션·확률 평가 → float lowering.
- **성공 기준:** 손 계산 골든(P(2d6≥9)=10/36, P(2d6≤3)=3/36 등) 일치, 합>1·rest 중복·
  상태 의존 목표·pref 위치 거부(위치 보고), 전 코퍼스 골든 IR 무회귀.

**Phase 2 — 예제 재저술 & 오라클 교차검증** *(행위+문서)*
- dungeon.lf 전투를 beat/fumble 표 + chance/rest로 재저술(win/miss/death 표 제거),
  소형 PRISM 오라클 픽스처로 닫힌형 교차검증(정확값 ∈ sim CI — D19 DNA). test_corpus·
  sim 골든 갱신. CLAUDE §4.2 확장, docgen(12차)이 chance를 "2d6 ≥ 9 (10/36)"로 렌더.
- **성공 기준:** bmc 검사 지위 불변(k-귀납 증명 유지), sim 새 닫힌형 골든 통과, 규칙서에
  주사위 원형 노출. "보류 중"에 맵/페이즈 desugar 후보를 트리거와 함께 기록.

### 4. 위험 & 미해결 질문

- **실물 3분기 정합:** 단일 롤 2문턱 근사가 실물 Dungeon!의 실패 표와 얼마나 다른지 —
  예제 주석에 모델링 결정 명시(규칙서에도 노출).
- **렉서:** `2d6`이 NUMBER+NAME으로 쪼개지지 않게 전용 토큰 — 기존 수식(`2*d` 류)과의
  모호성은 코퍼스+우선순위로 확인.
- **PRISM 합=1:** float lowering 후 합이 1±ε — 유리수로 계산해 마지막에 변환하므로
  구성적으로 안전하나 오라클 픽스처로 실측.

---

## 14차 마일스톤 — `ghost` 서술 변수(검증 제외 상태) — ⬜ 비준 대기

> 설계 근거는 본 절(착수 시 **decisions.md D31**로 승격). 한 줄: **비-ghost 궤적에 영향을
> 줄 수 없는 서술 전용 상태 변수**를 들여, 턴 수·최심 도달 층 같은 상태성 서술을 sim이
> 실행(분포 리포트)하되 bmc/PRISM은 상태공간에서 완전 제거(`erase_ghosts`)한다 — BMC
> 부하 0, 단방향 의존은 schema가 정적으로 강제(D24 계보).

### 1. 동기와 한 줄 목표

"게임이 보통 몇 턴 걸리나", "평균 최심 도달 층은?" 같은 서술적 정량은 규칙서·튜닝 모두에
유용하지만, 상태 변수로 넣는 순간 BMC/PRISM 상태공간이 곱으로 커진다(k-귀납·데드락 증명
저하). `ghost` 표식은 이 트레이드오프를 끊는다: sim(추정)은 얻고 bmc(증명)는 잃지 않는다.
위험은 하나 — ghost가 게임 진행에 몰래 영향을 주면 두 백엔드 의미가 갈라진다(D24가 막는
것과 동종의 조용한 불일치). 그래서 **단방향 의존을 schema가 정적으로 강제하는 게이트가
이 마일스톤의 본체**다 — 게이트 없이는 도입하지 않는다.

### 2. 핵심 설계 (D31 후보)

- **선언:** `ghost turns: int 0..` 수식어(`.lf` 전용, 배열 D28과 결합 가능 —
  `ghost visits[p1, p2]: int 0..`). IR `Variable.ghost: bool = False`(기본 False →
  골든 무회귀).
- **단방향 의존(핵심 불변식): "ghost 전부 제거 시 비-ghost 궤적 비트 동일".** ghost를
  읽을 수 있는 곳 = ① ghost 대입의 RHS(ghost·비-ghost 모두 읽기 가능), ② `distribution`
  check expr(sim 전용 리포트), ③ 문서 절 `[[..]]`(12차)뿐. **가드(when)·constraint·
  expects·reachable/invariant that·pref/weight 요율·비-ghost 효과 RHS에서 ghost 참조는
  schema가 위치와 함께 거부**(`_check_ghost_one_way`). init에서 ghost는 상수 고정만
  (자유 ghost sweep·constraint 파생 금지).
- **`erase_ghosts(ruleset)` — core의 순수 IR→IR 변환:** ghost 변수 선언·ghost 대입·
  init의 ghost conjunct를 제거. **bmc·PRISM 오라클은 erase 후 소비**(상태공간 완전
  제거 — 증명 지위·k-귀납 불변), **sim은 원본 실행**(ghost 대입은 rng 미소비 →
  비-ghost 추정 비트 동일). `check_finite_state`는 erase 후 기준(ghost는 real·무한
  이어도 PRISM 게이트에 무해).
- **리포트 정직성:** sim distribution에 ghost 식 허용 + "서술 변수(논리 검증 제외)"
  라벨. bmc 리포트에 ghost 부재를 각주로 명시(조용히 숨기지 않음).

### 3. 단계별 계획 (작은 PR · TDD · Tidy First)

> 게이트(매 PR): `pytest` + `ruff check` + `ruff format` + `mypy`(strict).

**Phase 0 — D31 기록 & 비준** *(행위 변경 없음)*
- decisions.md D31. 비준 포인트: ① 단방향 의존 규칙(특히 weight/pref에서도 금지),
  ② init 상수 고정만, ③ `erase_ghosts`를 core에 두고 bmc/PRISM만 통과, ④ 리포트 라벨.
- **성공 기준:** 사용자 비준.

**Phase 1 — 문법·IR·schema 게이트** *(구조+행위)*
- `ghost` 수식어 문법·`Variable.ghost`·참조 위치 게이트(`_check_ghost_one_way`).
- **성공 기준:** 위반 픽스처(가드/weight/pref/constraint/비-ghost RHS의 ghost 참조)
  전부 위치 보고 거부, ghost 없는 전 코퍼스 골든 IR 무회귀.

**Phase 2 — `erase_ghosts` + 백엔드 배선** *(행위적 변경, 핵심)*
- core 순수 변환 + bmc/PRISM 소비 전 적용, sim은 원본. distribution의 ghost 참조 허용.
- **성공 기준(핵심 회귀):** ghost 단 모델에서 ① bmc 리포트가 ghost 제거판과 **동일**
  (증명 지위 불변), ② sim 비-ghost 추정 **비트 동일**(rng 미소비 확인), ③ ghost
  distribution 신규 동작(평균·CI·백분위).

**Phase 3 — 예제·문서** *(행위+문서)*
- dungeon.lf에 ghost 추가(예: `turns` 게임 길이·`max_depth` 최심 층) + distribution
  check("평균 게임 길이·최심 도달 분포"), docgen "서술 변수" 표기(12차 후행 연계),
  CLAUDE §4 신설 절·concepts·README.
- **성공 기준:** 기존 bmc 9검사 지위 불변 + sim 신규 분포 리포트, 문서·예제 일관.

### 4. 위험 & 미해결 질문

- **검증 회피 오용:** 게임에 영향 있는 변수를 ghost로 선언 — 참조 게이트가 구조적으로
  막지만(영향을 줄 수 없음), "영향 주고 싶은데 ghost라 거부"가 UX로 나타난다 → 거부
  메시지가 "ghost 해제"를 안내.
- **distribution의 지위:** ghost 분포는 추정 리포트일 뿐 검증 아님 — 라벨로 명시(DNA).
- **무한 ghost의 sim 비용:** `int 0..` ghost 카운터의 표집 비용은 무시 가능 예상 — 실측.
- **12·13차와의 순서 의존:** 없음(독립 도입 가능) — docgen의 ghost 표기만 12차 후행.

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

- **맵/그래프 선언·페이즈 문법 desugar (규칙서 아크 후속, 진단 2026-07-06)**:
  `map { hall -- l1 -- l2 -- l3 }`→이동 전이 생성, 턴 페이즈 선언→phase enum+가드 결합.
  형식화 손실(순간이동·페이즈 수동 인코딩)의 나머지 처방 — 순수 desugar(D18 계보)라
  부하 0이나 문법 유지비가 있다. *트리거*: 실전 모델에서 이동/페이즈 보일러플레이트
  반복이 실측될 때(13차 chance와 동형 수법으로 도입).
- **모노폴리-미니 스트레스 테스트 (아크 후속, 진단 2026-07-02)**: 협상 없는 solo-변형
  (부동산 배열·찬스 카드 카운트 덱·긴 지평 경제)을 sim 전용으로 — 배열(D28) 규모와 sim의
  장기 지평 능력 실측. *트리거*: 배열을 수십 개 원소 규모로 쓰는 실전 요구가 생길 때.
- **효과 LHS 동적 색인 (D28 보류)**: `gold[turn] = …` — 프레임(D15)이 "모든 원소 조건부
  갱신"이 되어 세 백엔드 수술 필요. *트리거*: 플레이어별 전이 복제(가드+정적 색인)로
  감당 안 되는 실전 모델이 나올 때.
- **한정자 init 축약 (D28 후속)**: `all p in [p1, p2]: gold[p] == 0` 류 — 원소 나열
  초기화가 개체 수에 비례해 길어질 때. *트리거*: 북극성 4인판 등에서 불편 실측.
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
