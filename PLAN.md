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

## 2차 후보 (대기 — 우선순위·범위 미확정)

1차에서 의도적으로 미룬 것들. 실제 룰에서 병목이 되는 순서로 골라 진행한다.
각 항목은 착수 시 별도 설계 결정(D번호)과 테스트 코퍼스를 동반한다.

- **비율/확률 (LRA)**: 실수 제약(확률 합 = 1 등). 현재는 정수 스케일링으로 우회 중.
- **경계 검사 확장**: Optimize로 이론적 최대/최소 vs 기획 의도 상한을 더 폭넓게.
- **CI 통합**: PR마다 자동 실행 + 모순을 PR 코멘트로 리포트.
- **enum 인코딩 고도화**: 정수 인코딩 → Z3 `Datatype`. 서로 다른 enum이 같은 값
  이름을 쓰는 경우 지원(현재 1차 한계).
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
