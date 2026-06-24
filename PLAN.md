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

## 5차 마일스톤 — sim 선택 확률(무작위 정책) — 📋 계획 (2026-06-24)

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

**Phase 4 — (선택) 민감도 sweep & PRISM 유도-DTMC 교차검증** *(검증·확장)*
- `pref` 한 점을 쓸어(예 0→1) 승률 곡선 출력(민감도). PRISM이 `pref`를 살려 유도 DTMC의
  `P=?`를 풀어 sim 추정과 교차검증(선택 표집 정확성을 증명기로 재확인).
- **성공 기준:** sweep 곡선이 단조/직관과 일치, 유도-DTMC P=?가 sim CI에 포함. (PRISM 유도
  모드는 비용 보고 후 착수 — v1 비목표일 수 있음.)

### 4. 위험 & 미해결 질문

- **`pref` 합성 의미:** 가드+`pref`로 상태 의존 정책을 표현할 때, 도달 불가 가드 조합이
  가짜 선택 집합을 만들지 — 골든 코퍼스로 확인.
- **PRISM 유도-DTMC 모드 비용:** `pref`→PRISM 확률 명령 매핑이 기존 Pmax 경로와 충돌 없이
  공존하는지(dialect 게이트). v1은 sim 단독 골든 검증으로 갈음 가능.
- **런타임 식 `pref`(후속):** `${state expr}` 정책은 표현식 evaluator 재사용 가능하나 스코프
  확대 — v1은 상수 `pref`로 한정.

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
