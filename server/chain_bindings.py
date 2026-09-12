"""Which column of a table carries the DT job identity — READ, never assumed.

WHY THIS MODULE EXISTS
----------------------
Every chain mapper used to spell the job column ``dt_job``: either as a bare literal
(``_value(payload, "dt_job")``), or as the default half of
``rule.get("job_column", "dt_job")``.  A default that is only correct on the machine
that wrote it is worse than no default, because nobody ever has to declare the name
and so nobody ever finds out it is wrong.  The failure is SILENT at BOTH ends:

  * READING — ``_value(payload, "dt_job")`` returns ``None`` for a name the payload
    does not carry.  The mapper skips the row, returns an empty batch, and the chain
    worker records SUCCESS.  The loud ``source.dt_job`` ``AttributeError`` a few lines
    below is never reached, because the silent read already returned.
  * WRITING — ``crud.apply_batch_updates`` DROPS an ``updates`` key the target table
    does not declare in ``column_types``, warns once per ``(table, column)`` per
    process, and the write still returns success.

So a deployment that spells the column differently gets three dead chains, no
exception anywhere, and a 200.  No fixture in this repository could express that,
because every fixture writes ``dt_job``.

THE RULE
--------
::

    rule declaration  >  table_config derivation  >  refuse by name

There is no literal fallback.  ``68db020`` established exactly this precedence for map
coordinate bindings and deleted the convention fallback there for the same reason: a
name nobody declared, resolved to a convention, is a wrong answer wearing a configured
answer's clothes.  A refusal here names the rule, the config key, the table, and the
column, so the operator is told which declaration to write instead of being handed a
name that happens to work on one box.

PER TABLE, NOT PER CHAIN
------------------------
One mapper reads a trigger payload, queries a source table, and writes a target table.
Those are three different tables and they may legally spell the job differently — that
is precisely the case the single literal could not express.  Ask each table for its own
name, and let the rule override each one independently.

WHY NOT AN EXISTING PRIMITIVE
-----------------------------
The ``map_key_columns`` read IS an existing primitive and is reused:
``dt_map_derivation.identity_columns`` already reads it and already refuses by name.
This module wraps it rather than re-reading the key, so the chain and the dt_map
derivation cannot disagree about what a table's identity is.  What is added here and
does not belong there is (a) the rule-declaration layer, which is chain config that the
derivation engine has no business knowing about, and (b) the single-column
``business_key`` inheritance, which answers for a row-grained table like
``dt_inventory`` that is not a map at all.

``map_overlay.resolve_binding_parts`` is the other binding resolver and is deliberately
NOT reused: its precedence base is ``map_overlay_config.table_bindings``, it answers
about map coordinates, and it carries a lot/slot convention fallback that this change
exists to avoid.

DEPLOYMENT
----------
This module is TRACKED.  ``server/mappers/*.py`` is gitignored (only ``*.py.sample``
ships), so a helper placed beside the mappers would not reach a deployment at all.
"""
from __future__ import annotations

import logging

import dt_map_derivation

logger = logging.getLogger(__name__)


# Where a resolved name came from. Same vocabulary as `map_overlay`'s binding
# provenance, so an operator reading two refusals reads one language.
ORIGIN_DECLARED = "declared"
ORIGIN_INHERITED = "inherited"

_FROM_MAP_KEY_COLUMNS = "table_config.map_key_columns"
_FROM_BUSINESS_KEY = "table_config.business_key"


class ColumnBindingRefused(ValueError):
    """A column name could not be resolved, and the message NAMES what is missing.

    Subclasses ``ValueError`` on purpose: the chain worker aborts the transaction on
    any exception and logs the traceback, and the API layer already maps ``ValueError``
    to a 400 with the message body (same treatment as the ``replace_map`` scope
    refusal).  A new exception type would have needed both to be taught about it.
    """


def _table_config(table: str) -> dict:
    """Live declaration for `table`.

    Read through the module attribute every time — `crud.TABLE_CONFIG` is mutated in
    place on hot reload, so a snapshot taken at import goes stale silently.
    """
    from database import crud
    return (crud.TABLE_CONFIG or {}).get(table) or {}


def declared_columns(table: str):
    """Column names `table_config` states for `table`, or None if it states nothing.

    None means "I cannot judge this declaration" and is why a table absent from
    `table_config` keeps working instead of being refused.
    """
    types = _table_config(table).get("column_types")
    if not isinstance(types, dict) or not types:
        return None
    return set(types.keys())


def identity_column(table: str):
    """`(column, from)` derived from `table_config` alone, or `(None, why_not)`.

    Order:
      1. ``map_key_columns`` when it names EXACTLY ONE column — that column says which
         map/unit a row belongs to, which for these tables is the job.
      2. ``business_key`` when the table declares no ``composite_key_source`` and the
         business key is itself a declared column.  A table with no map key whose row
         identity is a single column is keyed by that column outright — ``dt_inventory``
         is one row per job and its business key IS the job.  The
         ``composite_key_source`` gate is what stops a composite CELL key
         (``dt_cell_key``, ``cell_key``, ``core_usage_cell_key``) from being mistaken
         for an identity column.
      3. Nothing.  Not a guess.
    """
    try:
        cols = dt_map_derivation.identity_columns(table)
    except dt_map_derivation.DerivationRefused:
        cols = []
    if len(cols) == 1:
        return cols[0], _FROM_MAP_KEY_COLUMNS
    if len(cols) > 1:
        return None, ("'%s' declares %d map_key_columns (%s), so which one carries the "
                      "job is not derivable" % (table, len(cols), ", ".join(cols)))

    cfg = _table_config(table)
    business_key = cfg.get("business_key")
    known = declared_columns(table)
    if (isinstance(business_key, str) and business_key.strip()
            and not cfg.get("composite_key_source")
            and known is not None and business_key in known):
        return business_key, _FROM_BUSINESS_KEY
    return None, ("'%s' declares neither a single-column 'map_key_columns' nor a "
                  "single-column 'business_key'" % table)


# ---------------------------------------------------------------------------
# 규칙 선언에서 «표 이름을 나르는» 키 — 그리고 그 표를 «읽는가 쓰는가»
# ---------------------------------------------------------------------------
# 🔴 열거가 «여기 하나»다. 검증기·순서 가드·맵퍼 읽기 검사가 «전부» 이것을 읽는다.
#    세 자리가 각자 목록을 들면, 새 키가 생긴 날 «하나»가 그것을 모르고 그 표가 조용히 빠진다 —
#    이 줄의 사실이 정확히 그것이다: 모델과 가드가 «셋»만 알아서 선언된 교차 «다섯»이
#    순서 가드에 «한 번도» 안 보였다.
# ⚠️ 역할은 «실측»이지 이름이 아니다. `metadata_target_table` 은 이름이 target 인데
#    `dt_inventory_metadata_mapper` 가 그것을 «source 로» 읽는다. 그래서 read 다.
#    ⛔ 개명하지 않는다 — 운영자가 적는 키이고, 이름을 바꾸는 것은 조작자 표면이다.
# ⚠️ 가상 조인의 `left_table`/`right_table` 은 여기 «없다» — 그 둘은 «비교»이지 «열기»가
#    아니라서 읽기가 아니다(실측: `dt_map_mapper:129·131`).
TABLE_ROLE_READ = "read"
TABLE_ROLE_WRITE = "write"

RULE_TABLE_KEYS = {
    "trigger_table": TABLE_ROLE_READ,
    "source_table": TABLE_ROLE_READ,
    "target_table": TABLE_ROLE_WRITE,
    "map_table": TABLE_ROLE_READ,
    "inventory_table": TABLE_ROLE_READ,
    "metadata_target_table": TABLE_ROLE_READ,
    "derivation_source_table": TABLE_ROLE_READ,
}

#: 위 키들로 «표현 못 하는» 읽기를 담는 일반 슬롯 — 예: `load_map_meta` 가 여는
#: `wafer_map_metadata`. ⛔ 목적마다 새 키를 만들지 않는다. 새 목적은 여기 «값»으로 적힌다.
READS_KEY = "reads"


#: 실행 «시점»에 정해지되 «집합»은 선언인 표 — `reference_spec` 이 이름 댈 수 있는 전부.
#: 🔴 `core_alignment_mapper._reference_spec` 은 `"{table}:{map_id}"` 를 만드는데 «표는»
#:    `rule["reference"]["table"]` 에서 오고 «map_id 만» 실행 시점에 정해진다. 그래서 순서
#:    가드가 볼 수 있다 — 이름은 몰라도 «집합»은 선언이 안다.
#: ⛔ 해석기를 고쳐 「읽은 표」를 반환에 «더하지» 않는다. 그건 실행 «뒤»라 순서 판단에 늦다.
REFERENCE_BLOCK = "reference"
REFERENCE_TABLE_KEY = "table"

# ---------------------------------------------------------------------------
# S-188 ⓐ — 체인 규칙의 «최상위» 칸 전부, 한 목록 (판정 300)
# ---------------------------------------------------------------------------
#: 🔴 이 목록의 주어는 «워커»가 아니라 «규칙을 받는 모듈 전부»다. 워커의 `rule.get` 전수는
#: 열하나인데, `chain_graph._mapper_edges`/`_contested`/`_contested_tables` 가 «워커가 안 읽는»
#: 넷을 더 읽는다 — `target_field` · `max_group_attempts` · `origin` · `params`. 열하나로 닫으면
#: 오늘 도는 것이 거절된다(실측 2026-09-12).
#:
#: ⚠️ 합성 규칙이 `params` «안»에 두는 이름은 여기 «없다» — `decision_key` ·
#: `reference_views` · `aggregations` · `alignment` 은 인리치 규칙의 칸이거나 `params` 의
#: 내용이고, 최상위에서 읽히지 않는다(`chain_graph:97` 이 `params` 를 꺼낸 «뒤» 읽는다).
#: 인리치·가상 조인 규칙의 칸을 여기 섞으면 «세 파일의 문법»이 한 목록이 되고, 그러면 이
#: 목록은 아무것도 거절하지 못한다.
#:
#: 🔴 `RULE_TABLE_KEYS` 는 이것의 «부분집합»이고 그 관계를 시험이 못 박는다. 표 키가 하나
#: 늘 때 이 목록에도 적어야 한다는 것을 사람이 기억하게 두지 않는다 — 위 `rule_tables` 의
#: 「여기서 다시 열거하지 않는다」와 같은 규율이다.
RULE_ROUTING_REQUIRED = ("name", "trigger_table")

#: ⚠️ `target_table` · `enabled` · `is_batch` 는 샘플 규칙 «열 개 전부»가 적지만 선택이다 —
#: 코드에 기본값이 있거나(`rule.get("enabled", True)` · `rule.get("is_batch", False)`) 데코레이터가
#: 댈 수 있다(`mapper_sdk.mapper(target_table=...)`). 「전부 적혀 있다」와 「없으면 거절」은
#: 다른 문장이고, 후자만 계약이다.
#: ⛔ 표를 이름 대는 칸을 여기 «글자로» 적지 않는다 — `RULE_TABLE_KEYS` 에서 «조립»한다.
#: 🔴 처음 이 목록을 적을 때 그 네 이름을 손으로 옮겨 적었고, 이 파일이 자기 규율로 막던 바로
#: 그 모양이라 `test_the_rule_table_keys_have_one_author` 가 «빨개졌다». 부분집합 «관계»를
#: 시험이 단언하는 것으로는 부족하다 — 관계는 참인데 «사본»이 둘이면 하나만 고쳐질 수 있다.
#: 조립하면 표 키가 하나 늘 때 이 목록이 «자동으로» 안다.
#: ⚠️ `trigger_table` 은 표 키«이면서» 필수다. 그래서 조립은 필수를 «빼고» 한다 — 한 이름이
#: `required` 와 `optional` 양쪽에 있으면 `exact(...)` 에게 두 말을 하는 것이고, 제 시험이
#: 그 중복을 잡았다(조립으로 바꾼 첫 판이 24/22 였다). `target_table` 도 표 키라서 아래
#: 글자 목록에서 «빠졌다».
RULE_ROUTING_OPTIONAL = tuple(
    key for key in RULE_TABLE_KEYS if key not in RULE_ROUTING_REQUIRED) + (
    "target_field", "trigger_columns", "enabled", "is_batch",
    "follow_up", "allow_chain_trigger", "allow_map_metadata_upsert",
    "max_group_attempts", "origin",
    # S-188 ⓓ: `mapper` is the ONE cell; the two-cell spelling stays readable. `params` is
    # where a mapper's arguments live. The symbols `MAPPER_KEY`/`PARAMS_KEY` below are
    # defined against these literals and a test asserts they agree — the literals are here
    # because this tuple is built before them.
    "mapper", "params",
    "mapper_module", "mapper_function",
    # 위 키로 표현 못 하는 읽기와, 실행 시점에 정해지는 참조 블록
    READS_KEY, REFERENCE_BLOCK,
)


#: The one cell a rule uses to name its mapper (S-188 ⓓ). `mapper_module` + `mapper_function`
#: remain readable — see `mapper_cells`.
MAPPER_KEY = "mapper"
PARAMS_KEY = "params"


def mapper_cells(rule):
    """`(name, module, function)` — which of the two spellings this rule used.

    🔴 BOTH STAY READABLE, AND THAT IS NOT TRANSITIONAL POLITENESS. The registry is empty
    wherever no mapper file uses the decorator yet — measured as ZERO on this box — so a
    loader that accepted only `mapper` would refuse every rule that runs today. The one cell
    is what an author SHOULD write; the two are what the file may still say.
    """
    rule = rule or {}
    return (str(rule.get(MAPPER_KEY) or "") or None,
            str(rule.get("mapper_module") or "") or None,
            str(rule.get("mapper_function") or "") or None)


#: 🔴 A CELL WHOSE NAME STARTS WITH THIS IS A COMMENT, and the convention has ONE author
#: here. The shipped rules carry `__comment`, `__why_enabled` and
#: `__alignment_thresholds_derivation`; the first version of the loader check left them out
#: of both the routing list and the flat-cell list, so `exact` refused them and NINE OF NINE
#: rules in this box were dropped — the whole chain, from a validator meant to protect it.
COMMENT_PREFIX = "__"


def comment_cells(rule):
    """Cells that are prose for the operator, not declaration."""
    return tuple(sorted(
        name for name in (rule or {})
        if isinstance(name, str) and name.startswith(COMMENT_PREFIX)))


def flat_param_cells(rule):
    """Top-level cells that are NOT routing — i.e. mapper arguments still written flat.

    ⚠️ ONE-WAY COMPATIBILITY (S-188 ⓓ). The operator's file is not touched: these are READ as
    though they sat in `params`, and the loader names them so the operator knows what to move.
    Double-underscore names are comments by this file's convention and are not arguments.
    """
    routing = set(routing_keys())
    return tuple(sorted(
        name for name in (rule or {})
        if isinstance(name, str) and not name.startswith(COMMENT_PREFIX)
        and name not in routing))


def params_of(rule):
    """The mapper's arguments: the `params` block, with flat cells read underneath it.

    🔴 `params` WINS. If a name is written both ways the block is the one the author moved
    on purpose, and silently preferring the flat copy would make the migration a no-op that
    looks done.
    """
    rule = rule or {}
    block = rule.get(PARAMS_KEY)
    merged = {name: rule[name] for name in flat_param_cells(rule)}
    if isinstance(block, dict):
        merged.update(block)
    return merged


#: S-188 ⓔ. The node vocabulary is the LEDGER skeleton's, verbatim: kinds `record`/`map`/
#: `leaf` and hints `choice`/`free`/`ref`/`number`/`flag`. 🔴 NOTHING NEW IS INVENTED HERE —
#: a kind the form renderer has never seen draws NOTHING, and this repository has paid for
#: 「a contract adopted before its material blanks the screen」 once already.
SKELETON_VERSION = 1

#: Which hint each routing cell gets. A cell absent from this map is `free`.
_SKELETON_HINTS = {
    "enabled": "flag",
    "is_batch": "flag",
    "follow_up": "flag",
    "allow_chain_trigger": "flag",
    "allow_map_metadata_upsert": "flag",
    "max_group_attempts": "number",
    "trigger_table": "ref",
    "target_table": "ref",
    "source_table": "ref",
    "map_table": "ref",
    "inventory_table": "ref",
    "metadata_target_table": "ref",
    "derivation_source_table": "ref",
    "mapper": "choice",
}


def skeleton():
    """The shape of ONE chain rule, generated from the list above.

    🔴 GENERATED, NOT WRITTEN. The ledger's skeleton is 「a SECOND statement of a contract
    whose first author is `setup_bundle.py`」 and `test_ledger_skeleton` exists because two
    authors of one contract drift in silence. Deriving this from `routing_keys()` means the
    file cannot say a different thing from the loader — there is only one author.

    ⚠️ IT DESCRIBES A RULE, NOT THE DOCUMENT. `chain_rules.json` holds `rules` as a LIST, and
    the skeleton vocabulary has no `list` kind — only `record`, `map` and `leaf`. Adding one
    would give the form a node it cannot draw, and calling the list a `map` keyed by `name`
    would state a shape the file does not have. A rule is also the unit a builder edits, so
    this is the useful half either way; the document level is named in the report as an open
    question rather than guessed at here.
    """
    required = set(RULE_ROUTING_REQUIRED)
    fields = []
    for key in routing_keys():
        if key == PARAMS_KEY:
            # The mapper's own arguments. `keyed_by` is the argument NAME, and what names are
            # legal is the mapper's to declare (`@mapper(params=…)`) — not this file's.
            node = {"kind": "map", "keyed_by": "param",
                    "node": {"kind": "leaf", "hint": "free"}}
        else:
            node = {"kind": "leaf", "hint": _SKELETON_HINTS.get(key, "free")}
        fields.append({"key": key, "required": key in required, "node": node})
    return {
        "skeleton_version": SKELETON_VERSION,
        "note": ("The shape of ONE chain rule. Generated from "
                 "`chain_bindings.routing_keys()`; the loader still decides what is good. "
                 "server/tests/test_chain_skeleton.py counts the two against each other."),
        "root": {"kind": "record", "fields": fields},
    }


def routing_keys():
    """이 규칙 문법이 최상위에서 «받는» 이름 전부 — 로더의 `exact(...)` 가 이것을 지난다.

    🔴 함수로 내는 이유는 「한 목록」이 두 벌이 되지 않게 하려는 것이다. 필수와 선택을 각자
    import 해 합치는 자리가 둘이면 그 둘이 갈릴 수 있고, 갈린 쪽이 «조용히» 덜 거절한다.
    """
    return tuple(RULE_ROUTING_REQUIRED) + tuple(RULE_ROUTING_OPTIONAL)


def reference_tables(rule):
    """이 규칙의 `reference_spec` 이 «이름 댈 수 있는» 표 — 선언에서 도출한다."""
    block = (rule or {}).get(REFERENCE_BLOCK) or {}
    name = block.get(REFERENCE_TABLE_KEY) if isinstance(block, dict) else None
    return {name.strip()} if isinstance(name, str) and name.strip() else set()


def rule_tables(rule, role):
    """이 규칙이 그 역할로 «이름 댄» 표들 — 저자는 위 열거 «하나»다.

    🔴 여기서 다시 열거하지 않는다. 순서 가드도 로드 검사도 이 함수를 지나므로,
       키가 하나 늘면 «한 줄»이 늘고 세 자리가 같이 안다.
    """
    rule = rule or {}
    out = set()
    for key, key_role in RULE_TABLE_KEYS.items():
        if key_role != role:
            continue
        name = rule.get(key)
        if isinstance(name, str) and name.strip():
            out.add(name.strip())
    if role == TABLE_ROLE_READ:
        # 판정 65: 실행 시점에 «고르는» 표도 «집합»은 선언이라 합집합으로 든다.
        # 과잉 미룸은 안전한 방향이고, 안 들면 그 읽기가 순서에 다시 안 보인다.
        out |= reference_tables(rule)
        declared = rule.get(READS_KEY)
        if isinstance(declared, (list, tuple, set)):
            for name in declared:
                if isinstance(name, str) and name.strip():
                    out.add(name.strip())
    return out


def resolve_table(rule, key: str, purpose: str = None) -> str:
    """이 규칙이 그 키로 «이름 댄» 표. 리터럴 기본값 «없음» — 없으면 이름 대어 거절한다.

    🔴 기본값이 실제로 하는 일은 「키를 빼면 «조용히» 그 표를 연다/쓴다」이다. 컬럼에는 이미
       그 규율이 있었고(§`resolve_column`) 표에만 «없었다» — 출하 템플릿 여섯에 열셋이 그렇게
       서 있었고 철자가 셋이었다.
    ⚠️ 거절문이 «규칙 이름과 키 이름»을 댄다. 이 전환의 비용은 「어느 규칙에 어느 키를 적어야
       하나」를 조작자가 아는 데 달려 있고, 그 답이 문장 안에 있어야 한다.
    """
    rule = rule or {}
    rule_name = rule.get("name") or "<unnamed rule>"
    if key not in RULE_TABLE_KEYS:
        raise ColumnBindingRefused(
            "'%s' is not a declared table key. The enumeration is "
            "chain_bindings.RULE_TABLE_KEYS (%s)."
            % (key, ", ".join(sorted(RULE_TABLE_KEYS))))
    name = rule.get(key)
    if isinstance(name, str) and name.strip():
        return name.strip()
    raise ColumnBindingRefused(
        "chain rule '%s' declares no '%s'%s. Add it to the rule in chain_rules.json — "
        "this key used to fall back to a literal, so a rule that omitted it silently "
        "reached a table nobody had named."
        % (rule_name, key, (" for %s" % purpose) if purpose else ""))


def _refuse_unknown(rule_name, key, name, table, purpose, known):
    raise ColumnBindingRefused(
        "chain rule '%s' resolves %s='%s' for %s on table '%s', but '%s' declares no "
        "such column (declared: %s). Correct the name in chain_rules.json, or declare "
        "the column in table_config.json — it cannot be inherited while a declaration "
        "out-ranks the derivation."
        % (rule_name, key, name, purpose, table, table, ", ".join(sorted(known))))


def resolve_column(rule, key: str, table: str, purpose: str) -> str:
    """The column of `table` that carries the job, for this rule. No literal default.

    `rule[key]` wins; otherwise `table_config` derives it; otherwise this REFUSES and
    the message names the rule, the key and the table.  `purpose` is a short phrase
    that says what the name is for ("the payload the chain is triggered by", "the
    output key written to the target"), so a refusal is actionable without reading the
    mapper.
    """
    rule = rule or {}
    rule_name = rule.get("name") or "<unnamed rule>"
    if not isinstance(table, str) or not table.strip():
        raise ColumnBindingRefused(
            "chain rule '%s' names no table for %s, so its job column cannot be "
            "resolved. Declare the table on the rule in chain_rules.json."
            % (rule_name, purpose))
    known = declared_columns(table)

    declared = rule.get(key)
    if isinstance(declared, str) and declared.strip():
        name = declared.strip()
        if known is not None and name not in known:
            _refuse_unknown(rule_name, key, name, table, purpose, known)
        return name

    name, origin_or_why = identity_column(table)
    if name is None:
        raise ColumnBindingRefused(
            "chain rule '%s' does not declare '%s' and it cannot be derived: %s. "
            "Declare '%s' on the rule in chain_rules.json, or give '%s' a "
            "single-column 'map_key_columns' in table_config.json. Refusing instead of "
            "assuming 'dt_job' — that name is only correct on the machine that wrote "
            "it, and assuming it makes %s fail silently."
            % (rule_name, key, origin_or_why, key, table, purpose))
    if known is not None and name not in known:
        _refuse_unknown(rule_name, key, name, table, purpose, known)
    logger.debug("[ChainBinding] %s.%s = '%s' (%s, for %s)",
                 rule_name, key, name, origin_or_why, purpose)
    return name


def resolve_decision_column(rule, key: str, decision_key, purpose: str) -> str:
    """Same precedence, for a name that must live in an alignment rule's decision key.

    The value is looked up out of a `key_values` dict whose keys ARE the alignment
    rule's `decision_key`, so the derivation source is that declaration rather than a
    table, and a declared name outside it can never match anything.
    """
    rule = rule or {}
    rule_name = rule.get("name") or "<unnamed rule>"
    names = [str(c) for c in (decision_key or ()) if str(c).strip()]

    declared = rule.get(key)
    if isinstance(declared, str) and declared.strip():
        name = declared.strip()
        if names and name not in names:
            raise ColumnBindingRefused(
                "chain rule '%s' declares %s='%s' for %s, but the alignment rule's "
                "decision_key is [%s]. A name outside the decision key matches nothing "
                "and would read as 'no job'."
                % (rule_name, key, name, purpose, ", ".join(names)))
        return name

    if len(names) == 1:
        return names[0]
    raise ColumnBindingRefused(
        "chain rule '%s' does not declare '%s' and the alignment rule's decision_key "
        "[%s] does not name exactly one column, so %s cannot be derived. Declare '%s' "
        "on the rule in chain_rules.json. Refusing instead of assuming 'dt_job'."
        % (rule_name, key, ", ".join(names) or "<empty>", purpose, key))


def model_column(model, table: str, column: str, purpose: str):
    """The mapped attribute for `column`, or a refusal that names table and column.

    Replaces the `hasattr(...)` gates that used to `return {}` — a loaded model without
    the resolved column means `table_config` and the physical table disagree, and
    continuing produced an empty batch that the worker recorded as success.
    """
    attribute = getattr(model, column, None)
    if attribute is None:
        raise ColumnBindingRefused(
            "'%s' resolves its job column to '%s' for %s, but the loaded model has no "
            "such attribute. table_config and the physical table disagree — run the "
            "schema sync, or correct the name." % (table, column, purpose))
    return attribute


# ---------------------------------------------------------------------------
# S-194 ① — the chain's half of the draft lifecycle
# ---------------------------------------------------------------------------
#: 🔴 THE SAME LIFECYCLE, A DIFFERENT DOCUMENT (판정 303). `config_drafts` owns draft →
#: review → activate with optimistic locking and a snapshot compare-and-swap; it asks a
#: document seven questions and this is the chain's set of answers. A second lifecycle was
#: refused because 「합칠 사람이 없다」 — nobody merges two, so there is one.
from types import SimpleNamespace

CHAIN_EDITABLE_FILE = "chain_rules.json"


class ChainRuleIndex:
    """The three things the lifecycle asks of an index: `nodes`, `node(key)`, `snapshot_hash`.

    ⚠️ THE CHAIN HAS NO EXPLORER INDEX, and that is the measured reason 「one bundle argument」
    could not open the lifecycle (S-194 design). What the machinery actually needs is small:
    a mapping of editable targets, a refusal by name for a key that is not one, and something
    to compare a draft's base against.

    🔴 THE SNAPSHOT HASH IS OVER THE RULES AS THE LOADER SEES THEM, not over the file's bytes.
    Two files that differ only in whitespace describe the same rules, and a draft rejected for
    a reformat would teach an operator that the lock is noise. Conversely a synthesized rule
    changing IS a change the draft must notice, because it can collide with a declared name.
    """

    def __init__(self, rules):
        self.nodes = {}
        for position, rule in enumerate(rules or ()):
            name = str((rule or {}).get("name") or "")
            if not name:
                continue
            self.nodes[name] = SimpleNamespace(
                key=name,
                canonical_id=name,
                kind="chain_rule",
                config_file=CHAIN_EDITABLE_FILE,
                # Only `config_file` and `bundle_path` are read downstream — `draft_target`
                # says so — and this is where in the document the rule lives.
                bundle_path=("rules", position),
                definition_hash=None,
                raw=rule,
            )
        self.snapshot_hash = self._hash(rules)

    @staticmethod
    def _hash(rules):
        import hashlib
        import json

        payload = json.dumps([r for r in (rules or ())], sort_keys=True,
                             ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def node(self, key):
        """⛔ REFUSES BY NAME, as the explorer's index does. A key the loader never saw is a
        typo or a rule that was removed, and resolving it to something would put a draft on a
        target that cannot be written back."""
        try:
            return self.nodes[str(key)]
        except KeyError:
            raise KeyError(
                "no chain rule named %r; declared: %s"
                % (key, ", ".join(sorted(self.nodes)) or "none")) from None


class ChainRuleDocument:
    """The chain's answers to the lifecycle's seven questions.

    ⚠️ VALIDATION IS THE LOADER'S, NOT A SECOND OPINION. `preview` scores a draft with the
    same `validation.Problems` + `routing_keys()` the loader uses (S-188 ⓐⓑ), so a draft the
    screen calls good cannot be a rule the loader then refuses.
    """

    editable_file = CHAIN_EDITABLE_FILE

    def node_of(self, context, target_key):
        return context.index.node(target_key)

    def has_node(self, context, target_key) -> bool:
        return str(target_key) in context.index.nodes

    def snapshot_hash(self, context):
        return context.index.snapshot_hash

    def target_of(self, record, context):
        key = str((record or {}).get("target_key"))
        existing = context.index.nodes.get(key)
        if existing is not None:
            return existing
        stored = (record or {}).get("target_bundle_path")
        if not stored:
            return context.index.node(key)      # refuses by name, as above
        # A draft that AUTHORS a rule has no node to ask — the same hole `draft_target`
        # records for the ledger, where the owner wrote a declaration by hand for two hours.
        return SimpleNamespace(
            key=key, canonical_id=key, kind="chain_rule",
            config_file=CHAIN_EDITABLE_FILE, bundle_path=tuple(stored),
            definition_hash=None, raw=(record or {}).get("raw"))

    def fill(self, context, node, raw):
        """⚠️ NOTHING IS FILLED IN. The ledger fills a declaration from the active setup so a
        partly written node still compiles; a chain rule is flat and the loader's required
        cells are two. Inventing defaults here would put values in the operator's file that
        the operator never wrote."""
        return raw

    def preview(self, context, node, raw):
        import validation

        problems = validation.Problems()
        problems.exact(raw if isinstance(raw, dict) else {}, "rule",
                       required=RULE_ROUTING_REQUIRED,
                       optional=RULE_ROUTING_OPTIONAL,
                       ignored=(flat_param_cells(raw) + comment_cells(raw))
                       if isinstance(raw, dict) else ())
        issues = [i.to_mapping() for i in problems.finish()]
        # 🔴 THE SCREEN MUST NOT BE BLINDER THAN THE LOG. The loader ACCEPTS an unknown
        # top-level cell — it is a mapper argument still written flat (S-188 ⓓ) — and warns by
        # name so the operator knows what to move. A preview that only reported refusals
        # would let an author leave the file in the state the boot line complains about every
        # morning, with the screen calling it good.
        flat = list(flat_param_cells(raw)) if isinstance(raw, dict) else []
        warnings = ([{"code": "flat_param_cell", "path": "rule." + name,
                      "message": "a mapper argument still written at the top level - "
                                 "move it under 'params'"} for name in flat])
        return SimpleNamespace(raw=raw, issues=issues, warnings=warnings, ok=not issues)

    def config_root(self, context):
        from pathlib import Path

        return Path(context.setup.config_root)
