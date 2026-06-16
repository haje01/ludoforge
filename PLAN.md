# PLAN.md — RuleForge 작업 계획

> 진행 상태는 [PROGRESS.md](PROGRESS.md), 설계 결정의 "왜"는
> [docs/decisions.md](docs/decisions.md), 아키텍처 SSOT는 [CLAUDE.md](CLAUDE.md).
> 완료된 1차 작업의 상세 이력은 git 커밋(S0~S8)과 decisions.md에 있다.

---

## 1차 마일스톤 — ✅ 완료 (2026-06-16)

수직 슬라이스 완성: `ruleforge check <path>`로 로드 → 스키마·참조 검증 →
Z3 번역 → Optimize 도달성 검사 → 한국어 리포트가 end-to-end로 동작한다.
LIA 수치 공식 + 조건부(`when`) 룰 + enum을 지원하고, 세 가지 모순 유형
(범위 봉쇄 / enum 도달 불가 / 전역 over-constraint)을 unsat core로 짚는다.

확정된 설계 결정은 [docs/decisions.md](docs/decisions.md)의 D1~D5 참조.

---

## 2차 마일스톤 — 진행 항목

### ✅ 완료: 불리언 상태 변수 (상호 배제) — D6 (2026-06-16)

`Not(And(stealthed, attacking))` 류 상호 배제 룰을 표현·검사한다. bool을 도달성
변수로 취급해 "상태 봉쇄" 모순을 잡는다(D3 의미론의 bool 확장). 확정 설계는
[docs/decisions.md](docs/decisions.md) D6 참조. 핵심:

- bool 타입 도입(z3.Bool, 도메인 제약 없음) + 불리언 리터럴 허용.
- 자유 bool의 True/False 각 상태 도달성을 **변수별로** 검사(D4 일관, 데카르트 곱 회피).
- 무조건 강제로 고정된 bool은 종속으로 제외(D5 일관, 거짓양성 회피).
- 네 번째 모순 유형 "상태 봉쇄" + examples/stealth_combat.rule.

### ✅ 완료: 비율/확률 (LRA, 실수 제약) — D7 (2026-06-16)

`prob: {type: real}` + `합 == 1.0` 류를 정수 스케일링 우회 없이 직접 표현한다.
확정 설계는 [docs/decisions.md](docs/decisions.md) D7 참조. 핵심:

- real 타입(z3.Real) + 실수 리터럴 + **상수 분모 나눗셈**(`1/3` → 정확한 유리수).
- 범위는 **피저빌리티만**(사용자 결정) — real은 reachability 선택자에 안 걸리고
  feasibility에만 참여. "확률 합=1" over-constraint를 잡음.
- Real 범위 도달성(선언 min/max gap)은 Optimize-on-real의 epsilon 문제로 후속 미룸.
- examples/drop_rates_real.rule로 정수 스케일링 없는 표현을 보임.

### ✅ 완료: enum 인코딩 고도화 (정수 → Z3 EnumSort) — D8 (2026-06-16)

정수 인코딩을 Z3 `EnumSort`로 교체해 타입 안전성을 얻고, **서로 다른 enum이 같은 값
이름**을 쓰는 1차 한계를 해소했다. 확정 설계는 [docs/decisions.md](docs/decisions.md) D8 참조. 핵심:

- enum→EnumSort(변수=Const, 값=sort 상수). 정수 순서/산술 우연 허용 제거(쓰는 곳 없음).
- 중복 값 disambiguation = **문맥 기반**(사용자 결정): `role == warrior`의 값을 비교 상대
  변수의 sort로 해석. 교차 enum 오용은 친절한 에러. sort 라벨은 프로세스 단위 유일.
- checks는 실질 변경 없음(enum_fix가 `const == const`). examples/day_night_cycle.rule.

### ✅ 완료: Real 범위 도달성 (끝점 feasibility) — D9 (2026-06-16)

D7이 미룬 조각. real 변수의 선언 min/max **끝점**이 룰 하에서 도달 가능한지 검사한다
(사용자 결정: **A-i 끝점 feasibility** — Optimize/epsilon 회피). 확정 설계는
[docs/decisions.md](docs/decisions.md) D9 참조. 핵심:

- `check()`에 real 끝점 검사(`var == 끝점` sat?) + 새 보고 타입 `BoundUnreachable`.
- 종속 real은 제외(D5 일관). 정확한 달성값은 비계산(정밀 gap은 후속 A-ii).
- prob_ok.rule을 진짜 정합으로 정정 + examples/crit_chance.rule.

## 2차 후보 (대기 — 우선순위·범위 미확정)

1차에서 의도적으로 미룬 것들. 실제 룰에서 병목이 되는 순서로 골라 진행한다.
각 항목은 착수 시 별도 설계 결정(D번호)과 테스트 코퍼스를 동반한다.

- **Real 범위 도달성 — 완전 Optimize(A-ii)**: 정확한 달성값·gap·접근(`<`) 구분. D9의 후속.
- **경계 검사 확장**: 종속 변수 정보성 리포트 / 선언 도메인과 별개의 기획 의도 상한.
- **CI 통합**: PR마다 자동 실행 + 모순을 PR 코멘트로 리포트.
- **명시적 도달성 단언(`expect:`)**: 기획자가 "이 상태는 도달 가능해야 한다"를
  직접 선언(D3에서 1차 비목표로 보류).

## 남은 열린 질문 (검증 필요)

- **unsat core 정밀도**: Optimize로 gap을 찾은 뒤 경계값 재-assert로 범인 룰을
  뽑는 방식이 코어를 적정 크기로 잡는지 — 더 복잡한 룰셋 코퍼스로 확인.
- **종속 변수 휴리스틱**(D5): `then`의 단일 등식으로 종속 변수를 판정하는 방식이
  `2*hp == ...` 같은 변형에서 오분류하지 않는지 — 코퍼스로 검증, 필요 시 정교화.

## 작업 규약 (유지)

- 각 단계는 작은 PR. TDD(Red→Green→Refactor), 단계마다 테스트 우선/동시.
- 게이트: `pytest` + `ruff check` + `ruff format` + `mypy`(strict) 통과.
- DSL 문법을 바꾸면 CLAUDE.md §4와 로더/번역기/문서를 함께 갱신.
- 비선형(NIA)으로 빠지는 룰은 우회(상수화·구간분할)를 제안하고 한계를 리포트에 명시.
