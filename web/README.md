# Ludoforge 웹 인터페이스 (D32)

기획자가 DSL을 배우지 않아도 되는 표면이다 — **산문/스프레드시트를 넣으면 AI가 검증
모델(`.lf`)로 번역**하고, 기획자는 생성된 **규칙서(산문)를 읽고 승인**한 뒤 실행한다.
판정은 항상 solver가 한다(원칙 1): LLM은 번역만, 모순 증명은 Z3, 분포 추정은 Monte Carlo.

## 실행

```bash
export ANTHROPIC_API_KEY=...   # 번역 기능에만 필요(검증·실행은 키 없이 동작)
ludoforge web                  # http://127.0.0.1:8321
ludoforge web --port 9000 --config configs/web.yaml
```

## 파이프라인

```
① 입력      산문 기획 + 시트(CSV — LLM 없이 table 절로 결정론 변환, sheet_import)
② 번역      LLM(Claude) → .lf 후보 → 로더·스키마 게이트 → 실패 오류를 되먹여 재시도
            (수리 루프, 상한 max_translate_attempts — translate.py)
③ 사람 게이트  생성 .lf(수정 가능)와 규칙서(docgen 미리보기)를 나란히 놓고 의도 확인
④ 실행      check(정적 모순 증명) / bmc(동역학 증명) / sim(분포 추정 — "증명 아님" 라벨)
            비동기 잡 + 폴링, 기존 자체 완결 HTML 리포트를 그대로 임베드
```

## 설정 (`configs/web.yaml`)

| 키 | 의미 | 기본 |
|----|------|------|
| `model` | 번역용 Claude 모델 | `claude-sonnet-5` |
| `max_translate_attempts` | 수리 루프 상한 | 3 |
| `bmc_k_max` | BMC 깊이 상한(요청 클램프) | 30 |
| `sim_samples_max` / `sim_horizon_max` | sim 표집/지평 상한 | 200000 / 10000 |
| `sim_workers` | sim 병렬 워커 | 1 |

`.lf`는 비-튜링완전이라 별도 샌드박스 없이 자원 상한 클램프만으로 서버 실행이 안전하다.

## 한계 (MVP)

- 잡은 인메모리(서버 재시작 시 소실) · 단일 사용자 전제 · 프로젝트/파일 관리 없음.
- LLM 번역의 "유효하지만 의도와 다른 형식화"는 기계가 못 잡는다 — 그래서 ③의 규칙서
  확인이 필수 단계이고, 번역 프롬프트가 `expect` 단언(D10)을 함께 생성하게 되어 있다.
