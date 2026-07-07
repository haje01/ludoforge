"""웹 인터페이스(D32 P3): 산문/시트 → LLM 번역 → 사람 게이트 → bmc/sim.

판정은 항상 solver(원칙 1) — 이 패키지의 LLM은 번역과 오류 수리 루프만 담당한다.
시트→table 변환(sheet_import)은 LLM 없이 결정론적이다.
"""
