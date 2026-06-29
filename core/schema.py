"""스키마·참조 검증(S3): 로더 통과 후 Z3 이전의 게이트.

검사하는 것(CLAUDE.md §3.3 — 형식/참조 무결성):
- 중복 id (constraint / expect / transition / check)
- 표현식 구문 오류(파싱 불가)
- 미정의 심볼 참조(선언 안 된 변수명 / enum 값 오타)
- `next.<var>` 참조 무결성(D12): 전이 then에서만 허용, 그 외 위치는 오류
- int 변수의 min > max
- constraint 등식으로 핀되는 파생 상수를 transition 효과가 갱신하지 않을 것
  (bmc는 매 스텝 불변식·sim은 init 파생만 → 갱신 시 두 백엔드 의미가 갈라짐)

여기서 실패하면 Z3 단계로 넘어가지 않는다. 모든 문제를 모아 SchemaError로 보고한다.
유한 상태(확률 백엔드(PRISM) 전제, D13) 검사는 backend-agnostic `validate()`와 분리된
별도 게이트 `check_finite_state()`에 둔다 — 논리 백엔드(Z3)는 무한 정수를 허용하므로.

참고: '순환 의존'은 현 DSL에선 룰·변수가 서로를 참조하지 않아 해당 없음.
파생 변수나 룰 간 참조가 도입되면 그때 검사를 추가한다.

표현식의 '미정의 심볼' 검사를 위해 ast로 식별자(Name)만 추출한다. 허용 노드
화이트리스트 강제와 Z3 매핑은 번역기(S4)의 책임이며 여기서는 하지 않는다.
"""

from __future__ import annotations

import ast

from core.ir import RuleSet

# 표현식에서 허용하는 함수 호출(번역기·sim·PRISM과 동일). 포화/클램프용이며 **효과
# (then/outcomes)에서만** 허용한다 — 술어(when·init·constraint·check·expect)에서 쓰면 거부.
_ALLOWED_FUNCS = frozenset({"min", "max"})


class SchemaError(Exception):
    """스키마·참조 검증 실패. 메시지에 발견된 모든 문제를 담는다."""


def validate(ruleset: RuleSet) -> None:
    """룰셋의 참조 무결성을 검사한다. 문제가 있으면 SchemaError를 던진다."""
    # 제약은 있는데 domain 변수가 전혀 없으면, constraints-only 파일을 단독 검사한 경우가
    # 대부분이다. 미정의 심볼 에러를 쏟아내는 대신 디렉토리 검사를 안내한다.
    if ruleset.constraints and not ruleset.variables:
        raise SchemaError(
            f"제약 {len(ruleset.constraints)}개가 있지만 domain 변수 선언이 없습니다.\n"
            "이 파일이 constraints만 담고 있다면, 공유 domain 파일이 함께 있는 "
            "디렉토리를 검사하세요 (예: ludoforge check <폴더>)."
        )

    errors: list[str] = []
    errors.extend(_check_variable_bounds(ruleset))
    errors.extend(_check_duplicate_constraint_ids(ruleset))
    errors.extend(_check_duplicate_expect_ids(ruleset))
    errors.extend(_check_duplicate_ids("transition", [t.id for t in ruleset.transitions]))
    errors.extend(_check_duplicate_ids("check", [c.id for c in ruleset.checks]))
    errors.extend(_check_transition_prefs(ruleset))
    errors.extend(_check_constraint_pinned_not_mutated(ruleset))
    errors.extend(_check_references(ruleset))

    if errors:
        raise SchemaError("스키마 검증 실패:\n" + "\n".join(f"- {e}" for e in errors))


def check_finite_state(ruleset: RuleSet) -> None:
    """확률(PRISM) 백엔드 전제(D13): 모든 int 변수에 유한 min·max가 있어야 한다.

    PRISM은 상태공간을 빌드하므로 경계 없는 변수를 다룰 수 없다. bool/enum은 본디
    유한하고, real은 이산화가 필요해 현 단계 확률 백엔드 범위 밖이다. 위반 시 SchemaError로
    친절히 안내한다.

    backend-agnostic `validate()`와 **분리된 별도 게이트**다 — 논리 백엔드(Z3)는 무한 정수를
    허용하므로 이 검사를 적용하지 않는다. 확률 백엔드(Phase 4)가 번역 전에 호출한다.
    """
    errors: list[str] = []
    for v in ruleset.variables:
        if v.type == "int" and (v.min is None or v.max is None):
            errors.append(
                f"변수 '{v.name}'(int): 유한 상태에는 min·max가 모두 필요합니다 "
                f"(현재 min={v.min}, max={v.max})."
            )
        elif v.type == "real":
            errors.append(
                f"변수 '{v.name}'(real): 확률 백엔드는 실수 변수를 "
                f"직접 다루지 못합니다(이산화 필요)."
            )
    if errors:
        raise SchemaError(
            "확률 백엔드(유한 상태) 검증 실패:\n" + "\n".join(f"- {e}" for e in errors)
        )


def _check_transition_prefs(ruleset: RuleSet) -> list[str]:
    """전이 선호도(pref, D20)는 음수일 수 없다 — IR 직접 구성 시의 방어적 검증.

    로더는 파싱 시 이미 거부하나, IR을 코드로 만들면 우회되므로 여기서도 막는다.
    """
    return [
        f"전이 '{t.id}': pref는 음수일 수 없습니다 (현재 {t.pref})"
        for t in ruleset.transitions
        if t.pref is not None and t.pref < 0
    ]


def _check_constraint_pinned_not_mutated(ruleset: RuleSet) -> list[str]:
    """constraint 등식(`then var == 값`)으로 핀되는 변수는 transition 효과로 갱신할 수 없다.

    그런 변수는 '모든 상태에서 그 값'인 파생 상수다(예: 던전!의 win_gold = role의 함수).
    bmc는 이 constraint를 **매 스텝 불변식**으로 강제하지만 sim은 **init 파생에만** 쓴다(D11
    dialect 분리). 따라서 transition이 핀 변수를 갱신하면 두 백엔드 의미가 갈라진다 — bmc는
    갱신된 후속 상태를 불변식 위반으로 UNSAT 가지치기(전이 발화 불가·데드락 오탐), sim은
    멀쩡히 변경(판별 기준선이 게임 중 이동). 이 조용한 불일치를 정적으로 크게 거부한다.

    좁게만 막는다: `<=`/`>=` 류 관계형 불변식은 변수를 특정 값으로 핀하지 않으므로
    (=핀 대상이 아님) 갱신과 공존해도 무방하다. 등식 핀만 충돌한다.
    """
    var_names = {v.name for v in ruleset.variables}
    pinned = _constraint_pinned_targets(ruleset, var_names)
    if not pinned:
        return []
    errors: list[str] = []
    for t in ruleset.transitions:
        for oc in t.outcomes:
            for var in sorted(_effect_targets(oc.then) & pinned):
                errors.append(
                    f"변수 '{var}'은(는) constraint 등식으로 파생되는 상수인데 전이 '{t.id}'의 "
                    f"효과가 이를 갱신합니다 — 파생 상수는 transition에서 바꿀 수 없습니다"
                    f"(bmc는 불변식 위반으로 가지치기, sim은 갱신 → 의미 불일치)."
                )
    return errors


def _constraint_pinned_targets(ruleset: RuleSet, var_names: set[str]) -> set[str]:
    """constraints의 then 등식 `var == 값`에서 값이 핀되는 변수명 집합.

    sim.engine._constraint_targets와 동형(같은 좁은 정의) — core가 sim에 의존하지 않도록
    여기서 재구현한다. `var == 값`(또는 그 and 결합)의 변수만 잡고 관계형 비교는 제외한다.
    """
    targets: set[str] = set()
    for con in ruleset.constraints:
        if con.then is None:
            continue
        try:
            tree = ast.parse(con.then, mode="eval").body
        except SyntaxError:
            continue  # 구문 오류는 _check_references가 보고
        for conj in _conjuncts(tree):
            target = _eq_var_target(conj, var_names)
            if target is not None:
                targets.add(target)
    return targets


def _effect_targets(then: str) -> set[str]:
    """전이 효과 then(`next.X == 식`의 and 결합)에서 갱신되는 변수명 X 집합."""
    try:
        tree = ast.parse(then, mode="eval").body
    except SyntaxError:
        return set()  # 구문 오류는 _check_references가 보고
    targets: set[str] = set()
    for conj in _conjuncts(tree):
        pair = _eq_pair(conj)
        if pair is None:
            continue
        for side in pair:
            if (
                isinstance(side, ast.Attribute)
                and isinstance(side.value, ast.Name)
                and side.value.id == "next"
            ):
                targets.add(side.attr)
    return targets


def _conjuncts(node: ast.expr) -> list[ast.expr]:
    """and 결합을 펼쳐 conjunct 목록으로. and가 아니면 단일 원소."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return list(node.values)
    return [node]


def _eq_pair(node: ast.expr) -> tuple[ast.expr, ast.expr] | None:
    """단일 `a == b` 비교면 (a, b)를, 아니면 None."""
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        return node.left, node.comparators[0]
    return None


def _eq_var_target(node: ast.expr, var_names: set[str]) -> str | None:
    """`var == 값` 등식에서 한 변이 선언된 변수명이면 그 이름, 아니면 None."""
    pair = _eq_pair(node)
    if pair is None:
        return None
    left, right = pair
    if isinstance(left, ast.Name) and left.id in var_names:
        return left.id
    if isinstance(right, ast.Name) and right.id in var_names:
        return right.id
    return None


def _check_variable_bounds(ruleset: RuleSet) -> list[str]:
    errors: list[str] = []
    for v in ruleset.variables:
        if v.type in ("int", "real") and v.min is not None and v.max is not None and v.min > v.max:
            errors.append(f"변수 '{v.name}': min({v.min}) > max({v.max})")
    return errors


def _check_duplicate_constraint_ids(ruleset: RuleSet) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for c in ruleset.constraints:
        if c.id in seen and c.id not in dups:
            dups.append(c.id)
        seen.add(c.id)
    return [f"중복된 constraint id: '{d}'" for d in dups]


def _check_duplicate_expect_ids(ruleset: RuleSet) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for e in ruleset.expects:
        if e.id in seen and e.id not in dups:
            dups.append(e.id)
        seen.add(e.id)
    return [f"중복된 expect id: '{d}'" for d in dups]


def _check_duplicate_ids(kind: str, ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for i in ids:
        if i in seen and i not in dups:
            dups.append(i)
        seen.add(i)
    return [f"중복된 {kind} id: '{d}'" for d in dups]


def _check_references(ruleset: RuleSet) -> list[str]:
    """표현식이 참조하는 심볼이 모두 정의돼 있는지 검사한다(제약·expect·전이 시스템 전부).

    유효 심볼 = 선언된 변수명 ∪ 모든 enum 값. (enum 값이 어느 변수 소속인지까지는
    여기서 따지지 않는다 — 오타 탐지가 목적. 교차 enum 오용은 번역기가 잡는다, D8.)
    전이 then은 `next.<var>`로 다음 상태를 참조할 수 있다(D12) — 그 외 위치에서 next.*를
    쓰면 오류로 본다. prob 검사의 spec은 PCTL이라 여기서 구문 검사하지 않는다(D11).
    """
    known_vars: set[str] = {v.name for v in ruleset.variables}
    known: set[str] = set(known_vars)
    for v in ruleset.variables:
        known.update(v.values)

    errors: list[str] = []
    for constraint in ruleset.constraints:
        for clause, expr in (("when", constraint.when), ("then", constraint.then)):
            if expr is None:
                continue
            errors.extend(
                _check_expr_references(f"제약 '{constraint.id}'", clause, expr, known, known_vars)
            )
    for expect in ruleset.expects:
        errors.extend(
            _check_expr_references(f"기대 '{expect.id}'", "that", expect.that, known, known_vars)
        )
    if ruleset.init is not None:
        errors.extend(_check_expr_references("init", "init", ruleset.init, known, known_vars))
    for t in ruleset.transitions:
        if t.when is not None:
            errors.extend(
                _check_expr_references(f"전이 '{t.id}'", "when", t.when, known, known_vars)
            )
        for i, oc in enumerate(t.outcomes):
            label = "then" if len(t.outcomes) == 1 else f"outcomes[{i}].then"
            errors.extend(
                _check_expr_references(
                    f"전이 '{t.id}'",
                    label,
                    oc.then,
                    known,
                    known_vars,
                    allow_next=True,
                    allow_funcs=True,  # 효과 RHS에서만 min/max(포화) 허용
                )
            )
    for c in ruleset.checks:
        if c.kind in ("reachable", "invariant") and c.that is not None:
            errors.extend(
                _check_expr_references(f"검사 '{c.id}'", "that", c.that, known, known_vars)
            )
        if c.kind == "distribution" and c.expr is not None:
            # distribution expr은 현재 상태 수치식(sim 전용, D19) — next.*는 불가.
            errors.extend(
                _check_expr_references(f"검사 '{c.id}'", "expr", c.expr, known, known_vars)
            )
    return errors


def _check_expr_references(
    subject: str,
    clause: str,
    expr: str,
    known: set[str],
    known_vars: set[str],
    allow_next: bool = False,
    allow_funcs: bool = False,
) -> list[str]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return [f"{subject}의 {clause} 표현식 구문 오류: {expr!r} ({e.msg})"]

    errors: list[str] = []
    # `next.<var>`(다음 상태 참조)를 식별한다. 그 `next` Name 노드는 일반 심볼 검사에서
    # 제외한다(변수가 아니라 다음 상태 표지이므로).
    next_markers: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == "next":
            next_markers.add(id(node.value))
            if not allow_next:
                errors.append(
                    f"{subject}의 {clause}에서 next.*는 전이 then에서만 쓸 수 있습니다: "
                    f"'next.{node.attr}'"
                )
            elif node.attr not in known_vars:
                errors.append(
                    f"{subject}의 {clause}가 미정의 변수의 다음 상태를 참조: 'next.{node.attr}'"
                )
        else:
            errors.append(f"{subject}의 {clause}에 허용되지 않는 속성 접근: '{ast.unparse(node)}'")

    # 함수 호출: min/max만, 효과(allow_funcs)에서만, 위치 인자 2개 이상. 그 외는 거부한다.
    # 허용 함수의 func Name 노드는 심볼 검사에서 제외한다(변수가 아니라 함수명이므로).
    func_markers: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            func_markers.add(id(func))  # 함수명은 변수 아님 — 심볼 검사에서 제외(중복 보고 방지)
        if isinstance(func, ast.Name) and func.id in _ALLOWED_FUNCS:
            if not allow_funcs:
                errors.append(
                    f"{subject}의 {clause}에서 {func.id}()는 효과(then/outcomes)에서만 "
                    f"쓸 수 있습니다(포화/클램프 전용)"
                )
            elif node.keywords or len(node.args) < 2:
                errors.append(
                    f"{subject}의 {clause}의 '{func.id}'은(는) 위치 인자 2개 이상이어야 합니다: "
                    f"'{ast.unparse(node)}'"
                )
        else:
            errors.append(
                f"{subject}의 {clause}에 허용되지 않는 함수 호출: '{ast.unparse(node)}' "
                f"(허용: {', '.join(sorted(_ALLOWED_FUNCS))})"
            )

    skip = next_markers | func_markers
    for name in sorted(
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in skip}
    ):
        if name not in known:
            errors.append(f"{subject}의 {clause}가 미정의 심볼을 참조: '{name}'")
    return errors
