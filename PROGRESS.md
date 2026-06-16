# PROGRESS.md — RuleForge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.

## 1차 마일스톤 (수직 슬라이스) — ✅ 완료 (2026-06-16)

`ruleforge check <path>` 파이프라인 end-to-end 동작. LIA 수치 공식 + 조건부 룰 +
enum 지원, 세 가지 모순 유형 탐지(범위 봉쇄/enum 도달 불가/전역 over-constraint).
테스트 61건, ruff/format/mypy(strict) 통과.

상세 이력은 git 커밋(S0~S8)과 [docs/decisions.md](docs/decisions.md)(D1~D5) 참조.

## 2차 — 불리언 상태 변수 (상호 배제, D6) — ✅ 완료

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| B1~B4 | bool 타입 + 자유 bool 도달성 + 문서 | ✅ | 69건, 커밋 a80efba |

## 2차 — 비율/확률 (LRA, D7) — ✅ 완료

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| R1~R3 | real 타입 + feasibility + 문서 | ✅ | 79건, 커밋 63a0f88 |

## 2차 — enum 인코딩 고도화 (EnumSort, D8) — ✅ 완료

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| E1~E3 | enum→EnumSort + 문맥 해석 + 문서 | ✅ | 84건, 커밋 27a645a |

## 2차 — Real 범위 도달성 (끝점 feasibility, D9) — ✅ 완료

깊이(사용자 결정): **A-i 끝점 feasibility**(Optimize/epsilon 회피). 근거는 [PLAN.md](PLAN.md)
및 decisions.md D9 참조.

| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| F1 | (행위) check()에 real 끝점 검사 + BoundUnreachable + report | ✅ | 종속 real 제외(D5), 88건 |
| F2 | (행위/코퍼스) 끝점 봉쇄 모순/정합 코퍼스 + prob_ok 정정 | ✅ | 90건 |
| F3 | (문서) decisions.md D9, CLAUDE.md §4, examples, README | ✅ | |

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

다음 후보는 [PLAN.md](PLAN.md) "2차 후보" 참조(Real 완전 Optimize A-ii/경계 검사 확장/expect: 등).

## 작업 로그
- 2026-06-16: 1차 마일스톤 완료(S0~S8). 이후 협업 패턴 문서화, 기획 모순 예제 모음
  (examples/), 예제를 examples/로 일원화. PLAN/PROGRESS를 2차용으로 이월 정리.
- 2026-06-16: 2차 D6(불리언 상태 변수/상호 배제) 완료. bool 타입 도입(ir/loader/translator),
  자유 bool의 True/False 도달성 검사(checks.py, D4 일관 per-bool, 종속 bool 제외).
  네 번째 모순 유형 "상태 봉쇄" 추가. 코퍼스 픽스처 2개 + examples/stealth_combat.rule.
  테스트 69건, ruff/format/mypy(strict) 통과. (커밋 a80efba)
- 2026-06-16: 2차 D7(비율/확률 LRA) 완료. real 타입 도입(z3.Real, 실수 리터럴, 상수 분모
  나눗셈=정확한 유리수). 범위는 피저빌리티만 — real은 reachability 선택자에 안 걸리고
  feasibility에만 참여(범위 도달성은 후속). 실수 over-constraint 코퍼스 2개 +
  examples/drop_rates_real.rule. 테스트 78건, ruff/format/mypy(strict) 통과. (커밋 63a0f88)
- 2026-06-16: 2차 D8(enum EnumSort 고도화) 완료. 정수 인코딩→z3 EnumSort. 서로 다른 enum이
  같은 값 이름을 써도 안전(문맥 기반 disambiguation). 교차 enum 오용은 친절한 에러.
  sort 라벨 프로세스 단위 유일화로 translate 반복 호출 충돌 방지. 중복 값 코퍼스 2개 +
  examples/day_night_cycle.rule. 테스트 83건, ruff/format/mypy(strict) 통과. (커밋 27a645a)
- 2026-06-16: 2차 D9(Real 끝점 도달성) 완료. real 변수의 선언 min/max 끝점 도달성 검사
  (A-i 끝점 feasibility, Optimize/epsilon 회피). 새 보고 타입 BoundUnreachable. 종속 real
  제외(D5 일관). prob_ok.rule 정정 + examples/crit_chance.rule. 테스트 90건,
  ruff/format/mypy(strict) 통과.
