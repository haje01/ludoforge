"""ghost 서술 변수 제거(D31) — 순수 IR→IR 변환.

ghost 변수는 서술 전용이다(단방향 의존 — schema `_check_ghost_one_way`가 강제): 비-ghost
궤적에 영향을 줄 수 없으므로, 지워도 나머지 의미가 비트 동일하게 보존된다. **bmc·PRISM
오라클은 소비 전에 이 변환을 거쳐** 상태공간에서 ghost를 완전히 제거하고(증명 지위 불변),
**sim은 원본을 실행**해 ghost 분포를 추정한다(D11 dialect 분리의 연장).

함수형 코어(§7): 입력 RuleSet을 바꾸지 않고 새 RuleSet을 돌려준다.
"""

from __future__ import annotations

import ast
from dataclasses import replace

from core.ir import RuleSet


def erase_ghosts(ruleset: RuleSet) -> RuleSet:
    """ghost 변수 선언·ghost 대입·init의 ghost conjunct를 제거한 RuleSet을 돌려준다.

    ghost가 없으면 입력을 그대로 돌려준다(무비용 경로). 효과의 모든 대입이 ghost였다면
    `True`로 남긴다 — 프레임(D15)이 모든 변수를 유지하는 자기 분기(분기 구조 보존)."""
    ghosts = frozenset(v.name for v in ruleset.variables if v.ghost)
    if not ghosts:
        return ruleset
    transitions = tuple(
        replace(
            t,
            outcomes=tuple(replace(oc, then=_strip_effect(oc.then, ghosts)) for oc in t.outcomes),
        )
        for t in ruleset.transitions
    )
    return replace(
        ruleset,
        variables=tuple(v for v in ruleset.variables if not v.ghost),
        init=_strip_init(ruleset.init, ghosts),
        transitions=transitions,
    )


def ghost_names(ruleset: RuleSet) -> tuple[str, ...]:
    """선언 순서대로의 ghost 변수 이름 — 리포트 각주용(제거를 조용히 숨기지 않는다)."""
    return tuple(v.name for v in ruleset.variables if v.ghost)


def _strip_effect(then: str, ghosts: frozenset[str]) -> str:
    """효과(`next.X == 식`의 and 결합)에서 ghost 대입 conjunct를 제거한다."""
    try:
        tree = ast.parse(then, mode="eval").body
    except SyntaxError:
        return then  # 구문 오류는 schema가 이미 보고 — 여기선 통과(방어)
    kept = [conj for conj in _conjuncts(tree) if _assign_target(conj) not in ghosts]
    if len(kept) == len(_conjuncts(tree)):
        return then  # 변화 없음 — 원문 보존
    if not kept:
        return "True"
    return " and ".join(ast.unparse(c) for c in kept)


def _strip_init(init: str | None, ghosts: frozenset[str]) -> str | None:
    """init 술어에서 ghost를 참조하는 conjunct(상수 고정 — schema가 보장)를 제거한다."""
    if init is None:
        return None
    try:
        tree = ast.parse(init, mode="eval").body
    except SyntaxError:
        return init
    kept = [c for c in _conjuncts(tree) if not _refs_ghost(c, ghosts)]
    if len(kept) == len(_conjuncts(tree)):
        return init
    if not kept:
        return None
    return " and ".join(ast.unparse(c) for c in kept)


def _conjuncts(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return list(node.values)
    return [node]


def _assign_target(conj: ast.expr) -> str | None:
    """conjunct가 `next.X == 식` 대입이면 X, 아니면 None."""
    if not (
        isinstance(conj, ast.Compare) and len(conj.ops) == 1 and isinstance(conj.ops[0], ast.Eq)
    ):
        return None
    for side in (conj.left, conj.comparators[0]):
        if (
            isinstance(side, ast.Attribute)
            and isinstance(side.value, ast.Name)
            and side.value.id == "next"
        ):
            return side.attr
    return None


def _refs_ghost(conj: ast.expr, ghosts: frozenset[str]) -> bool:
    return any(isinstance(n, ast.Name) and n.id in ghosts for n in ast.walk(conj))
