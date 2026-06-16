# PLAN.md — RuleForge 작업 계획

> 진행 상태는 [PROGRESS.md](PROGRESS.md), 설계 결정의 "왜"는
> [docs/decisions.md](docs/decisions.md), 아키텍처 SSOT는 [CLAUDE.md](CLAUDE.md).
> 완료된 작업의 상세 이력은 git 커밋과 decisions.md에 있다.

---

## 1차 마일스톤 — ✅ 완료 (2026-06-16)

수직 슬라이스 완성: `ruleforge check <path>`로 로드 → 스키마·참조 검증 →
Z3 번역 → Optimize 도달성 검사 → 한국어 리포트가 end-to-end로 동작한다.
LIA 수치 공식 + 조건부(`when`) 룰 + enum을 지원하고, 세 가지 모순 유형
(범위 봉쇄 / enum 도달 불가 / 전역 over-constraint)을 unsat core로 짚는다.

확정된 설계 결정은 [docs/decisions.md](docs/decisions.md)의 D1~D5 참조.

---

## 2차 마일스톤 — ✅ 완료 (2026-06-16)

표현력과 검사 범위를 확장했다. 확정 설계는 decisions.md D6~D10, 상세 이력은 git 커밋 참조.

- **불리언 상태 / 상호 배제 (D6)**: `type: bool` + `not (a and b)`. 자유 bool의
  True/False 도달성 검사 → "상태 봉쇄" 모순.
- **비율/확률 LRA (D7)**: `type: real` + 상수 분모 나눗셈(`1/3`=정확한 유리수).
  feasibility 참여로 "확률 합=1" over-constraint 탐지.
- **enum EnumSort 고도화 (D8)**: 정수 인코딩→EnumSort. 서로 다른 enum이 같은 값
  이름을 써도 안전(문맥 기반 disambiguation).
- **Real 끝점 도달성 (D9)**: real 선언 min/max 끝점 봉쇄 검사(A-i 끝점 feasibility).
- **명시적 도달성 단언 `expect:` (D10)**: 기획자가 조합 도달성을 직접 선언, `rules ∧
  that`가 unsat이면 미충족 모순.

탐지하는 모순 유형: 범위 봉쇄 / enum 도달 불가 / 전역 over-constraint / 상태 봉쇄 /
실수 끝점 봉쇄 / 도달성 단언 미충족. 예제는 [examples/](examples/README.md).

---

## 다음 후보 (대기 — 우선순위·범위 미확정)

착수 시 별도 설계 결정(D번호)과 테스트 코퍼스를 동반한다.

- **CI 통합** *(다음 재개 예정)*: PR마다 `ruleforge check` 자동 실행 + 모순을 PR
  코멘트로 리포트, 모순 시 fail.
- **Real 범위 도달성 — 완전 Optimize(A-ii)**: 정확한 달성값·gap·접근(`<`) 구분. D9의 후속.
- **경계 검사 확장**: 종속 변수 정보성 리포트 / 선언 도메인과 별개의 기획 의도 상한.

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
