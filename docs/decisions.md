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
  여전히 PRISM 경로(`ludoforge prob`)에만 적용되고, sim은 무한·real을 허용한다. 다중 백엔드 Phase 0
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
    명시한다(무한 지평 보장은 k-induction 필요 — 미해결, PLAN §6).
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
  **검증 완료**(아래 검증 후기).
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

## D21. 구조 단순화 — PRISM을 테스트 전용 오라클로 격하 + 던전 예제 통합

- **상태:** 초안 (2026-06-24) — D13·D16·D19의 PRISM 위상을 갱신한다(사용자 표면에서 내림).
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
    `market_sim`을 **단일 MDP+pref 던전**(`examples/dungeon.rule`)으로 합친다 — 클래스 밸런스
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
  - examples: 4벌→`dungeon.rule` 1벌 통합. `dungeon_sim`은 오라클 픽스처로
    `tests/fixtures/`에 보존(이름 명확화). `market_sim`(real 쇼케이스)은 통합 흡수 여부 검토.
  - tests: `test_probforge` 축소(오라클 관련 매핑만), `test_sim_oracle` 픽스처 경로 갱신,
    `test_bmc`·`test_cli`·`test_corpus`(EXAMPLE_EXPECTED)·`test_sim_scale`에서 prob 표면 정리.
  - 문서: CLAUDE.md §1(PRISM=테스트 오라클)·§3·§4.1(kind 집합·prob 제거)·§6, concepts.md
    §8.6/§8.8/§9.6(PCTL·오라클 재서술), README, PLAN/PROGRESS. **D13·D16·D19 상태 주석 갱신.**
- **성공 기준:**
  - `ludoforge` CLI는 check·bmc·sim 3개만 노출(`prob` 없음). `kind: prob` 쓴 `.rule`은 친절히 거부.
  - 통합 `dungeon.rule` 한 모델이 bmc(클래스별 winnable·no_deadlock)·sim(직업별 승률·분포)로
    동작. 예제 수가 던전 계열에서 4→1로 감소.
  - `test_sim_oracle`가 픽스처 DTMC로 PRISM 정확값 ∈ sim CI 회귀를 유지(PRISM 설치 시)·
    미설치 시 skip. 정적 모순 예제·테스트는 무변경.
  - 전체 테스트·ruff·mypy 통과.

---

## 참고
- 결정의 도메인 배경: [concepts.md](concepts.md) (특히 §4 — 도달 가능성 검사)
- 살아있는 계획·진행: [../PLAN.md](../PLAN.md) / [../PROGRESS.md](../PROGRESS.md)
- 아키텍처 SSOT: [../CLAUDE.md](../CLAUDE.md)
