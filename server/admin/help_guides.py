# -*- coding: utf-8 -*-
"""The admin help's declaration answer (owner 10-29 «선언법도 도우미에», lead): the declaration guides cut into
sections, the three nearest a guide-worded search picked, the model writing one declaration from them, and that
declaration put through the save's own judgement without saving.

    guides      the five below - cut at headings, at bold numbered items (**①…), a section over CAP split at table rows
                or blank lines with its table's header row; the Status line out, and of the rest only the SENTENCES
                with a retired mark (⚰ 🪦) - a current rule on the same line stays
    pick        character 2- and 3-gram BM25 over section name + text, no package
    answer      {"kind", "name", "declaration", "why", "sections"} - a section the pieces do not name is dropped
    check       chain_rule · table: the save itself, stopped before its write (`check_only`); ledger: the draft
                preview's judgement (`compile_draft_preview`) on the node the answer names; else «not checked»
Measured on the box (lead 10-29, 20 operator questions, guide-worded searches): the right section in the three 19-20
of 20, the declaration prompt 2.1k-3.4k tokens estimated.
"""
import collections
import json
import math
import os
import re

import paths

GUIDES = ("docs/guide/config/chain_rules.md", "docs/guide/config/table_config.md",
          "docs/guide/config/ledger_declaration_by_example.md", "docs/guide/config/enrichment_rules.md",
          "docs/guide/CONFIG_ROLLOUT_GUIDE.md")
#: A section longer than this many characters is split at its table rows / blank lines.
CAP = 2000
#: Sections the declaration prompt carries.
PICKED = 3
#: The sections' estimated tokens the prompt may carry - more stop at the first that would pass it (one always goes).
SECTION_TOKENS = 3800
KINDS = ("chain_rule", "table", "ledger")

_HEADING = re.compile(r"^(#{1,4})\s+(.*)")
_ITEM = re.compile(r"^\*\*([①-⑳].*?)\*\*")
_RETIRED = re.compile(r"[⚰🪦]")
_SENTENCE = re.compile(r"(?<=[.!?。»」)])\s+(?=\S)")
_TABLE_RULE = re.compile(r"^\|[\s:|-]+\|?$")

SYSTEM = ("You write ONE declaration that answers an operator's question, from the guide sections below only. Answer "
          'one JSON object: {"kind": "chain_rule" | "table" | "ledger", "name": the chain rule\'s name, the table\'s '
          'name, or for the ledger the declaration\'s path such as sources.<id>, "declaration": the JSON object to '
          'save under that name, "why": one short English sentence, "sections": the names of the sections you used, '
          "copied exactly as they are given}. Use only cells the sections show.")


def estimated_tokens(text):
    """Tokens as the high estimate: 4 characters a token, a Hangul syllable 2 (the prompt cap's measure)."""
    hangul = len(re.findall(r"[가-힣]", text))
    return (len(text) - hangul) / 4 + 2 * hangul


def _sentences_kept(line):
    """`line` without the Status line and without the sentences that carry a retired mark - None when nothing is left."""
    if line.startswith("> **Status"):
        return None
    if not _RETIRED.search(line):
        return line
    kept = [sentence for sentence in _SENTENCE.split(line) if not _RETIRED.search(sentence)]
    return " ".join(kept) if kept else None


def _split(text):
    """A long section's pieces, each table piece led by its table's header row."""
    rows, header = text.split("\n"), None
    for n, row in enumerate(rows):
        if row.startswith("|") and n + 1 < len(rows) and _TABLE_RULE.match(rows[n + 1]):
            header = row + "\n" + rows[n + 1]
    pieces, current = [], ""
    for block in re.split(r"\n(?=\| )|\n\n", text):
        if current and len(current) + len(block) > CAP:
            pieces.append(current)
            current = header + "\n" if header and block.startswith("| ") else ""
        current = (current + "\n" + block) if current else block
    return pieces + [current]


def cut(guide, text):
    """[{"name", "text"}] of one guide's text - its sections, the history sentences out."""
    out, path, item, body, fence = [], [], None, [], False

    def close():
        joined = "\n".join(body).strip()
        if not (path and joined):
            return
        name = "%s: %s" % (os.path.basename(guide), " > ".join(path + ([item] if item else [])))
        pieces = _split(joined) if len(joined) > CAP else [joined]
        for k, piece in enumerate(pieces):
            out.append({"name": name + ("" if len(pieces) == 1 else " (part %d)" % (k + 1)), "text": piece})

    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
        heading = None if fence else _HEADING.match(line)
        if heading:
            close()
            level = len(heading.group(1))
            path, item, body = path[:level - 1] + [heading.group(2).strip()], None, []
            continue
        numbered = None if fence else _ITEM.match(line)
        if numbered:
            close()
            item, body = numbered.group(1).strip(), []
        kept = _sentences_kept(line)
        if kept is not None:
            body.append(kept)
    close()
    return out


def _grams(text):
    text = re.sub(r"\s+", " ", text.lower())
    return [text[i:i + n] for n in (2, 3) for i in range(len(text) - n + 1) if text[i:i + n].strip()]


class _Index:
    def __init__(self, pieces, k1=1.2, b=0.75):
        self.pieces = pieces
        self.tf = [collections.Counter(_grams(p["name"] + "\n" + p["text"])) for p in pieces]
        self.length = [sum(tf.values()) for tf in self.tf]
        average = sum(self.length) / len(self.length) if self.length else 1
        df = collections.Counter(g for tf in self.tf for g in tf)
        self.idf = {g: math.log(1 + (len(pieces) - f + 0.5) / (f + 0.5)) for g, f in df.items()}
        self.norm = [k1 * (1 - b + b * n / average) for n in self.length]
        self.k1 = k1

    def nearest(self, search, count):
        grams = set(_grams(search))
        scored = [(sum(self.idf[g] * tf[g] * (self.k1 + 1) / (tf[g] + self.norm[i]) for g in grams if g in tf), i)
                  for i, tf in enumerate(self.tf)]
        return [self.pieces[i] for _score, i in sorted(scored, reverse=True)[:count]]


_built = {"stamp": None, "index": None}


def _stamp():
    """(path, mtime_ns, size) of each guide - None for a missing one. The config watcher is not asked: it watches the
    config files (its contract), not docs/ (lead 10-29)."""
    stamp = []
    for guide in GUIDES:
        try:
            st = os.stat(os.path.join(paths.REPO_ROOT, guide))
            stamp.append((guide, st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append((guide, None, None))
    return tuple(stamp)


def index():
    """The guides' sections, cut again only when a guide changed (`_stamp`). A missing guide is refused by name."""
    stamp = _stamp()
    missing = [guide for guide, at, _size in stamp if at is None]
    if missing:
        raise LookupError("guide not found: %s" % ", ".join(os.path.join(paths.REPO_ROOT, g) for g in missing))
    if _built["stamp"] != stamp:
        pieces = []
        for guide in GUIDES:
            with open(os.path.join(paths.REPO_ROOT, guide), encoding="utf-8") as handle:
                pieces += cut(guide, handle.read())
        _built.update(stamp=stamp, index=_Index(pieces))
    return _built["index"]


def nearest(search):
    """The sections the declaration prompt carries for `search`: the PICKED nearest, stopped before one would pass
    SECTION_TOKENS (the first always goes)."""
    out, spent = [], 0
    for piece in index().nearest(search, PICKED):
        cost = estimated_tokens(piece["name"] + "\n" + piece["text"])
        if out and spent + cost > SECTION_TOKENS:
            break
        out.append(piece)
        spent += cost
    return out


def prompt_of(question, pieces):
    return ("Guide sections:\n\n" + "\n\n".join("## %s\n%s" % (p["name"], p["text"]) for p in pieces)
            + "\n\nQuestion: " + question)


def check(kind, name, declaration):
    """The save's own judgement of `declaration`, nothing written -> {"ok": True, "said"} · {"ok": False, "said"} ·
    {"not_checked": why}."""
    from fastapi import HTTPException

    from ledger import admin

    if kind not in KINDS:
        return {"not_checked": "unknown declaration kind %r - one of %s" % (kind, ", ".join(KINDS))}
    if not isinstance(declaration, dict) or not (isinstance(name, str) and name.strip()):
        return {"not_checked": "the answer gave no name and declaration object to check"}
    try:
        if kind == "chain_rule":
            said = admin.save_chain_rule_raw(name, declaration, admin.file_fingerprint(admin.chain_rules_path()),
                                             check_only=True)
        elif kind == "table":
            said = admin.save_table_config_raw(name, declaration,
                                               admin.file_fingerprint(admin.table_config_path()), check_only=True)
        else:
            return _ledger_check(name, declaration)
    except HTTPException as refused:
        detail = refused.detail if isinstance(refused.detail, dict) else {"message": str(refused.detail)}
        return {"ok": False, "said": detail.get("message") or str(detail)}
    except Exception as e:                                           # noqa: BLE001 - said on the answer
        from error_said import told

        return {"not_checked": "the check itself failed: %s: %s" % (type(e).__name__, told(e))}
    return {"ok": True, "said": " · ".join(said.get("notes") or ()) or None}


def _ledger_check(target, declaration):
    """The ledger draft preview's judgement of `declaration` at `target` (a declaration path such as sources.<id>)."""
    from ledger.config_drafts import compile_draft_preview
    from ledger_api.ontology_config_explorer_router import _service_for

    setup, explorer, _hash = _service_for(None).active()
    node = next((node for node in explorer.nodes.values()
                 if ".".join(str(part) for part in node.bundle_path) == target.strip()), None)
    if node is None:
        return {"not_checked": "the ledger declaration has no %r to check against - only an existing one is checked"
                               % target}
    preview = compile_draft_preview(setup, node, declaration)
    if preview.valid:
        return {"ok": True, "said": None}
    return {"ok": False, "said": " | ".join(str(error.get("message")) for error in preview.errors)}


def answer(question, search, ask_json):
    """One declaration for `question` -> {"kind", "name", "declaration", "why", "sections", "dropped_sections",
    "check", "refused"}. `search` is the model's guide-worded search from the help's first ask."""
    from utils import llm

    try:
        pieces = nearest(search or question)
    except LookupError as missing:
        return {"refused": str(missing), "sections": [], "dropped_sections": 0, "check": {"not_checked": str(missing)}}
    try:
        said = ask_json(prompt_of(question, pieces), system=SYSTEM)
    except llm.LlmRefused as e:                                    # not JSON, or the call failed - said
        return {"refused": str(e), "sections": [], "dropped_sections": 0, "check": {"not_checked": str(e)}}
    names = {p["name"] for p in pieces}
    cited = list(dict.fromkeys(s for s in said.get("sections") or () if isinstance(s, str)))
    kept = [s for s in cited if s in names]
    return {"kind": said.get("kind"), "name": said.get("name"), "declaration": said.get("declaration"),
            "why": said.get("why"), "sections": kept, "dropped_sections": len(cited) - len(kept),
            "check": check(said.get("kind"), said.get("name"), said.get("declaration")), "refused": None}
