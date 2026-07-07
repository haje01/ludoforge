# 설계 결정 기록 (ADR)

> 이 문서는 Ludoforge의 주요 설계 결정과 **기각한 대안·그 이유**를 박제한다.
> PLAN.md(살아있는 계획)와 달리 이 기록은 **불변**이다 — 결정을 바꾸려면
> 기존 항목을 수정하지 말고 새 항목을 추가하고 옛 항목을 `상태: 대체됨`으로 표시한다.
> 목적: 이미 검토·기각한 대안을 미래에 다시 제안하는 낭비를 막는다.

각 항목 형식: 맥락 → 결정 → 기각한 대안과 이유 → 영향.

> **명명 규약 갱신 (2026-06-17):** 디렉토리를 `ruleforge/→logic/`, `probforge/→prob/`,
> `forge_core/→core/`로 리네임하고, 브랜드명 **RuleForge/ProbForge**는 각각 **'논리 백엔드'/
> '확률 백엔드'**로 통일했다 — 우산 CLI `ludoforge`의 서브명령(`check`/`bmc`/`prob`)으로만
> 노출되므로 별도 제품명은 혼란만 준다. **이하 항목에 남은 옛 이름·경로는 결정 시점의
> 사실을 보존한 역사적 표기다**(ADR 불변 원칙).

---

## D1. 1차 마일스톤을 수직 슬라이스로 한정

- **상태:** 확정 (2026-06-16)
- **맥락:** CLAUDE.md §4는 수치공식·조건부효과·상호배제·비율/확률 등 여러 룰
  패턴을 제시한다. 1차에 어디까지 커버할지 정해야 계획 규모가 결정된다.
- **결정:** 1차는 **수직 슬라이스** — LIA(선형 정수) 수치공식 + `when→Implies`
  + unsat core/반례 리포트가 `ludoforge check rules/` 한 줄로 end-to-end로 도는 것.
- **기각한 대안:**
  - *1차부터 전 패턴 커버*: 범위가 넓어 파이프라인 전체를 검증하기 전에 표면적만
    넓어진다. CLAUDE.md §2.5 "점진적 형식화" 원칙과 충돌.
- **영향:** 상호 배제(`Not(And(...))`), 비율/확률(LRA), 경계검사 확장은 2차로 미룸.

---

## D2. 표현식 파싱은 `ast` + 노드 화이트리스트

- **상태:** 확정 (2026-06-16)
- **맥락:** 룰의 `when`/`then`은 `"hp == level * 100"` 같은 표현식 **문자열**이고,
  번역기가 이를 Z3 식으로 바꿔야 한다.
- **결정:** `ast.parse(expr, mode="eval")` 로 트리를 얻고, **허용 노드만**
  (BinOp +−×, Compare ==/<=/</>=/>, Name, Num, BoolOp and/or, UnaryOp not)
  재귀적으로 Z3 식에 매핑. 허용 외 노드는 명시적 에러.
- **기각한 대안:**
  - *`eval()` 사용*: 임의 코드 실행 위험. 룰 파일은 신뢰 경계 밖일 수 있어 절대 불가.
  - *Lark 등 자체 문법*: 1차 표현 범위(산술·비교·불리언)에 비해 구현·유지 비용 과다.
    자체 문법이 필요할 만큼 표현식이 복잡해지면 그때 도입(2차 이후).
- **영향:** 지원 연산자는 화이트리스트로 명시적 관리. 새 연산자는 의식적으로 추가.

---

## D3. 모순 검사 의미론 = 선언 도메인의 도달 가능성

- **상태:** 확정 (2026-06-16)
- **맥락:** CLAUDE.md §3은 "여러 룰 동시 assert → unsat이면 모순"이라 적었다.
  그런데 대표 예시(warrior_hp)가 이 방식으로 **안 잡힌다**.
- **결정:** 모순 = **"기획자가 합법이라 여기는 상태를 룰들이 불가능하게 만든다"**.
  선언된 도메인 전 구간이 룰 하에서 도달 가능한지 검사하고, 봉쇄되면 모순으로
  보고하며 봉쇄한 룰을 unsat core로 짚는다.
- **기각한 대안:**
  - *naive "전부 assert → unsat"*: 변수가 자유변수라 Z3가 모순을 **피해 가는 값**
    (`role=mage` 또는 `level=50`)을 하나 찾아 **sat**을 반환 → 조건부 모순을 놓친다.
    warrior 예시(레벨 51+ 전사 불가)가 정확히 이 함정.
  - *기획자가 도달성을 명시 선언(`expect:` 문법)*: 확실하지만 기획자 부담이 크고
    문법 확장이 필요. 1차 비목표.
- **영향:** checks.py는 단순 unsat 검사가 아니라 도달성 기반으로 설계. 구현은 D4.

---

## D4. 도달성 구현 = Z3 Optimize로 달성범위 vs 선언범위 비교

- **상태:** 확정 (2026-06-16)
- **맥락:** D3의 "도달 가능성"을 어떻게 검사할지가 거짓양성·성능(조합 폭발)을 가른다.
- **결정:** 데카르트 순회 대신 **Optimize 기반 범위 비교**.
  각 enum 값을 고정하고, 각 수치 변수마다 Z3 `Optimize`로 룰 하의 실제 달성 가능한
  max/min을 구해 **선언 범위보다 좁으면 모순**으로 본다. 비용은
  `enum 값 수 × 변수 수`로 선형. CLAUDE.md "경계 검사: Optimize로 이론적 최대/최소
  vs 기획 의도 상한"과 일치.
  - 범인 룰 추출: gap을 찾은 뒤 경계값(`var == 선언max`)을 tracked로 assert하고
    `unsat_core()` 로 봉쇄 룰 집합을 얻는다.
- **기각한 대안:**
  - *전 조합(enum값 × 변수 경계의 데카르트 곱) 순회*: 변수 증가에 따라 조합 폭발.
    게다가 원래 도달 불가가 정상인 조합까지 검사해 거짓양성을 낸다.
- **영향:** warrior 예시를 "전사는 레벨 50까지만 가능(선언 max=100)"으로 정밀 보고.
  남은 검증 포인트: unsat core 재추출이 코어를 적정 크기로 잡는지 코퍼스로 확인(PLAN §4).

---

## D5. 도달성 검사 대상은 독립 변수만

- **상태:** 확정 (2026-06-16) — D4를 정밀화
- **맥락:** D4를 문자 그대로 "모든 수치 변수의 달성범위 < 선언범위면 모순"으로 구현하면
  warrior 예시에서 둘이 잡힌다: (1) `level`이 50까지만 가능(선언 max=100) — 진짜 모순,
  (2) `hp`가 100 이상만 가능(선언 min=0) — **거짓 양성**. hp는 `hp==level*100`으로
  값이 결정되는 종속 변수라 hp=0은 "도달해야 할 상태"가 아니다.
- **결정:** 도달성 검사는 **독립 변수만** 대상으로 한다. 어떤 룰의 `then`에서
  `var == ...`(단일 등식, 한쪽이 그 변수) 형태로 값이 결정되는 변수는 **종속**으로 보고
  검사에서 제외한다.
- **기각한 대안:**
  - *모든 변수의 min/max 검사(D4 문자 그대로)*: 구현은 단순하나 종속 변수에서 거짓 양성
    발생. 거짓 양성은 검증기의 가치를 직접 훼손한다(CLAUDE.md §8).
  - *기획자가 도달성 대상을 명시 선언*: D3에서 이미 1차 비목표로 기각(`expect:` 문법 부담).
- **영향:** checks.py가 `then`의 등식에서 종속 변수를 휴리스틱으로 탐지(`_dependent_variables`).
  현 DSL(`var == expr`)에 충분하며, `2*hp == ...` 같은 변형이 필요해지면 그때 정교화.
  남은 검증 포인트: 이 휴리스틱이 의도 외 변수를 종속/독립으로 오분류하지 않는지 코퍼스로 확인.

---

## D6. 불리언 상태 변수와 상호 배제 — 도달성으로 검사

- **상태:** 확정 (2026-06-16) — 2차 첫 항목, D3~D5를 bool로 확장
- **맥락:** 상호 배제(`Not(And(stealthed, attacking))`)는 1차 비목표(D1)였다. 실제 룰엔
  "은신과 공격 동시 불가" 같은 상태 제약이 흔해 2차 첫 항목으로 골랐다. bool 타입과
  그 모순 검사 의미론을 정해야 한다.
- **결정:**
  - **타입:** `Variable.type`에 `"bool"` 추가. z3.Bool로 번역하고 도메인 제약은 없다
    (자유 True/False). 표현식 화이트리스트(D2)에 불리언 리터럴 `True`/`False`를 허용.
  - **모순 의미론:** bool도 D3을 따른다 — 선언된 상태(True/False 각각)가 룰 하에서
    도달 가능해야 한다. 상호 배제 등으로 한 상태가 봉쇄되면 모순으로 보고하고 범인 룰을
    unsat_core로 짚는다.
  - **구현:** D4의 "데카르트 곱 회피" 정신을 따라 **자유 bool별 도달성**으로 검사한다.
    각 enum 조합(실행 가능한 것) 안에서 자유 bool의 True/False를 각각 고정해 feasibility를
    본다. enum×bool 전 조합을 순회하지 않으므로 조합 폭발과 중복 보고가 없다.
  - **종속 bool 제외(D5 일관):** 무조건(`when` 없는) 룰로 상수 고정되는 bool(bare atom
    `x` / `not x` / `x == True/False`)은 종속으로 보고 검사에서 제외한다. 조건부(`when`)로만
    강제되는 bool은 자유로 남겨, 그 강제가 상호 배제와 충돌해 상태를 봉쇄하면 모순으로 잡는다.
- **기각한 대안:**
  - *표현식 지원만(도달성 검사 제외)*: bool 룰을 쓸 수는 있으나 "상태 봉쇄"를 못 잡아
    상호 배제 모순 탐지라는 본래 가치를 놓친다(PLAN의 동기와 불일치).
  - *enum×bool 데카르트 곱으로 도달성 검사*: enum 값이 전역 불가일 때 그 bool 조합 전부가
    중복 보고되고 조합이 폭발한다 — D4가 이미 기각한 함정의 재현.
- **영향:** checks.py에 `_check_bool_states`/`_determined_bools` 추가. `UnreachableState`
  (구 `UnreachableEnum`)와 `assignment`(구 `enum_assignment`) 필드가 enum·bool 상태를
  공통 표현. 남은 검증 포인트: 종속 bool 휴리스틱이 의도 외 bool을 오분류하지 않는지 코퍼스로 확인.

---

## D7. 실수 변수(LRA) — 피저빌리티만, 상수 분모 나눗셈만

- **상태:** 확정 (2026-06-16) — 2차, 비율/확률 도입
- **맥락:** 확률 합=1 같은 비율 제약은 정수 스케일링(loot_table은 0~100 퍼센트)으로
  우회 중이었다. 실수(real) 변수를 도입해 `prob: {type: real}` + `합 == 1.0`을 직접
  표현하고자 한다. 단, Z3 Optimize로 실수 변수의 달성 범위를 구하면 상한이 비-도달
  (strict `<`)일 때 epsilon(무한소) 값을 돌려줘 `.as_long()`도 못 쓰는 어려움이 있다.
- **결정:**
  - **타입:** `Variable.type`에 `"real"` 추가, z3.Real로 번역. 선언 min/max는
    feasibility 제약(`>=`/`<=`)으로 둔다. 화이트리스트(D2)에 실수 리터럴을 허용.
  - **도달성 범위 = 피저빌리티만(사용자 결정):** real 변수는 reachability 선택자
    (int/enum/bool)에 들지 않아 도달성을 직접 검사하지 않는다. domain·rule 제약으로
    feasibility에만 참여 → "확률 합=1" 류 over-constraint와 enum 조건부 모순은 잡고,
    선언 min/max gap(범위 도달성)은 비목표로 둔다.
  - **나눗셈 = 상수 분모만(사용자 결정):** `p == 1/3`처럼 분모가 상수 리터럴일 때만
    허용한다(선형 LRA 유지). 분자는 Real로 올려 **정확한 유리수**로 다룬다(파이썬 float
    0.333… 아님). 변수 분모(`a/b`)는 비선형이라 명시적 TranslationError로 거부한다.
- **기각한 대안:**
  - *완전한 실수 도달성(Optimize on real)*: epsilon(비-도달 상한)과 Fraction 보고 처리가
    필요해 비용·위험이 크다. feasibility만으로 핵심 가치(확률 합=1)가 이미 커버되므로
    "점진적 형식화"(CLAUDE.md §2.5)에 따라 후속으로 미룬다(PLAN "2차 후보").
  - *변수 분모 나눗셈 허용*: NRA(비선형 실수)라 느리거나 unknown. CLAUDE.md §10 비선형
    우회 원칙과 충돌.
- **영향:** `Variable.min/max`를 `float | None`으로 넓힘(int 경계는 여전히 정수 런타임).
  translator에 real 도메인·실수 리터럴·`_translate_div`(상수 분모) 추가. checks.py는
  실질 변경 없음(real이 feasibility에만 참여). examples/drop_rates_real.rule로 정수
  스케일링 없는 표현을 보인다.

---

## D8. enum 인코딩 = Z3 EnumSort, 중복 값 이름은 문맥 해석

- **상태:** 확정 (2026-06-16) — 2차, 1차 enum 한계 해소
- **맥락:** 1차는 enum을 0,1,2… 정수로 인코딩하고 변수는 `[0, n-1]` Int로 뒀다. 이 방식은
  (a) `role < mage` 같은 무의미한 순서 비교/산술이 우연히 허용되고, (b) enum 값 이름을
  전역으로 해석해 **서로 다른 enum이 같은 값 이름**(예: 두 enum 모두 `active`)을 쓰면
  충돌했다. 실제 룰에서 상태 enum이 같은 라벨을 공유하는 일은 흔하다.
- **결정:**
  - **인코딩:** 각 enum 변수를 고유 `z3.EnumSort`로 만든다(변수=Const, 값=sort 상수).
    유한·상호 배타라 도메인 제약이 불필요하고, 순서 비교/산술은 sort상 자연히 막힌다.
    (조사 결과 기존 룰은 모두 `enum_var == value` 동등 비교뿐이라 순서 제거가 안전.)
  - **중복 값 disambiguation = 문맥 기반(사용자 결정):** 바깥 문법(`role == warrior`)을
    유지한다. 비교에서 한쪽이 enum 변수면 다른쪽 bare 값 이름을 그 변수의 enum sort
    값으로 해석한다(`_translate_compare`). 전역 유일한 값만 심볼표에 두고, 중복 이름은
    문맥으로만 푼다. 다른 enum의 값을 잘못 비교하면 원시 z3 sort 에러 대신 친절한
    TranslationError를 낸다.
  - **sort 라벨 유일성:** z3 전역 컨텍스트는 같은 이름의 enum sort 재선언을 거부하므로,
    sort 라벨에 프로세스 단위 일련번호를 붙여 `translate()` 반복 호출(테스트 등) 충돌을
    막는다. 라벨은 내부용이라 의미에 영향 없음.
- **기각한 대안:**
  - *정규화 문법 `role.warrior`*: 모호함은 0이나 ast.Attribute 도입 + 기존 모든 룰
    마이그레이션(비호환). 모든 사용처가 `var == value`라 문맥 해석으로 충분.
  - *정수 인코딩 유지(타입 안전만)*: 중복 값 이름 지원이라는 본래 목표를 못 채운다.
- **영향:** `Translation.enum_encoding`이 {값: 정수}에서 {값: z3 sort 상수}로 바뀜. checks.py는
  enum_fix가 `const == const`로 그대로 동작해 실질 변경 없음. examples/day_night_cycle.rule로
  중복 값 이름 시나리오를 보인다. 한계: 서로 다른 enum 변수끼리 직접 비교(`var1 == var2`,
  다른 sort)는 타입 오류다(의도적 — 의미가 없음).

---

## D9. Real 범위 도달성 = 끝점 feasibility (A-i)

- **상태:** 확정 (2026-06-16) — D7이 미룬 조각
- **맥락:** D7은 real을 feasibility에만 참여시키고 선언 min/max **범위 도달성**은 미뤘다.
  이유는 Z3 Optimize로 실수 최적값을 구하면 비-도달 상한(strict `<`)이 `1 - ε`(무한소)·
  `oo` 같은 특수 산술로 나와 `.as_long()`이 안 통하기 때문. int(D4)은 Optimize로 정확한
  달성값을 구하지만 real은 그 길이 험하다.
- **결정(사용자):** **끝점 feasibility(A-i)** — real 변수의 선언 끝점이 도달 가능한지
  `var == 선언끝점`의 sat 여부로만 검사한다. unsat이면 봉쇄로 보고하고 범인 룰을
  unsat_core로 짚는다. 정확한 달성값(예: "0.5까지만")은 구하지 않는다. Optimize/epsilon을
  전혀 쓰지 않아 안전하고, 기존 feasibility 기계(`_feasibility`)를 그대로 재사용한다.
  종속 real(공식으로 값 결정)은 끝점 미달이 정상이라 제외한다(D5 일관).
- **기각한 대안:**
  - *완전 Optimize(A-ii)*: 정확한 gap·"접근(`<`) vs 봉쇄" 구분까지 주지만 ε·∞·Fraction
    해석이 필요해 비용·위험이 크다. 끝점 검사만으로 "선언 범위가 봉쇄됐다"는 핵심 신호는
    이미 잡히므로 점진 전략으로 A-ii를 후속(PLAN "2차 후보")으로 둔다.
  - *real 도달성 계속 미검사(D7 상태 유지)*: int과 비대칭이고, "[0,1] 선언 후 룰이
    0.3으로 막음" 같은 흔한 모순을 놓친다.
- **영향:** checks.py에 `_check_real_bound`와 새 보고 타입 `BoundUnreachable`(달성값 필드
  없음 — A-i가 안 구함) 추가. report.py에 끝점 봉쇄 포맷 추가. **부수효과:** D7 때
  정합으로 뒀던 prob_ok.rule이 사실 선언 끝점(common min 0)을 floor 룰로 막고 있어
  D9에선 모순이 된다 — 룰을 정정해 진짜 정합으로 바꿨다. examples/crit_chance.rule로
  실수 끝점 봉쇄를 보인다.

---

## D10. 명시적 도달성 단언 `expect:`

- **상태:** 확정 (2026-06-16) — D3에서 1차 비목표로 보류했던 것을 2차에 도입
- **맥락:** 지금까지 도달성은 **선언 도메인에서 자동 추론**했다(D3~D9). 그런데 "공격과
  방어를 동시에 최대로 찍을 수 있어야 한다" 같은 **변수 조합의 도달성**은 변수별 경계
  검사(D4)로 안 보인다(각 변수는 단독으로 최대에 도달하므로). 기획자가 이런 양의 도달성을
  직접 선언할 수단이 필요하다.
- **결정:** 최상위 `expects:` 섹션을 둔다. 각 항목은 `{ id, desc?, that }`이고 `that`는
  "도달 가능해야 하는 조건" 표현식이다. 의미론: `domain ∧ constraints ∧ that`가 **SAT이면 충족**,
  **UNSAT이면 미충족**(룰이 봉쇄) → 모순으로 보고하고 봉쇄한 룰을 unsat_core로 짚는다.
  자동 도달성 추론(D3)의 **역방향**이다. 구현은 기존 `_feasibility`(tracked solver)를
  그대로 재사용한다 — `that`를 untracked로 add하고 룰을 tracked로 둬 core가 범인 룰이 된다.
  enum 조합 순회와 무관한 **전역 검사**라 루프 밖에서 expect마다 한 번씩 본다.
- **기각한 대안:**
  - *도달성을 계속 자동 추론만*: 변수 조합 도달성(동시 최대 등)을 표현할 수 없다. D4의
    변수별 경계는 결합 제약(`atk+def<=budget`)이 만드는 조합 봉쇄를 못 잡는다.
  - *expect를 룰처럼 assert*: expect는 "막혀선 안 되는 상태"라 룰(불변식)과 의미가 반대다.
    assert하면 오히려 제약이 되어버린다 — 별도 'sat이어야 함' 질의로 둬야 한다.
- **영향:** IR에 `Expect`/`RuleSet.expects`, 로더 `expects:` 파싱, 스키마 중복 id·참조 검증,
  translator `expect_constraints`, checks `_check_expects`/`UnmetExpectation`, report 포맷 추가.
  examples/stat_budget.rule로 변수별 경계로는 안 보이는 동시 도달성 모순을 보인다. 한계:
  `that` 표현식의 변수명은 파이썬 식별자 규칙을 따른다(예약어 `def` 등은 변수명 불가 — D2의
  ast 파싱 특성).

---

## D11. 다중 백엔드 계약 — 공유 IR(`forge-core`) + 두 증명 백엔드

- **상태:** 확정 (2026-06-17) — 3차 마일스톤(다중 백엔드) Phase 0
- **맥락:** 게임처럼 턴·이동·누적이 있는 동역학과 주사위·확률을 검증하고 싶다. 한 엔진
  으로 다 하려는 건 수학적으로 불가능하다 — 논리 증명(SMT/Z3)과 확률(모델검사)은 다른
  수학이다. 그러나 게임 월드는 하나로 기술(SSOT)하고 싶다.
- **결정:** **모델은 하나, 백엔드는 둘.** 로더·스키마·IR을 공유 라이브러리 `forge-core`로
  두고, 그 위에 두 백엔드를 둔다 — **RuleForge**(IR → Z3/BMC, 논리 증명)와
  **ProbForge**(IR → PRISM, 확률 증명). **질의(속성) dialect는 백엔드별로 가른다**:
  Z3쪽은 도달성/불변식/unsat-core, PRISM쪽은 PCTL/CSL. 모델만 공유한다.
- **기각한 대안:**
  - *단일 엔진으로 논리+확률 동시*: Z3는 확률·기댓값을 계산할 수 없다(만족가능성만). 억지로
    넣으면 "결정론적 증명"이라는 존재 이유(§2.1)를 배신한다.
  - *백엔드마다 별도 파서/IR*: "하나의 SSOT"가 "어긋나는 두 파서"가 된다 — 드리프트로
    구조가 붕괴. 파서 공유가 이 아키텍처의 생사를 가른다.
  - *질의 언어 통일*: Z3 질의와 PCTL은 본질이 달라, 공통 추상은 양쪽에 도움 안 되는
    레이어만 더한다.
- **영향:** Phase 1에서 `forge-core` 추출(순수 리팩터). 패키징(별도 repo vs `forge prove`/
  `forge measure` 서브커맨드)은 **Phase 4로 보류** — 파서 공유만 깨지지 않으면 선택 자유.

---

## D12. 전이 시스템 의미 — init·transitions·checks, 확률은 주석

- **상태:** 확정 (2026-06-17) — 다중 백엔드 Phase 0 (세부 문법은 Phase 2에서 확정)
- **맥락:** 현재 IR은 변수의 **단일 정적 스냅샷**만 표현한다(D1~D10). 턴·이동·누적을 보려면
  상태 전이가 필요하다. 두 백엔드가 공유할 모델 골격을 정해야 한다.
- **결정:** 공유 모델 = **guarded-command 전이 시스템**. DSL에 `init`(초기 상태 술어) /
  `transitions`(가드된 상태→다음상태, `next.<var>`로 다음값 참조, `outcomes`로 분기) /
  `checks`(kind·that·spec)를 추가한다. 기존 `domain`/`constraints`/`expects`는 그대로 둔다.
  - **확률 가중치는 골격 위의 주석**이다: RuleForge는 가중치를 **지우고**(weight-erasure)
    분기를 비결정으로 본다(주사위 = 적대적 비결정). ProbForge는 가중치를 읽는다. 정성(논리)
    모델은 정량(확률) 모델에서 확률을 잊은 **건전한 추상** — 둘은 정련 관계라 한 모델이
    자의적이지 않다.
  - RuleForge는 전이를 **k 스텝 언롤링**해 Z3로 본다(BMC). `assert_and_track` 규율 유지.
- **기각한 대안:**
  - *정적 스냅샷 유지(전이 없음)*: 게임 동역학을 표현조차 못 한다 — 이 마일스톤의 동기와 불일치.
  - *무한 지평 보장을 기본으로*: BMC는 본질적으로 k까지만 증명한다. 무경계 보장은
    k-induction/불변식이 필요(미해결, PLAN §6). k-bound 한계는 리포트에 명시하고 숨기지 않는다.
- **영향:** Phase 2에서 IR에 `Transition`/`Check`와 스키마 검증(`next.` 참조 무결성, 유한
  범위 요구) 추가. 던전! 미니 예제로 시연. 구체 문법(`next.` 표기·`outcomes` 구조)은
  Phase 2에서 코퍼스로 검증 후 확정 — 본 ADR은 계약 수준만 박제한다.

---

## D13. ProbForge = PRISM 기반 증명기, 유한 상태 강제

- **상태:** ~~확정 (2026-06-17)~~ → **D19로 갱신 (2026-06-23):** PRISM은 *주* 정량
  백엔드에서 **소형 모델 교차검증 오라클**로 내려가고, 정량 추정의 무게중심은 Monte Carlo
  시뮬레이터(`sim/`)로 옮겼다. "MC는 증명 아니라 기각"이라던 본 결정의 입장은 D19가
  뒤집는다(정확값이 곧 상태폭발로 불가능한 영역이라 추정으로 재배치). 유한 상태 강제는
  여전히 PRISM 경로에만 적용되고, sim은 무한·real을 허용한다. 다중 백엔드 Phase 0
  → **D23으로 갱신 (2026-06-25):** PRISM은 사용자 CLI 표면에서 완전히 내려가 `ludoforge prob`·
  DSL `kind: prob`이 제거됐다 — 이제 *테스트 전용* 교차검증 오라클이다(reachable→Pmax로 충분).
- **맥락:** "Machinations 같은 확률 기능"은 두 갈래다 — 망라적 확률 모델검사(PRISM, 증명)와
  표집 시뮬레이션(몬테카를로, 추정). ProbForge의 정체성을 정해야 한다.
- **결정:** **ProbForge = PRISM 기반 *증명기*** — RuleForge(논리 증명)와 대칭. 유한 상태
  안에서 정확한 확률·기댓값을 **보장**한다(예: `P>=0.95 [F win]`). PRISM은 상태공간을
  빌드하므로 **모든 대상 변수에 유한 경계를 강제**한다 — 경계 없는 변수는 ProbForge에서
  명시적 거부(Z3는 무한 정수를 허용해도). `unknown`·타임아웃은 수치로 뭉개지 않고 별도 보고.
- **기각한 대안:**
  - *ProbForge = 몬테카를로 시뮬레이터*: 표집은 *추정*이지 *증명*이 아니다 — 희귀 모순을
    놓친다. 프로젝트의 "증명" 정체성과 어긋난다. 몬테카를로/Machinations export는 **별도의
    저엄밀 경로**(Phase 5, "증명 아님" 라벨)로 분리한다.
  - *무한 상태 허용*: PRISM이 상태공간을 못 빌드한다. 유한 경계는 타협이 아니라 PRISM의
    전제다.
- **영향:** 상태 폭발(`gold×room×hp×class`)이 ProbForge의 실질적 천장 — 추상화/구간화 전략이
  미해결 리스크(PLAN §6). Phase 4에서 IR→PRISM 생성·`prism` CLI 호출·결과 파싱 구현.

---

## D14. 비목표 선 정련 — 건전성 속성은 목표, 밸런스 튜닝은 비목표

- **상태:** ~~확정 (2026-06-17)~~ → **D19로 개정 (2026-06-23):** 밸런스 *튜닝*(직업별
  승률 비교, 분포)은 **이제 목표다** — 단 **추정으로(sim, "증명 아님" 라벨)**, 증명으로가
  아니다. 본 ADR의 "튜닝=비목표" 선은 *증명 백엔드*(Z3/BMC·PRISM)에만 유효하고, 추정
  백엔드(`sim`)는 그 선 너머를 정직한 신뢰구간과 함께 다룬다. 건전성 속성은 여전히 증명
  목표. 다중 백엔드 Phase 0, CLAUDE.md §1 비목표 갱신과 연동
- **맥락:** D13으로 확률을 다루게 되면서, CLAUDE.md §1의 "밸런스·재미는 비목표"와 "기획
  단계 *정적* 검증" 문구가 모호해진다. 확률을 어디까지 다룰지 선을 그어야 scope creep을 막는다.
- **결정:**
  - ProbForge가 다루는 확률은 **건전성(soundness) 속성만**: "승리 가능한가 · 확률적
    데드락이 없는가 · 기대 게임 길이가 유한한가". 이는 *설계 정합성*이다.
  - **밸런스 *튜닝*·재미 평가는 비목표 유지**: "A직업 승률이 B와 5% 이내인가" 같은 연속적
    품질은 여전히 Machinations 등 시뮬레이션 몫.
  - **"정적"의 재정의:** 여전히 *설계 단계* 검증이다(런타임 서버 검증 아님). 단 "단일
    스냅샷"이 아니라 전이 시스템(BMC)·확률 모델검사를 포함한다 — 모두 설계 시점 정적 분석.
  - **Machinations export는 단방향 뷰만**(생성물 편집 금지) — 양방향이면 SSOT가 둘이 되어 드리프트.
- **기각한 대안:**
  - *밸런스 전체를 목표로*: 연속적·통계적 품질은 증명 대상이 아니다(CLAUDE.md §1 정신).
    건전성과 튜닝의 선을 안 그으면 ProbForge가 시뮬레이터로 번진다.
  - *Machinations 파일 양방향 동기화*: 시각 편집이 매력이지만 SSOT를 깨뜨린다.
- **영향:** CLAUDE.md §1 비목표 2개 항목을 본 결정에 맞게 정련(같은 커밋). §3에 다중 백엔드
  방향 주석 추가.

---

## D15. BMC 의미론 — 프레임=미변경 유지, constraints=상태 불변식, 반복 심화

- **상태:** 확정 (2026-06-17) — 다중 백엔드 Phase 3 (RuleForge BMC 백엔드)
- **맥락:** 전이 시스템(D12)을 Z3로 검사하려면 언롤링 의미를 못박아야 한다. 특히 전이가
  일부 변수만 건드릴 때(`next.gold == gold+300`) 나머지 변수(room 등)를 어떻게 둘지가
  모델의 의미를 통째로 가른다. 또 정적 `constraints`(예: `role==fighter → win_gold==10000`)와
  확률 가중치를 BMC에서 어떻게 취급할지 정해야 한다.
- **결정:**
  - **프레임 = 미변경 유지(PRISM 관례):** 전이의 한 outcome이 `next.X`로 제약하지 않은
    변수는 다음 상태에서 값이 유지된다(`next.y == y`). 게임의 자연스러운 의미이고
    **PRISM 갱신 의미와 일치**해 ProbForge와 모델을 공유할 수 있다. "건드리지 않으면
    그대로"가 기본이다. (제약된 변수 집합 = 그 outcome의 then에 등장하는 `next.*` 전부;
    프레임은 outcome 단위로 적용한다.)
  - **정적 `constraints` = 모든 상태의 불변식:** constraints는 한 상태가 합법인지 규정하므로 BMC의
    **모든 스텝 s_i에 적용**한다(when→Implies(then)). 전이는 합법 상태 사이를 움직인다.
    `domain` min/max도 매 스텝 적용.
  - **확률 가중치 = 무시(weight-erasure, D12):** outcome들을 비결정 분기(Or)로 본다.
    "도달 가능 = 어떤 주사위열이 그 상태를 만든다", "불변식 위반 = 어떤 주사위열이 깨뜨린다".
  - **반복 심화(iterative deepening):** 깊이 j=0..k마다 `init ∧ T_0..T_{j-1} ∧ φ(s_j)`를
    따로 풀어 **가장 짧은 반례**를 찾는다. 데드락(가드가 모두 거짓인 도달 상태)으로 경로가
    끊겨도 자연히 처리된다.
  - **속성:** `reachable`(sat → 도달 경로), `invariant`(어떤 깊이서 ¬φ sat → 깨짐 경로,
    아니면 k까지 유지), `no_deadlock`(가드 전부 거짓인 도달 상태 → 데드락 경로). 전이 선택은
    스텝별 `action@i` 정수로 인코딩해 경로에 어느 전이가 발생했는지 보고한다.
  - **k-bound 정직성:** "k까지 유지/미도달"은 증명이 아니라 **유계 결과**임을 리포트에 항상
    명시한다(무한 지평 보장은 k-induction 필요 — **D25로 해소**: k-귀납이 붙어 귀납 가능한
    속성은 무한 지평 증명으로 승격된다. 비귀납 속성은 여전히 유계 결과로 정직하게 보고).
- **기각한 대안:**
  - *프레임=미제약(자유)*: 안 건드린 변수가 임의로 바뀌어(룸 순간이동) 게임 의미가 깨진다.
  - *constraints를 BMC에서 제외*: role↔win_gold 같은 상태 불변 관계가 사라져 거짓 도달성을 낸다.
  - *전체 경로를 한 식으로(고정 길이 k)*: 데드락으로 짧은 경로만 가능할 때 거짓 unsat.
    반복 심화가 짧은 반례와 데드락을 함께 처리.
- **영향:** `ruleforge/solver/bmc.py` 신설(언롤링·속성 검사·경로 추출·리포트). 번역기에
  표현식 재사용 진입점 `translate_expression` 추가, `next.X`는 호출자가 Name으로 치환해
  넘긴다. CLI에 `ludoforge bmc <path> --k N` 추가. **BMC 범인-core 귀속**(어느 룰/전이가
  도달성을 막았는지)은 후속 — 현 단계는 trace가 설명이다(BMC 표준, 성공 기준과 일치).
  던전! 픽스처를 examples/로 승격(전이가 이제 실행 가능).

---

## D16. ProbForge — IR→PRISM 매핑 (스켈레톤)

- **상태:** 확정 (2026-06-17) — 다중 백엔드 Phase 4 (ProbForge). PRISM 4.8.1로 e2e
  **검증 완료**(아래 검증 후기). → **D23으로 갱신 (2026-06-25):** IR→PRISM 매핑은 유지하되
  `prob`(PCTL spec) 분기는 제거됐다(reachable→Pmax·invariant→Pmin만). `ludoforge prob` CLI도
  제거 — 본 매핑은 이제 테스트 오라클(`tests/test_sim_oracle.py`)에서만 호출된다.
- **맥락:** 공유 IR(가중치 보존)을 PRISM guarded-command 모델로 번역해야 한다. PRISM은
  유한 상태·정수/불리언만 다루고, enum·정적 constraints·확률 가중치를 어떻게 매핑할지 정해야 한다.
- **결정:**
  - **유한 상태 게이트:** 번역 전에 `check_finite_state()`(D13)로 무한 int·real을 거부한다.
  - **enum = 정수 인덱스 + 전역 const:** `const int <값> = <idx>;`를 emit하고 변수는
    `[0..n-1]`. 값 이름을 그대로 PRISM 식에 쓴다(`room=center`). **값 이름은 전역 유일해야**
    한다(중복 시 ProbForge 오류) — D8의 문맥 disambiguation은 PRISM 스켈레톤에선 미지원.
  - **정적 constraints = init 술어로 인코딩:** constraints와 `init`을 `init…endinit` 블록에 conjoin한다.
    전이가 바꾸지 않는 변수(프레임 불변, 예 role·win_gold)는 init에서 고정되면 영구 유지되어
    **그 경우에 한해 건전**하다. 전이가 바꾸는 변수에 대한 rule은 매 스텝 강제되지 않는다
    (스켈레톤 한계, 후속). PRISM 갱신 의미가 곧 D15 프레임이라 프레임은 자동.
  - **확률 가중치 = 정규화:** 전이별 weight를 합=1로 정규화해 `p:(update)` 분기로 emit.
    bare `then`(weight 1.0)은 분기 없는 결정적 명령.
  - **outcome.then = 배정형만:** `next.X == 식`(And 결합) 형태만 PRISM 갱신 `(X'=식)`으로
    번역한다. 부등식 등 비배정 then은 거부(PRISM 갱신은 배정이라).
  - **속성 매핑:** reachable→`Pmax=? [ F (that) ]`, invariant→`Pmin=? [ G (that) ]`,
    prob→`spec` 그대로(PRISM PCTL 원문, ProbForge 전용 escape hatch, D11). no_deadlock는
    PRISM이 자동 탐지하므로 prop 미생성(리포트에 안내). 모델 타입은 **mdp**(비결정 가능).
  - **실행 연동:** `prism` 바이너리를 PATH 또는 `PRISM` 환경변수로 찾는다. 없으면 모델만
    생성·출력하고 안내한다(graceful). 설치되면 model+props를 실행해 `Result:`를 파싱.
- **기각한 대안:**
  - *enum 값을 인라인 정수로*: 생성 모델·PCTL이 `room=1`처럼 읽기 어렵다. const가 명확.
  - *constraints를 매 상태에 강제(예 라벨/모듈)*: 일반 해법은 복잡. 프레임 불변 변수 한정 init
    인코딩이 던전!엔 충분하고 단순. 일반화는 후속.
  - *dtmc 강제*: 비결정(전이 다중 활성·자유 enum)을 못 담는다. mdp가 일반.
- **영향:** `probforge/` 신설(`prism_gen.py` 번역, `runner.py` 실행/파싱). CLI `ludoforge
  prob <path>`. 던전! prob spec을 PRISM 문법으로 정정(`&`/`=`). 생성 텍스트는 골든 테스트로
  검증, 실제 PRISM 실행은 `shutil.which("prism")` 게이트 통합테스트(바이너리 없으면 skip).
- **검증 후기(PRISM 4.8.1 e2e):** 던전!에서 `Pmax=?/Pmin=?`가 실제로 계산됨(승리 확률
  Pmax [F win] = 1.0 — 0.7 성공·무제한 재도전이라 결국 승리). 실행 중 두 가지를 고침:
  - **상태 폭발:** gold·win_gold가 `[0..30000]`이면 PRISM 상태공간이 ~70억 → 빌드 멈춤
    (D13 천장 실증). 던전! 수치를 `[0..20]`로 축약하고 전투 상한 가드를 추가(BMC는 영향
    없음 — k 스텝만 펼치므로). 큰 수치는 BMC 전용으로 두고 PRISM은 축약본.
  - **prob spec 문법:** PRISM은 `Pmax>=0.95`를 거부 — 바운드 아닌 **쿼리형 `Pmax=?`**
    를 쓴다(실제 확률값을 보고). 던전! spec을 쿼리형으로 정정.
  - 자유 enum(role)으로 초기 상태가 둘 → PRISM은 결과를 `[min,max]` 범위로 보고(파서가
    문자열로 수용). 다중 초기상태는 정상.

---

## D17. DSL 섹션 리네임 — `rules`→`constraints`, `properties`→`checks`

- **상태:** 확정 (2026-06-17)
- **맥락:** DSL 최상위가 `rules`/`transitions`/`properties`로 나뉘는데, 두 문제가 있었다.
  (1) `rules`라는 이름이 .rule 파일·"기획 룰"이라는 **우산 개념**과 겹쳐, 정적 불변식
  섹션을 가리키는지 전체 룰셋을 가리키는지 모호했다. (2) `properties`는 PRISM 등
  모델검사 관례 용어지만 기획자에게 직관적이지 않았다. 한편 `rules`와 `transitions`는
  `when`/`then` 표면이 닮아 합치자는 의견도 있었다.
- **결정:**
  - `rules` → **`constraints`**, `properties` → **`checks`** 로 섹션 키를 바꾼다.
    IR도 같이 바꾼다: 클래스 `Rule`→`Constraint`, `Property`→`Check`,
    `RuleSet.rules`→`.constraints`, `RuleSet.properties`→`.checks`.
  - **하위 호환 별칭은 두지 않는다**(초기 단계 + 최소 코드). 기존 `.rule` 파일은
    일괄 마이그레이션한다.
  - **`transitions`는 별도 유지**(합치지 않음): `constraints`는 단일 상태 불변식
    (`∀s. when(s)→then(s)`)이고 `transitions`는 두 상태 사이 관계
    (`when(s)→then(s,s')`, `next.*`·`outcomes`)다. BMC 인코딩에서 노는 자리가 달라
    (전자=매 스텝, 후자=스텝 사이, D15) 합치면 의도가 흐려진다(설계 원칙 2).
  - **모델 정의 vs 명세 분리는 유지**: `domain`/`init`/`constraints`/`transitions`는
    "무엇이 참인가"(solver가 가정), `checks`는 "무엇을 확인할 것인가"(solver가 증명/반증).
    이는 PRISM(모델/속성 파일)·NuSMV·TLA+의 표준 구도다.
- **기각한 대안:**
  - *`rules`→`invariant`*: `checks`의 `kind: invariant`(검증 대상)와 충돌. 가정된 공리와
    검증할 추측은 형식방법론에서 구분해야 한다 — `constraints`가 그 경계를 더 잘 드러낸다.
  - *`rules`+`transitions` 병합*: 위 의미 차이로 기각.
  - *PRISM 관례대로 `properties` 유지*: 기획자 직관 우선. 단 PRISM 백엔드 내부 식별자
    (`PrismProperty` 등)와 model-checking 개념어 "속성"은 그대로 둔다.
- **영향:** loader 키, `core/ir.py`(`Constraint`/`Check`), schema·translator·bmc·prism_gen·
  cli, 전체 `.rule`(examples·fixtures·rules)·테스트·문서를 일괄 갱신. 내부 plumbing 식별자
  중 우산 의미가 자연스러운 것(`culprit_rules`, `rule_constraints`)은 churn 최소화로 유지.

---

## D18. DSL 템플릿 확장 — `for:` / `${expr}` / `tables:` (Tier 1+2)

- **상태:** 확정 (2026-06-22) — Tier 1(템플릿·곱) + Tier 2(데이터 테이블) 도입, 산술 계산식만 보류
- **맥락:** 클래스의존 전투(D-dungeon)처럼 구조가 같고 데이터만 다른 항목이 클래스×몬스터
  곱으로 늘어난다(4×2=8 전투 전이, 클래스·몬스터·아이템이 늘면 폭증). `.rule`이 보일러
  플레이트로 길어지고 오타 위험이 커진다.
- **결정:** `constraints`/`transitions`/`checks` 항목에 `for:` 템플릿을 둔다. **로더가
  파싱 직후 구체 항목으로 펼친다(desugar)** — IR·translator·bmc·prism_gen은 무변경, 구체
  항목만 소비. 백엔드별로 펼치지 않고 프론트 1곳에서 펼쳐 검증 대상이 투명하다.
  - **Tier 1** — `for:` = **레코드 리스트**(행별 데이터) 또는 **매핑 `{param:[값]}`의
    데카르트 곱**. `${name}` 치환.
  - **Tier 2** — 최상위 `tables:`(이름→상수/표, desugar 시점 데이터·IR엔 안 들어감)와
    색인 참조 `${win[monster][cls]}`. 곱 `for:`와 합쳐 데이터를 표로 분리한다.
  - `${expr}`는 ast로 파싱해 화이트리스트 노드(**Name·Subscript·Constant**)만 평가 —
    `eval` 미사용(§7 규율). 문자열 전체가 `${expr}`이면 **값의 타입 보존**(weight 숫자),
    아니면 문자열 보간. 미정의 이름·색인 실패는 LoaderError(위치 보고).
  - 생성 id는 템플릿대로 **결정적·추적 가능**(`fight_dragon_rogue`) → unsat core·반례
    리포트가 여전히 사람이 읽는 범인을 짚는다(원칙 4).
- **기각/보류한 대안:**
  - *백엔드(PRISM/Z3)에서 각자 펼치기*: 3 백엔드에 같은 로직 중복, 검증 대상 불투명.
  - *IR에 파라미터화 유지*: IR·세 백엔드를 모두 손봐야 함. 펼침은 순수 desugar라 IR 이전이 맞다.
  - *산술 계산식(`${1 - win - death}`)*: 부동소수 정밀도가 dungeon 골든값(0.07 등)을 깨고
    PRISM 출력을 더럽혀 **보류**(`miss`는 표에 명시). 필요 시 Tier 2.5(반올림 규약 동반).
- **영향:** `core/loader.py`에 확장 패스(`_expand_items`/`_for_records`/`_subst_*`/`_eval_template*`)
  + `tables:` 파싱. `load_rule_file`이 세 섹션에 적용. CLAUDE.md §4.2 문서화, test_expand.py(11건).
  dungeon! 전투 8개를 `tables:`(win/miss/death/reward/cap) + 곱 `for:` 한 벌로 표현(펼침 결과는
  기존 IR과 동일 — 기존 테스트 무변경).
  **한계:** 소스만 줄이고 검증 모델은 그대로(PRISM/Z3엔 여전히 N·M 명령). 데이터도 잔존.

---

## D19. 정량 백엔드 무게중심 이동 — Monte Carlo 시뮬레이터(`sim/`), PRISM은 오라클

- **상태:** 확정 (2026-06-23) — 4차 마일스톤(정량 추정) Phase 0. D13·D14를 갱신한다.
  → **D23으로 보강 (2026-06-25):** PRISM을 "오라클로 유지"한 본 결정을 한 걸음 더 — 사용자
  CLI/DSL 표면(`ludoforge prob`·`kind: prob`)까지 제거해 PRISM을 *테스트 전용* 오라클로 확정.
- **맥락:** ProbForge=PRISM(D13, D16)은 *망라적 증명*이라 정확하지만 **상태 폭발이 너무
  쉽게 천장에 닿는다** — D16 후기에서 gold·win_gold `[0..30000]`만으로 ~70억 상태가 되어
  빌드가 멈췄고, 던전!을 `[0..20]`로 축약해야 했다. 그런데 **정확한 확률값이 필요한 영역이
  바로 상태 폭발로 계산 불가능한 영역**이라는 비대칭이 있다. 한편 정성(존재) 건전성 —
  "승리 가능한가·데드락 없는가·불변식 깨지는가" — 은 **이미 Z3/BMC가 증명**한다(D15,
  weight-erasure). 따라서 PRISM이 유일하게 기여하던 건 *정확한 확률·기댓값*이고, 그것이
  가장 안 되는 부분이다. 고차원·연속(real)·큰 범위를 다루려면 다른 도구가 필요하다.
- **결정:** **정량 백엔드의 무게중심을 망라적 증명(PRISM)에서 표집 추정(Monte Carlo)으로
  옮긴다.** 새 백엔드 `sim/`(IR 전이 시스템 인터프리터 + 표집 집계), CLI `ludoforge sim`.
  - **(1) PRISM은 오라클로 유지(완전 제거 안 함).** 작은 유한 모델에서 PRISM(증명)으로
    시뮬레이터(추정)를 **교차검증**해 시뮬레이터에 신뢰를 부여한다 — D13의 "표집은 증명이
    아니다" 반론을 *건설적으로* 무력화한다(증명기가 추정기를 검정). `ludoforge prob`·
    `prob/`·IR→PRISM 코드는 유지(폐기 비용 0, 회귀 가드로 활용).
  - **(2) DTMC만 허용(비결정 금지).** 표집이 well-defined하려면 *어떤 도달 상태에서도
    가드(`when`) 참인 전이가 최대 1개*여야 한다(분기는 outcome 가중치로만). enabled 전이가
    둘 이상이면 확률이 스케줄러 선택에 의존해 의미가 모호해진다 — 이 경우 **명시적 거부**
    (그 비결정은 BMC/PRISM-mdp가 다룬다). D15의 weight-erasure(가중치 버리고 비결정 허용)와
    정확히 **대칭의 반대**다: sim은 *가중치를 살리고 비결정은 막는다*. v1은 표집 중 enabled>1
    발견 시 런타임 거부, 사전 정적 검사(Z3로 두 가드 동시 충족 가능성 질의)는 후속.
  - **(3) 튜닝을 목표로 승격(D14 개정).** 분포·직업별 승률·기대 게임 길이 등 정량 *품질*
    질의를 **목표에 포함**한다. 새 검사 `kind: distribution`(임의 식 `expr`의 평균±CI·백분위·
    히스토그램). 단 모든 sim 결과에 **"증명 아님 · 표집 추정" 라벨**을 단다(D13이 저엄밀
    경로에 요구했던 라벨링을 sim 백엔드의 1급 규율로 격상).
  - **(4) 유한상태 게이트 불필요 → 고차원·연속 자연 지원.** sim은 상태공간을 빌드하지
    않으므로 `check_finite_state()`(D13) 없이 **무한 int·real 변수**를 그대로 시뮬레이션한다.
    종료 보장을 위해 **지평 H(최대 스텝)** 를 두고, H 내 미종료 run 비율을 보고한다(절단 편향).
  - **(5) 초기 자유변수 = sweep(전이 비결정과 구분).** `init`이 일부 변수만 고정하면 나머지
    자유변수(예 던전!의 `role`)는 **전이 비결정이 아니라 설정 파라미터**다 — 값별로 분리해
    각각 N회 표집하고 **설정별로 분포를 보고**한다(이것이 곧 "직업별 승률 비교" 튜닝 기능).
    자유 조합 열거가 폭발하면 상한을 두고 절단 사실을 보고(정직성). enum/bool 한정 시작.
  - **(6) 재현성 = counter-based RNG.** numpy `SeedSequence.spawn(N)`으로 run마다 독립·
    재현 스트림을 만들어 **워커 수·스케줄과 무관하게 같은 결과**를 보장한다(분산이 곧
    비결정이 되지 않게). base seed는 CLI 인자·설정.
  - **(7) 분산은 구조만, 구현은 로컬부터.** v1은 `multiprocessing`로 코어 분산. 단 집계를
    **결합 가능(mergeable)** 하게 설계한다(평균/분산=Welford, 분포=고정빈 히스토그램,
    카운트=합) — 전체 샘플을 들지 않고 부분합만 합산. run 샤딩 = `SeedSequence.spawn` 분배.
    transport(Ray/dask/k8s)는 같은 집계 인터페이스에 후속 교체.
  - **(8) 정직성(프로젝트 DNA).** 모든 sim 리포트에 ① N 샘플 ② 신뢰구간/표준오차 ③ 지평
    H·미종료 비율 ④ 미관측 사건의 **rule-of-three 상한(≈3/N)**(0/N을 "불가능"이라 하지
    않음 — 존재 증명은 Z3/BMC 몫) ⑤ DTMC라 스케줄러 정책 없음을 명시. `unknown`을 뭉개지
    않는 기존 규율의 표집판.
  - **표현식은 ast 화이트리스트 *평가기*(렌더 아님).** 값 계산이라 `_render`(PRISM 문자열)·
    `translate_expression`(Z3)와 별도의 evaluator를 둔다 — `eval` 미사용(§7, D18과 같은 규율).
- **기각/대비한 대안:**
  - *PRISM 완전 제거*: 교차검증 오라클 가치 + 유지비 0 → 보존. (브랜치명 `feat/no-prism`은
    "PRISM을 *주* 정량 백엔드에서 내린다"는 뜻이지 코드 삭제가 아니다.)
  - *MDP 비결정 표집(균등/임의 스케줄러)*: 확률이 스케줄러에 의존해 의미가 모호 → DTMC로
    제한해 well-defined. 비결정 확률 한계(Pmax/Pmin)는 PRISM-mdp·BMC가 다룬다.
  - *D13의 "MC는 증명 아니라 ProbForge에서 기각" 입장*: 정량 정확값이 바로 상태폭발로
    불가능한 영역임을 인정하고, 증명은 존재(Z3/BMC)·소형 정확(PRISM)에 남기고 고차원
    정량은 추정으로 재배치. **D13을 본 결정으로 갱신**(아래 D13 상태 주석).
  - *희귀사건 정밀 표집(importance sampling 등)*: v1 비목표. 희귀 모순/도달성은 Z3/BMC가
    증명으로 잡고, sim은 rule-of-three 상한만 정직하게 보고.
- **영향:**
  - `sim/` 신설: `engine.py`(전이 시스템 인터프리터·DTMC 게이트·표집), `aggregate.py`
    (결합가능 집계: Welford·히스토그램·rule-of-three), `runner.py`(multiprocessing 분배·
    seed spawn), `report.py`("증명 아님" 라벨·CI·절단 비율 한국어 리포트), 표현식 evaluator.
  - `core/ir.py`: `Check`에 `distribution` kind 수용(임의 식 평가 위해 `expr` 필드 추가
    검토 — `that`는 술어, `expr`는 수치식이라 구분). `kind` 집합 확장.
  - CLI `ludoforge sim <path> [--samples N] [--horizon H] [--seed S] [--workers W]`.
  - 문서: CLAUDE.md §1 비목표(튜닝 승격)·§4.1(distribution kind)·§6(`sim/` 추가)·§3,
    D14 개정(튜닝=목표), concepts.md §8 보강(증명 vs 추정 스펙트럼). PLAN/PROGRESS 새 마일스톤.
  - 성공 기준: 던전!에서 sim 승률이 PRISM 오라클 값과 신뢰구간 내 일치(교차검증), real·
    무한 변수 모델이 sim으로 추정되고, 비결정(enabled>1) 모델은 친절히 거부.
- **검증 후기(Phase 1~4 완료, PRISM 4.10.1 교차검증):**
  - **엔진/집계/병렬(Phase 1~3):** DTMC 게이트(enabled>1 거부)·흡수(fixpoint) 자연종료
    감지로 절단 지표 정상화. 결합가능 집계(Welford·Wilson·rule-of-three)와 numpy
    SeedSequence 청크 병렬로 **워커 수 무관 비트 동일** 재현성 달성(청크 수·병합 순서 고정).
  - **오라클 교차검증(Phase 4):** DTMC 던전판(`examples/dungeon_sim.rule`, win_gold는 클래스별
    constraints 파생)에서 role 고정 시 PRISM Pmax=정확값이 sim 95% CI에 들어옴 — fighter
    0.922·rogue 0.834·wizard 0.945(|Δ|<0.0022). **추정기가 증명기와 일치**함을 실증해 D13의
    "표집은 증명 아님" 반론을 건설적으로 무력화. sim은 constraints를 *초기값 파생*에만 쓰고
    매 스텝 불변식으로 강제하진 않는다(현 한계 — 프레임 불변 변수엔 충분, 일반화는 후속).
  - **검사 dialect 정리:** `distribution`(sim 전용)을 BMC·PRISM이 건너뛰도록 수정(이전엔 BMC가
    no_deadlock로 오인). numpy는 스텁 호환 위해 `<2.2` 핀(2.2+ PEP695 type이 mypy 3.11 파싱 실패).

---

## D20. sim 선택 확률 — 무작위 정책(randomized policy)으로 플레이어 비결정 해소

- **상태:** 확정 (2026-06-24, 사용자 비준) — D19의 "DTMC만 허용(enabled>1 거부)"을 *조건부로* 완화한다.
- **맥락:** D19의 sim은 도달 상태마다 enabled 전이가 최대 1개여야 하고(2개 이상이면
  `DtmcViolation`), 그래서 플레이어 *전략*을 가드에 박아넣어야 한다 —
  `examples/dungeon_sim.rule`이 "목표 미달이면 싸우고 채우면 귀환"을 `gold < win_gold` /
  `gold >= win_gold` 상호배타 가드로 인코딩한 게 그 예다. 두 문제가 있다.
  (1) **게임 규칙과 플레이어 정책이 한 파일에 엉킨다** — 같은 규칙을 다른 전략으로 돌리려면
  `.rule`을 통째로 복제해야 한다(SSOT 드리프트). (2) **현실 플레이어는 최적이 아닌데**
  PRISM `Pmax`는 *이론적 최적* 천장만 준다. "귀환을 70% 확률로 일찍 하는 플레이어의 승률은?"
  같은 *행동(behavior) 모델링*·민감도 분석은 Monte Carlo가 잘하는 일이고 D19가 sim에 맡긴
  튜닝/추정 영역인데, 지금은 표현할 길이 없다.
- **핵심 개념:** 게임 MDP의 비결정성은 두 종류다 — **환경/우연**(전투 승패·몬스터 뽑기,
  이미 `outcomes.weight`로 모델, D12)과 **플레이어 선택**(더 깊이 갈까/귀환할까, 현재 미모델).
  본 결정은 후자에 확률을 배정해 **무작위 메모리리스 정책(randomized scheduler)으로 비결정을
  해소**한다. 그 결과는 다시 DTMC라서 sim 엔진과 자연히 맞는다 — 매 스텝 **2단 표집**:
  ① enabled 전이들 중 정책 확률로 하나 고르고 → ② 그 전이의 outcome을 weight로 고른다.
- **결정:**
  - **(1) 전이 레벨 선호도 `pref`(상대 가중치).** `Transition`에 `pref: float | None = None`
    추가(None=**미선언**). 어떤 전이들이 *동시에* enabled인지는 정적으로 모르므로(상태 의존),
    분포를 정적으로 붙이지 않고 **런타임에 enabled된 것들끼리 `pref`로 정규화**한다. 균등
    선택을 원하면 co-enabled 전이에 **같은 `pref`를 명시**한다(생략은 균등이 아니라 거부 — (3)).
  - **(2) `weight`와 다른 키워드.** `outcomes.weight`는 *환경 우연*(D12, BMC가 erase),
    `pref`는 *플레이어 정책*으로 의미가 다르다. 같은 `weight`로 쓰면 D12 의미론이 흐려져
    별도 식별자를 둔다. (`pref` = preference.)
  - **(3) 안전망 유지 — 선택은 명시적 opt-in.** enabled>1일 때 *모든* co-enabled 전이가
    `pref`를 선언했으면 선택 집합으로 보고 표집한다. **하나라도 `pref` 없는 게 섞여 있으면
    여전히 `DtmcViolation`으로 거부**한다(=의도치 않은 가드 중첩이라는 모델링 버그를 조용히
    표집으로 덮지 않는다, §실패는 크게 드러내기). 전부 `pref` 없으면 D19 그대로 거부.
    `pref` 합이 0이면 outcome weight-합-0과 동형으로 오류.
  - **(4) 백엔드 dialect(D11) — `pref`는 sim 전용 주석.** BMC는 `pref`를 erase한다(어차피
    모든 경로를 탐색 = 선택 비결정 자체가 BMC의 일, weight-erasure와 일관). PRISM은 기본
    `pref`를 무시하고 `Pmax`(MDP, 모든 스케줄러 최적화)를 유지한다 — `distribution`이 sim
    전용인 것과 동형. (PRISM이 `pref`를 살려 *유도 DTMC*의 `P=?`를 푸는 모드는 후속.)
  - **(5) 정직성 라벨(D19 격상).** sim 리포트는 결과가 **"주어진 정책 하의 추정 · Pmax 아님"**
    임을 명시한다. 고정 무작위 정책의 승률은 항상 `Pmax`의 **하한**이다(정책이 우연히 최적일
    때만 일치). D19의 교차검증 구도("sim DTMC == PRISM Pmax")는 *선택이 없는*(모든 enabled
    집합이 단일) 모델에서만 성립 — `pref`로 선택이 생기면 PRISM `Pmax`가 아니라 *같은 정책으로
    유도한 DTMC의 `P=?`* 와 비교해야 한다.
  - **(6) 상태 의존 정책은 가드+`pref` 합성으로.** v1의 `pref`는 상수다. 상태에 따라 전략을
    바꾸려면 가드로 후보를 좁히고(`when`) 잔여 비결정을 `pref`로 푼다 — 상태 의존이 그대로
    표현된다. `pref`에 `${state expr}`(런타임 식) 허용은 후속(표현식 evaluator 재사용).
- **기각/대비한 대안:**
  - *enabled>1을 무조건 균등 표집(opt-in 없이)*: 의도치 않은 가드 중첩(모델 버그)을 조용히
    덮어 "실패는 크게 드러내기" 원칙 위배 → 명시적 `pref` opt-in으로 (3).
  - *`weight` 키워드 재사용*: 환경 우연(D12)과 플레이어 정책을 한 이름으로 뭉개면 weight-erasure
    의미론이 모호 → 별도 `pref`로 (2).
  - *별도 정책 오버레이 파일(규칙 1개 × 정책 N개)*: SSOT 분리엔 가장 깔끔하나 인프라 비용↑.
    인라인 `pref`로 시작하고 오버레이는 후속 경로로 남긴다.
  - *`pref`를 PRISM에도 즉시 반영(유도 DTMC P=?)*: 교차검증 가치는 있으나 v1 비목표 —
    선택 표집 자체의 정확성은 닫힌형 혼합을 아는 골든 모델로 sim 단독 검증(아래 성공 기준).
- **영향:**
  - `core/ir.py`: `Transition`에 `pref: float | None = None`(None=미선언).
  - `core/loader.py`: `_parse_transition`이 `pref` 파싱(생략 시 None, 음수·비수 거부).
    `for:`/`${expr}` 템플릿과 호환(전체-`${expr}`이면 타입 보존, D18).
  - `core/schema.py`: `pref` 음수 금지 정도(sim 전용이라 가벼운 검증). BMC/PRISM 경로는 무변경.
  - `sim/engine.py`: `run_once`의 `len(enabled) > 1` 분기를 — 모든 enabled가 `pref` 보유 시
    정규화 표집, 혼재/부재 시 `DtmcViolation` — 으로 교체. `_sample_transition` 헬퍼 추가.
    RNG는 기존 counter-based 스트림 그대로(추가 draw 1회, 순서 결정적 → 워커 무관 재현성 유지).
  - `sim/report.py`: "주어진 정책 하의 추정 · Pmax 아님" 라벨.
  - 문서: CLAUDE.md §4.1(`pref` 문법·dialect 표)·§2(안전망), concepts.md §8(정책/스케줄러).
  - 예제: `examples/dungeon_sim.rule`의 가드-인코딩 전략을 `pref` 정책으로 분리한 변형 예제
    (규칙은 MDP로 두고 정책만 `pref`로) 추가 검토.
- **성공 기준:**
  - 닫힌형을 아는 골든 모델(한 상태에서 `pref` p/(1-p)로 갈리는 2전이 → 도달 분포)에서 sim
    추정이 p를 95% CI 안에 맞춘다(선택 표집 정확성, PRISM 없이 sim 단독).
  - 모든 enabled가 `pref` 미선언인 비결정 모델은 여전히 친절히 거부(`DtmcViolation`).
  - `pref` 일부 누락(혼재)도 거부(안전망). `pref` 합 0도 오류.
  - 기존 DTMC 예제(`dungeon_sim.rule`)는 `pref` 무선언이라 **동작·결과 불변**(하위 호환).
  - BMC/PRISM은 `pref`를 무시하고 기존과 동일 결과(dialect 분리 회귀).

---

## D21. 외부 DSL(자체 문법)로 표면 언어 승격 + `=`/`==`(대입/비교) 분리

- **상태:** 구현 중 (2026-06-25, 사용자 결정) — 외부 DSL 채택·`=`/`==` 분리 확정. 파일
  확장자 **`.lf`**(YAML `.rule`과 확장자로 디스패치), YAML은 **디프리케이트**(1회 경고).
  구현 진행: `core/text_loader.py`(Lark) S1~S6 — domain·정적식·전이·checks·템플릿·desc/author·
  로더 디스패치·dungeon 이관까지 골든 IR 등가로 고정(테스트 통과). D2(ast 표현식 파싱)·
  D18(템플릿)의 *프론트엔드 기구*를 대체하되 **결정론 원칙은 보존**(런타임 evaluator는 잔존).
  전 예제 이관·YAML 제거 완료 시 D2·D18을 `상태: 대체됨(프론트엔드 한정)`으로 표시 예정.
- **맥락:** 현재 `.rule`은 순수 YAML이 아니라 문자열에 **미니언어 2겹**을 품는다 —
  ① 표현식(`"role == warrior and level == 100"`, D2가 ast 화이트리스트로 파싱),
  ② 템플릿(D18: `for:` 곱·`${win[mon][cls]}` 색인 보간·`tables:`). 이 둘은 *호스트(YAML)가
  못 주는 것을 손으로 재구현한 자리*다 — D18이 `${1-win-death}` 산술을 부동소수 문제로 보류한
  것이 그 한계의 징후다. 표면 언어를 세 후보로 검토했다: ① YAML 유지, ② Internal DSL(Python
  임베드, 연산자 오버로딩), ③ 외부 DSL(자체 문법·Lark).
- **핵심 개념/근거:**
  - **Internal(Python) DSL의 결함:** Python은 `and`/`or`/`not`을 오버로딩할 수 없어 `&`/`|`/`~`
    (정밀도 괄호 함정)이나 `all_()`/`any_()`로 우회해야 하고, 무엇보다 **룰이 임의 Python**이
    되어 "룰=선언적 데이터·결정론 검증"(§2 원칙1·2)을 *런타임에 막아야* 한다 — 환각 위험을
    구조가 아닌 규율로 누른다. LLM 생성·diff·round-trip도 데이터(YAML)보다 나쁘다.
  - **외부 DSL의 정합:** 문법이 곧 경계다 — `while`·함수정의·import·부수효과를 *애초에
    표현 불가*로 만들어 비-튜링완전 선언을 **구조적으로** 보장한다(§2와 가장 정합). 파서를
    직접 소유해 `line:col`·도메인 인지 에러를 준다(§7·원칙4). 미니언어 2겹을 1개 일관 문법으로
    통합하고 `and/or/not`·다음상태·`for`·`table`·색인을 1급 시민으로 올린다.
  - **`=`/`==` 분리의 근거 = 엔진 의미론을 정직하게 노출:** 전이 효과는 *이미* 비교가 아니라
    **대입+프레임**이다 — `sim/engine.py` `apply_outcome`가 `_next_assignment`로 `next.X == rhs`를
    풀어 `state[var]=eval(rhs)`로 실행하고, `logic/solver/bmc.py` `_frame`이 미언급 변수에
    `next.y==y`(유지)를 자동 추가한다(D15). 즉 현행 `then`의 `==`는 *비교 기호로 대입을 쓰는*
    거짓 표기다. 다음상태(프라임)는 PRISM `(gold'=expr)`와도 동형이다.
- **결정:**
  - **(1) YAML→자체 문법(.rule) 승격.** Lark/EBNF, **비-튜링완전**(`for`=명시적 유한 리스트
    위 데카르트 곱, `${expr}`는 *id 이름* 보간에만, 표현식 안은 진짜 색인 `win[mon][cls]`).
    **IR은 불변** — AST→기존 IR lowering, desugar는 순수 구문 변환 → 백엔드 3종·스키마·검사
    무변경. (문법 초안 EBNF는 PLAN.md 6차 §3.)
  - **(2) `=`(대입) vs `==`(비교) 분리, 판별자 = 프라임 유무.** 다음상태 `gold'`엔 `=`(전이
    `then`/`outcomes` 전용), 같은상태 술어(`when`·`init`·정적 `constraint`·`check.that`)엔 `==`.
    `when gold = 5`(가드 대입)·`then gold' == x`(효과 비교)는 **파스 에러**(오타 방어, Python
    직관 재사용).
  - **(3) 다중 효과는 `;`(병렬 대입 집합)**, `and` 아님. `{ gold' = 0; room' = hall }`.
    `대입 and 대입`은 타입 에러로 차단. PRISM 병렬 업데이트와 정합.
  - **(4) BMC 술어 효과(`gold' > gold` 비결정) 포기.** sim은 이미 거부하므로 양 백엔드가
    일치하게 된다 — 비결정은 `outcomes`(우연)·`pref`(선택, D20)로만 표현(D11~D14). 코퍼스
    실손실 0.
  - **(5) 무회귀 게이트 = 골든 IR 등가.** 코퍼스 각 예제를 두 포맷(YAML·자체)으로 두고
    **IR 바이트 동일**을 고정(§8). 통과 전엔 YAML 로더 병행 유지, 통과 후 이관·디프리케이트.
- **기각/대비한 대안:**
  - *YAML 유지*: 미니언어 2겹·D18 한계(`${1-win-death}` 보류)·빈약한 에러 위치가 잔존.
  - *Internal(Python) DSL*: 표면 ergonomics(IDE·타입체크·import 재사용)는 좋으나 `and/or`
    오버로딩 불가·`&` 정밀도·**임의 코드로 결정론 경계 약화**·LLM 생성/round-trip 난해 →
    §2 정체성과 상충. (지난 검토에서 "추가 프론트엔드"로는 가치 있으나 주력 교체엔 부적합.)
  - *`then`을 술어로 유지(현행 `==`)*: 엔진이 대입으로 해석하는 사실과 표기가 어긋난 채로
    남고, sim(대입 강제)과 BMC(술어 허용)의 의미 불일치도 잔존.
  - *외부 문법이 PCTL까지 삼킴*: dialect 분리(D11) 훼손 → `prob`의 `spec`은 백엔드 전용
    불투명 문자열로 남긴다.
- **영향:**
  - `core/loader.py`: PyYAML→Lark 파서로(또는 병행 프론트엔드). `core/ir.py`·`core/schema.py`
    무변경(IR 동일). D2의 ast 화이트리스트는 *런타임 evaluator*(§7, sim)로 잔존 — 파싱 기구만 교체.
  - 문서: CLAUDE.md §4(전방 노트)·§5(파서), PLAN.md 6차. 예제·`rules/`는 Phase 5 이관(그전 병행).
  - 작업규약("DSL 문법 바꾸면 §4·로더·번역기·문서 함께 갱신")이 더 무거워짐 — 키워드/토큰을
    Phase 1에서 신중히 동결.
- **성공 기준:**
  - 코퍼스 전 예제가 두 포맷에서 **IR 바이트 동일**(골든 등가) — 1건이라도 불일치면 fail.
  - `=`/`==` 오용·`for` 비-리터럴 범위·미정의 색인이 `line:col`로 거부.
  - 자체 `.rule`이 BMC/sim/PRISM에서 YAML과 **동일 결과**(백엔드 무회귀).
  - 비-튜링완전 불변식 유지: `for`/`${}`가 화이트리스트 노드만 평가(§7), 일반 루프·재귀 불가.

---

## D22. 전이 효과의 프라임 표기(`var'`) 제거 — `then` 문맥이 곧 다음 상태

- **상태:** 확정 (2026-06-25, 사용자 결정) — D21의 "프라임 `gold'` ⟺ `=`(대입)" 판별 *표기*를
  개정(프라임 제거). `=`/`==`(연산자) + `then`/`when` 문맥이 대입/비교를 가르는 핵심은 유지된다.
- **맥락:** D21은 전이 효과를 `gold' = expr`(프라임 LHS + `=`), 같은상태 술어는 `==`로 분리했다.
  프라임은 (a) 다음상태 마커, (b) PRISM `(gold'=…)`/TLA+ 관례 동형 — 두 역할이었다. 그러나
  `then`/`outcomes` 문맥에선 LHS가 **항상** 다음상태이고 `=`(대입) vs `==`(비교)가 이미 대입/비교를
  가르므로, 프라임은 **의미를 결정하지 않는 잉여 토큰**이다. 단순 set(`room' = hall`)에선 순전한
  노이즈로 읽혔다(사용자 지적).
- **결정:** 전이 효과 대입에서 프라임을 **제거** — `room = hall`, `gold = gold + 1`. 문법은
  `assign: NAME "=" sum`. `=`/`==` + 문맥(`then` vs `when`/pred)이 대입/비교를 강제한다: 효과에
  `==`·가드/init/pred에 `=`는 구문 오류. 우변·가드는 현재 상태만 참조(다음상태 참조는 효과 LHS
  한정). IR lowering 불변 — `room = hall` → `next.room == hall`(PRISM `(room'=…)` 동형성은
  IR에서 유지).
- **기각/대비한 대안:**
  - *프라임 유지(D21 원안)*: PRISM/TLA+ 관례·자기참조(`gold' = gold+1`)의 시각적 명료성이 장점
    이나, 사용자가 노이즈로 판단. 자기참조 가독성은 임퍼러티브 관례(`x = x+1`)로 충분.
  - *명시 `next` 키워드(`next.room = hall`)*: 더 장황 — 프라임보다 못함.
- **영향:**
  - `core/text_loader.py`: 문법 `assign: NAME "'" "=" sum` → `NAME "=" sum`(1줄). 변환기·desugar·
    lowering 무변경(`'`는 익명 토큰이라 transformer items에 없었음).
  - 예제 14개(`.lf`)·테스트 효과 표기 일괄 갱신. 프라임 거부 테스트 2건 삭제(개념 소멸),
    가드-대입 거부 테스트 1건 추가.
  - 문서: CLAUDE.md §4·§4.1, PLAN.md 6차 §2·§3, README·editors(구문 강조에서 프라임 규칙 제거).
- **성공 기준:** 프라임 제거 후 코퍼스 14개 `.lf`가 `.rule`과 **IR 골든 등가 유지**(파라미터화
  하니스), 효과의 `==`·가드의 `=`가 구문 오류 거부, 전체 273 테스트 통과. ✅ 충족.

---

## D23. 구조 단순화 — PRISM을 테스트 전용 오라클로 격하 + 던전 예제 통합

- **상태:** 확정 (2026-06-25, 사용자 비준) — D13·D16·D19의 PRISM 위상을 갱신한다(사용자
  표면에서 내림). **번호 이력:** feat/new-dsl 머지로 D21·D22가 외부 DSL에 선점되어 본 결정을
  D21→**D23**으로 옮겼고, 머지로 예제가 모두 `.lf`로 이관됨에 따라 아래 통합 대상을 `.lf`
  기준으로 재서술했다(6차 외부 DSL 완료 위에 쌓는 7차 마일스톤).
- **맥락:** D19가 정량 무게중심을 PRISM→sim으로 옮기며 PRISM을 "소형 모델 교차검증 오라클"
  한 가지로 이미 격하했다. 그 결과 (1) PRISM의 *사용자 표면*(`ludoforge prob` CLI, DSL
  `kind: prob`/`spec` PCTL, 외부 prism 바이너리 의존)이 격에 안 맞게 남아 있고, (2) 던전
  예제가 **백엔드별로 4벌**(`dungeon` bmc+prob MDP / `dungeon_sim` sim+오라클 DTMC /
  `dungeon_policy` sim+pref MDP / `market_sim` sim real)로 비대해졌다. 특히 `dungeon_sim`은
  *PRISM 오라클 전용으로 만든 특수 DTMC*라, PRISM을 표면에서 내리면 존재 이유가 사라진다.
  두 군더더기가 같은 뿌리(PRISM의 어정쩡한 위상)에서 나온다.
- **결정:**
  - **(1) PRISM = 테스트 전용 오라클로 격하(제거 아님).** 사용자 표면을 전부 걷어낸다:
    `ludoforge prob` CLI 서브명령, DSL `kind: prob`·`spec`(PCTL), prob 예제, 문서의 "백엔드"
    로서의 PRISM. 단 `prob/`(prism_gen·runner)와 `test_sim_oracle.py`, **작은 DTMC 오라클
    픽스처**(`tests/fixtures/`로 이동)는 **남긴다** — sim 추정을 증명기로 검정하는 D19 신뢰
    논증("증명기가 추정기를 검정")은 프로젝트 DNA라 회귀로 보존한다.
  - **(2) 오라클은 reachable로 충분.** prism_gen은 `reachable`→`Pmax=? [F]`로 매핑하므로,
    오라클(DTMC라 Pmax=Pmin=정확값)은 `kind: prob`/PCTL 없이 `reachable` 검사만으로 돈다.
    따라서 DSL에서 `kind: prob`/`spec`을 떼도 오라클은 깨지지 않는다. prism_gen의 `prob`
    분기(spec 통과)는 사문화되므로 제거한다(reachable/invariant→PCTL 매핑만 유지).
  - **(3) 던전 예제를 하나의 실전형으로 통합.** `dungeon`·`dungeon_sim`·`dungeon_policy`·
    `market_sim`(모두 `.lf`)을 **단일 MDP+pref 던전**(`examples/dungeon.lf`)으로 합친다 — 클래스 밸런스
    (role sweep·클래스별 win_gold·클래스의존 전투 tables)에 "욕심 vs 안전"의 `pref` 선택을
    얹고, **bmc로 건전성**(클래스별 winnable·no_deadlock·불변식) + **sim으로 정책 추정**
    (직업별 승률·gold `distribution`)을 한 모델에서 본다. bmc는 pref를 무시(비결정 탐색),
    sim은 pref로 표집 — 하나의 모델, 두 질문(dialect 분리 D11·D20)을 그대로 시연한다.
  - **(4) 정적 모순 예제는 유지.** `item_enchant`·`loot_table` 등 정적 검사 예제는 프로젝트
    *창립 가치*(Z3 모순 증명, warrior-HP류)라 건드리지 않는다 — 통합 대상은 던전/전이 계열뿐.
- **기각/대비한 대안:**
  - *PRISM 완전 제거*: 유지 비용이 낮고(격리된 prob/ 411줄·graceful) 잃는 게 증명기 오라클
    (프로젝트 영혼)이라, 표면만 걷고 내부 오라클은 보존하는 쪽이 비용 대비 낫다.
  - *현행 유지*: `ludoforge prob`·`kind: prob`·4벌 예제의 학습/유지 표면이 D19 이후 위상과
    안 맞는다 — 표면 단순화의 실익이 크다.
  - *Pmax(최적 정책 확률) 사용자 노출 유지*: 존재·건전성은 BMC가 증명하고 정량은 sim 추정
    으로 옮긴 D19 방향상, 최적 확률 *증명*은 비목표로 둔다(오라클 내부에서만 사용).
- **영향:**
  - CLI: `ludoforge/cli.py`에서 `prob` 서브명령 제거(check·bmc·sim만).
  - core: `Check.spec` 필드·`kind: prob` 파싱/검증 제거(`ir.py`·`loader.py`·`schema.py`).
    `kind` ∈ {`reachable`,`invariant`,`no_deadlock`,`distribution`}로 축소.
  - prob: `prism_gen`의 `prob`(spec) 분기 제거, reachable/invariant→PCTL만 유지. `runner` 유지.
  - examples: 던전 4벌(`.lf`) 중 `dungeon`·`dungeon_sim`·`dungeon_policy`→`dungeon.lf` 1벌
    통합, `dungeon_sim`은 오라클 픽스처 `tests/fixtures/oracle_dungeon.lf`로도 보존(이름 명확화).
    **`market_sim`은 real·연속 능력(D19) 시연용으로 최소 보존**(통합 안 함, 사용자 결정
    2026-06-25). 단일파일 골든 참조용 `.rule`(머지 시 병존)은 통합·디프리케이트와 함께 정리.
  - tests: `test_probforge` 축소(오라클 관련 매핑만), `test_sim_oracle` 픽스처 경로 갱신,
    `test_bmc`·`test_cli`·`test_corpus`(EXAMPLE_EXPECTED)·`test_sim_scale`에서 prob 표면 정리.
  - 문서: CLAUDE.md §1(PRISM=테스트 오라클)·§3·§4.1(kind 집합·prob 제거)·§6, concepts.md
    §8.6/§8.8/§9.6(PCTL·오라클 재서술), README, PLAN/PROGRESS. **D13·D16·D19 상태 주석 갱신.**
- **성공 기준:**
  - `ludoforge` CLI는 check·bmc·sim 3개만 노출(`prob` 없음). `kind: prob` 쓴 파일은 친절히 거부.
  - 통합 `dungeon.lf` 한 모델이 bmc(클래스별 winnable·no_deadlock)·sim(직업별 승률·분포)로
    동작. 예제 수가 던전 계열에서 4→1로 감소.
  - `test_sim_oracle`가 픽스처 DTMC로 PRISM 정확값 ∈ sim CI 회귀를 유지(PRISM 설치 시)·
    미설치 시 skip. 정적 모순 예제·테스트는 무변경.
  - 전체 테스트·ruff·mypy 통과.
---

## D24. 파생 상수(constraint 등식 핀)는 transition 효과로 갱신 금지

- **상태:** 확정 (2026-06-29, 사용자 비준) — `core/schema.py`에 정적 게이트 구현·테스트 완료.
- **맥락:** 던전!의 `win_gold`는 `constraint rogue_win_target: when role == rogue then win_gold == 10`
  처럼 **role의 함수로 파생되는 상수**다(게임 내내 불변, transition 효과엔 등장하지 않음).
  그런데 두 백엔드가 `constraint`를 **다르게** 해석한다: bmc는 매 스텝 **상태 불변식**으로
  강제하고(D15·`bmc._state_constraints`), sim은 **초기 상태 파생에만** 쓴다(`engine._propagate_
  constraints` — 이후 스텝엔 불변식 미적용, D11 dialect 분리). 이 차이 자체는 의도된 설계지만,
  만약 누군가 `win_gold`를 transition `then`에서 갱신하면(`then win_gold = win_gold + 5`) 두
  해석이 **충돌**한다 — role은 전이로 안 바뀌므로(프레임 유지) bmc는 갱신 후 스텝에서
  `role==rogue → win_gold==10` 불변식을 위반해 **후속 상태를 UNSAT으로 가지치기**(전이 발화
  불가·`no_deadlock` 오탐·도달성 무음 실패)하는 반면, sim은 불변식을 안 걸어 **멀쩡히 갱신**
  (승리 판별 기준선이 게임 중 이동)한다. 같은 모델이 백엔드별로 다르게 동작하는, 프로젝트가
  가장 경계하는 **조용한 불일치**(원칙 3·"실패는 크게")다.
- **결정:** 근원은 *한 변수가 양립 불가능한 두 역할(파생 상수 ∧ 가변 상태)을 겸하는 것*이다.
  `schema.validate()`에 정적 게이트 `_check_constraint_pinned_not_mutated`를 추가해, **constraint
  등식으로 핀되는 변수**(`then var == 값`의 변수 = sim `_constraint_targets`와 동형) ∩
  **transition 효과 LHS**(`next.X`) ≠ ∅ 이면 백엔드 도달 전에 `SchemaError`로 거부한다.
  메시지는 어느 변수·어느 전이인지 사람이 읽게 짚는다(원칙 4).
- **좁은 차단(핵심 트레이드오프):** constraint 전부를 막지 않는다. `then var == 값` **등식 핀**만
  변수를 특정값으로 고정해 갱신과 충돌하고, `then hp <= 5000` 같은 **관계형 불변식**은 hp가
  transition으로 변해도 정상이다(불변식 + 가변 상태는 합법). `_constraint_targets`가 등식 핀만
  잡으므로 `<=`/`>=`류는 자연히 통과 — 과잉 차단 없음.
- **기각한 대안:**
  - *sim도 constraint를 매 스텝 불변식으로 강제*: sim 의미를 광범위하게 바꾸고(D19가 init-파생만
    하기로 한 결정 번복), 근원을 막는 게 아니라 **두 백엔드가 똑같이 런타임에 실패**하게 만들
    뿐 — 설계 실수를 정적으로 못 잡는다. 기각.
  - *1급 파생 바인딩(`derived win_gold := f(role)`)*: 상태 변수가 아니므로 transition `then`에
    쓰는 것 자체가 구문 불가 — 개념적으로 가장 깨끗하나 IR·로더·세 백엔드를 다 건드리는 큰
    변경이라 보류. 필요해지면 후속. 현 단계는 좁은 스키마 검사가 비용 대비 낫다.
- **영향:** `core/schema.py`(`validate`에 검사 1개 + 헬퍼 `_constraint_pinned_targets`·
  `_effect_targets`·`_conjuncts`·`_eq_pair`·`_eq_var_target` — core가 sim에 의존하지 않게 재구현),
  `tests/test_schema.py`(거부 2 + 통과 2 케이스), CLAUDE.md §4.1, README "DSL 작성 팁".
- **성공 기준:** `examples/dungeon.lf`는 그대로 통과, `win_gold`를 transition에서 갱신하도록
  변형하면 정확히 거부. 관계형 불변식 + 갱신은 통과. 전체 테스트·ruff·mypy 통과.
---

## D25. BMC k-귀납 — 유계 결과를 무한 지평 증명으로 승격

- **상태:** 확정 (2026-07-02, 사용자 비준 — 종료코드 승격 포함) — 8차 마일스톤.
- **맥락:** D15가 못박은 대로 BMC의 `invariant`/`no_deadlock` "k까지 유지"는 증명이 아닌
  **유계 결과**다("무한 지평 보장은 k-induction 필요 — 미해결"). 게임이 커질수록(표현력
  확장 아크의 북극성: Dungeon! 2~4인 레이스판, 수백 턴) 미증명 구간이 리포트의 대부분이
  된다. "존재·건전성은 solver가 증명한다"(원칙 1·D19 분업)를 완성하려면 무한 지평 증명
  경로가 필요하다.
- **결정:**
  - **귀납 스텝:** base(기존 init 기준 BMC)가 k까지 통과한 뒤, **init을 뗀** 임의 합법
    상태열 s_0..s_j에 대해 `φ(s_0) ∧ … ∧ φ(s_{j-1}) ∧ ¬φ(s_j)`가 **unsat**이면 φ는 모든
    깊이에서 성립(증명). j=0..k로 시도해 **최소 귀납 깊이 j**를 보고한다(j=0 = 귀납 가설
    없이 모든 합법 상태에서 성립).
  - **귀납 가설에 상태 제약 포함(D15 재사용):** 도메인 min/max·정적 constraints는 매 스텝
    불변식(D15)이므로 스텝 검사의 모든 s_i에 건다. 건전성: 도달 가능한 상태는 항상
    합법이므로 합법 상태로 좁혀 귀납해도 도달 상태를 놓치지 않는다.
  - **세 kind 모두 같은 꼴로 승격:** `invariant` → `holds`(증명) / `no_deadlock` →
    `no_deadlock`(증명 — 전이 관계가 s_0..s_{j-1}의 발화를 이미 강제하므로 `¬enabled(s_j)`
    unsat 검사와 동형) / `reachable`의 k-미도달 → ¬that을 귀납해 성공 시
    `unreachable`(도달 불가 확정).
  - **정직성(무타협):** 스텝이 sat(비귀납)이거나 unknown이면 기존 k-bound status를
    유지하고 사유를 detail로 남긴다 — 절대 증명으로 뭉개지 않는다(§8). 귀납 반례(CTI)는
    도달 가능성을 보장하지 않으므로 v1은 사유 한 줄만(CTI trace 노출은 후속).
  - **종료코드(사용자 비준 2026-07-02):** 증명된 `holds`/`no_deadlock`은 정상(0).
    **`unreachable`(도달 불가 확정)은 reachable 검사의 실패 확정 → `has_violation`
    (종료코드 1)로 승격** — "아직 k가 작아 미도달"(3)과 "영원히 불가"(1)를 가른다.
  - **기본 활성:** 별도 플래그 없음. base 통과 후에만 추가 solver 호출이라 저비용.
- **기각한 대안:**
  - *distinct-state(단순 경로) 강화 즉시 도입*: 유한 상태에서 귀납 완전성을 높이지만
    제약이 커진다 — "참인데 비귀납"이 실전에서 반복 관측될 때 후속(PLAN 8차 Phase 5).
  - *보조 불변식 합성·IC3/PDR*: 비귀납 불변식의 근본 해법이나 스코프가 다른 마일스톤.
  - *`unreachable`를 미확인(3)으로 유지*: 확정 부정을 미확인과 뭉개 정직성 원칙에 반함. 기각.
- **영향:** `logic/solver/bmc.py`(`_solver_span` init 매개화 + `_induction` + 새 status
  `holds`/`no_deadlock`/`unreachable` + 리포트 라벨), `logic/solver/html_report.py`(배지·
  k-bound 라벨 동기화), `ludoforge/cli.py`(종료코드 문서), `tests/test_bmc.py`(+귀납 픽스처
  `bmc_induction.lf`), CLAUDE.md §4.1, concepts.md, D15 상태 주석.
- **성공 기준:** `dungeon.lf`의 `gold_nonneg`·`no_monster_in_hall`·`sound_victory`·`no_stuck`
  이 무한 지평 증명으로 승격, 기존 reachable-sat 검사 무변경. 비귀납 케이스는 k-bound
  status + 사유 유지. 전체 테스트·ruff·mypy 통과.
---

## D26. 상태 의존 `pref`/`weight` — 런타임 식 허용

- **상태:** 확정 (2026-07-02, 사용자 비준) — 9차 마일스톤.
- **맥락:** D20의 `pref`(플레이어 정책)와 D12의 outcome `weight`(환경 우연)는 상수라,
  적응적 정책("목표 근접이면 귀환 선호")과 **비복원 추출**(남은 덱 구성에 의존하는 조우
  확률 — 카드 게임 일반·실물 Dungeon!의 관문)을 표현할 수 없다. 구현 지형은 유리하다:
  sim 평가기는 변수 나눗셈을 이미 지원하고(`sim/engine.py` `_BIN_OPS`의 `Div`), sim은
  outcome weight를 이미 정규화 표집하며, PRISM 생성기도 이미 비율형(`_prob`의
  `weight/total`)으로 렌더한다 — 게이트는 문법·IR·로더의 "상수만" 강제뿐이다.
- **결정:**
  - **IR 타입 확장(하위 호환):** `Outcome.weight: float | str` · `Transition.pref:
    float | str | None`. 수치 리터럴·표 색인(desugar 후 수치)은 지금처럼 float —
    골든 IR 등가 무회귀. 상태 식일 때만 표현식 문자열(str)로 보존.
  - **평가 의미론:** 식은 **전이 직전 상태**에서 평가(`next.*` 금지). `weight`는 음수/합0
    이하이면 런타임 SimError(실패는 크게), 합이 양수면 정규화 표집(기존 의미의 자연 확장).
    `pref`는 D20 의미 전부 불변(co-enabled 정규화·opt-in 안전망·enabled 1개 rng 미소비).
  - **enabledness는 가드 단독(백엔드 공통 규율):** weight/pref는 어떤 백엔드에서도 enabled
    여부를 바꾸지 않는다. "덱 소진" 같은 상태는 **가드로 배제**하는 것이 모델러 책임 —
    sim이 합 0 상태를 만나면 가드 누락으로 보고 에러.
  - **dialect 분리 유지(D11):** BMC는 weight-erasure(D15)·pref 무시(D20) 그대로(식이어도
    지움). PRISM 오라클은 weight 식을 비율형 `(w_i)/(Σw)`로 렌더(합=1 구성적 보장).
    pref는 PRISM에서도 계속 무시.
  - **BMC 과근사 정직성:** weight-erasure는 상태 의존 weight에서 더 거친 추상이 된다 —
    weight 식이 0인 분기도 BMC는 "가능"으로 탐색(reachable 증인이 확률 0 분기를 밟을 수
    있음). 불변식/데드락엔 건전(과근사). 문서에 명시하고, weight>0의 Z3 가드 결합 정련은
    비선형(변수 나눗셈) 위험이 있어 후속.
  - **`.lf` 전용:** 디프리케이트된 YAML(`.rule`)엔 미도입 — 식이 오면 명확히 거부(조용한
    float 강제 변환 금지).
  - **스키마 검증:** 식의 참조 무결성(정의된 변수만·`next.*` 금지), 음수 상수 로드 거부
    유지. 실행 시 수치 타입은 런타임 검사.
- **기각한 대안:**
  - *weight 0을 enabledness에 반영*: 백엔드마다 enabled 의미가 갈라진다(BMC는 식을 못
    보므로) — 가장 경계하는 조용한 불일치. 기각.
  - *합=1 엄격 검증(정규화 금지)*: 비복원 추출의 자연형(`count/total`)은 구성적으로 합=1
    이나, 상대 가중치(2:1) 표기를 막아 사용성만 잃음. 기존 정규화 의미 유지.
  - *YAML에도 도입*: 디프리케이트 표면에 신규 표현력 투자는 낭비. 기각.
- **영향:** `core/text_loader.py`(t_pref expr·outcome weight 식 보존), `core/ir.py`,
  `core/loader.py`(YAML 거부), `core/schema.py`(식 검증), `sim/engine.py`(런타임 평가),
  `prob/prism_gen.py`(식 렌더), `examples/dungeon.lf`(덱 카운터+적응 pref, 북극성 1단계),
  픽스처 `urn.lf`(비복원 골든·오라클), CLAUDE.md §4.1, concepts.md, README.
- **성공 기준:** urn(2색 비복원) sim 분포가 닫힌형·PRISM 정확값과 일치, 상수 모델
  SimReport 비트 동일(하위 호환), 던전 확장이 bmc·sim 양쪽 동작. 테스트·ruff·mypy 통과.
---

## D27. 플레이어 태그 — 전이 소유 선언(다인 게임 입구)

- **상태:** 확정 (2026-07-02, 사용자 비준) — 10차 마일스톤.
- **맥락:** 전이 시스템에 플레이어 개념이 없어, 턴제 다인 게임을 `turn` enum + 가드로
  손으로 인코딩해도 **도구는 어느 선택이 누구 것인지 모른다** — 가드 실수로 두 플레이어의
  선택이 한 상태에 겹쳐도(co-enabled) sim이 조용히 pref로 표집해 버린다(턴제 위반의 무음
  통과). 표현력 확장 아크(8차 k-귀납 → 9차 상태 의존 pref/weight → **10차** → 11차 배열)의
  세 번째 단계이자 북극성 2단계(2인 레이스 던전)의 전제.
- **결정:**
  - **`Transition.player: str | None = None`(IR) + `.lf` `player NAME` 절.** None=무소속
    (환경/자연 전이). `for` 템플릿의 loop 변수를 태그 자리에 쓰면 desugar가 치환한다.
  - **태그 = 소유 선언, 스케줄러 아님.** 누구 턴인지는 여전히 모델(`turn` enum + 가드 +
    효과)의 몫 — 태그는 검증·리포트용 메타데이터일 뿐 전이 시스템 의미(D12·D15)를 바꾸지
    않는다.
  - **참조 무결성:** 태그 이름은 **선언된 enum의 값**이어야 한다(schema 오타 게이트, 관례상
    `turn: enum { p1, p2 }`). 별도 `players` 선언 형식은 도입하지 않는다(IR 표면 최소).
  - **sim 소유 게이트(핵심):** co-enabled 선택 집합(enabled≥2)의 태그는 **모두 동일**해야
    한다(None 포함). 혼성(p1+p2 또는 태그+무소속)이면 상태·전이·소유를 짚어 명시 거부 —
    가드 실수를 조용히 덮지 않는다(실패는 크게). **동시 수(simultaneous move)는 v1 비지원.**
    단일 소유 집합의 표집은 기존과 완전 동일(2단 표집·rng 소비 규칙 불변) → 태그 없는
    기존 모델은 비트 동일 하위 호환.
  - **BMC/PRISM: 완전 무시** — weight-erasure(D12)·pref 무시(D20)와 같은 계보의 주석
    (dialect 분리 D11). 적대적 해석(∃전략 ∀응수)은 별도 마일스톤(태그가 그때의 어휘).
  - **`.lf` 전용**(D26과 동일) — 디프리케이트된 YAML엔 미도입.
  - **북극성:** 신규 `examples/dungeon_race.lf`(2인 레이스 — 턴 교대·공유 몬스터 덱·비대칭
    정책). 1인판 `dungeon.lf`는 기준 예제로 유지 — 레이스판의 플레이어별 스칼라 수동
    복제가 11차(배열)의 동기를 시연한다.
- **기각한 대안:**
  - *별도 `players { … }` 선언*: enum 값 게이트로 충분한 것에 IR 표면만 늘린다. 기각.
  - *혼성 co-enabled 허용(동시 수 해석)*: 백엔드 의미가 갈라지고(BMC는 어차피 한편)
    턴제 가드 실수를 덮는다. 동시 수는 필요해지면 별도 결정으로. 기각.
  - *태그로 턴 스케줄링 자동화*: 전이 시스템 의미 변경 — 세 백엔드 전부 손대는 큰 수술이며
    가드 기반 표현이 이미 충분하다. 기각.
- **영향:** `core/ir.py`(`Transition.player`), `core/text_loader.py`(`t_player` 절·desugar
  치환·예약어), `core/schema.py`(enum 값 게이트), `sim/engine.py`(소유 게이트·정책 라벨),
  `examples/dungeon_race.lf`(북극성 2단계), CLAUDE.md §4.1, concepts.md, README.
- **성공 기준:** 태그 없는 전 코퍼스 골든 IR·sim 비트 동일 무회귀, 혼성 co-enabled 픽스처
  거부(원인 짚는 메시지), 레이스 예제가 bmc(양쪽 winnable·불변식·데드락)와 sim(매치업
  승률)에서 동작. 테스트·ruff·mypy 통과.
---

## D28. 배열/인덱스 변수 — 유한 색인 스칼라 가족(순수 desugar)

- **상태:** 확정 (2026-07-02, 사용자 비준) — 11차 마일스톤(표현력 확장 아크의 마지막).
- **맥락:** 플레이어별 상태는 스칼라 수동 복제다(10차 레이스: `gold_p1`/`gold_p2` + 전이
  12개 — 변수 *이름*은 템플릿 불가). 개체가 늘수록 소스가 곱으로 는다. 한편 진단
  (2026-07-02)에서 "가변 길이 컬렉션은 상태폭발·결정불가로 직행하는 문"이라 경계 게이트를
  합의했다 — PRISM의 도입→격하 왕복(D13→D19→D23)을 반복하지 않기 위함.
- **결정:**
  - **선언 = 유한 색인 배열:** `gold[p1, p2]: int 0..30` — 색인은 **명시적 유한 값 목록**.
    desugar가 **스칼라 가족 `<base>_<idx>`**(`gold_p1`·`gold_p2`, 선언 순서 유지)로 펼친다.
  - **구현 = 순수 desugar(D18 계보):** 정적 색인(`gold[리터럴]`·`gold[loop변수]`)은 파스
    트리에서 스칼라 이름으로 치환 — **IR·세 백엔드·결정론 경계 무변경**. 펼친 이름이
    기존 변수와 충돌하면 로드 거부(조용한 잠식 금지). 효과 LHS도 정적 색인 허용
    (`gold[p] = …` — assign 좌변 확장).
  - **동적 색인은 읽기 전용(Tier 2):** `gold[turn]`(색인이 enum 변수)은 desugar가 유한
    case-분기 **IfExp**로 lowering(`gold_p1 if turn == p1 else gold_p2`). 평가기·Z3(If)·
    PRISM(ternary)에 IfExp 지원을 더하되, **IfExp는 desugar 산출물로만 등장**(문법에 삼항
    없음 — 사용자 표면 비-튜링완전 유지). 허용 위치: 술어·효과 RHS·요율(pref/weight).
  - **효과 LHS 동적 색인은 보류:** `gold[turn] = …`는 프레임(D15)이 "모든 원소 조건부
    갱신"이 되어 세 백엔드 수술 필요 — v1은 명확한 에러. 턴제의 "현재 플레이어" 갱신은
    플레이어별 전이(가드) + 정적 색인이 관례.
  - **경계 게이트(비도입):** 가변 길이 시퀀스·삽입/삭제·손패 연산 없음 — 카운트 멀티셋
    (9차 비복원)이 덱/자원의 지원 표현. 한정자 init 축약(`all p in …`)도 후속.
  - **리포트 = 펼친 이름 노출**(`gold_p1` — 결정적·추적 가능, D18 id 원칙). 되접기 표시는
    후속.
  - **이름 공간:** 표(table)와 배열은 같은 색인 구문 — base 이름으로 판별하며 겹치면 거부.
    배열 base의 bare 사용(색인 없이)은 거부.
- **기각한 대안:**
  - *IR 1급 배열(백엔드别 배열 이론/리스트)*: Z3 배열 이론·sim 리스트·PRISM 인코딩을 모두
    수술하는 최대 침습 — 유한 색인에선 스칼라 가족과 표현력이 같다. 기각(가변 길이가
    실제로 필요해지는 날의 별도 결정).
  - *동적 색인 전면 허용(LHS 포함)*: 프레임 의미 수술. 보류.
- **영향:** `core/text_loader.py`(선언·색인 desugar·assign 좌변), `sim/engine.py`(IfExp
  평가), `logic/solver/translator.py`(z3.If), `prob/prism_gen.py`(ternary),
  `core/schema.py`(참조 검사), `examples/dungeon_race.lf`(접기 — 북극성 3단계),
  `tests/fixtures/race_manual.lf`(수동판 골든 스냅샷), CLAUDE.md §4, concepts.md, README.
- **성공 기준:** 접은 레이스 예제의 IR이 수동판과 **구조 동일**(골든 등가 — 배열 desugar
  ≡ 수동 스칼라의 영구 증명), bmc/sim 결과 무변경, 동적 색인 술어가 세 백엔드 일치
  (PRISM 오라클 교차검증), LHS 동적 색인·이름 충돌·미선언 색인은 위치 짚는 거부.
---

## D29. 문서 메타데이터 + 규칙서 생성기 — `.lf`를 게임 규칙 SSOT 문서로

- **상태:** 확정 (2026-07-06, 사용자 비준) — 12차 마일스톤(규칙서 SSOT 아크 12~14차의 첫째).
- **맥락:** `.lf`는 검증·추정에 최적화되어 실제 게임 규칙의 서술이 유실된다(진단 2026-07-06
  — PLAN 아크 개요). 그중 **서술 손실**(검증에 무의미한 절차·연출·출처)의 처방이다:
  `desc` 한 줄로는 못 담아 실제 규칙 설명이 `//` 주석에 산다(dungeon.lf 헤더 22줄) —
  주석은 구조가 없어 도구(문서 생성·리포트)가 못 쓰고 참조 무결성도 없다.
- **결정:**
  - **문서 절 문법(`.lf` 전용 — D26·D27 계보):** 선언(constraint/transition/check/expect)
    몸통에 `note "..."`(반복 허용 — 절차·연출 산문, 선언 순서 유지), `ref "..."`(출처 —
    룰북 페이지·URL), `tag name, ...`(분류). domain 변수·`table` 헤더에 `desc "..."`
    (용어집·표 설명). 최상위 `section "제목"`(문서 목차 — 이후 선언들이 그 절에 속함).
  - **IR passthrough:** frozen `Doc(notes, ref, tags)` + 각 선언 IR에 `doc: Doc | None =
    None`, `Variable.desc: str | None = None`. 기본 None → 골든 IR 등가 무회귀. 세 백엔드는
    전부 무시 — D12 weight-erasure·D20 pref·D27 player와 같은 **"지워지는 주석" 계보**.
    **`section`·table desc는 IR 미탑재**(문서 전용 — 파스 트리에만).
  - **규칙서 생성은 desugar *전* 파스 트리 기반(P2):** `ludoforge doc`(`core/docgen.py`)은
    저자가 쓴 접힌 형태(for 템플릿 1개 + 표)를 렌더한다 — IR(검증용·펼친 8개 전이)과 문서
    뷰(표면용)의 요구가 다르다. SSOT는 `.lf` 하나, 규칙서는 단방향 파생 뷰.
  - **`[[이름]]` 참조 게이트(드리프트 억제):** note/desc(변수·table desc·section 제목 포함)
    안 `[[이름]]`은 로드 시 검사 — 변수·enum 값·선언 id·table 이름 중 하나여야 하며
    미정의면 거부(실패는 크게). `ref`는 외부 출처라 검사 제외. 한계: 존재만 검사 — 산문
    *내용*의 드리프트는 못 잡는다(완화: docgen이 형식부를 산문 옆에 항상 병기).
- **기각한 대안:** 상세/추상 모델 파일 분리(기계 검사 없는 대응 = 산문 드리프트 재현),
  Event-B식 정련 증명(체급 초과), 규칙서 손 저술(생성이 아니면 반드시 어긋남 — 창립 문제).
- **영향:** `core/ir.py`(Doc·desc), `core/text_loader.py`(문서 절 문법·참조 게이트),
  P2에서 `core/docgen.py`+`ludoforge/cli.py`(doc 서브명령), P3에서 예제 저술·CLAUDE §4.
- **성공 기준:** 문서 절 픽스처 round-trip(IR doc 채움), 미정의 `[[..]]` 거부, 문서 절 없는
  전 코퍼스 골든 IR 무회귀·백엔드 무변경(P1). dungeon.lf 규칙서가 사람이 읽는 규칙 설명
  문서로 생성(P2~P3).
---

## D30. 주사위 확률식 `chance`/`rest` — 닫힌형 유리수 desugar

- **상태:** 확정 (2026-07-06, 사용자 비준) — 13차 마일스톤(규칙서 SSOT 아크의 둘째).
- **맥락:** 형식화 손실의 대표 — dungeon.lf의 win/miss/death 표 24칸은 실제 규칙("2d6이
  격파 목표값 이상이면 승리")을 손으로 환산한 매직 넘버였다. 원형(목표값)은 주석에만 살고,
  표를 고칠 때 규칙과 어긋나도 아무도 모른다. D18은 `${1-win-death}`류 잔여 계산을
  부동소수 정밀도 문제로 보류했었다.
- **결정:**
  - **문법(`.lf` 전용):** outcome weight 자리에 `chance(<dice pred>)` | `rest`. dice
    원자는 `NdM` 1개(전용 토큰 — n≥1·m≥2·n×m≤10000), 술어는 `NdM CMP 상수식`(상수식 =
    리터럴·표 색인·loop 변수 — desugar 후 상수 강제, 상태 의존 목표는 거부: 상태 의존
    확률은 D26 식 weight의 몫). **pref엔 불허**(정책은 주사위가 아님 — 문법 차원 거부).
  - **desugar(D18 계보 순수 구문 변환):** NdM 분포를 `Fraction` 콘볼루션으로 정확 계산 →
    술어 확률 → 기존 **float weight로 lowering**. IR·세 백엔드·결정론 경계 불변.
  - **`rest` = 유리수 잔여:** 1 − (같은 블록의 chance·상수 가중치 합, Fraction 정확).
    블록당 1회. chance/rest는 **상수 가중치와만** 혼합(상태 식 weight와 섞으면 거부 —
    잔여·합 검사가 불가능해짐). 합 > 1이면 거부. D18의 잔여 계산 보류를 해소한다.
  - **예제 수치 변동 수용(비준):** dungeon.lf 전투를 격파 목표값 표(beat)+치명 문턱 표
    (fumble)+`chance`/`rest`로 재저술 — 기존 확률을 정확히 역산할 수 없어 sim 추정치가
    2d6 격자로 이동한다(새 닫힌형 골든으로 교체, 모델링 결정은 예제에 명시).
- **기각한 대안:** 산술 보간(`${1-win-death}`) 재도입(정밀도·가독 — rest가 대체),
  dice 합성(`2d6+1d4`)·개별 눈 참조(실전 트리거 시 확장), 상태 의존 목표값(D26과 중복).
- **영향:** `core/text_loader.py`(DICE 토큰·chance/rest 문법·Fraction desugar),
  `examples/dungeon.lf`(전투 재저술), `tests/`(닫힌형 골든·오라클 픽스처), CLAUDE §4.1·§4.2.
- **성공 기준:** 손 계산 골든(P(2d6≥9)=10/36 등) 일치, 합>1·rest 중복·상태 의존 목표·혼합
  거부, 전 코퍼스 무회귀, dungeon bmc 검사 지위 불변 + sim 새 닫힌형 골든, PRISM 오라클
  교차검증(닫힌형 ∈ sim CI).
---

## D31. `ghost` 서술 변수 — 검증 제외 상태(단방향 의존)

- **상태:** 확정 (2026-07-06, 사용자 비준) — 14차 마일스톤(규칙서 SSOT 아크의 셋째·마지막).
- **맥락:** "게임이 보통 몇 번의 전투를 거치나" 같은 서술적 정량은 규칙서·튜닝에 유용하나,
  상태 변수로 넣는 순간 BMC/PRISM 상태공간이 곱으로 커진다(k-귀납·데드락 증명 저하).
  ghost가 게임 진행에 몰래 영향을 주면 두 백엔드 의미가 갈라진다(D24와 동종의 조용한
  불일치) — 그래서 **단방향 의존을 schema가 정적으로 강제하는 게이트가 본체**다.
- **결정:**
  - **선언:** `ghost turns: int 0..` 수식어(`.lf` 전용, 배열 D28과 결합 가능). IR
    `Variable.ghost: bool = False`(기본 False → 골든 무회귀).
  - **단방향 의존(핵심 불변식): "ghost 전부 제거 시 비-ghost 궤적 비트 동일".** ghost를
    읽을 수 있는 곳 = ① ghost 대입의 RHS, ② `distribution` check expr(sim 전용 리포트),
    ③ 문서 절 `[[..]]`(D29). **가드·constraint·expects·reachable/invariant that·
    pref/weight 요율·비-ghost 효과 RHS에서 ghost 참조는 schema가 거부**
    (`_check_ghost_one_way`). init에서 ghost는 **상수 고정 필수**(자유 sweep·파생 금지).
  - **`erase_ghosts(ruleset)` — core의 순수 IR→IR 변환:** ghost 선언·ghost 대입·init의
    ghost conjunct 제거(효과가 전부 ghost면 `True`로 — 프레임이 유지하는 자기 분기).
    **bmc·PRISM 오라클은 소비 전 erase**(상태공간 완전 제거 — 증명 지위 불변), **sim은
    원본 실행**(ghost 대입은 rng 미소비 → 비-ghost 추정 비트 동일). `check_finite_state`는
    ghost를 건너뛴다(erase 후 기준 — ghost는 무한 int여도 PRISM 게이트에 무해).
  - **리포트 정직성:** sim distribution의 ghost 식 결과에 "서술 변수(ghost — 논리 검증
    제외)" 라벨. bmc 리포트에 ghost 제거를 각주로 명시(조용히 숨기지 않음).
- **기각한 대안:** ghost의 가드/weight 참조 허용(백엔드 의미 분기 — D24 교훈), bmc가
  ghost를 그대로 태우기(상태공간 낭비 — 이 마일스톤의 존재 이유 부정), 별도 관측 전용
  파일(SSOT 분리 — 아크 개요에서 기각한 상세/추상 분리와 동종).
- **영향:** `core/ir.py`(ghost)·`core/text_loader.py`(수식어)·`core/schema.py`(게이트·
  finite 스킵)·`core/ghost.py`(erase, 신설)·`logic/solver/bmc.py`(erase+각주)·
  `prob/prism_gen.py`(erase)·`sim/aggregate.py`(라벨)·`examples/dungeon.lf`·CLAUDE §4.
- **성공 기준:** ghost 단 모델에서 bmc 리포트가 ghost 제거판과 동일(증명 지위 불변),
  sim 비-ghost 추정 비트 동일, ghost distribution 신규 동작, 위반 참조는 위치 짚는 거부.
---

## D32. 도메인 축소 — "게임 기획 언어"에서 "수치·경제 시스템 검증기"로

- **상태:** 확정 (2026-07-07, 사용자 비준) — 15차 마일스톤(피벗 아크의 시작).
- **맥락:** 원 목표("기획자가 기획 전용 언어로 게임을 기획하고, 그 자체가 기획문서가
  된다")는 두 구조적 벽에 막힌다는 진단을 사용자가 비준했다.
  ① **표현력의 벽:** 지금까지의 확장(D18 표·D28 배열·D30 주사위)은 전부 *구조는 같고
  데이터만 다른* 조합 폭발을 접는 장치다. 테라포밍 마즈류의 **카드별 고유 메커니즘**은
  이 부류가 아니며, 기술하려면 DSL이 범용 언어가 되어야 한다 — 비-튜링완전성과 Z3 번역
  가능성이라는 존재 이유가 무너진다. ② **상태공간의 벽:** 설령 기술돼도 BMC·k-귀납·
  PRISM은 소형 모델에서만 답한다. 형식 기법의 일반사와 동형(TLA+도 프로토콜 커널만
  검증) — "전체의 SSOT"가 아니라 "치명적 부분계의 검증기"가 생존형이다.
  한편 원 *동기 문제*(여러 기획자의 룰이 함께 두면 모순 — warrior_hp)는 게임 전체
  모델링을 요구하지 않았고, 기존 예제 13개 중 11개가 이미 수치·경제 계열이었다
  (피벗은 방향 전환이 아니라 현상 인정).
- **결정:**
  - **도메인 재정의:** 본 도구는 **게임 수치·경제 시스템 검증기**다 — 성장 공식·드랍률·
    재화 싱크/소스·상한 규칙의 모순 증명(check)·동역학 건전성(bmc)·분포 추정(sim).
    게임 전체를 기술하는 기획 언어는 명시적 비목표로 격하한다(CLAUDE §1).
  - **표면 언어 단일화:** 초기 YAML(`.rule`) 프론트엔드를 제거한다(D21 디프리케이트의
    완결). 로더 진입점(`load_rule_file`/`load_rules`)은 유지하되 `.rule`/`.yaml`은 `.lf`
    안내와 함께 명시 거부. `old_examples/`·이관 등가 하니스 은퇴(접힘 문법 골든은
    `race_manual.lf` 쌍이 계속 지킨다).
  - **예제 지위 조정:** 보드게임 통합 예제(dungeon·dungeon_race)는 전 기능 시연·테스트
    픽스처로 유지하되 대표 지위는 수치·경제 예제로 옮긴다.
  - **동결(제거 아님):** PRISM 오라클(`prob/`)·주사위 D30·player D27은 유지 비용이 낮아
    남기되 신규 투자하지 않는다.
  - **인터페이스 전환(후속 마일스톤):** "기획자가 배우는 언어"에서 **"AI가 유지하는
    중간표현"**으로 — 산문/시트 입력 → LLM 번역(수리 루프: 로더·스키마 오류 피드백) →
    사람 게이트(생성 `.lf` + docgen 규칙서 병렬 확인) → bmc/sim 실행의 웹 인터페이스.
    시트→`table` 절은 LLM 없이 결정론 변환. **판정은 항상 solver — 원칙 1 불변**(LLM은
    번역만, unsat core 설명만).
- **기각한 대안:** DSL 표현력 확장으로 전체 게임 커버(튜링완전화 → 검증 가능성 붕괴 —
  맥락 ①), 현상 유지(포지셔닝 모호 → 기획자 채택 동인 부족), YAML 병행 유지(두 프론트엔드
  동기화 비용이 좁힌 도메인에서 무근거 — 기존 사용자 없음).
- **영향:** `core/loader.py`(YAML 분기 제거)·`old_examples/` 삭제·`tests/fixtures/*.rule`
  → `.lf` 이관(IR 등가 19/19 확인)·`pyproject`(pyyaml 제거)·CLAUDE §1(정의·비목표)·
  §4~§6(.rule 흔적)·README. 웹 인터페이스는 별도 마일스톤(웹 MVP)으로.
- **성공 기준:** 기존 검증·추정 능력 무회귀(전체 테스트 통과), `.rule` 입력이 명확한
  안내와 함께 거부, 문서가 좁힌 도메인을 일관되게 말한다. 웹 MVP: 산문+시트 입력이
  사람 승인을 거쳐 bmc/sim 리포트까지 한 화면에서 흐른다.

---

## 참고
- 결정의 도메인 배경: [concepts.md](concepts.md) (특히 §4 — 도달 가능성 검사)
- 살아있는 계획·진행: [../PLAN.md](../PLAN.md) / [../PROGRESS.md](../PROGRESS.md)
- 아키텍처 SSOT: [../CLAUDE.md](../CLAUDE.md)
