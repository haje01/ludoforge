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

문서 메타데이터(D29, 12차): 선언 몸통의 `note`/`ref`/`tag`, 변수·table의 `desc`, 최상위
`section`. note/ref/tag는 IR `Doc`으로 passthrough(백엔드 무시 — "지워지는 주석" 계보),
section·table desc는 IR 미탑재(규칙서 생성 전용 — docgen이 desugar 전 트리를 소비, P2).
note/desc 본문의 `[[이름]]` 상호참조는 로드 시 존재를 검사한다(드리프트 억제, 실패는 크게).

주사위 닫힌형(D30, 13차): outcome weight 자리의 `chance(NdM CMP 상수)`·`rest`를 desugar가
`Fraction`으로 정확 계산해 기존 float weight로 lowering한다(순수 구문 변환 — IR·백엔드
불변). 룰북 원형(격파 목표값)이 SSOT에 남는다. 상태 의존 확률은 D26 식 weight의 몫.
"""

from __future__ import annotations

import ast
import itertools
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

import lark

from core.ir import Check, Constraint, Doc, Expect, Outcome, RuleSet, Transition, Variable


class TextLoaderError(Exception):
    """자체 문법 파싱/lowering 실패. 위치(줄·열)를 포함해 보고한다(§7·원칙4)."""


_GRAMMAR = r"""
start: item*

?item: domain_block | init_decl | constraint_decl | expect_decl | transition_decl | check_decl
     | table_decl | for_block | section_decl

// ── 문서(D29) — 규칙서 전용, IR 미탑재. section은 이후 선언들의 목차 절 ──
section_decl: "section" STRING

// ── 템플릿(S5) — desugar에서 펼침. IR엔 구체 항목만 남는다(D18) ──
table_decl: "table" NAME t_desc? "{" t_entry* "}"
t_desc: "desc" STRING
t_entry: NAME ":" t_val ","?
?t_val: NUMBER          -> t_num
      | NAME            -> t_name
      | "{" t_entry* "}" -> t_dict
for_block: "for" binding ("," binding)* ":" templatable
binding: NAME "in" "[" NAME ("," NAME)* "]"
?templatable: constraint_decl | transition_decl | check_decl

// ── 도메인 ──
domain_block: "domain" "{" var_decl* "}"
var_decl: ghost_mod? NAME v_idx? ":" var_type v_desc?
ghost_mod: "ghost"                    // 서술 전용 상태(D31) — sim만 실행, bmc/PRISM은 erase
v_idx: "[" NAME ("," NAME)* "]"       // 유한 색인 배열(D28) — desugar가 스칼라 가족으로 펼침
v_desc: "desc" STRING -> meta_desc    // 용어집용 변수 설명(D29)
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

// ── 메타데이터(S6) + 문서 절(D29) — desc는 모든 선언, author는 constraint 전용.
//    note(반복 허용 산문)·ref(출처)·tag(분류)는 IR Doc으로 passthrough(백엔드 무시).
//    예약어 주의: desc/author/note/ref/tag/section은 절 시작 위치에서 키워드다.
meta: "desc" STRING -> meta_desc
    | "note" STRING -> meta_note
    | "ref" STRING  -> meta_ref
    | "tag" NAME ("," NAME)* -> meta_tag
?c_meta: meta | "author" STRING -> meta_author

// ── 전이(S3) — 효과는 대입(`var' = expr`), 술어 가드는 `==` ──
transition_decl: "transition" id ":" meta* t_guard? t_player? t_pref? t_body
t_guard: "when" pred
t_player: "player" NAME                  // 전이 소유 선언(D27) — 선언된 enum 값이어야(schema)
t_pref: "pref" sum                       // 상수 또는 현재 상태 식(D26 — 적응적 정책)
t_body: "then" update            -> then_body
      | "outcomes" ":" outcome+  -> outcomes_body
outcome: o_weight "->" update            // weight: 상수/표 색인(desugar 후 수치) 또는 상태 식(D26)
?o_weight: sum
         | chance_w                      // 주사위 닫힌형(D30) — Fraction으로 정확 계산 후 float
         | rest_w                        // 잔여 = 1 - 같은 블록의 상수 가중치 합(블록당 1회, D30)
chance_w: "chance" "(" DICE CMP sum ")"  // 목표값(sum)은 desugar 후 상수 강제(상태 의존은 D26 몫)
!rest_w: "rest"
?update: assign                          -> single_update
       | "{" assign (";" assign)* "}"    -> multi_update
assign: NAME "=" sum                     // var = expr — then 문맥이 곧 다음 상태(D22)
      | index "=" sum -> assign_indexed  // 배열 정적 색인 LHS(D28) — desugar가 스칼라로 해소

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
DICE: /\d+d\d+/
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


# ── 주사위 닫힌형 chance/rest(D30) — desugar 시점 Fraction 정확 계산 ─────────────


@dataclass(frozen=True)
class _Chance:
    """`chance(NdM CMP 상수)`의 닫힌형 확률(D30). desugar 동안만 존재 — IR엔 float weight."""

    prob: Fraction


@dataclass(frozen=True)
class _Rest:
    """`rest` 마커(D30) — outcomes 블록 해소 시 잔여(1 − 상수 가중치 합)를 받는다."""

    line: int
    column: int


def _dice_pred_prob(n: int, m: int, op: str, target: Fraction) -> Fraction:
    """NdM 분포(Fraction 콘볼루션)에서 `합 CMP target`의 정확한 확률."""
    dist: dict[int, Fraction] = {0: Fraction(1)}
    face_p = Fraction(1, m)
    for _ in range(n):
        nxt: dict[int, Fraction] = {}
        for s, p in dist.items():
            for face in range(1, m + 1):
                nxt[s + face] = nxt.get(s + face, Fraction(0)) + p * face_p
        dist = nxt
    ops: dict[str, Callable[[int], bool]] = {
        "==": lambda s: s == target,
        "!=": lambda s: s != target,
        "<=": lambda s: s <= target,
        ">=": lambda s: s >= target,
        "<": lambda s: s < target,
        ">": lambda s: s > target,
    }
    return sum((p for s, p in dist.items() if ops[op](s)), Fraction(0))


def _resolve_outcomes(entries: list[Any]) -> tuple[Outcome, ...]:
    """outcomes 블록의 chance/rest(D30)를 닫힌형 float weight로 해소한다.

    마커가 없으면 그대로(기존 경로 — 하위 호환 비트 동일). 있으면: ① 다른 가중치는 전부
    상수여야 하고(상태 식 weight와 혼합 금지 — 잔여·합 검사 불가), ② 유리수 합이 1을
    넘으면 거부, ③ `rest`는 블록당 1회로 잔여(1 − 합)를 정확히 받는다."""
    if all(isinstance(e, Outcome) for e in entries):
        return tuple(entries)
    known = Fraction(0)
    rest_seen: _Rest | None = None
    slots: list[tuple[Fraction | None, str]] = []  # (확률, then) — None = rest 자리
    for e in entries:
        if isinstance(e, Outcome):
            if isinstance(e.weight, str):
                raise TextLoaderError(
                    "chance/rest(D30)는 상수 가중치와만 섞을 수 있습니다 — 상태 의존 "
                    f"weight('{e.weight}')와 혼합 금지(상태 의존 확률은 D26 식 weight로만)."
                )
            slots.append((Fraction(str(e.weight)), e.then))
            known += Fraction(str(e.weight))
            continue
        marker, then = e
        if isinstance(marker, _Chance):
            slots.append((marker.prob, then))
            known += marker.prob
        else:
            if rest_seen is not None:
                raise TextLoaderError(
                    f"{marker.line}:{marker.column}: rest는 outcomes 블록당 한 번만 "
                    f"쓸 수 있습니다(D30)."
                )
            rest_seen = marker
            slots.append((None, then))
    if known > 1:
        raise TextLoaderError(
            f"outcomes의 chance/상수 가중치 합이 1을 넘습니다: {known} (D30 — "
            f"주사위 문턱들이 겹치지 않는지 확인하세요)."
        )
    return tuple(
        Outcome(then=then, weight=float(prob if prob is not None else 1 - known))
        for prob, then in slots
    )


def _extract_doc(tagged: list[tuple[str, Any]]) -> tuple[list[tuple[str, Any]], Doc | None]:
    """태그된 메타 항목에서 문서 절(note/ref/tag, D29)을 Doc으로 걷어내고 나머지를 돌려준다.

    문서 절이 하나도 없으면 doc=None — 기존 골든 IR 등가 무회귀(기본값 보존)."""
    notes: list[str] = []
    ref: str | None = None
    tags: tuple[str, ...] = ()
    rest: list[tuple[str, Any]] = []
    for tag, val in tagged:
        if tag == "note":
            notes.append(val)
        elif tag == "ref":
            ref = val
        elif tag == "tag":
            tags = tags + val
        else:
            rest.append((tag, val))
    if notes or ref or tags:
        return rest, Doc(notes=tuple(notes), ref=ref, tags=tags)
    return rest, None


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
        # desugar(_expand_tree)가 모든 색인을 리터럴/스칼라로 해소한다 — 여기 닿으면
        # for/table/배열 어디에도 없는 이름을 색인한 것(방어).
        raise TextLoaderError(
            "색인(name[key])은 표(table)·배열 변수·for 바인딩에서만 쓸 수 있습니다."
        )

    def v_idx(self, items: list[Any]) -> Any:
        # 배열 선언(D28)은 desugar(_expand_tree)가 스칼라 가족으로 펼친다 — 방어.
        raise TextLoaderError("배열 선언이 펼쳐지지 않았습니다(내부 오류).")

    def verbatim(self, items: list[lark.Token]) -> str:
        # 동적 색인(D28)의 desugar 산출물 — 완성된 파이썬-식 문자열을 그대로 통과.
        return str(items[0])

    def id(self, items: list[lark.Token]) -> str:
        tok = items[0]
        return tok[1:-1] if tok.type == "STRING" else str(tok)

    # --- 메타데이터(S6): (태그, 값) 마커로 반환, 각 decl이 추출 ---
    def meta_desc(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("desc", str(items[0])[1:-1])

    def meta_author(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("author", str(items[0])[1:-1])

    # --- 문서 절(D29): Doc passthrough — 백엔드는 무시, 규칙서(P2)가 소비 ---
    def meta_note(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("note", str(items[0])[1:-1])

    def meta_ref(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("ref", str(items[0])[1:-1])

    def meta_tag(self, items: list[lark.Token]) -> tuple[str, tuple[str, ...]]:
        return ("tag", tuple(str(t) for t in items))

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

    def ghost_mod(self, items: list[Any]) -> tuple[str, bool]:
        return ("ghost", True)

    def var_decl(self, items: list[Any]) -> Variable:
        # items = [ghost?(("ghost", True)), NAME, 타입 dict, v_desc?(("desc", str), D29)].
        # v_idx는 desugar가 이미 펼쳤으므로 여기 없다(있으면 v_idx()가 먼저 거부).
        name: str | None = None
        kwargs: dict[str, Any] = {}
        desc: str | None = None
        ghost = False
        for it in items:
            if isinstance(it, lark.Token):
                name = str(it)
            elif isinstance(it, dict):
                kwargs = it
            elif it[0] == "ghost":
                ghost = True
            else:
                desc = it[1]  # ("desc", 값)
        assert name is not None
        return Variable(name=name, desc=desc, ghost=ghost, **kwargs)

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
        tagged, doc = _extract_doc(items[1:-1])
        when = desc = author = None
        for tag, val in tagged:
            if tag == "when":
                when = val
            elif tag == "desc":
                desc = val
            elif tag == "author":
                author = val
        return (
            "constraint",
            Constraint(id=cid, when=when, then=then, desc=desc, author=author, doc=doc),
        )

    def expect_decl(self, items: list[Any]) -> tuple[str, Any]:
        # items = [id, *meta, that]. 마지막은 that 술어.
        eid, that = items[0], items[-1]
        tagged, doc = _extract_doc(items[1:-1])
        desc = None
        for tag, val in tagged:
            if tag == "desc":
                desc = val
        return ("expect", Expect(id=eid, that=that, desc=desc, doc=doc))

    # --- 전이(S3): 효과는 `next.<var> == <rhs>` 문자열로 lowering ---
    def assign(self, items: list[Any]) -> str:
        # `var = rhs`(then 문맥=다음 상태) → IR의 `next.var == rhs` 문자열(엔진/번역기 표기).
        name_tok, rhs = items
        return f"next.{name_tok} == {rhs}"

    def assign_indexed(self, items: list[Any]) -> str:
        # 배열 정적 색인 LHS(D28) — desugar가 `name`(스칼라)으로 해소한 뒤에만 도달한다.
        # 해소된 name 규칙은 str을 내므로 assign과 동형. (미해소 index는 index()가 먼저 거부.)
        lhs, rhs = items
        return f"next.{lhs} == {rhs}"

    def single_update(self, items: list[str]) -> str:
        return items[0]

    def multi_update(self, items: list[str]) -> str:
        # `{ a = ..; b = .. }` 병렬 대입 집합 → `and` 결합(YAML의 다중 효과와 동형).
        return " and ".join(items)

    def chance_w(self, items: list[Any]) -> _Chance:
        # `chance(NdM CMP 상수)`(D30) → 닫힌형 확률(Fraction). 목표값은 desugar가 이미
        # 리터럴로 해소한 상수여야 한다(표 색인·loop 변수 포함) — 상태 식이면 거부.
        dice_tok, cmp_tok, rhs = items
        loc = f"{dice_tok.line}:{dice_tok.column}: "
        n, m = (int(part) for part in str(dice_tok).split("d"))
        if n < 1 or m < 2 or n * m > 10_000:
            raise TextLoaderError(
                loc
                + f"주사위 '{dice_tok}'는 지원 범위 밖입니다(개수 ≥1 · 면 ≥2 · 개수×면 ≤ 10000)."
            )
        try:
            target = Fraction(str(rhs))
        except (ValueError, ZeroDivisionError):
            raise TextLoaderError(
                loc + f"chance({dice_tok} {cmp_tok} …)의 목표값은 상수여야 합니다"
                f"(리터럴·표 색인·loop 변수 — 상태 의존 확률은 D26 식 weight로): '{rhs}'"
            ) from None
        return _Chance(prob=_dice_pred_prob(n, m, str(cmp_tok), target))

    def rest_w(self, items: list[lark.Token]) -> _Rest:
        return _Rest(line=items[0].line or 0, column=items[0].column or 0)

    def outcome(self, items: list[Any]) -> Outcome | tuple[Any, str]:
        weight_node, then = items
        if isinstance(weight_node, _Chance | _Rest):  # D30 — 블록 해소는 outcomes_body에서
            return (weight_node, then)
        return Outcome(then=then, weight=_rate(str(weight_node)))

    def then_body(self, items: list[str]) -> tuple[str, tuple[Outcome, ...]]:
        # bare then → weight=1.0 단일 Outcome(YAML 로더 정규화와 동형).
        return ("body", (Outcome(then=items[0], weight=1.0),))

    def outcomes_body(self, items: list[Any]) -> tuple[str, tuple[Outcome, ...]]:
        return ("body", _resolve_outcomes(items))

    def t_guard(self, items: list[str]) -> tuple[str, Any]:
        return ("when", items[0])

    def t_pref(self, items: list[Any]) -> tuple[str, Any]:
        # sum 규칙이 이미 파이썬-식 문자열로 lowering — 수치면 float, 아니면 상태 식(D26).
        return ("pref", _rate(str(items[0])))

    def t_player(self, items: list[lark.Token]) -> tuple[str, str]:
        return ("player", str(items[0]))

    def transition_decl(self, items: list[Any]) -> tuple[str, Any]:
        tid = items[0]
        tagged, doc = _extract_doc(items[1:])
        when: str | None = None
        pref: float | str | None = None
        player: str | None = None
        desc: str | None = None
        outcomes: tuple[Outcome, ...] = ()
        for tag, val in tagged:
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
            Transition(
                id=tid, outcomes=outcomes, when=when, pref=pref, desc=desc, player=player, doc=doc
            ),
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
        tagged, doc = _extract_doc(items[1:-1])
        desc = None
        for tag, val in tagged:
            if tag == "desc":
                desc = val
        return ("check", Check(id=cid, desc=desc, doc=doc, **kind_kwargs))

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


# propagate_positions: 규칙서 생성(docgen, D29 P2)이 트리 노드의 원문 조각을 잘라 쓰기
# 위해 meta(start_pos/end_pos)를 보존한다 — IR 변환 경로에는 영향 없음(메타는 부가 정보).
_PARSER = lark.Lark(_GRAMMAR, parser="lalr", propagate_positions=True)
_TRANSFORMER = _ToIR()
_TMPL = re.compile(r"\$\{([^}]+)\}")


def parse_doc_tree(src: str, source: str | None = None) -> lark.Tree[lark.Token]:
    """규칙서 생성용(D29 P2) — desugar *전* 파스 트리(위치 보존)를 돌려준다.

    docgen은 저자가 쓴 접힌 형태(for 템플릿·표·section)를 렌더해야 하므로 IR이 아니라
    이 트리를 소비한다. 검증(스키마·참조 게이트)은 별도로 `parse_rule_text`가 담당한다."""
    prefix = f"{source}: " if source else ""
    try:
        return _PARSER.parse(src)
    except lark.exceptions.UnexpectedInput as exc:
        loc = f"line {exc.line} col {exc.column}"
        raise TextLoaderError(f"{prefix}구문 오류 ({loc}): {exc}") from exc
    except lark.exceptions.LarkError as exc:
        raise TextLoaderError(f"{prefix}파싱 실패: {exc}") from exc


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


def _var_decl_parts(vd: Any) -> tuple[Any, Any | None, Any, Any | None, Any | None]:
    """var_decl 자식 분해 → (NAME 토큰, v_idx|None, 타입 트리, desc|None, ghost|None).

    ghost_mod(D31)·v_desc(D29)가 선택 절이라 자식 수·위치가 가변 — 노드 종류로 판별한다."""
    name_tok = None
    v_idx = vtype = v_desc = ghost = None
    for c in vd.children:
        if isinstance(c, lark.Token):
            name_tok = c
        elif c.data == "ghost_mod":
            ghost = c
        elif c.data == "v_idx":
            v_idx = c
        elif c.data == "meta_desc":
            v_desc = c
        else:
            vtype = c
    return name_tok, v_idx, vtype, v_desc, ghost


def _collect_tables(tree: Any) -> dict[str, Any]:
    """최상위 `table_decl`들을 이름→데이터 dict로 수집(IR엔 안 들어감, D18).

    t_desc(표 설명, D29)는 데이터가 아니라 건너뛴다(규칙서 생성 전용)."""
    tables: dict[str, Any] = {}
    for child in tree.children:
        if isinstance(child, lark.Tree) and child.data == "table_decl":
            name = str(child.children[0])
            tables[name] = {
                str(e.children[0]): _eval_tval(e.children[1])
                for e in child.children[1:]
                if isinstance(e, lark.Tree) and e.data == "t_entry"
            }
    return tables


def _collect_domain_vars(tree: Any) -> set[str]:
    """도메인 변수명 집합 — for loop 변수와의 충돌 감지에 쓴다(조용한 shadowing 방지).

    배열 선언(D28)은 base 이름과 펼친 원소 이름을 모두 포함한다."""
    names: set[str] = set()
    for child in tree.children:
        if isinstance(child, lark.Tree) and child.data == "domain_block":
            for vd in child.children:
                name_tok, v_idx, _vtype, _desc, _ghost = _var_decl_parts(vd)
                names.add(str(name_tok))
                if v_idx is not None:  # 배열 선언
                    names.update(f"{name_tok}_{idx}" for idx in v_idx.children)
    return names


@dataclass(frozen=True)
class _Array:
    """유한 색인 배열 선언(D28). desugar 동안만 존재 — IR엔 스칼라 가족만 남는다."""

    base: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class _EnumVar:
    """스칼라 enum 변수(동적 색인 후보, D28). desugar env에서 치환 금지 마커를 겸한다."""

    values: tuple[str, ...]


@dataclass(frozen=True)
class _IfExpr:
    """동적 색인의 lowering 산출물(D28) — 완성된 파이썬-식 문자열(유한 case-분기 IfExp).

    사용자 문법엔 삼항이 없다 — desugar 내부 생성물로만 IR에 들어간다(비-튜링완전 유지)."""

    text: str


def _collect_enum_vars(tree: Any) -> dict[str, _EnumVar]:
    """스칼라 enum 변수(이름 → 값들). 배열의 동적 색인(`arr[turn]`) 판별·검증용(D28).

    배열 원소 enum(`monster[p1]` 등)은 v1에서 색인 변수로 못 쓴다."""
    out: dict[str, _EnumVar] = {}
    for child in tree.children:
        if not (isinstance(child, lark.Tree) and child.data == "domain_block"):
            continue
        for vd in child.children:
            name_tok, v_idx, vtype, _desc, _ghost = _var_decl_parts(vd)
            if v_idx is None and isinstance(vtype, lark.Tree) and vtype.data == "enum_type":
                out[str(name_tok)] = _EnumVar(tuple(str(t) for t in vtype.children))
    return out


def _collect_arrays(tree: Any) -> dict[str, _Array]:
    """domain의 배열 선언(D28)을 base 이름 → _Array로 수집한다."""
    arrays: dict[str, _Array] = {}
    for child in tree.children:
        if not (isinstance(child, lark.Tree) and child.data == "domain_block"):
            continue
        for vd in child.children:
            name_tok, v_idx, _vtype, _desc, _ghost = _var_decl_parts(vd)
            if v_idx is None:
                continue
            base = str(name_tok)
            values = tuple(str(t) for t in v_idx.children)
            if len(set(values)) != len(values):
                raise TextLoaderError(f"배열 '{base}'의 색인 값이 중복됩니다: {values}")
            arrays[base] = _Array(base, values)
    return arrays


def _expand_domain(child: Any) -> Any:
    """domain_block의 배열 선언을 스칼라 가족 var_decl들로 펼친다(선언 순서 유지, D28).

    펼친 이름(`<base>_<idx>`)이 기존/다른 선언과 충돌하면 거부한다(조용한 잠식 금지)."""
    out: list[Any] = []
    seen: set[str] = set()

    def _claim(name: str) -> None:
        if name in seen:
            raise TextLoaderError(
                f"변수 이름 충돌: '{name}' — 배열 펼침(<base>_<색인>)과 기존 선언이 "
                f"겹칩니다. 배열 base나 변수 이름을 바꾸세요(D28)."
            )
        seen.add(name)

    # 충돌은 선언 순서와 무관하게 잡아야 하므로 두 패스: 모든 최종 이름을 먼저 등록.
    for vd in child.children:
        base_tok, v_idx, _vtype, _desc, _ghost = _var_decl_parts(vd)
        if v_idx is not None:
            for idx in v_idx.children:
                _claim(f"{base_tok}_{idx}")
        else:
            _claim(str(base_tok))
    for vd in child.children:
        base_tok, v_idx, type_tree, desc_tree, ghost_tree = _var_decl_parts(vd)
        if v_idx is None:
            out.append(vd)
            continue
        # 배열의 desc(D29)·ghost(D31)는 펼친 원소 전부에 승계된다(가족 공통 속성).
        head = [ghost_tree] if ghost_tree is not None else []
        extra = [desc_tree] if desc_tree is not None else []
        for idx in v_idx.children:
            name_tok = lark.Token("NAME", f"{base_tok}_{idx}")
            out.append(lark.Tree("var_decl", [*head, name_tok, type_tree, *extra]))
    return lark.Tree("domain_block", out)


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


def _eval_index(node: Any, env: dict[str, Any], lhs: bool = False) -> Any:
    base_name = str(node.children[0])
    if base_name not in env:
        raise TextLoaderError(f"미정의 테이블/배열/파라미터: '{base_name}'")
    val: Any = env[base_name]
    if isinstance(val, _Array):
        return _resolve_array_element(val, node, env, lhs=lhs)
    for key_node in node.children[1:]:
        k = _eval_key(key_node, env)
        try:
            val = val[k]
        except (KeyError, IndexError, TypeError) as e:
            raise TextLoaderError(f"표 색인 실패: '{base_name}[...]' ({e!r})") from e
    return val


def _resolve_array_element(
    arr: _Array, node: Any, env: dict[str, Any], lhs: bool = False
) -> str | _IfExpr:
    """배열 색인(D28)을 해소한다 — 정적(리터럴·loop 변수)이면 스칼라 이름
    `<base>_<idx>`, 동적(enum 변수)이면 유한 case-분기 IfExp 식(읽기 전용).

    효과 LHS의 동적 색인은 보류라 거부한다(프레임 의미 수술 필요 — D28)."""
    keys = node.children[1:]
    if len(keys) != 1:
        raise TextLoaderError(f"배열 '{arr.base}'는 색인을 1개만 받습니다(선언이 1차원).")
    key = keys[0]
    if key.data != "key_name":
        raise TextLoaderError(f"배열 '{arr.base}'의 색인은 이름이어야 합니다(수·문자열 불가).")
    name = str(key.children[0])
    if name in env and isinstance(env[name], str):
        name = env[name]  # for loop 변수 → 바인딩 값
    if name in arr.values:
        return f"{arr.base}_{name}"
    ev = env.get(name)
    if isinstance(ev, _EnumVar):
        if lhs:
            raise TextLoaderError(
                f"효과 좌변의 동적 색인('{arr.base}[{name}] = …')은 지원하지 않습니다"
                f"(D28 보류) — 플레이어별 전이(가드 `{name} == 값`) + 정적 색인을 쓰세요."
            )
        missing = sorted(set(ev.values) - set(arr.values))
        if missing:
            raise TextLoaderError(
                f"동적 색인 '{arr.base}[{name}]': enum '{name}'의 값 {missing}이 배열 색인"
                f"(선언: {', '.join(arr.values)})에 없습니다 — 색인 집합이 enum 값을 덮어야 합니다."
            )
        return _IfExpr(_ifexp_text(arr, name, ev.values))
    raise TextLoaderError(
        f"배열 '{arr.base}'에 색인 값 '{name}'가 없습니다 "
        f"(선언: {', '.join(arr.values)}). 동적 색인은 선언된 enum 변수로만 가능합니다(D28)."
    )


def _ifexp_text(arr: _Array, var: str, values: tuple[str, ...]) -> str:
    """동적 색인의 유한 case-분기 문자열: `(a_v1 if var == v1 else (… else a_vn))`."""
    expr = f"{arr.base}_{values[-1]}"
    for v in reversed(values[:-1]):
        expr = f"({arr.base}_{v} if {var} == {v} else {expr})"
    return expr


def _interp_string(token: Any, env: dict[str, Any]) -> Any:
    """id STRING의 `${...}`를 env로 보간(전체/부분 모두 문자열 — id는 항상 문자열)."""
    inner = str(token)[1:-1]

    def repl(m: re.Match[str]) -> str:
        return str(_eval_env_expr(m.group(1), env))

    return lark.Token("STRING", '"' + _TMPL.sub(repl, inner) + '"')


def _subst_tree(node: Any, env: dict[str, Any]) -> Any:
    """식·id 트리에서 loop 변수(name)·표/배열 색인(index)·id `${}`를 env로 해소."""
    if isinstance(node, lark.Token):
        return _interp_string(node, env) if node.type == "STRING" else node
    if node.data == "assign_indexed":
        # 효과 좌변 색인(D28) — 배열의 정적 색인만 허용(동적은 _resolve가 거부).
        lhs_node, rhs = node.children
        base = str(lhs_node.children[0])
        if not isinstance(env.get(base), _Array):
            raise TextLoaderError(f"효과 좌변의 색인('{base}[…] = …')은 배열 변수만 가능합니다.")
        val = _eval_index(lhs_node, env, lhs=True)
        assert isinstance(val, str)  # lhs=True면 동적 색인이 이미 거부됨
        return lark.Tree(node.data, [_literal_tree(val), _subst_tree(rhs, env)])
    if node.data == "index":
        val = _eval_index(node, env)
        if isinstance(val, _IfExpr):
            # 동적 색인(D28) — 완성된 식 문자열을 그대로 통과시키는 verbatim 노드.
            return lark.Tree("verbatim", [lark.Token("NAME", val.text)])
        return _literal_tree(val)
    if node.data == "name":
        nm = str(node.children[0])
        if nm in env and isinstance(env[nm], _Array):
            raise TextLoaderError(
                f"배열 변수 '{nm}'는 색인해서만 씁니다(예: {nm}[{env[nm].values[0]}])."
            )
        if nm in env and isinstance(env[nm], _EnumVar):
            return node  # 도메인 enum 변수 — 치환 대상 아님(동적 색인 판별용 마커)
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


def _expand_for(node: Any, base_env: dict[str, Any], domain_vars: set[str]) -> list[Any]:
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
        env = {**base_env, **dict(zip(params, combo, strict=True))}
        out.append(_subst_tree(template, env))
    return out


def _expand_tree(tree: Any, base_env: dict[str, Any], domain_vars: set[str]) -> Any:
    """table_decl 제거, 배열 선언 펼치기(D28), for_block 펼치기, 그 외 항목은
    tables+arrays-env로 치환(상수·배열 색인 허용)."""
    children: list[Any] = []
    for child in tree.children:
        # table은 데이터로 소비되고 section(D29)은 문서 전용 — 둘 다 IR로 가지 않는다.
        if isinstance(child, lark.Tree) and child.data in ("table_decl", "section_decl"):
            continue
        if isinstance(child, lark.Tree) and child.data == "domain_block":
            children.append(_expand_domain(child))
        elif isinstance(child, lark.Tree) and child.data == "for_block":
            children.extend(_expand_for(child, base_env, domain_vars))
        else:
            children.append(_subst_tree(child, base_env))
    return lark.Tree("start", children)


# ── `[[이름]]` 참조 게이트(D29) — 문서 산문의 드리프트 억제 ──────────────────────
#
# note/desc(변수·table desc·section 제목 포함)의 `[[이름]]`은 모델 요소(변수·enum 값·
# 선언 id·table 이름)를 가리켜야 한다. 존재만 검사한다 — 산문 *내용*의 드리프트는 못
# 잡는다(한계, D29). `ref`는 외부 출처(룰북·URL)라 검사하지 않는다.

_DOCREF = re.compile(r"\[\[([^\[\]]+)\]\]")


def _tree_doc_strings(tree: Any) -> list[tuple[str, str]]:
    """IR에 안 실리는 문서 문자열(D29) — (문맥 라벨, 본문). table desc·section 제목."""
    out: list[tuple[str, str]] = []
    for child in tree.children:
        if not isinstance(child, lark.Tree):
            continue
        if child.data == "section_decl":
            out.append(("section", str(child.children[0])[1:-1]))
        elif child.data == "table_decl":
            for c in child.children[1:]:
                if isinstance(c, lark.Tree) and c.data == "t_desc":
                    out.append((f"table '{child.children[0]}'", str(c.children[0])[1:-1]))
    return out


def _check_doc_refs(rs: RuleSet, table_names: set[str], tree_docs: list[tuple[str, str]]) -> None:
    """문서 본문(note/desc)의 `[[이름]]`이 전부 모델 요소를 가리키는지 검사한다(D29)."""
    known: set[str] = set(table_names)
    for v in rs.variables:
        known.add(v.name)
        known.update(v.values)
    known.update(c.id for c in rs.constraints)
    known.update(e.id for e in rs.expects)
    known.update(t.id for t in rs.transitions)
    known.update(ch.id for ch in rs.checks)

    def scan(where: str, text: str | None) -> None:
        for m in _DOCREF.finditer(text or ""):
            name = m.group(1).strip()
            if name not in known:
                raise TextLoaderError(
                    f"{where}의 문서 참조 [[{name}]]가 미정의입니다 — 변수·enum 값·"
                    f"선언 id·table 이름만 참조할 수 있습니다(D29)."
                )

    for v in rs.variables:
        scan(f"변수 '{v.name}' desc", v.desc)
    decls: list[tuple[str, str, str | None, Any]] = []
    decls += [("constraint", c.id, c.desc, c.doc) for c in rs.constraints]
    decls += [("expect", e.id, e.desc, e.doc) for e in rs.expects]
    decls += [("transition", t.id, t.desc, t.doc) for t in rs.transitions]
    decls += [("check", ch.id, ch.desc, ch.doc) for ch in rs.checks]
    for kind, ident, desc, doc in decls:
        scan(f"{kind} '{ident}' desc", desc)
        if doc is not None:
            for note in doc.notes:
                scan(f"{kind} '{ident}' note", note)
    for where, text in tree_docs:
        scan(where, text)


def parse_rule_text(src: str, source: str | None = None) -> RuleSet:
    """자체 문법 텍스트를 IR로 파싱한다.

    파싱 → 데구거(table/for/${} 펼치기) → IR 변환. `source`는 진단 메시지의 파일명(선택).
    구문 오류·경계 타입 오류·템플릿 오류는 위치 정보와 함께 `TextLoaderError`로 보고한다.
    """
    prefix = f"{source}: " if source else ""
    tree = parse_doc_tree(src, source)

    try:
        tables = _collect_tables(tree)
        arrays = _collect_arrays(tree)
        enum_vars = _collect_enum_vars(tree)
        domain_vars = _collect_domain_vars(tree)
        overlap = set(tables) & set(arrays)
        if overlap:
            raise TextLoaderError(
                f"표(table)와 배열 변수의 이름이 겹칩니다: {sorted(overlap)} — "
                f"색인 구문이 같아 판별할 수 없으니 한쪽 이름을 바꾸세요(D28)."
            )
        overlap_tv = set(tables) & domain_vars
        if overlap_tv:
            raise TextLoaderError(
                f"표(table) 이름이 도메인 변수와 겹칩니다: {sorted(overlap_tv)} — "
                f"치환이 모호해지니 한쪽 이름을 바꾸세요."
            )
        expanded = _expand_tree(tree, {**tables, **arrays, **enum_vars}, domain_vars)
        rs: RuleSet = _TRANSFORMER.transform(expanded)
        _check_doc_refs(rs, set(tables), _tree_doc_strings(tree))
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
