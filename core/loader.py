"""로더: 룰 파일을 IR(RuleSet)로 변환하는 진입점.

표면 언어는 자체 문법 `.lf` 하나다(D21·D32) — 파싱은 `core/text_loader`가 한다.
초기 YAML(`.rule`) 프론트엔드는 D21로 디프리케이트를 거쳐 D32(도메인 축소)에서 제거됐다.
`.rule`/`.yaml`을 만나면 명확한 안내와 함께 거부한다(조용한 무시 금지, §2).

책임 경계: 이 모듈은 파일 IO·확장자 디스패치·디렉토리 병합만 담당한다. 구조적 파싱은
`core/text_loader`, 참조 무결성(미정의 심볼, 중복 id, 순환 의존)은 `core/schema`의 몫이다.
실패 시 어떤 파일/필드가 문제인지 명시한 LoaderError를 던진다(CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path

from core.ir import Check, Constraint, Expect, RuleSet, Transition, Variable


class LoaderError(Exception):
    """룰 파일 로딩 실패. 메시지에 문제 위치(파일/필드)를 담는다."""


def load_rules(path: str | Path) -> RuleSet:
    """경로를 로드한다. 파일이면 단일 RuleSet, 디렉토리면 모든 .lf를 병합한다.

    디렉토리 병합은 여러 기획자가 각자 파일에 쓴 룰을 함께 검사하기 위함이다
    (CLAUDE.md §1 — 파일 간 모순 탐지가 본 도구의 핵심 가치).
    """
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.lf"))
        if not files:
            raise LoaderError(f"디렉토리에 .lf 파일이 없습니다: {path}")
        return _merge([load_rule_file(f) for f in files])
    return load_rule_file(path)


def _merge(rulesets: list[RuleSet]) -> RuleSet:
    """여러 RuleSet을 병합한다. 변수는 이름으로 합치되 충돌(다른 선언)은 오류.

    전이 시스템(D12)도 병합한다: transitions/checks는 이어 붙이고, `init`은 전역
    초기 상태라 둘 이상의 파일이 선언하면 모호하므로 오류로 본다.
    """
    variables: dict[str, Variable] = {}
    constraints: list[Constraint] = []
    expects: list[Expect] = []
    transitions: list[Transition] = []
    checks: list[Check] = []
    init: str | None = None
    for rs in rulesets:
        for v in rs.variables:
            if v.name in variables and variables[v.name] != v:
                raise LoaderError(f"변수 '{v.name}'가 파일마다 다르게 선언되었습니다.")
            variables[v.name] = v
        constraints.extend(rs.constraints)
        expects.extend(rs.expects)
        transitions.extend(rs.transitions)
        checks.extend(rs.checks)
        if rs.init is not None:
            if init is not None:
                raise LoaderError("init(초기 상태)이 둘 이상의 파일에 선언되었습니다 (전역 1개).")
            init = rs.init
    return RuleSet(
        variables=tuple(variables.values()),
        constraints=tuple(constraints),
        expects=tuple(expects),
        init=init,
        transitions=tuple(transitions),
        checks=tuple(checks),
    )


def load_rule_file(path: str | Path) -> RuleSet:
    """단일 룰 파일(.lf)을 읽어 RuleSet으로 변환한다."""
    path = Path(path)
    if path.suffix in (".rule", ".yaml", ".yml"):
        raise LoaderError(
            f"YAML 룰 형식은 제거되었습니다(D32): {path} — 자체 문법(.lf)으로 작성하세요."
        )
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise LoaderError(f"룰 파일을 찾을 수 없습니다: {path}") from e

    from core.text_loader import TextLoaderError, parse_rule_text

    try:
        return parse_rule_text(text, source=path.name)  # 병합 시 범인 파일 추적(원칙4)
    except TextLoaderError as e:
        raise LoaderError(str(e)) from e
