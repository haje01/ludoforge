"""외부 DSL(자체 문법) 텍스트 로더 — `.rule` 자체 문법 → 기존 IR(D21, 6차 마일스톤).

YAML 로더(`core/loader.py`)와 **같은 IR**을 만드는 병행 프론트엔드다. 표면 문법만 다르고
백엔드·결정론 경계는 IR이 불변이라 무회귀다(D21). Lark 문법으로 파싱하고 Transformer로
기존 IR 데이터클래스로 lowering한다.

설계 메모:
- 비-튜링완전(D21): 문법에 루프·import가 없다. 표현식은 화이트리스트 노드(논리·비교·
  산술·이름·수, 그리고 `min`/`max` 호출)만 — `eval` 없이 **문자열로 lowering**해 기존 ast
  화이트리스트 평가기(§7, D2)·Z3 번역기가 그대로 소비한다. 즉 IR의 표현식 문자열 표기는
  YAML과 동일한 파이썬-식이다. `min`/`max`는 포화/클램프용이며 **효과(then/outcomes)에서만**
  허용한다 — 문법은 어디서나 파싱하되 효과 전용 제한은 schema가 강제한다(generic + gate).
- `RANGENUM`은 소수점 뒤 숫자를 강제(`\\d+(\\.\\d+)?`)해 `0..30`이 float `0.`으로
  잘못 잠식되는 것을 막는다. 표현식 안의 수치는 별도 `NUMBER`(컨텍스트 렉서가 구분).
- `==`(비교)만 CMP 토큰에 둔다 — 단독 `=`(대입)는 전이 효과 전용이라 술어 위치에서 쓰면
  구문 오류가 된다(`=`/`==` 판별 기반).

현재 구현 범위: **S1 `domain` + S2 정적식 + S3 전이(`transitions`/`outcomes`/`pref`)**.
전이 효과는 `var = expr`(대입; `then`/`outcomes` 문맥이 곧 다음 상태) → IR의 `next.var == expr`
문자열로 lowering하고, `;` 다중 대입은 `and` 결합한다. 프라임(`var'`) 표기는 제거했다(D22 —
`then` 문맥이 다음상태라 잉여, `=`/`==`가 대입/비교를 가름). `=`(효과)/`==`(술어) 판별은
문맥+연산자가 강제한다.
checks(`reachable`/`invariant`/`no_deadlock`/`prob`/`distribution`)와 **S5 템플릿**(`table`/
`for`/`${}` desugar)까지 포함한다 — `prob`의 PCTL은 불투명 문자열(core 미파싱, D11),
`distribution`은 sim 전용 수치식. 템플릿은 파스 트리에서 펼쳐 IR엔 구체 항목만 남긴다(D18).
desc/author surface와 코퍼스 이관은 S6.
"""

from __future__ import annotations

import ast
import itertools
import re
from dataclasses import replace
from typing import Any

import lark

from core.ir import Check, Constraint, Expect, Outcome, RuleSet, Transition, Variable


class TextLoaderError(Exception):
    """자체 문법 파싱/lowering 실패. 위치(줄·열)를 포함해 보고한다(§7·원칙4)."""


_GRAMMAR = r"""
start: item*

?item: domain_block | init_decl | constraint_decl | expect_decl | transition_decl | check_decl
     | table_decl | for_block

// ── 템플릿(S5) — desugar에서 펼침. IR엔 구체 항목만 남는다(D18) ──
table_decl: "table" NAME "{" t_entry* "}"
t_entry: NAME ":" t_val ","?
?t_val: NUMBER          -> t_num
      | NAME            -> t_name
      | "{" t_entry* "}" -> t_dict
for_block: "for" binding ("," binding)* ":" templatable
binding: NAME "in" "[" NAME ("," NAME)* "]"
?templatable: constraint_decl | transition_decl | check_decl

// ── 도메인 ──
domain_block: "domain" "{" var_decl* "}"
var_decl: NAME ":" var_type
?var_type: int_type | real_type | bool_type | enum_type
int_type:  "int" range?
real_type: "real" range?
bool_type: "bool"
enum_type: "enum" "{" NAME ("," NAME)* "}"
range: range_lo ".." range_hi
range_lo: RANGENUM?
range_hi: RANGENUM?

// ── 정적 선언(S2) ──
init_decl: "init" ":" pred
constraint_decl: "constraint" id ":" c_meta* guard? "then" pred
guard: "when" pred
expect_decl: "expect" id ":" meta* pred
id: NAME | STRING

// ── 메타데이터(S6) — desc는 모든 선언, author는 constraint 전용(IR 필드와 일치) ──
meta: "desc" STRING -> meta_desc
c_meta: "desc" STRING -> meta_desc | "author" STRING -> meta_author

// ── 전이(S3) — 효과는 대입(`var' = expr`), 술어 가드는 `==` ──
transition_decl: "transition" id ":" meta* t_guard? t_player? t_pref? t_body
t_guard: "when" pred
t_player: "player" NAME                  // 전이 소유 선언(D27) — 선언된 enum 값이어야(schema)
t_pref: "pref" sum                       // 상수 또는 현재 상태 식(D26 — 적응적 정책)
t_body: "then" update            -> then_body
      | "outcomes" ":" outcome+  -> outcomes_body
outcome: sum "->" update                 // weight: 상수/표 색인(desugar 후 수치) 또는 상태 식(D26)
?update: assign                          -> single_update
       | "{" assign (";" assign)* "}"    -> multi_update
assign: NAME "=" sum                     // var = expr — then 문맥이 곧 다음 상태(D22)

// ── checks(S4) — kind별 dialect 분리(distribution=sim 수치식) ──
check_decl: "check" id meta* check_kind
check_kind: "reachable" ":" pred    -> check_reachable
          | "invariant" ":" pred    -> check_invariant
          | "no_deadlock"           -> check_no_deadlock
          | "distribution" ":" pred -> check_distribution

// ── 표현식(술어=같은 상태, `==` 비교) ──
?pred: pred "or" and_e   -> or_op
     | and_e
?and_e: and_e "and" not_e -> and_op
      | not_e
?not_e: "not" not_e -> not_op
      | comp
?comp: sum
     | sum (CMP sum)+ -> compare
?sum: product
    | sum "+" product -> add
    | sum "-" product -> sub
?product: atom
        | product "*" atom -> mul
        | product "/" atom -> div
?atom: NUMBER -> number
     | call
     | index
     | NAME   -> name
     | "(" pred ")" -> paren
     | "-" atom -> neg
call: NAME "(" sum ("," sum)* ")"     // min/max만 의미 허용 — 효과 전용 제한은 schema가 강제
index: NAME ("[" key "]")+
key: NAME -> key_name | NUMBER -> key_num | STRING -> key_str

CMP: /==|!=|<=|>=|<|>/
RANGENUM: /-?\d+(\.\d+)?/
NUMBER: /\d+(\.\d+)?/
NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
STRING: /"[^"]*"/
COMMENT: /\/\/[^\n]*/

%import common.WS
%ignore WS
%ignore COMMENT
"""


def _to_int(tok: lark.Token | None, what: str) -> int | None:
    """int 변수 경계: 정수만 허용(소수점이 있으면 거부 — _parse_opt_int와 동형)."""
    if tok is None:
        return None
    text = str(tok)
    if "." in text:
        raise TextLoaderError(
            f"{tok.line}:{tok.column}: int 변수의 {what} 경계는 정수여야 합니다: {text!r}"
        )
    return int(text)


def _to_float(tok: lark.Token | None) -> float | None:
    """real 변수 경계: 정수/실수 모두 float로 정규화(_parse_opt_float와 동형)."""
    return None if tok is None else float(str(tok))


def _rate(text: str) -> float | str:
    """weight/pref 값(D26): 수치(상수·desugar된 표 색인)면 float — 기존 골든 IR과 등가,
    아니면 현재 상태 식 문자열로 보존(전이 직전 상태에서 sim이 평가)."""
    try:
        return float(text)
    except ValueError:
        return text


class _ToIR(lark.Transformer[lark.Token, RuleSet]):
    """파스 트리 → 기존 IR.

    표현식 규칙은 **파이썬-식 문자열**을 반환한다(IR이 표현식을 문자열로 보관하므로).
    구조 규칙은 (종류, 값) 마커를 반환하고 `start`가 RuleSet으로 조립한다.
    """

    # --- 표현식: 파이썬-식 문자열로 lowering ---
    def or_op(self, items: list[str]) -> str:
        a, b = items
        return f"{a} or {b}"

    def and_op(self, items: list[str]) -> str:
        a, b = items
        return f"{a} and {b}"

    def not_op(self, items: list[str]) -> str:
        (a,) = items
        return f"not {a}"

    def compare(self, items: list[Any]) -> str:
        parts = [str(items[0])]
        for i in range(1, len(items), 2):
            parts.append(str(items[i]))  # CMP
            parts.append(str(items[i + 1]))  # 우변
        return " ".join(parts)

    def add(self, items: list[str]) -> str:
        a, b = items
        return f"{a} + {b}"

    def sub(self, items: list[str]) -> str:
        a, b = items
        return f"{a} - {b}"

    def mul(self, items: list[str]) -> str:
        a, b = items
        return f"{a} * {b}"

    def div(self, items: list[str]) -> str:
        a, b = items
        return f"{a} / {b}"

    def neg(self, items: list[str]) -> str:
        (a,) = items
        return f"-{a}"

    def number(self, items: list[lark.Token]) -> str:
        return str(items[0])

    def name(self, items: list[lark.Token]) -> str:
        return str(items[0])

    def paren(self, items: list[str]) -> str:
        return f"({items[0]})"

    def call(self, items: list[Any]) -> str:
        # `min/max(a, b, ...)` → 파이썬-식 문자열(다운스트림 ast가 그대로 소비). 함수명·인자
        # 개수의 의미 검증은 schema/번역기가 한다(여기선 구문만). 효과 전용 제한도 schema.
        name_tok, args = items[0], items[1:]
        return f"{name_tok}(" + ", ".join(str(a) for a in args) + ")"

    def index(self, items: list[Any]) -> str:
        # desugar(_expand_tree)가 모든 색인을 리터럴로 해소한다 — 여기 닿으면 for/table
        # 바인딩 없이 색인을 쓴 것(방어).
        raise TextLoaderError("표 색인(name[key])은 for/table 바인딩 안에서만 쓸 수 있습니다.")

    def id(self, items: list[lark.Token]) -> str:
        tok = items[0]
        return tok[1:-1] if tok.type == "STRING" else str(tok)

    # --- 메타데이터(S6): (태그, 값) 마커로 반환, 각 decl이 추출 ---
    def meta_desc(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("desc", str(items[0])[1:-1])

    def meta_author(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("author", str(items[0])[1:-1])

    # --- 도메인(S1) ---
    def range_lo(self, items: list[lark.Token]) -> lark.Token | None:
        return items[0] if items else None

    def range_hi(self, items: list[lark.Token]) -> lark.Token | None:
        return items[0] if items else None

    def range(self, items: list[Any]) -> tuple[lark.Token | None, lark.Token | None]:
        lo, hi = items
        return lo, hi

    def int_type(self, items: list[Any]) -> dict[str, Any]:
        lo, hi = items[0] if items else (None, None)
        return {"type": "int", "min": _to_int(lo, "min"), "max": _to_int(hi, "max")}

    def real_type(self, items: list[Any]) -> dict[str, Any]:
        lo, hi = items[0] if items else (None, None)
        return {"type": "real", "min": _to_float(lo), "max": _to_float(hi)}

    def bool_type(self, items: list[Any]) -> dict[str, Any]:
        return {"type": "bool"}

    def enum_type(self, items: list[lark.Token]) -> dict[str, Any]:
        return {"type": "enum", "values": tuple(str(t) for t in items)}

    def var_decl(self, items: list[Any]) -> Variable:
        name_tok, kwargs = items
        return Variable(name=str(name_tok), **kwargs)

    # --- 구조 마커 ---
    def domain_block(self, items: list[Variable]) -> tuple[str, Any]:
        return ("domain", tuple(items))

    def init_decl(self, items: list[str]) -> tuple[str, Any]:
        return ("init", items[0])

    def guard(self, items: list[str]) -> tuple[str, Any]:
        return ("when", items[0])

    def constraint_decl(self, items: list[Any]) -> tuple[str, Any]:
        # items = [id, *태그된(meta/guard), then]. 마지막은 then 술어(untagged str).
        cid, then = items[0], items[-1]
        when = desc = author = None
        for tag, val in items[1:-1]:
            if tag == "when":
                when = val
            elif tag == "desc":
                desc = val
            elif tag == "author":
                author = val
        return ("constraint", Constraint(id=cid, when=when, then=then, desc=desc, author=author))

    def expect_decl(self, items: list[Any]) -> tuple[str, Any]:
        # items = [id, *meta, that]. 마지막은 that 술어.
        eid, that = items[0], items[-1]
        desc = None
        for tag, val in items[1:-1]:
            if tag == "desc":
                desc = val
        return ("expect", Expect(id=eid, that=that, desc=desc))

    # --- 전이(S3): 효과는 `next.<var> == <rhs>` 문자열로 lowering ---
    def assign(self, items: list[Any]) -> str:
        # `var = rhs`(then 문맥=다음 상태) → IR의 `next.var == rhs` 문자열(엔진/번역기 표기).
        name_tok, rhs = items
        return f"next.{name_tok} == {rhs}"

    def single_update(self, items: list[str]) -> str:
        return items[0]

    def multi_update(self, items: list[str]) -> str:
        # `{ a = ..; b = .. }` 병렬 대입 집합 → `and` 결합(YAML의 다중 효과와 동형).
        return " and ".join(items)

    def outcome(self, items: list[Any]) -> Outcome:
        weight_str, then = items
        return Outcome(then=then, weight=_rate(str(weight_str)))

    def then_body(self, items: list[str]) -> tuple[str, tuple[Outcome, ...]]:
        # bare then → weight=1.0 단일 Outcome(YAML 로더 정규화와 동형).
        return ("body", (Outcome(then=items[0], weight=1.0),))

    def outcomes_body(self, items: list[Outcome]) -> tuple[str, tuple[Outcome, ...]]:
        return ("body", tuple(items))

    def t_guard(self, items: list[str]) -> tuple[str, Any]:
        return ("when", items[0])

    def t_pref(self, items: list[Any]) -> tuple[str, Any]:
        # sum 규칙이 이미 파이썬-식 문자열로 lowering — 수치면 float, 아니면 상태 식(D26).
        return ("pref", _rate(str(items[0])))

    def t_player(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("player", str(items[0]))

    def transition_decl(self, items: list[Any]) -> tuple[str, Any]:
        tid = items[0]
        when: str | None = None
        pref: float | str | None = None
        player: str | None = None
        desc: str | None = None
        outcomes: tuple[Outcome, ...] = ()
        for tag, val in items[1:]:
            if tag == "when":
                when = val
            elif tag == "player":
                player = val
            elif tag == "pref":
                pref = val
            elif tag == "desc":
                desc = val
            elif tag == "body":
                outcomes = val
        return (
            "transition",
            Transition(id=tid, outcomes=outcomes, when=when, pref=pref, desc=desc, player=player),
        )

    # --- checks(S4) ---
    def check_reachable(self, items: list[str]) -> dict[str, Any]:
        return {"kind": "reachable", "that": items[0]}

    def check_invariant(self, items: list[str]) -> dict[str, Any]:
        return {"kind": "invariant", "that": items[0]}

    def check_no_deadlock(self, items: list[Any]) -> dict[str, Any]:
        return {"kind": "no_deadlock"}

    def check_distribution(self, items: list[str]) -> dict[str, Any]:
        return {"kind": "distribution", "expr": items[0]}

    def check_decl(self, items: list[Any]) -> tuple[str, Any]:
        # items = [id, *meta, kind_kwargs(dict)]. 마지막은 kind dict.
        cid, kind_kwargs = items[0], items[-1]
        desc = None
        for tag, val in items[1:-1]:
            if tag == "desc":
                desc = val
        return ("check", Check(id=cid, desc=desc, **kind_kwargs))

    def start(self, items: list[tuple[str, Any]]) -> RuleSet:
        variables: tuple[Variable, ...] = ()
        constraints: list[Constraint] = []
        expects: list[Expect] = []
        transitions: list[Transition] = []
        checks: list[Check] = []
        init: str | None = None
        for kind, value in items:
            if kind == "domain":
                variables = value
            elif kind == "constraint":
                constraints.append(value)
            elif kind == "expect":
                expects.append(value)
            elif kind == "transition":
                transitions.append(value)
            elif kind == "check":
                checks.append(value)
            elif kind == "init":
                if init is not None:
                    raise TextLoaderError("init은 한 번만 선언할 수 있습니다.")
                init = value
        return RuleSet(
            variables=variables,
            constraints=tuple(constraints),
            expects=tuple(expects),
            init=init,
            transitions=tuple(transitions),
            checks=tuple(checks),
        )


_PARSER = lark.Lark(_GRAMMAR, parser="lalr")
_TRANSFORMER = _ToIR()
_TMPL = re.compile(r"\$\{([^}]+)\}")


# ── 데구거(S5): table 수집 → for 곱 펼치기 → loop var·색인·${} 해소(D18) ──────────
#
# YAML 로더의 `_expand_items`/`_subst_*`/`_eval_template`과 **동형 결과**를 내되, 외부 DSL은
# loop 변수·표 색인을 1급 식(`name`·`index`)으로 표현하므로 `${}`는 id 문자열 보간에만 남는다.
# 펼치기는 파스 트리에서 끝나고, 그 뒤 `_ToIR`이 구체 항목만 본다(결정론 경계 무관, §2·§4.2).


def _eval_env_expr(src: str, env: dict[str, Any]) -> Any:
    """id `${...}` 보간용 제한된 식 평가 — 로더 `_eval_template_node`와 같은 화이트리스트."""
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise TextLoaderError(f"템플릿 식 구문 오류: '{src}' ({e.msg})") from e
    return _eval_ast(tree.body, env, src)


def _eval_ast(node: ast.AST, env: dict[str, Any], src: str) -> Any:
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise TextLoaderError(f"템플릿의 미정의 파라미터/테이블: '{node.id}'")
        return env[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Subscript):
        base = _eval_ast(node.value, env, src)
        key = _eval_ast(node.slice, env, src)
        try:
            return base[key]
        except (KeyError, IndexError, TypeError) as e:
            raise TextLoaderError(f"템플릿 색인 실패: '{src}' ({e!r})") from e
    raise TextLoaderError(f"템플릿 식에 허용되지 않는 요소: '{src}' ({type(node).__name__})")


def _eval_tval(node: Any) -> Any:
    """`table` 값 노드(t_num/t_name/t_dict)를 파이썬 값으로."""
    if node.data == "t_num":
        text = str(node.children[0])
        return float(text) if "." in text else int(text)
    if node.data == "t_name":
        return str(node.children[0])
    return {str(e.children[0]): _eval_tval(e.children[1]) for e in node.children}


def _collect_tables(tree: Any) -> dict[str, Any]:
    """최상위 `table_decl`들을 이름→데이터 dict로 수집(IR엔 안 들어감, D18)."""
    tables: dict[str, Any] = {}
    for child in tree.children:
        if isinstance(child, lark.Tree) and child.data == "table_decl":
            name = str(child.children[0])
            tables[name] = {
                str(e.children[0]): _eval_tval(e.children[1]) for e in child.children[1:]
            }
    return tables


def _collect_domain_vars(tree: Any) -> set[str]:
    """도메인 변수명 집합 — for loop 변수와의 충돌 감지에 쓴다(조용한 shadowing 방지)."""
    names: set[str] = set()
    for child in tree.children:
        if isinstance(child, lark.Tree) and child.data == "domain_block":
            names.update(str(vd.children[0]) for vd in child.children)
    return names


def _literal_tree(value: Any) -> Any:
    """치환 값(숫자/이름)을 식 리터럴 노드로."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TextLoaderError(f"표/파라미터 값을 식에 넣을 수 없습니다: {value!r}")
    if isinstance(value, str):
        return lark.Tree("name", [lark.Token("NAME", value)])
    return lark.Tree("number", [lark.Token("NUMBER", repr(value))])


def _eval_key(node: Any, env: dict[str, Any]) -> Any:
    if node.data == "key_name":
        name = str(node.children[0])
        if name not in env:
            raise TextLoaderError(f"미정의 색인 파라미터: '{name}'")
        return env[name]
    if node.data == "key_num":
        return int(str(node.children[0]))
    return str(node.children[0])[1:-1]  # key_str


def _eval_index(node: Any, env: dict[str, Any]) -> Any:
    base_name = str(node.children[0])
    if base_name not in env:
        raise TextLoaderError(f"미정의 테이블/파라미터: '{base_name}'")
    val: Any = env[base_name]
    for key_node in node.children[1:]:
        k = _eval_key(key_node, env)
        try:
            val = val[k]
        except (KeyError, IndexError, TypeError) as e:
            raise TextLoaderError(f"표 색인 실패: '{base_name}[...]' ({e!r})") from e
    return val


def _interp_string(token: Any, env: dict[str, Any]) -> Any:
    """id STRING의 `${...}`를 env로 보간(전체/부분 모두 문자열 — id는 항상 문자열)."""
    inner = str(token)[1:-1]

    def repl(m: re.Match[str]) -> str:
        return str(_eval_env_expr(m.group(1), env))

    return lark.Token("STRING", '"' + _TMPL.sub(repl, inner) + '"')


def _subst_tree(node: Any, env: dict[str, Any]) -> Any:
    """식·id 트리에서 loop 변수(name)·표 색인(index)·id `${}`를 env로 해소."""
    if isinstance(node, lark.Token):
        return _interp_string(node, env) if node.type == "STRING" else node
    if node.data == "index":
        return _literal_tree(_eval_index(node, env))
    if node.data == "name":
        nm = str(node.children[0])
        if nm in env and not isinstance(env[nm], dict):  # 표(dict)는 bare로 치환 안 함
            return _literal_tree(env[nm])
        return node
    if node.data == "t_player":
        # player 태그(D27)의 NAME도 loop 변수면 치환 — `for p in [p1, p2]: ... player p`.
        nm = str(node.children[0])
        if nm in env and isinstance(env[nm], str):
            return lark.Tree(node.data, [lark.Token("NAME", env[nm])])
        return node
    return lark.Tree(node.data, [_subst_tree(c, env) for c in node.children])


def _expand_for(node: Any, tables: dict[str, Any], domain_vars: set[str]) -> list[Any]:
    """`for p in [..], q in [..]: <item>`를 데카르트 곱으로 펼친다(키 순서, 로더와 동형)."""
    *bindings, template = node.children
    params = [str(b.children[0]) for b in bindings]
    for p in params:
        if p in domain_vars:
            raise TextLoaderError(
                f"for loop 변수 '{p}'가 도메인 변수와 이름이 같습니다 — 치환이 모호해지니 "
                f"다른 이름을 쓰세요(예: monster → mon)."
            )
    value_lists = [[str(t) for t in b.children[1:]] for b in bindings]
    out: list[Any] = []
    for combo in itertools.product(*value_lists):
        env = {**tables, **dict(zip(params, combo, strict=True))}
        out.append(_subst_tree(template, env))
    return out


def _expand_tree(tree: Any, tables: dict[str, Any], domain_vars: set[str]) -> Any:
    """table_decl 제거, for_block 펼치기, 그 외 항목은 tables-env로 치환(상수 색인 허용)."""
    children: list[Any] = []
    for child in tree.children:
        if isinstance(child, lark.Tree) and child.data == "table_decl":
            continue
        if isinstance(child, lark.Tree) and child.data == "for_block":
            children.extend(_expand_for(child, tables, domain_vars))
        else:
            children.append(_subst_tree(child, tables))
    return lark.Tree("start", children)


def parse_rule_text(src: str, source: str | None = None) -> RuleSet:
    """자체 문법 텍스트를 IR로 파싱한다.

    파싱 → 데구거(table/for/${} 펼치기) → IR 변환. `source`는 진단 메시지의 파일명(선택).
    구문 오류·경계 타입 오류·템플릿 오류는 위치 정보와 함께 `TextLoaderError`로 보고한다.
    """
    prefix = f"{source}: " if source else ""
    try:
        tree = _PARSER.parse(src)
    except lark.exceptions.UnexpectedInput as exc:
        loc = f"line {exc.line} col {exc.column}"
        raise TextLoaderError(f"{prefix}구문 오류 ({loc}): {exc}") from exc
    except lark.exceptions.LarkError as exc:
        raise TextLoaderError(f"{prefix}파싱 실패: {exc}") from exc

    try:
        expanded = _expand_tree(tree, _collect_tables(tree), _collect_domain_vars(tree))
        rs: RuleSet = _TRANSFORMER.transform(expanded)
    except TextLoaderError as exc:  # 데구거에서 직접 발생
        if prefix:
            raise TextLoaderError(f"{prefix}{exc}") from exc
        raise
    except lark.exceptions.VisitError as exc:
        if isinstance(exc.orig_exc, TextLoaderError):
            raise TextLoaderError(f"{prefix}{exc.orig_exc}") from exc.orig_exc
        raise

    if source is None:
        return rs
    # 병합 시 범인 파일 추적용 source(파일명) 부여 — YAML 로더와 동일 규약(원칙4).
    return replace(
        rs,
        constraints=tuple(replace(c, source=source) for c in rs.constraints),
        transitions=tuple(replace(t, source=source) for t in rs.transitions),
        checks=tuple(replace(ch, source=source) for ch in rs.checks),
    )
