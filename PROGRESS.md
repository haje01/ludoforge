# PROGRESS.md — RuleForge 진행 상태

> 새 에이전트는 [PLAN.md](PLAN.md)와 이 파일을 먼저 읽고 작업을 이어간다.
> 각 단계 완료 시 상태와 날짜를 갱신한다.

## 현재 마일스톤: 1차 수직 슬라이스 — ✅ 전체 완료 (2026-06-16)

`ruleforge check <path>`로 로드→스키마→번역→Optimize 도달성 검사→한국어 리포트가
end-to-end로 동작. flagship warrior 모순을 정확히 탐지(level/max, 범인 2룰),
종속 변수 거짓양성 없음. 테스트 54건, ruff/format/mypy strict 통과.


| 단계 | 내용 | 상태 | 비고 |
|------|------|------|------|
| S0 | 프로젝트 셋업 (pyproject, uv, ruff, mypy) | ✅ 완료 | 게이트 통과, CLI 골격 동작 |
| S1 | IR 데이터클래스 (`dsl/ir.py`) | ✅ 완료 | frozen Variable/Rule/RuleSet, 테스트 6건 |
| S2 | 로더 (`dsl/loader.py`) | ✅ 완료 | .rule→IR, 구조 파싱만, LoaderError 명시 |
| S3 | 스키마·참조 검증 (`dsl/schema.py`) | ✅ 완료 | 중복id·구문·미정의심볼·min>max, 오류 모아 보고 |
| S4 | 표현식 번역기 (`solver/translator.py`) | ✅ 완료 | ast 화이트리스트→Z3, Implies, enum 정수인코딩 |
| S5 | 검사 로직 (`solver/checks.py`) | ✅ 완료 | Optimize 도달성, 독립변수만, unsat_core 범인추출, unknown 별도보고 |
| S6 | 리포터 (`solver/report.py`) | ✅ 완료 | 한국어, 모순/도달불가/unknown 표시, 순수함수 |
| S7 | CLI (`cli.py`) | ✅ 완료 | check 파이프라인, 디렉토리 병합, 종료코드 0/1/2/3 |
| S8 | 테스트 코퍼스 (`tests/fixtures/`) | ✅ 완료 | consistent/contradiction 코퍼스, D5 거짓양성 회귀 잠금 |

상태 범례: ⬜ 대기 / 🔵 진행중 / ✅ 완료 / ⚠️ 막힘

## 작업 로그
- 2026-06-16: deep-interview로 1차 설계 결정 확정(D1~D4), PLAN.md/PROGRESS.md 작성.
- 2026-06-16: S0 완료 — pyproject.toml(uv, z3/pyyaml/typer, ruff/mypy strict), 패키지 골격(dsl/solver/cli), 스모크 테스트 3건, `ruleforge check` CLI 골격. pytest/ruff/mypy 모두 통과.
- 2026-06-16: S1 완료 — IR(frozen Variable/Rule/RuleSet, `RuleSet.variable()` 조회). TDD(Red→Green), 테스트 6건. 전체 게이트 통과.
- 2026-06-16: S2 완료 — 로더(.rule YAML→IR). 구조 파싱만 담당(참조 무결성은 S3), 실패 시 파일/필드 명시 LoaderError. 픽스처 warrior_hp.rule, 테스트 6건. 전체 게이트 통과.
- 2026-06-16: S3 완료 — 스키마·참조 검증. 중복 rule id, 표현식 구문오류, 미정의 심볼 참조(ast Name 추출), int min>max 검사. 모든 오류를 모아 SchemaError로 보고. 순환의존은 현 DSL상 비해당. 테스트 7건. 전체 게이트 통과.
- 2026-06-16: S4 완료 — 번역기(IR→Z3). ast 화이트리스트(BoolOp/UnaryOp/BinOp +−×/Compare 6종/Name/정수상수)→Z3 매핑, 연쇄비교 And 지원, when→Implies, enum 0..n-1 정수인코딩. 허용 외 노드는 룰id 명시 TranslationError. Translation(z3_vars/domain_constraints/rule_constraints/enum_encoding) 반환. 테스트 8건(Z3 의미론 검증 포함). 전체 게이트 통과.
- 2026-06-16: S5 결정 — 도달성 검사는 '독립 변수만' 대상(종속 변수 hp=0 같은 거짓양성 회피). 사용자 확인.
- 2026-06-16: S5 완료 — 검사 로직(D3/D4). enum 값 조합 고정 × 독립 변수의 선언 경계를 Optimize로 도달성 확인, 봉쇄 시 경계값 assert_and_track→unsat_core로 범인 룰 추출. enum 조합 자체 실행불가도 보고. unknown은 별도 보고. CheckReport(violations/unreachable_enums/unknowns). 테스트 4건(flagship warrior 모순=level/max/범인2룰, 정합셋, unreachable enum, unknown없음). 전체 게이트 통과.
- 2026-06-16: S6 완료 — 리포터(CheckReport→한국어 문자열, 순수함수). 모순 건수·enum조건·달성vs선언·범인룰 제시, unreachable enum 표시, unknown은 ⚠️ 별도 섹션으로 노출. 출력(IO)은 S7 CLI로 분리. 테스트 5건. flagship 리포트 육안 확인. 전체 게이트 통과.
- 2026-06-16: S7 완료 — CLI 통합. `ruleforge check <path>`로 로드→스키마→번역→검사→리포트. loader.load_rules로 단일파일/디렉토리 모두 지원, 디렉토리는 .rule 병합(변수 충돌 오류, 파일 간 모순 탐지). 종료코드 0=정합/1=모순/2=오류/3=unknown. 실제 엔트리포인트 동작 확인. 테스트 5건(단일/디렉토리병합/스키마오류/없는경로). 전체 게이트 통과.
- 2026-06-16: 후속 개선 — 협업 패턴(공유 _domain.rule + 기획자별 rules-only 파일)이 디렉토리 병합으로 이미 지원됨을 확인·README 문서화(별도 import 구문 불필요, YAGNI). rules-only 파일 단독 검사 시 디렉토리 검사를 안내하는 친절한 SchemaError 가드 추가. 테스트 2건(schema/cli). 전체 게이트 통과.
- 2026-06-16: S8 완료 — 테스트 코퍼스(CLAUDE.md §8). fixtures/consistent(2건)·contradiction(3건: range violation/unreachable enum/전역 over-constraint) 코퍼스를 parametrize로 검증, 빈 코퍼스 함정 방지 테스트, 범인 룰 정밀도 잠금. D5 거짓양성(종속변수 hp) 영구 회귀 테스트 고정. 테스트 10건. **1차 마일스톤 전체 완료**(총 54건 통과).
