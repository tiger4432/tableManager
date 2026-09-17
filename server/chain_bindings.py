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
    # ⚰️ [S-284] IT USED TO SWALLOW THE REFUSAL INTO AN EMPTY LIST. `cols = []` then made
    # 「the product refused this declaration」 walk out through the same sentence as 「this
    # table declares nothing」 - and those two send an operator in OPPOSITE directions: one
    # goes and writes a `map_key_columns` they have already written, the other needs the
    # refusal's own reason, which appeared nowhere.
    refusal = None
    try:
        cols = dt_map_derivation.identity_columns(table)
    except dt_map_derivation.DerivationRefused as exc:
        cols, refusal = [], str(exc)
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
    if refusal:
        # ⚠️ ONLY THE FINAL SENTENCE CHANGES. A refused map key does not stop the business
        # key from answering above - the order in this docstring is 1, then 2, then nothing,
        # and a refusal at 1 is not a refusal of 2.
        return None, ("'%s' declares 'map_key_columns' and the product refused it (%s), "
                      "and its 'business_key' cannot stand in" % (table, refusal))
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

#: 로더가 «짝으로» 세운 규칙이 「나는 이 선언의 둘째 반쪽이다」를 적는 칸 (S-270).
#: 🔴 여기가 저자다 — `chain.rule_shape.COMPANION_CELL` 이 이 이름을 «가져다» 쓴다. 두 벌로
#: 적으면 한쪽만 고쳐지는 날 문법은 모르는 칸이 되고, 그 규칙은 매 부팅 경고를 받는다.
COMPANION_CELL_NAME = "companion_of"

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
    "max_group_attempts", "max_group_rows", "group_by", "idempotent", "origin",
    # S-270: 로더가 «짝으로 세운» 규칙이 자기가 어느 선언의 둘째 반쪽인지 적는 칸.
    # `origin` 과 «같은 부류»다 — 문법이 받기는 하지만 쓰는 것은 로더다. 여기 없으면
    # `flat_param_cells` 가 이것을 「params 로 옮기라」고 «매 부팅» 경고한다(실측 2026-09-16:
    # 조인 하나당 한 줄). 영구 경고 한 줄은 진짜 경고 하나를 안 읽히게 만든다.
    COMPANION_CELL_NAME,
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


def rule_refusals(rule, path, *, mapper_resolvable, mapper_params=None):
    """Why this chain rule CANNOT RUN — the one spelling, for every reader (S-180 ⓑ-0).

    🔴 IT WAS SPELLED TWICE AND THE TWO HAD ALREADY DIVERGED. The loader
    (`chain_ingestion_worker.load_chain_rules`) scored the grammar and refused an
    unresolvable mapper; the explorer's chain draft adapter (retired, S-205) re-typed the
    same `exact` tuple and had no mapper check at all — so the dry-run screen ACCEPTED a
    rule the loader would drop, which is exactly the thing that function's own note
    forbids: 「the screen must not be blinder than the log」.

    🔴 `mapper_resolvable` IS A CALLABLE, NOT A REGISTRY. This module must not import
    `mapper_sdk`: S-188 set that direction on purpose, and a grammar that reached into the
    registry would make 「what the rules file may say」 depend on 「what this process happens
    to have imported」.

    ⚠️ WHAT IS REFUSED IS 「CANNOT RUN」, NOT 「UNFAMILIAR」. An unknown top-level cell is a
    mapper argument still written flat, and where nobody said otherwise the product cannot
    tell a stale one from a live one - the mapper that reads it lives in a gitignored file.
    Those are WARNED about by name (`rule_warnings`), never refused.

    🔴 UNLESS THE MAPPER SAID WHAT IT READS (S-152, 판정 371·372). `@mapper(params=…)` is a
    DECLARATION, and once it exists the product CAN tell: a flat cell outside it is a name
    this mapper will never look at. `trigger_colums` for `trigger_columns` used to roll on as
    a warning and silently take the whole table with it, because a typo and a stale argument
    look the same until something declares the difference.
    ⚠️ 「Can tell」 is the whole of the rule: no declaration, no refusal - today's warning
    stands, because refusing there would refuse a working rule over a name nobody defined.

    🔴 `mapper_params` IS A CALLABLE, for the same reason `mapper_resolvable` is: this module
    must not import `mapper_sdk` (S-188 set that direction), or 「what the rules file may
    say」 would depend on 「what this process happens to have imported」.
    """
    import validation

    candidate = rule if isinstance(rule, dict) else {}
    problems = validation.Problems()
    problems.exact(candidate, path,
                   required=RULE_ROUTING_REQUIRED,
                   optional=RULE_ROUTING_OPTIONAL,
                   ignored=(flat_param_cells(candidate) + comment_cells(candidate)))
    issues = list(problems.finish())

    one_cell, module_name, function_name = mapper_cells(candidate)
    resolvable = bool(mapper_resolvable(one_cell)) if one_cell else False
    if not resolvable and not (module_name and function_name):
        issues.append(validation.DeclarationValidationError(
            "unresolvable_mapper", path + "." + MAPPER_KEY,
            "names no mapper this process can run: '%s' is not registered and "
            "mapper_module/mapper_function are not both set" % (one_cell or "")))

    # 🔴 [S-153, 판정 378] A CEILING THAT IS NOT A POSITIVE NUMBER IS NOT A CEILING. Written
    # as text or as zero it would read as 「no limit」 or 「merge nothing」 depending on who
    # looked, and the operator would have declared a performance handle that quietly does
    # neither. The DEFAULT is a different thing entirely (`NO_GROUP_MERGE`, set by the
    # product when the cell is absent) - what is refused here is a cell somebody WROTE.
    if MAX_GROUP_ROWS_KEY in candidate:
        written = candidate.get(MAX_GROUP_ROWS_KEY)
        # ⚠️ THE CHECK SAYS WHAT THE MESSAGE SAYS. `int(2.5)` is 2, so scoring through a cast
        # would accept 「two and a half rows」 while the refusal below promises a whole number -
        # and an operator reading that sentence would never learn which half was wrong.
        # `bool` is an `int` in Python, and `True` is not a ceiling.
        rows = written if isinstance(written, int) and not isinstance(written, bool) else None
        if rows is None or rows <= 0:
            issues.append(validation.DeclarationValidationError(
                "bad_group_rows", path + "." + MAX_GROUP_ROWS_KEY,
                "a group-row ceiling must be a positive whole number, got %r" % (written,)))

    # 🔴 [S-155, 판정 384] IDEMPOTENCE IS A YES OR A NO, and a string 「false」 is a YES
    # to every truth test in Python. The cell decides whether a failed group is fed to the
    # mapper a second time, so a value that cannot be read as a boolean must not be guessed at.
    if IDEMPOTENT_KEY in candidate and not isinstance(candidate.get(IDEMPOTENT_KEY), bool):
        issues.append(validation.DeclarationValidationError(
            "bad_idempotent", path + "." + IDEMPOTENT_KEY,
            "idempotence must be true or false, got %r" % (candidate.get(IDEMPOTENT_KEY),)))

    # 🔴 [S-154, 판정 381] A GROUP KEY NAMES COLUMNS OF THE TRIGGER TABLE. A name that is
    # not one matches nothing, so every row would key on the same absent value and the whole
    # table would arrive as ONE group - the loudest possible version of the misspelling S-152
    # closed one cell over. `declared_columns` is the author of 「what columns does this table
    # have」; `None` from it means 「the catalogue says nothing」 and is why a table it does not
    # declare keeps working instead of being refused.
    if GROUP_BY_KEY in candidate:
        written = candidate.get(GROUP_BY_KEY)
        names = (written if isinstance(written, list)
                 and all(isinstance(n, str) and n.strip() for n in written) else None)
        if names is None:
            issues.append(validation.DeclarationValidationError(
                "bad_group_by", path + "." + GROUP_BY_KEY,
                "a group key must be a list of column names, got %r" % (written,)))
        else:
            known = declared_columns(str(candidate.get("trigger_table") or ""))
            for missing in (sorted(set(names) - known) if known is not None else ()):
                issues.append(validation.DeclarationValidationError(
                    "unknown_group_column", path + "." + GROUP_BY_KEY,
                    "'%s' is not a column of trigger table '%s' - a name that matches "
                    "nothing would put the whole table in one group"
                    % (missing, candidate.get("trigger_table"))))

    # 🔴 THE ONE BRANCH THIS ROUND ADDS. Only where a declaration exists, and only over the
    # cells the rule actually wrote - `params_of` reads the block with the flat cells beneath
    # it, which is the same view the mapper will be handed.
    declared = mapper_params(one_cell) if (mapper_params and resolvable and one_cell) else None
    if declared is not None:
        for name in sorted(set(params_of(candidate)) - set(declared)):
            issues.append(validation.DeclarationValidationError(
                "undeclared_param", path + "." + name,
                "'%s' does not read an argument by this name (it declares: %s) - a "
                "misspelling here runs against the whole table"
                % (one_cell, ", ".join(sorted(declared)) or "none")))
    return issues


def rule_warnings(rule, path="rule"):
    """What this rule should be TIDIED about, in one spelling. Never a refusal.

    ⚠️ A WARNING AND A REFUSAL ARE DIFFERENT FACTS and an operator does something different
    about each: the flat cell RUNS today and wants moving, the refusal does not run at all.
    Keeping them one function would make the screen show a rule as broken for a cell that
    works.
    """
    import validation

    flat = flat_param_cells(rule) if isinstance(rule, dict) else ()
    return [validation.DeclarationValidationError(
        "flat_param_cell", path + "." + name,
        "a mapper argument still written at the top level - move it under 'params'")
        for name in flat]


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


#: 🔴 [S-153] ONE SPELLING OF THE CEILING'S NAME. The grammar tuple above is built before
#: this line, so the literal appears there too - and `test_the_rule_table_keys_have_one_author`
#: is the reason that pair is asserted rather than trusted.
MAX_GROUP_ROWS_KEY = "max_group_rows"

#: 🔴 [S-154] ONE SPELLING OF THE GROUP KEY'S NAME, for the same reason as the ceiling.
#: ⚠️ NOT THE WALK'S `group_by` AND NOT A SYNTHESIZED RULE'S `decision_key`. The walk's is
#: a QUERY argument and the alignment rule's is the unit a confirmation is stamped onto; this
#: one says which rows reach a mapper in ONE call. Three axes, and a refusal message that
#: mixed them would send an operator to the wrong file.
GROUP_BY_KEY = "group_by"

#: 🔴 [S-155] ONE SPELLING OF THE IDEMPOTENCE CELL'S NAME.
#: ⚠️ IT IS AN OPT-OUT. Absent and `true` are TODAY'S ANSWER - the retry cap decides - and
#: only `false` changes anything. A cell whose declared value does nothing is the defect
#: S-152 and S-221 each closed once; a `true`-only cell would have been the third.
IDEMPOTENT_KEY = "idempotent"


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
    "max_group_rows": "number",
    "idempotent": "flag",
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
            node = _params_node()
        else:
            node = {"kind": "leaf", "hint": _SKELETON_HINTS.get(key, "free")}
        fields.append({"key": key, "required": key in required, "node": node})
    return {
        "skeleton_version": SKELETON_VERSION,
        "note": ("The shape of ONE chain rule. Generated from "
                 "`chain_bindings.routing_keys()`; the loader still decides what is good. "
                 "server/tests/test_chain_skeleton.py counts the two against each other."),
        "root": {"kind": "record", "fields": fields},
        # 🔴 [S-241] THE SECOND SHAPE, BECAUSE THE GRAMMAR HAS TWO. A rule may be written
        # flat (today's cells) or unified (`on`/`derive`/`into`), and the form could draw
        # only the first - so the grammar this product added could be READ by the loader and
        # never WRITTEN by the screen. Both shapes ride together and the rule itself says
        # which one it is (`chain_rule_raw_view`'s `grammar`).
        "unified_root": _unified_root(),
    }


def _field(key, node, required=False):
    return {"key": key, "required": required, "node": node}


def _record(*fields):
    return {"kind": "record", "fields": list(fields)}


def _leaf(key):
    return {"kind": "leaf", "hint": _SKELETON_HINTS.get(key, "free")}


def _params_node():
    """The mapper's own arguments: a free map, keyed by the argument NAME.

    🔴 [판정 536] WHAT NAMES ARE LEGAL IS THE MAPPER'S TO DECLARE (`@mapper(params=…)`),
    never this file's. Measured 2026-09-17: the flat rules here carry 25 cells the chain
    grammar does not know, and what reads them lives in `server/mappers/*.py` - the owner's
    files, gitignored. Enumerating them here would put domain words in code AND would be
    wrong for the thirty-fifth argument an installation adds tomorrow.
    「적을 자리를 만들고 값은 «비워 둔다»」.

    ⚠️ ONE AUTHOR, TWO SKELETONS. The flat root and the unified `derive.mapper` branch are
    the same cell in two grammars; spelling the node twice is how the form comes to offer one
    shape where the loader takes another.

    🔴 [판정 557] `of` · `member` · `keyed_by: "name"` — THE SPELLING THE READER KNOWS.
    This said `node:` and `keyed_by: "param"`, and the shared descent
    (`client2/src/ontology_skeleton.js`, whose own note says 「DESCENT HAS ONE AUTHOR」)
    reads `node.of`. Measured by the application lane: `shapeAt(['derive','mapper','params',
    <any name>])` came back NULL, so the form had a place for a mapper argument and no shape
    to draw in it. 「자리는 있는데 그릴 수는 없다」.

    ⚠️ ONE KIND, TWO SPELLINGS - today's defect at another seat. The ledger's 32 map nodes
    all say `of`, the chain's 2 said `node`, and the fix goes to the 2: the reader is the
    authority, and teaching it a second spelling would make the split permanent.

    ⚠️ `keyed_by` IS FIXED HERE TOO, though the ruling named only the other two. The
    reader's vocabulary is `'name' | 'index'` (its line 16) and it only tests for `index`,
    so `"param"` worked by falling through - a third spelling that happens to land right.
    That is the same defect as `node`, at the same node, and it is cheaper to say now.
    """
    return {"kind": "map", "keyed_by": "name", "member": "인자",
            "of": {"kind": "leaf", "hint": "free"}}


def _unified_root():
    """The unified rule's shape, GENERATED from `rule_shape`'s own words (S-241).

    🔴 [판정 407] `derive` AND `into` ARE 「PICK ONE」, WHICH THE VOCABULARY COULD NOT SAY.
    The client measured it: kind = record|map|leaf, six hints, and no `oneOf` anywhere -
    `hint: choice` picks a VALUE, not a SHAPE. So drawing 「one of three derive kinds」 meant
    the form hand-drawing what the grammar knows, which is how a screen comes to disagree
    with a loader. One node kind closes it.

    🔴 [S-241-b, 판정 411] A BRANCH NODE IS WHAT LIVES UNDER THE BRANCH KEY - the key is
    already the cell. My first cut wrapped three of the five in a record, so the form would
    have asked for `into: {"table": {"table": "dt_x"}}` where the declaration says
    `into: {"table": "dt_x"}`. The client measured it against the committed declaration
    fixtures before building against it (`fedf6a15`). `join` and `decide` were right because
    their cell IS a record; `mapper`, `table` and `read` are a name, a name and a flag.

    ⚠️ THE BRANCH KEYS ARE THE LIST. 판정 407's node also carries a `list` naming a
    closed list, and this file does NOT emit one: nothing serves closed lists on the chain
    side (`chain_rule_raw_view` publishes none, and the only `closed_lists()` in the
    repository belongs to the ledger authoring screen). Naming a list nobody serves would be
    the 「the form draws it and nothing reads it」 defect three of this week's rounds removed -
    so the values have ONE author, `branches`. Adding a `lists` cell later is additive; a
    dangling name would not have been. This choice is reported, not assumed - if the ruling
    goes the other way it is one cell to add.
    """
    from chain import join_into, rule_shape

    derive_branches = {
        "join": _record(*[_field(cell, _leaf(cell)) for cell in join_into.JOIN_CELLS]),
        "decide": _record(*[_field(cell, _leaf(cell))
                            for cell in rule_shape.DECIDE_CELLS]),
        # 🔴 [판정 536 ⑥] A NAME AND ITS ARGUMENTS, because that is what the internal model
        #   already holds: `from_chain_rule` builds `derive.mapper` as
        #   `{mapper, mapper_module, mapper_function, params}`. This node said `leaf`, so the
        #   form could NAME a mapper and not CONFIGURE one - an operator had to hand-edit
        #   JSON to set a single argument. ⚰ The old comment called it 「a leaf rather than a
        #   second vocabulary」; the second vocabulary was never the risk, the missing room was.
        "mapper": _record(
            _field("mapper", _leaf("mapper")),
            _field("mapper_module", _leaf("mapper_module")),
            _field("mapper_function", _leaf("mapper_function")),
            _field(PARAMS_KEY, _params_node())),
    }
    into_branches = {
        "table": _leaf("target_table"),
        "read": {"kind": "leaf", "hint": "flag"},
    }
    return _record(
        _field("name", _leaf("name"), required=True),
        _field("enabled", _leaf("enabled")),
        _field("on", _record(_field("table", _leaf("trigger_table"), required=True),
                             _field("columns", _leaf("trigger_columns")))),
        _field("derive", {"kind": "oneOf", "hint": "choice",
                          "branches": {kind: derive_branches[kind]
                                       for kind in rule_shape.DECLARED_KINDS}},
               required=True),
        _field("into", {"kind": "oneOf", "hint": "choice",
                        "branches": {kind: into_branches[kind]
                                     for kind in rule_shape.INTO_KINDS}},
               required=True),
        _field("key", _record(*[_field(cell, _leaf(cell))
                                for cell in rule_shape.KEY_CELLS])),
        _field("limits", _record(*[_field(cell, _leaf(cell))
                                   for cell in rule_shape._LIMIT_KEYS])),
        # 🔴 [판정 536 ① · 546 ①] THE FOURTEEN THE UNIFIED SHAPE HAD NO ROOM FOR. Measured
        #   2026-09-17: nine of the ten rules in this box carry cells the form could not
        #   draw, because they fell into `extra` - and `is_batch` alone decides how a rule
        #   is CALLED (판정 506). A grammar that cannot hold nine of ten declarations is the
        #   one with the missing axis, not the declarations.
        # ⚠️ THE LIST IS COMPUTED (`routing_keys()` minus what the unified shape folds), so a
        #   cell added to the chain grammar tomorrow appears here without this file changing.
        #   Spelling fourteen names here would be the third author of one list.
        # ⛔ AND THE NAMES ARE THE OPERATOR'S. `RULE_TABLE_KEYS` says it: 「개명하지 않는다 —
        #   운영자가 적는 키이고, 이름을 바꾸는 것은 조작자 표면이다」.
        *[_field(cell, _leaf(cell)) for cell in rule_shape.axis_keys()],
    )


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
# ⚰️ S-194's draft adapter RETIRED 2026-09-13 (S-205, 판정 340)
# ---------------------------------------------------------------------------
#: 🔴 THE DOOR TURNED OUT TO BE SOMEWHERE ELSE. `ChainRuleDocument`/`ChainRuleIndex` gave the
#: chain a seat in the explorer's draft lifecycle, and 판정 325 then ruled that a chain rule is
#: authored from the admin CHAIN TAB's raw route -- so the adapter never gained a product
#: caller. Measured at retirement: callers outside its own tests, ZERO.
#:
#: ⚠️ AND IT WAS WRONG WHERE NOBODY LOOKED. `config_root` returned the ontology root while
#: `chain_rules.json` lives in its PARENT, so activating through it would have written a file
#: no loader reads. No test ever called that method, so the seat was wrong from the day it was
#: written and said nothing about it.
#:
#: 🔴 ITS TESTS WENT IN THE SAME COMMIT. 「테스트는 자기가 재던 코드와 같은 커밋에서 죽는다」 --
#: leaving them standing would have left the only callers alive and made the count look real.
#:
#: 📎 What survives is the half with readers: `rule_refusals`/`rule_warnings` (the ONE grammar
#: judge, S-180 ⓑ-0) and `skeleton()`, which the chain tab's own route hands over (S-204).


