"""IR → PRISM 모델·속성 번역(D16). PRISM 없이도 검증 가능한 순수 텍스트 생성.

매핑(decisions.md D16):
- enum = `const int <값>=<idx>;` + 변수 `[0..n-1]`. 값 이름 전역 유일 강제.
- 정적 constraints + init = `init…endinit` 술어로 인코딩(프레임 불변 변수에 한해 건전).
- 전이 = guarded command. 가중치 정규화(합=1), bare then은 결정적 명령.
- outcome.then은 `next.X == 식`(And 결합) 배정형만 → PRISM 갱신 `(X'=식)`.
- 속성: reachable→`Pmax=? [F that]`, invariant→`Pmin=? [G that]`. (PCTL `prob`은 D23으로
  사용자 표면에서 제거 — PRISM은 테스트 오라클이라 reachable→Pmax로 충분.)

표현식은 ast로 파싱해 PRISM 식 문자열로 렌더한다(Python `and/or/not/==` → PRISM
`&/|/!/=`). enum 값은 위 const라 이름 그대로 쓴다.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from core.ghost import erase_ghosts
from core.ir import RuleSet, Transition, Variable
from core.schema import check_finite_state


class ProbError(Exception):
    """IR→PRISM 번역 실패(비배정 then, enum 값 충돌 등). 위치를 메시지에 담는다."""


@dataclass(frozen=True)
class PrismProperty:
    prop_id: str
    kind: str
    pctl: str
    desc: str | None


@dataclass(frozen=True)
class PrismProgram:
    model: str
    properties: tuple[PrismProperty, ...]


def generate(ruleset: RuleSet) -> PrismProgram:
    """검증된 RuleSet을 PRISM 모델·속성으로 번역한다(D16).

    ghost 서술 변수(D31)는 상태공간에서 제거하고 번역한다(erase 후 소비 — sim 전용 서술).
    유한 상태 게이트(D13)를 먼저 통과해야 한다 — 무한 int·real이면 SchemaError.
    """
    ruleset = erase_ghosts(ruleset)
    check_finite_state(ruleset)
    return PrismProgram(model=_model_text(ruleset), properties=_properties(ruleset))


# ---------- 모델 ----------


def _model_text(ruleset: RuleSet) -> str:
    lines: list[str] = ["mdp", ""]
    lines.extend(_enum_consts(ruleset))
    lines.append("module game")
    for v in ruleset.variables:
        lines.append("  " + _var_decl(v))
    lines.append("")
    for line in _commands(ruleset):
        lines.append("  " + line)
    lines.append("endmodule")

    init_block = _init_block(ruleset)
    if init_block:
        lines.append("")
        lines.extend(init_block)
    return "\n".join(lines) + "\n"


def _enum_consts(ruleset: RuleSet) -> list[str]:
    """enum 값을 전역 const int로 emit. 값 이름은 전역 유일해야 한다(D16)."""
    out: list[str] = []
    seen: dict[str, str] = {}
    for v in ruleset.variables:
        if v.type != "enum":
            continue
        for idx, val in enumerate(v.values):
            if val in seen:
                raise ProbError(
                    f"PRISM 백엔드는 enum 값 이름이 전역 유일해야 합니다: "
                    f"'{val}'가 '{seen[val]}'와 '{v.name}'에 중복됩니다."
                )
            seen[val] = v.name
            out.append(f"const int {val} = {idx};")
    if out:
        out.append("")
    return out


def _var_decl(v: Variable) -> str:
    if v.type == "int":
        # check_finite_state가 min·max 존재를 보장한다(D13).
        return f"{v.name} : [{int(v.min)}..{int(v.max)}];"  # type: ignore[arg-type]
    if v.type == "bool":
        return f"{v.name} : bool;"
    if v.type == "enum":
        return f"{v.name} : [0..{len(v.values) - 1}];"
    raise ProbError(f"PRISM 백엔드가 지원하지 않는 타입: '{v.name}'({v.type})")


def _commands(ruleset: RuleSet) -> list[str]:
    out: list[str] = []
    for t in ruleset.transitions:
        guard = _render(_parse(t.when)) if t.when is not None else "true"
        consts = _const_weights(t)
        if consts is not None and sum(consts) <= 0:
            raise ProbError(f"전이 '{t.id}'의 weight 합이 0입니다.")
        # guard와 _updates는 이미 필요한 괄호를 포함한다(이중 괄호 회피).
        if len(t.outcomes) == 1:
            out.append(f"[{t.id}] {guard} -> {_updates(t.outcomes[0].then)};")
        elif consts is not None:
            total = sum(consts)
            branches = " + ".join(
                f"{_prob(w, total)}:{_updates(oc.then)}"
                for oc, w in zip(t.outcomes, consts, strict=True)
            )
            out.append(f"[{t.id}] {guard} -> {branches};")
        else:
            # 상태 의존 weight(D26): 비율형 (w_i)/(Σw)로 렌더 — 상태마다 합=1이 구성적으로
            # 보장된다. 합0 상태는 가드가 배제해야 하며(D26 규율), 어기면 PRISM이 모델
            # 검사 시점에 well-formedness 오류로 크게 알린다(오라클의 이중 안전망).
            terms = [_weight_term(oc.weight) for oc in t.outcomes]
            total_expr = "(" + "+".join(terms) + ")"
            branches = " + ".join(
                f"({term})/{total_expr}:{_updates(oc.then)}"
                for term, oc in zip(terms, t.outcomes, strict=True)
            )
            out.append(f"[{t.id}] {guard} -> {branches};")
    return out


def _const_weights(t: Transition) -> list[float] | None:
    """모든 outcome weight가 상수면 float 목록, 하나라도 상태 식(D26)이면 None."""
    weights: list[float] = []
    for oc in t.outcomes:
        if isinstance(oc.weight, str):
            return None
        weights.append(float(oc.weight))
    return weights


def _weight_term(w: float | str) -> str:
    """weight 하나를 PRISM 항으로 — 상수는 수치, 상태 식(D26)은 PRISM 식으로 렌더."""
    return _render(_parse(w)) if isinstance(w, str) else _num(float(w))


def _init_block(ruleset: RuleSet) -> list[str]:
    terms: list[str] = []
    if ruleset.init is not None:
        terms.append(f"({_render(_parse(ruleset.init))})")
    for constraint in ruleset.constraints:
        terms.append(f"({_rule_pred(constraint)})")
    if not terms:
        return []
    return ["init", "  " + " & ".join(terms), "endinit"]


def _rule_pred(constraint: object) -> str:
    """constraint를 PRISM 상태 술어로. when이 있으면 (when => then)."""
    then = _render(_parse(constraint.then))  # type: ignore[attr-defined]
    when = getattr(constraint, "when", None)
    if when is not None:
        return f"{_render(_parse(when))} => {then}"
    return then


# ---------- 속성 ----------


def _properties(ruleset: RuleSet) -> tuple[PrismProperty, ...]:
    out: list[PrismProperty] = []
    for c in ruleset.checks:
        if c.kind == "no_deadlock":
            continue  # PRISM이 데드락을 자동 탐지 — 별도 prop 미생성(리포트에서 안내).
        if c.kind == "distribution":
            continue  # distribution은 sim 백엔드 전용(D19) — PRISM은 분포를 다루지 않음.
        if c.kind == "reachable":
            pctl = f"Pmax=? [ F ({_render(_parse(c.that or ''))}) ]"
        elif c.kind == "invariant":
            pctl = f"Pmin=? [ G ({_render(_parse(c.that or ''))}) ]"
        else:
            raise ProbError(f"검사 '{c.id}'의 알 수 없는 kind: '{c.kind}'")
        out.append(PrismProperty(prop_id=c.id, kind=c.kind, pctl=pctl, desc=c.desc))
    return tuple(out)


# ---------- 표현식 렌더 ----------

_BOOL_OP = {ast.And: " & ", ast.Or: " | "}
# `/`는 PRISM에서 항상 실수 나눗셈(double) — 상태 의존 weight(D26)의 비율식에 쓰인다.
_BIN_OP = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_CMP_OP = {
    ast.Eq: "=",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}


def _parse(expr: str) -> ast.expr:
    return ast.parse(expr, mode="eval").body


def _render(node: ast.AST) -> str:
    """ast 표현식을 PRISM 식 문자열로 렌더한다(D16). 화이트리스트 노드만."""
    if isinstance(node, ast.BoolOp):
        sep = _BOOL_OP[type(node.op)]
        return "(" + sep.join(_render(v) for v in node.values) + ")"
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return f"!({_render(node.operand)})"
        if isinstance(node.op, ast.USub):
            return f"-{_render(node.operand)}"
        raise ProbError("지원하지 않는 단항 연산자")
    if isinstance(node, ast.BinOp):
        op = _BIN_OP.get(type(node.op))
        if op is None:
            raise ProbError(f"PRISM 백엔드가 지원하지 않는 산술 연산자: {type(node.op).__name__}")
        return f"({_render(node.left)} {op} {_render(node.right)})"
    if isinstance(node, ast.Compare):
        return _render_compare(node)
    if isinstance(node, ast.Call):
        return _render_call(node)
    if isinstance(node, ast.Name):
        return node.id  # 변수명 또는 enum 값 const(둘 다 그대로)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if isinstance(node.value, int):
            return str(node.value)
        if isinstance(node.value, float):
            return _num(node.value)  # weight 식(D26)의 실수 상수 — 상태 변수는 여전히 유한만
        raise ProbError(f"PRISM 백엔드가 지원하지 않는 상수: {node.value!r}")
    if isinstance(node, ast.Attribute):
        raise ProbError("next.* 는 전이 갱신(then)에서만 쓸 수 있습니다.")
    if isinstance(node, ast.IfExp):
        # 배열 동적 색인(D28)의 desugar 산출물 — PRISM 삼항 `cond ? a : b`로 렌더.
        return f"({_render(node.test)} ? {_render(node.body)} : {_render(node.orelse)})"
    raise ProbError(f"PRISM 백엔드가 지원하지 않는 표현식 요소: {type(node).__name__}")


def _render_compare(node: ast.Compare) -> str:
    operands = [node.left, *node.comparators]
    parts: list[str] = []
    for i, op in enumerate(node.ops):
        sym = _CMP_OP.get(type(op))
        if sym is None:
            raise ProbError(f"지원하지 않는 비교 연산자: {type(op).__name__}")
        parts.append(f"({_render(operands[i])} {sym} {_render(operands[i + 1])})")
    return parts[0] if len(parts) == 1 else "(" + " & ".join(parts) + ")"


def _render_call(node: ast.Call) -> str:
    """min/max 함수 호출을 PRISM 식으로(둘 다 PRISM 내장 함수, 가변 인자 지원)."""
    func = node.func
    if not (isinstance(func, ast.Name) and func.id in ("min", "max")):
        raise ProbError(
            f"PRISM 백엔드가 지원하지 않는 함수 호출: '{ast.unparse(node)}' (허용: min, max)"
        )
    if node.keywords or len(node.args) < 2:
        raise ProbError(f"'{func.id}'은(는) 2개 이상의 위치 인자가 필요합니다")
    return f"{func.id}({', '.join(_render(a) for a in node.args)})"


def _updates(then_expr: str) -> str:
    """outcome.then(`next.X == 식` 배정형)을 PRISM 갱신 `(X'=식)`으로(D16)."""
    node = _parse(then_expr)
    if isinstance(node, ast.Constant) and node.value is True:
        # ghost 전용 효과가 erase되어 빈 갱신이 된 분기(D31) — PRISM 항등 갱신.
        return "true"
    conjuncts = (
        node.values if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And) else [node]
    )
    parts: list[str] = []
    for c in conjuncts:
        var, rhs = _assignment(c)
        parts.append(f"({var}'={_render(rhs)})")
    return " & ".join(parts)


def _assignment(node: ast.AST) -> tuple[str, ast.expr]:
    """`next.X == 식`에서 (X, 식 노드)를 뽑는다. 배정형이 아니면 ProbError."""
    if not (
        isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
    ):
        raise ProbError("PRISM 갱신은 'next.X == 식' 배정형이어야 합니다(부등식 등 불가).")
    for a, b in ((node.left, node.comparators[0]), (node.comparators[0], node.left)):
        if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "next":
            return a.attr, b
    raise ProbError("PRISM 갱신의 좌변은 next.<변수>여야 합니다.")


def _prob(weight: float, total: float) -> str:
    # 부동소수 합(예 0.7+0.3=0.999…)을 허용오차로 1.0 취급. 아니면 정규화 분수로.
    if abs(total - 1.0) < 1e-9:
        return _num(weight)
    return f"{_num(weight)}/{_num(total)}"


def _num(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)
