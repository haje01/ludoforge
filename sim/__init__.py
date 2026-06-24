"""확률 추정 백엔드 (Monte Carlo) — 주 정량 경로(decisions.md D19).

공유 IR의 guarded-command 전이 시스템(D12)을 *표집*으로 시뮬레이션해 승리 확률·기대 길이·
분포를 **추정**한다(증명 아님). PRISM(prob/)이 망라적 증명이라 상태 폭발에 막히는 고차원·
연속(real) 모델을 표집으로 다룬다. 무게중심은 추정이지만, 소형 모델에서 PRISM을 오라클로
교차검증한다(Phase 4).

구성(PLAN 4차 마일스톤):
- engine.py    전이 시스템 인터프리터·DTMC 게이트·1 run 표집 (Phase 1)
- aggregate.py 결합가능 집계(Welford·히스토그램·rule-of-three) (Phase 2)
- runner.py    multiprocessing 분배·SeedSequence (Phase 3)
- report.py    추정+신뢰구간 한국어 리포트("증명 아님" 라벨) (Phase 2)
"""
