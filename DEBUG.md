# DEBUG.md

## 2026-07-07 — 웹 번역 수리 루프 3회 전패 (구문 오류: check kind 자리 COLON)

**증상:** 산문 "전사 최대 HP는 레벨당 100 / HP 상한 1000 / 레벨 상한 100 / 전사는 레벨
100까지 성장 가능해야" 입력 시 번역이 3회 모두 게이트 실패. 오류:
`구문 오류 (line 19 col 23): Unexpected token COLON ... Expected: REACHABLE/INVARIANT/...`
(kind 키워드 자리에서 `:`) — 수리 루프가 같은 실수를 반복해 소진.

**재현:** `check hp_ok: hp <= 1000` (kind 누락)이 동일 오류를 냄 — LLM이 expect처럼
`check <id>: <pred>`를 쓴 것. 재현 스크립트로 확인(2026-07-07).

**가정과 증거:**
1. (H1) 시스템 프롬프트의 check 예시가 "kind 필수"를 명시하지 않고 dynamics 절에만
   있어, 정적 모델에서 도달성 의도를 check로 쓰며 kind를 빠뜨림.
   증거: 오류 위치가 정확히 kind 자리(COLON), Expected 목록이 kind 키워드들.
2. (H2) 정적 모델(전이 없음)의 "가능해야 한다" 의도는 expect(D10)가 맞는 구문인데
   프롬프트가 static→expect / dynamic→check 구분을 강제하지 않음.
   증거: 산문이 순수 정적(공식+상한+도달 의도)인데 check를 시도함.
3. (H3) 수리 프롬프트가 오류의 줄/열만 주고 해당 소스 줄을 인용하지 않아, 모델이
   자신의 어느 줄이 문제인지 놓치고 같은 형태를 반복.
   증거: 3회 모두 같은 부류의 구문 오류로 실패(오류 메시지 동일 패턴).

**실험 1 (H1+H2):** 시스템 프롬프트에 ① `check <id> <kind>: <pred>`에서 kind 필수 명시,
② "정적 모델(전이 없음)에서는 check 금지, expect 사용" 규칙 추가. → 적용.
**실험 2 (H3):** 수리 프롬프트에 오류가 짚는 줄의 원문을 인용해 되먹임. → 적용.

**결과:** 실험 1+2 적용(2026-07-07). 회귀 테스트로 고정:
`test_repair_prompt_quotes_offending_line`(문제 줄 인용 되먹임)·
`test_system_prompt_teaches_check_kind_and_static_expect`(프롬프트 계약).
같은 산문 재입력으로 실사용 재검증 완료(2026-07-07, 사용자 확인) — **해결.**
