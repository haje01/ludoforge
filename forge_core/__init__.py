"""forge-core: 공유 DSL 프론트엔드(SSOT).

룰 파일 로딩, 중간표현(IR), 스키마·참조 검증을 담는다. RuleForge(Z3 백엔드)와
향후 ProbForge(PRISM 백엔드)가 **같은 IR을 소비**한다(decisions.md D11). 백엔드별
번역·검사 로직은 여기 두지 않는다 — 프론트엔드만.
"""
