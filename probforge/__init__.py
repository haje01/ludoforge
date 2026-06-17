"""ProbForge: 확률 증명 백엔드(PRISM). 공유 forge_core IR을 소비한다(D11).

RuleForge(Z3/BMC, 논리 증명)와 대칭인 두 번째 백엔드다. IR(가중치 보존)을 PRISM
guarded-command 모델로 번역하고(D16), PRISM으로 PCTL 속성을 검사한다. 유한 상태가
전제이며(check_finite_state, D13), 모델 타입은 mdp.

번역(prism_gen) ↔ 실행(runner)을 분리한다 — 번역은 PRISM 없이도 검증 가능하고, 실행은
`prism` 바이너리가 있을 때만 동작한다(graceful).
"""
