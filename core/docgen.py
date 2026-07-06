"""규칙서 생성기(D29, 12차 P2) — `.lf` 하나에서 사람이 읽는 게임 규칙서를 만든다.

`ludoforge doc`이 호출한다. **desugar *전* 파스 트리**(`parse_doc_tree`)를 소비해 저자가
쓴 접힌 형태(for 템플릿 1개 + 표·section 목차)를 그대로 렌더한다 — IR(검증용, 펼친 구체
항목)과 문서 뷰(표면용)의 요구가 다르기 때문이다(D29). SSOT는 `.lf` 하나, 규칙서는
단방향 파생 뷰(읽기 전용)다.

구성: 목차(section) → 본문(저자 소스 순서 그대로 — 용어집(domain)·데이터 표(table)·
초기 상태·규칙(constraint/transition/expect)이 section 절 아래에 흐름대로) → 마지막에
**검증·추정 성질**(check들을 모아 "이 규칙서가 기계 검증/추정하는 성질"로 — 일반 규칙서와의
차별점). check만 본문 위치에서 빼내 모으고, 나머지는 저자 흐름을 보존한다.

- 표현식·효과는 원문 조각(위치 슬라이스)으로 보여준다 — 재-포매팅하지 않아 저자 표기 보존.
- `[[이름]]` 상호참조(로더가 존재를 이미 검사)는 HTML에서 앵커 링크로, 앵커가 없는
  이름(enum 값·펼친 템플릿 id 등)은 용어 스타일로 렌더한다. Markdown에선 코드 스팬.
- HTML은 자체 완결(인라인 CSS·외부 의존/CDN 없음 — bmc/sim html_report와 동일 규율)이고
  타임스탬프 등 비결정 요소가 없다 — 같은 입력은 같은 출력(결정론).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

import lark

from core.text_loader import _eval_tval, parse_doc_tree

_DOCREF = re.compile(r"\[\[([^\[\]]+)\]\]")

# check kind → 규칙서용 한국어 라벨(백엔드 dialect, D11)
_CHECK_LABEL = {
    "check_reachable": "도달 가능해야 함 (존재 — bmc 증명/sim 추정)",
    "check_invariant": "불변식 (항상 성립 — bmc 증명)",
    "check_no_deadlock": "막다른 상태 없음 (bmc 증명)",
    "check_distribution": "분포 추정 (sim 전용 — 증명 아님)",
}


# ── 문서 모델 — 파스 트리에서 추출한 렌더 입력(불변) ────────────────────────────


@dataclass(frozen=True)
class VarEntry:
    """용어집 항목 — 도메인 변수(배열이면 색인 포함 원문 표기)."""

    name: str
    type_text: str
    desc: str | None


@dataclass(frozen=True)
class TableEntry:
    """데이터 표 — 1단(키→값) 또는 2단(행×열 행렬)."""

    name: str
    desc: str | None
    columns: tuple[str, ...]  # 1단이면 ("값",)
    rows: tuple[tuple[str, tuple[str, ...]], ...]  # (행 키, 셀들)


@dataclass(frozen=True)
class RuleEntry:
    """규칙 항목 — init/constraint/transition/expect/check 공통 렌더 입력.

    `fields`는 (라벨, 원문 조각) 순서쌍 — 예: ("언제", "room == hall and …").
    `outcomes`는 확률 분기 (weight 원문, 효과 원문). `template`은 for 바인딩
    (변수, 값들) — 접힌 템플릿임을 표시한다(D29: 펼치지 않는다).
    """

    kind: str  # "init" | "constraint" | "transition" | "expect" | "check"
    id: str = ""
    desc: str | None = None
    author: str | None = None
    notes: tuple[str, ...] = ()
    ref: str | None = None
    tags: tuple[str, ...] = ()
    fields: tuple[tuple[str, str], ...] = ()
    outcomes: tuple[tuple[str, str], ...] = ()
    template: tuple[tuple[str, tuple[str, ...]], ...] = ()
    check_label: str | None = None


@dataclass(frozen=True)
class Section:
    """규칙서의 한 절 — `section "제목"` 이후의 항목들(첫 section 전은 제목 없는 서두)."""

    title: str | None
    items: tuple[VarEntry | TableEntry | RuleEntry, ...]


@dataclass(frozen=True)
class DocModel:
    title: str
    sections: tuple[Section, ...]
    checks: tuple[RuleEntry, ...]  # 본문에서 빼내 맨 끝 "검증·추정 성질" 절로
    anchors: frozenset[str]  # [[이름]] 링크 대상(변수·표·선언 id)


# ── 트리 → 문서 모델 ────────────────────────────────────────────────────────────


def _slice(src: str, node: Any) -> str:
    """노드가 덮는 원문 조각(위치 슬라이스) — 저자 표기를 보존하되 개행·들여쓰기는
    한 칸 공백으로 접는다(식은 논리적 한 줄 — 여러 줄 가드의 소스 들여쓰기 제거)."""
    if isinstance(node, lark.Token):
        text = src[node.start_pos : node.end_pos]
    else:
        meta = node.meta
        if meta.empty:  # 키워드만으로 이뤄진 노드(bool 등) — 호출부가 폴백을 처리
            return ""
        text = src[meta.start_pos : meta.end_pos]
    return " ".join(text.split())


def _unquote(tok: Any) -> str:
    text = str(tok)
    return text[1:-1] if text.startswith('"') else text


def _meta_pairs(children: list[Any]) -> list[tuple[str, str | tuple[str, ...]]]:
    """선언 자식 중 메타 절(meta_desc/meta_author/meta_note/meta_ref/meta_tag)을 추출."""
    out: list[tuple[str, str | tuple[str, ...]]] = []
    for c in children:
        if not isinstance(c, lark.Tree):
            continue
        if c.data == "meta_tag":
            out.append(("tag", tuple(str(t) for t in c.children)))
        elif c.data in ("meta_desc", "meta_author", "meta_note", "meta_ref"):
            out.append((str(c.data)[5:], _unquote(c.children[0])))
    return out


def _doc_kwargs(children: list[Any]) -> dict[str, Any]:
    """메타 절 → RuleEntry의 desc/author/notes/ref/tags 키워드 인자."""
    desc = author = ref = None
    notes: list[str] = []
    tags: tuple[str, ...] = ()
    for key, val in _meta_pairs(children):
        if key == "desc":
            desc = val
        elif key == "author":
            author = val
        elif key == "note":
            notes.append(str(val))
        elif key == "ref":
            ref = val
        elif key == "tag":
            assert isinstance(val, tuple)
            tags = tags + val
    return {"desc": desc, "author": author, "notes": tuple(notes), "ref": ref, "tags": tags}


def _var_type_text(node: Any) -> str:
    """변수 타입의 표기 — 트리에서 재구성한다(키워드가 익명 토큰이라 슬라이스 불가)."""
    data = str(node.data)
    if data == "enum_type":
        return "enum { " + ", ".join(str(t) for t in node.children) + " }"
    if data == "bool_type":
        return "bool"
    base = "int" if data == "int_type" else "real"
    if not node.children:
        return base
    lo_t, hi_t = node.children[0].children  # range → (range_lo, range_hi)
    lo = str(lo_t.children[0]) if lo_t.children else ""
    hi = str(hi_t.children[0]) if hi_t.children else ""
    return f"{base} {lo}..{hi}"


def _domain_entries(block: Any) -> list[VarEntry]:
    out: list[VarEntry] = []
    for vd in block.children:
        name = str(vd.children[0])
        v_idx = vtype = None
        desc: str | None = None
        for c in vd.children[1:]:
            if isinstance(c, lark.Tree) and c.data == "v_idx":
                v_idx = c
            elif isinstance(c, lark.Tree) and c.data == "meta_desc":
                desc = _unquote(c.children[0])
            else:
                vtype = c
        if v_idx is not None:  # 배열(D28)은 접힌 표기 그대로 — 용어집도 저자 서술을 보존
            name += "[" + ", ".join(str(t) for t in v_idx.children) + "]"
        out.append(VarEntry(name=name, type_text=_var_type_text(vtype), desc=desc))
    return out


def _table_entry(node: Any, src: str) -> TableEntry:
    name = str(node.children[0])
    desc: str | None = None
    entries: list[Any] = []
    for c in node.children[1:]:
        if isinstance(c, lark.Tree) and c.data == "t_desc":
            desc = _unquote(c.children[0])
        elif isinstance(c, lark.Tree) and c.data == "t_entry":
            entries.append(c)
    data = {str(e.children[0]): _eval_tval(e.children[1]) for e in entries}
    if data and all(isinstance(v, dict) for v in data.values()):
        # 2단 표 → 행렬. 열은 첫 행의 키 순서(이후 행의 신규 키는 뒤에 덧붙임).
        columns: list[str] = []
        for row in data.values():
            for k in row:
                if k not in columns:
                    columns.append(k)
        rows = tuple((rk, tuple(str(rv.get(c, "")) for c in columns)) for rk, rv in data.items())
        return TableEntry(name=name, desc=desc, columns=tuple(columns), rows=rows)
    rows = tuple((k, (str(v),)) for k, v in data.items())
    return TableEntry(name=name, desc=desc, columns=("값",), rows=rows)


def _rule_entry(node: Any, src: str) -> RuleEntry:
    """constraint/transition/expect/check/init 트리 → RuleEntry."""
    data = str(node.data)
    if data == "init_decl":
        return RuleEntry(
            kind="init", id="init", fields=(("초기 상태", _slice(src, node.children[0])),)
        )

    ident = _unquote(node.children[0].children[0])
    doc = _doc_kwargs(node.children[1:])

    if data == "constraint_decl":
        fields: list[tuple[str, str]] = []
        for c in node.children[1:]:
            # guard/then/pref 류는 자식(식)을 자른다 — 래퍼 노드는 키워드까지 포함한다.
            if isinstance(c, lark.Tree) and c.data == "guard":
                fields.append(("언제", _slice(src, c.children[0])))
        fields.append(("항상", _slice(src, node.children[-1])))
        return RuleEntry(kind="constraint", id=ident, fields=tuple(fields), **doc)

    if data == "expect_decl":
        return RuleEntry(
            kind="expect",
            id=ident,
            fields=(("도달 가능해야 함", _slice(src, node.children[-1])),),
            **doc,
        )

    if data == "check_decl":
        kind_node = node.children[-1]
        label = _CHECK_LABEL[str(kind_node.data)]
        fields = []
        if kind_node.children:
            what = "값" if kind_node.data == "check_distribution" else "조건"
            fields.append((what, _slice(src, kind_node.children[0])))
        return RuleEntry(kind="check", id=ident, fields=tuple(fields), check_label=label, **doc)

    assert data == "transition_decl", data
    fields = []
    outcomes: list[tuple[str, str]] = []
    for c in node.children[1:]:
        if not isinstance(c, lark.Tree):
            continue
        if c.data == "t_guard":
            fields.append(("언제", _slice(src, c.children[0])))
        elif c.data == "t_player":
            fields.append(("행위자", str(c.children[0])))
        elif c.data == "t_pref":
            fields.append(("선호도(pref)", _slice(src, c.children[0])))
        elif c.data == "then_body":
            fields.append(("효과", _slice(src, c.children[0])))
        elif c.data == "outcomes_body":
            for oc in c.children:
                w, upd = oc.children
                outcomes.append((_slice(src, w), _slice(src, upd)))
    return RuleEntry(
        kind="transition", id=ident, fields=tuple(fields), outcomes=tuple(outcomes), **doc
    )


def _for_entry(node: Any, src: str) -> RuleEntry:
    """for 템플릿 — 내부 항목을 접힌 형태 그대로(치환 없이) 렌더하고 바인딩을 표시한다."""
    *bindings, template = node.children
    binds = tuple((str(b.children[0]), tuple(str(t) for t in b.children[1:])) for b in bindings)
    entry = _rule_entry(template, src)
    return RuleEntry(
        kind=entry.kind,
        id=entry.id,
        desc=entry.desc,
        author=entry.author,
        notes=entry.notes,
        ref=entry.ref,
        tags=entry.tags,
        fields=entry.fields,
        outcomes=entry.outcomes,
        template=binds,
        check_label=entry.check_label,
    )


def build_doc_model(src: str, title: str, source: str | None = None) -> DocModel:
    """`.lf` 원문 → 문서 모델. 파싱만 한다 — 스키마·참조 검증은 호출부(CLI) 책임."""
    tree = parse_doc_tree(src, source)
    sections: list[Section] = []
    checks: list[RuleEntry] = []
    anchors: set[str] = set()
    cur_title: str | None = None
    cur_items: list[VarEntry | TableEntry | RuleEntry] = []

    def flush() -> None:
        if cur_items or cur_title is not None:
            sections.append(Section(title=cur_title, items=tuple(cur_items)))

    for child in tree.children:
        assert isinstance(child, lark.Tree)
        data = str(child.data)
        if data == "section_decl":
            flush()
            cur_title = _unquote(child.children[0])
            cur_items = []
            continue
        if data == "domain_block":
            entries = _domain_entries(child)
            cur_items.extend(entries)
            anchors.update(e.name.split("[")[0] for e in entries)
        elif data == "table_decl":
            te = _table_entry(child, src)
            cur_items.append(te)
            anchors.add(te.name)
        elif data == "for_block":
            entry = _for_entry(child, src)
            (checks if entry.kind == "check" else cur_items).append(entry)
            anchors.add(entry.id)
        else:
            entry = _rule_entry(child, src)
            if entry.kind == "check":
                checks.append(entry)
            elif entry.kind == "init":
                cur_items.append(entry)
            else:
                cur_items.append(entry)
                anchors.add(entry.id)
    flush()
    anchors.update(c.id for c in checks)
    return DocModel(
        title=title, sections=tuple(sections), checks=tuple(checks), anchors=frozenset(anchors)
    )


# ── Markdown 렌더 ────────────────────────────────────────────────────────────────

_KIND_LABEL = {
    "init": "초기 상태",
    "constraint": "제약",
    "transition": "행동/사건",
    "expect": "도달성 단언",
    "check": "검증 성질",
}


def _md_text(text: str) -> str:
    """문서 산문 — [[이름]]을 코드 스팬으로(GH Markdown엔 안정적 앵커가 없다)."""
    return _DOCREF.sub(lambda m: f"`{m.group(1).strip()}`", text)


def _md_rule(e: RuleEntry) -> list[str]:
    head = f"### {e.id} — {_KIND_LABEL[e.kind]}" if e.kind != "init" else "### 초기 상태"
    out = [head, ""]
    if e.template:
        combo = " × ".join(f"{v} ∈ {{{', '.join(vals)}}}" for v, vals in e.template)
        out += [f"*템플릿 — {combo} 조합마다 하나씩.*", ""]
    if e.desc:
        out += [_md_text(e.desc), ""]
    meta_bits = [b for b in (e.author and f"작성 {e.author}", e.ref and f"출처 {e.ref}") if b]
    if e.tags:
        meta_bits.append("태그 " + ", ".join(e.tags))
    if meta_bits:
        out += ["*" + " · ".join(meta_bits) + "*", ""]
    if e.check_label:
        out += [f"- **종류**: {e.check_label}"]
    out += [f"- **{label}**: `{text}`" for label, text in e.fields]
    if e.outcomes:
        out.append("- **결과** (확률 → 효과):")
        out += [f"  - `{w}` → `{u}`" for w, u in e.outcomes]
    out.append("")
    for note in e.notes:
        out += [f"> {_md_text(note)}", ""]
    return out


def render_doc_markdown(src: str, title: str, source: str | None = None) -> str:
    """`.lf` 원문 → Markdown 규칙서."""
    model = build_doc_model(src, title, source)
    out: list[str] = [f"# {model.title}", ""]
    toc = [s.title for s in model.sections if s.title]
    if toc:
        out += ["## 목차", ""] + [f"- {t}" for t in toc] + ["- 검증·추정 성질", ""]
    for sec in model.sections:
        if sec.title:
            out += [f"## {sec.title}", ""]
        glossary = [i for i in sec.items if isinstance(i, VarEntry)]
        if glossary:
            out += ["### 용어집", "", "| 변수 | 타입 | 설명 |", "|---|---|---|"]
            out += [
                f"| `{v.name}` | `{v.type_text}` | {_md_text(v.desc or '')} |" for v in glossary
            ]
            out.append("")
        for item in sec.items:
            if isinstance(item, VarEntry):
                continue
            if isinstance(item, TableEntry):
                out += [f"### 표 {item.name}", ""]
                if item.desc:
                    out += [_md_text(item.desc), ""]
                out += [
                    "| " + " | ".join(("",) + item.columns) + " |",
                    "|" + "---|" * (len(item.columns) + 1),
                ]
                out += ["| **" + rk + "** | " + " | ".join(cells) + " |" for rk, cells in item.rows]
                out.append("")
            else:
                out += _md_rule(item)
    if model.checks:
        out += [
            "## 검증·추정 성질",
            "",
            "이 규칙서의 아래 성질은 기계가 검증/추정한다"
            " (`ludoforge bmc` 증명 · `ludoforge sim` 추정).",
            "",
        ]
        for c in model.checks:
            out += _md_rule(c)
    return "\n".join(out).rstrip() + "\n"


# ── HTML 렌더 (자체 완결 — bmc/sim html_report 규율) ────────────────────────────

_CSS = """
:root {
  --bg: #0d1117; --panel: #161b22; --border: #30363d; --fg: #e6edf3;
  --muted: #8b949e; --accent: #58a6ff; --ok: #3fb950; --warn: #d29922; --cfg: #bc8cff;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0; padding: 2rem;
  font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif; line-height: 1.55; }
.wrap { max-width: 900px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
h2 { font-size: 1.2rem; color: var(--cfg); margin: 2rem 0 .75rem;
  padding-bottom: .4rem; border-bottom: 1px solid var(--border); }
.subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.5rem; }
.toc { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: .9rem 1.25rem; margin-bottom: 1.5rem; }
.toc a { color: var(--accent); text-decoration: none; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 1rem 1.25rem; margin: 0 0 1rem; }
.card h3 { margin: 0 0 .4rem; font-size: 1rem; }
.kind { color: var(--muted); font-weight: 400; font-size: .8rem; margin-left: .4rem; }
.tmpl { color: var(--cfg); font-size: .82rem; margin: .1rem 0 .4rem; }
.desc { color: var(--fg); margin: .2rem 0 .5rem; }
.meta { color: var(--muted); font-size: .8rem; margin: .2rem 0 .5rem; }
.field { font-size: .9rem; margin: .25rem 0; }
.field .label { color: var(--muted); display: inline-block; min-width: 7.5rem; }
code { background: #21262d; border-radius: 4px; padding: .1rem .35rem;
  font-family: ui-monospace, "Cascadia Code", monospace; font-size: .85em; }
.note { border-left: 3px solid var(--accent); color: var(--muted);
  padding: .15rem .75rem; margin: .5rem 0; font-size: .88rem; }
table { border-collapse: collapse; margin: .5rem 0 1rem; font-size: .88rem; }
th, td { border: 1px solid var(--border); padding: .3rem .7rem; text-align: left; }
th { color: var(--muted); font-weight: 600; background: #1c2129; }
a.xref { color: var(--accent); text-decoration: none; border-bottom: 1px dotted var(--accent); }
.term { color: var(--accent); }
.checks-intro { color: var(--muted); font-size: .88rem; margin-bottom: 1rem; }
.tag { display: inline-block; background: #21262d; border: 1px solid var(--border);
  border-radius: 10px; padding: 0 .5rem; font-size: .75rem; color: var(--muted);
  margin-right: .3rem; }
.foot { color: var(--muted); font-size: .75rem; margin-top: 2rem; text-align: center; }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _html_text(text: str, anchors: frozenset[str]) -> str:
    """산문 — 이스케이프 후 [[이름]]을 앵커 링크(정의로 이동)로. 앵커 없는 이름
    (enum 값·펼친 템플릿 id 등)은 용어 스타일만 입힌다(죽은 링크 방지)."""

    def repl(m: re.Match[str]) -> str:
        name = m.group(1).strip()
        if name in anchors:
            return f'<a class="xref" href="#def-{name}">{name}</a>'
        return f'<span class="term">{name}</span>'

    return _DOCREF.sub(repl, _esc(text))


def _html_rule(e: RuleEntry, anchors: frozenset[str]) -> str:
    kind = _KIND_LABEL[e.kind] if not e.check_label else e.check_label
    out = [f'<div class="card" id="def-{_esc(e.id)}">']
    out.append(f'<h3>{_esc(e.id)}<span class="kind">{_esc(kind)}</span></h3>')
    if e.template:
        combo = " × ".join(f"{v} ∈ {{{', '.join(vals)}}}" for v, vals in e.template)
        out.append(f'<div class="tmpl">템플릿 — {_esc(combo)} 조합마다 하나씩</div>')
    if e.desc:
        out.append(f'<div class="desc">{_html_text(e.desc, anchors)}</div>')
    meta_bits = [b for b in (e.author and f"작성 {e.author}", e.ref and f"출처 {e.ref}") if b]
    if meta_bits:
        out.append(f'<div class="meta">{_esc(" · ".join(meta_bits))}</div>')
    if e.tags:
        out.append(
            '<div class="meta">' + "".join(f'<span class="tag">{_esc(t)}</span>' for t in e.tags)
        )
        out.append("</div>")
    for label, text in e.fields:
        out.append(
            f'<div class="field"><span class="label">{_esc(label)}</span>'
            f"<code>{_esc(text)}</code></div>"
        )
    if e.outcomes:
        out.append('<div class="field"><span class="label">결과(확률 → 효과)</span></div>')
        for w, u in e.outcomes:
            out.append(
                f'<div class="field" style="margin-left:1rem"><code>{_esc(w)}</code>'
                f" → <code>{_esc(u)}</code></div>"
            )
    for note in e.notes:
        out.append(f'<div class="note">{_html_text(note, anchors)}</div>')
    out.append("</div>")
    return "\n".join(out)


def _html_glossary(items: list[VarEntry], anchors: frozenset[str]) -> str:
    rows = "\n".join(
        f'<tr id="def-{_esc(v.name.split("[")[0])}"><td><code>{_esc(v.name)}</code></td>'
        f"<td><code>{_esc(v.type_text)}</code></td>"
        f"<td>{_html_text(v.desc or '', anchors)}</td></tr>"
        for v in items
    )
    return (
        "<h3>용어집</h3>\n<table><thead><tr><th>변수</th><th>타입</th><th>설명</th>"
        f"</tr></thead><tbody>\n{rows}\n</tbody></table>"
    )


def _html_table(t: TableEntry, anchors: frozenset[str]) -> str:
    head = "".join(f"<th>{_esc(c)}</th>" for c in t.columns)
    body = "\n".join(
        f"<tr><th>{_esc(rk)}</th>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>"
        for rk, cells in t.rows
    )
    desc = f'<div class="desc">{_html_text(t.desc, anchors)}</div>' if t.desc else ""
    return (
        f'<div id="def-{_esc(t.name)}"><h3>표 {_esc(t.name)}</h3>{desc}\n'
        f"<table><thead><tr><th></th>{head}</tr></thead><tbody>\n{body}\n</tbody></table></div>"
    )


def render_doc_html(src: str, title: str, source: str | None = None) -> str:
    """`.lf` 원문 → 자체 완결형 HTML 규칙서(외부 의존성 없음, 결정론)."""
    model = build_doc_model(src, title, source)
    parts: list[str] = []
    toc = [s.title for s in model.sections if s.title]
    if toc:
        links = "".join(f'<li><a href="#sec-{i}">{_esc(t)}</a></li>' for i, t in enumerate(toc))
        links += '<li><a href="#sec-checks">검증·추정 성질</a></li>'
        parts.append(f'<div class="toc"><b>목차</b><ul>{links}</ul></div>')
    sec_no = 0
    for sec in model.sections:
        if sec.title:
            parts.append(f'<h2 id="sec-{sec_no}">{_esc(sec.title)}</h2>')
            sec_no += 1
        glossary = [i for i in sec.items if isinstance(i, VarEntry)]
        if glossary:
            parts.append(_html_glossary(glossary, model.anchors))
        for item in sec.items:
            if isinstance(item, VarEntry):
                continue
            if isinstance(item, TableEntry):
                parts.append(_html_table(item, model.anchors))
            else:
                parts.append(_html_rule(item, model.anchors))
    if model.checks:
        parts.append('<h2 id="sec-checks">검증·추정 성질</h2>')
        parts.append(
            '<div class="checks-intro">아래 성질은 산문 약속이 아니라 기계가 확인한다 — '
            "<code>ludoforge bmc</code>(증명)·<code>ludoforge sim</code>(추정).</div>"
        )
        parts.extend(_html_rule(c, model.anchors) for c in model.checks)
    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(model.title)}</title>\n"
        f"<style>{_CSS}</style></head>\n"
        '<body><div class="wrap">\n'
        f"<h1>{_esc(model.title)}</h1>\n"
        '<div class="subtitle">이 규칙서는 기계 검증 가능한 SSOT(.lf)에서 생성된 파생'
        " 뷰입니다 — 규칙 수정은 원본 .lf에서.</div>\n"
        f"{body}\n"
        '<div class="foot">Ludoforge · ludoforge doc (D29) — .lf에서 생성됨</div>\n'
        "</div></body></html>\n"
    )
