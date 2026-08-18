"""Immutable read model for the Ledger v2 ontology configuration explorer.

The explorer never guesses links from ``@1``-looking strings.  Every resolved edge is
checked against the registries in one compiled :class:`LedgerSetupSnapshot`, and every
edge keeps the JSON pointer at which the reference was declared.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from . import setup_bundle


KIND_ORDER = {
    "source_plan": 0,
    "profile": 1,
    "mapping": 2,
    "binding": 3,
    "pack": 4,
    "claim": 5,
    "predicate": 6,
    "entity": 7,
    "preparer": 8,
    "mapper": 9,
    "verified_join": 10,
    "table": 11,
}

_VERSIONED_ID = re.compile(r"^(?P<prefix>.+)@(?P<version>[0-9]+)(?P<suffix>(?:[/#].*)?)$")


class ConfigExplorerError(ValueError):
    """A refusal.  `details` carries the rows an operator needs in order to ACT on it.

    A refusal that only states a fault ("this is referenced") leaves the operator with no
    next move; the rows that made the refusal true have to travel with it.  Absent details
    stay out of `to_mapping` entirely, so the wire shape of an ordinary refusal does not
    grow a null field.
    """

    def __init__(self, code: str, path: str, message: str,
                 details: Sequence[Mapping[str, Any]] | None = None):
        self.code = code
        self.path = path
        self.message = message
        self.details = tuple(dict(item) for item in details) if details else tuple()
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code, "path": self.path, "message": self.message}
        if self.details:
            value["details"] = [dict(item) for item in self.details]
        return value


def node_key(kind: str, canonical_id: str) -> str:
    return f"{kind}|{canonical_id}"


#: kind -> the `ledger_config.json` section that OWNS declarations of that kind.
#:
#: `build_explorer_index` already encodes this pairing, but only for declarations that
#: EXIST: it reads a section, then names each member's `bundle_path` as it goes. Creating a
#: declaration has to go the other way -- from a kind and a not-yet-used id to the place it
#: will live -- and there is no node to ask. Stated once here so the authoring path and the
#: index cannot disagree about where a `mapper` lives; `_authorable_bundle_path` below is
#: the only way to build that path, and `test_config_explorer_sections_match_the_index`
#: scores this map against the index rather than trusting both to be edited together.
#:
#: `table` and `verified_join` are deliberately absent. `table` moved out of this file to
#: `server/config/table_config.json` on 2026-08-18 and is read-only here; `virtual_joins`
#: is an optional section this screen does not yet author. Absence from this map is what
#: makes a kind un-creatable, so adding one is a decision, not a typo.
AUTHORABLE_SECTIONS: Mapping[str, str] = MappingProxyType({
    "predicate": "vocabulary",
    "entity": "entities",
    "pack": "packs",
    "preparer": "source_preparers",
    "mapper": "mappers",
    "profile": "profiles",
    "source_plan": "sources",
})


def authorable_bundle_path(kind: str, canonical_id: str) -> tuple[str, str]:
    """Where a declaration of `kind` named `canonical_id` lives, existing or not."""
    section = AUTHORABLE_SECTIONS.get(kind)
    if section is None:
        raise ConfigExplorerError(
            "unauthorable_kind", "kind",
            f"declarations of kind {kind!r} cannot be created or removed on this screen",
        )
    return (section, canonical_id)


def referrers(index: "ExplorerIndex", key: str) -> tuple[dict[str, Any], ...]:
    """Who points AT `key`, named precisely enough to go and repoint them.

    `inbound` is the only place that knows this.  A count would not do: an operator cannot
    repoint what the screen will not name, so each row carries the referring declaration's
    id AND the exact json pointer at which the reference was declared.

    Only `resolved` edges count.  An unresolved inbound edge names a target that does not
    exist in this snapshot -- it is already dangling, and treating it as a referrer would
    make a declaration undeletable because something ELSE is broken.
    """
    rows: list[dict[str, Any]] = []
    for edge in index.inbound.get(key, ()):
        if edge.status != "resolved":
            continue
        source = index.nodes.get(edge.from_key)
        rows.append({
            "key": edge.from_key,
            "canonical_id": source.canonical_id if source is not None else edge.from_key,
            "kind": source.kind if source is not None else "unknown",
            "reference_kind": edge.reference_kind,
            "json_pointer": edge.json_pointer,
        })
    rows.sort(key=lambda row: (row["kind"], row["canonical_id"], row["json_pointer"]))
    return tuple(rows)


def require_no_referrers(index: "ExplorerIndex", key: str, action: str) -> None:
    """Refuse to `action` a declaration that something OUTSIDE the deletion still reaches.

    🔴 READ THIS BEFORE WIRING IT TO THE DELETE BUTTON.  The decision procedure is
    `deletion_plan` below; this function is the FALLBACK it is built out of, and its name
    does not say so -- a name is a poor carrier for "this is the last resort".  Wire it as
    THE gate and the screen deadlocks: measured
    on the live root, the number of declarations with no referrer is ZERO, and a source and
    its profile name each OTHER (`sources.<id>.profile_id` and `profiles.<id>.source`), so
    neither ever reaches an in-degree of zero.  A screen guarded this way refuses every
    delete and reads to the author as "this screen cannot delete anything".

    The ruling (2026-08-18) is that in-degree is the wrong instrument and the right question
    is REACHABILITY AFTER the deletion, over the whole reference component:

      * the deletable unit is the component, not the node -- a source and the profile only
        it uses go together, because neither is meaningful alone;
      * walk from the sources that REMAIN; whatever is then unreachable was only held up by
        what is going away, and goes with it;
      * `referrers()` is what the screen SHOWS before the confirm.  Listing the casualties
        is the guard that actually prevents the orphan.  This refusal is the fallback for
        the case where a reacher survives outside the set being deleted.

    🔴 The regression to watch: if the screen ever refuses a delete whose only referrers are
    INSIDE the set being deleted, the instrument is wrong again.  Do not special-case the
    source-profile pair -- the mutual reference is structural and a third kind will join the
    cycle, at which point a hardcoded pair check dies quietly.

    What the whole thing is for: removing or renaming a referenced declaration does not fail
    at write time.  The file is written, and the breakage surfaces later as a loader error
    about a reference nobody remembers making.  That silent dangling reference is the defect.

    Repointing the referrers is NOT done here.  Rewriting somebody else's declaration as a
    side effect of a delete is a second, unreviewed edit riding on one activation, and the
    operator never saw its diff.  The refusal says so rather than leaving it implied.

    The message names the ACTION, not only the fault -- "this is referenced" tells an
    operator nothing about which of their two buttons just refused them.
    """
    rows = referrers(index, key)
    if not rows:
        return
    node = index.nodes.get(key)
    subject = node.canonical_id if node is not None else key
    raise ConfigExplorerError(
        "declaration_is_referenced", "target_key",
        f"{action} refused: {subject!r} is still referenced by {len(rows)} declaration(s); "
        f"repoint them first (this screen does not rewrite referrers for you)",
        rows,
    )


def self_standing_keys(index: "ExplorerIndex") -> frozenset[str]:
    """Declarations nothing points at -- the entry points a walk has to start from.

    In-degree is the wrong GATE (see `require_no_referrers`) but it is the right way to
    name this set, and the two uses must not be confused.  A half-wired declaration is the
    normal state of the screen this feeds: an author creates a pack minutes before any
    profile uses it.  If such a pack were not a walk root, the first unrelated deletion
    would find it unreachable and sweep it away.

    Measured 2026-08-18: the live root has ZERO of these, and the transfer sample has one
    (`table|dt_inventory`).  That is why sources are roots too -- on a fully wired config
    this set is empty and a walk seeded only from it would mark the entire graph dead.
    """
    return frozenset(
        key for key in index.nodes
        if not any(edge.status == "resolved" for edge in index.inbound.get(key, ()))
    )


def _reachable(index: "ExplorerIndex", roots: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    stack = [key for key in roots if key in index.nodes]
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        seen.add(key)
        for edge in index.outbound.get(key, ()):
            if edge.status == "resolved" and edge.to_key is not None:
                stack.append(edge.to_key)
    return seen


def _walk_roots(index: "ExplorerIndex") -> frozenset[str]:
    """Where a reachability walk starts: sources, plus anything nothing points at.

    A `source_plan` is a root because it is the only declaration that stands on its own
    reason -- everything else in the bundle exists to serve one.  It is a root even though
    its profile points AT it, which is the whole reason the walk survives the mutual
    reference that defeats in-degree.
    """
    return frozenset(
        key for key, node in index.nodes.items() if node.kind == "source_plan"
    ) | self_standing_keys(index)


@dataclass(frozen=True)
class DeletionPlan:
    """What actually goes when the author deletes `targets`, and what refuses to.

    `removed` is the reference COMPONENT, not the selected nodes.  A source and the
    profile only it uses go together because neither is meaningful alone; listing the
    casualties before the confirm is the guard that prevents the orphan.
    """

    targets: tuple[str, ...]
    removed: tuple[dict[str, Any], ...]
    released: tuple[dict[str, Any], ...]
    blocked: tuple[dict[str, Any], ...]

    @property
    def removed_keys(self) -> tuple[str, ...]:
        return tuple(row["key"] for row in self.removed)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "targets": list(self.targets),
            "removed": [dict(row) for row in self.removed],
            "released": [dict(row) for row in self.released],
            "blocked": [dict(row) for row in self.blocked],
            "removed_total": len(self.removed),
            "blocked_total": len(self.blocked),
        }


def deletion_plan(index: "ExplorerIndex", targets: Iterable[str]) -> DeletionPlan:
    """The deletable unit is the reference COMPONENT, and the question is reachability
    AFTER the deletion.

    🔴 IN-DEGREE IS NOT THE INSTRUMENT.  Measured on the live root: every declaration has
    a referrer, and a source and its profile name each other, so a screen gated on
    in-degree refuses every delete and reads as "this screen cannot delete anything".

    The procedure, which never mentions a kind and so cannot rot when a third kind joins
    the cycle:

      1. walk from the roots that REMAIN (`_walk_roots` minus the targets);
      2. whatever was reachable BEFORE and is not reachable after was only held up by what
         is going away -- it is a casualty and goes with the deletion;
      3. a target that is STILL reachable is blocked: something outside the deletion set
         points at it, and the plan names the reacher rather than silently widening.

    Step 2 subtracts against the BEFORE walk rather than against every node, so garbage
    that was already unreachable -- an orphaned cycle nothing enters -- is left exactly
    where it was.  A deletion may only take what it is actually holding up.

    `released` is separate from `removed` because a `table` node is authored in
    `table_config.json`, which this screen only reads.  Such a node stops being referenced
    and nothing is written for it; folding it into `removed` would tell the author their
    physical schema is about to be deleted.
    """
    requested: list[str] = []
    for key in targets:
        node = index.node(key)          # refuses an unknown selection by name
        if node.config_file != setup_bundle.CONFIG_FILENAME:
            raise ConfigExplorerError(
                "undeletable_declaration", "targets",
                f"{node.canonical_id!r} is declared in {node.config_file}, which this "
                f"screen only reads; it cannot be deleted here",
            )
        if key not in requested:
            requested.append(key)
    if not requested:
        raise ConfigExplorerError(
            "empty_deletion", "targets", "no declaration was selected for deletion")

    target_set = set(requested)
    roots = _walk_roots(index)
    before = _reachable(index, roots)
    after = _reachable(index, roots - target_set)
    dead = (target_set | (before - after)) - after

    def order(key: str) -> tuple[int, str, str]:
        node = index.nodes[key]
        return (KIND_ORDER.get(node.kind, 99), node.canonical_id, key)

    removed: list[dict[str, Any]] = []
    released: list[dict[str, Any]] = []
    for key in sorted(dead, key=order):
        node = index.nodes[key]
        row = node.to_mapping(include_definition=False)
        row["reason"] = "selected" if key in target_set else "orphaned"
        # Why this one is going: the referrers that are themselves dying.  An author who
        # cannot see what was holding a casualty up has no way to check the plan.
        row["held_by"] = [
            item["key"] for item in referrers(index, key) if item["key"] in dead
        ]
        (removed if node.config_file == setup_bundle.CONFIG_FILENAME
         else released).append(row)

    blocked: list[dict[str, Any]] = []
    for key in sorted(target_set & after, key=order):
        node = index.nodes[key]
        row = node.to_mapping(include_definition=False)
        row["reason"] = "still_referenced"
        row["reached_by"] = [
            dict(item) for item in referrers(index, key) if item["key"] not in target_set
        ]
        blocked.append(row)

    return DeletionPlan(
        targets=tuple(sorted(target_set, key=order)),
        removed=tuple(removed),
        released=tuple(released),
        blocked=tuple(blocked),
    )


def require_deletable(index: "ExplorerIndex", plan: DeletionPlan, action: str) -> None:
    """Refuse a plan whose targets something OUTSIDE the deletion still reaches.

    The rows travel with the refusal for the same reason as in `require_no_referrers`: a
    refusal that only states a fault leaves the operator with no next move.  Here the move
    is usually "add the reacher to the selection", which is why the reacher is named.
    """
    if not plan.blocked:
        return
    subjects = ", ".join(repr(row["canonical_id"]) for row in plan.blocked)
    rows = [
        {**reacher, "blocked_key": row["key"]}
        for row in plan.blocked for reacher in row["reached_by"]
    ]
    raise ConfigExplorerError(
        "declaration_is_referenced", "targets",
        f"{action} refused: {subjects} would still be referenced from outside the "
        f"deletion; select the referring declaration too, or repoint it first",
        rows,
    )


def pointer_escape(value: str) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def pointer(*parts: Any) -> str:
    return "/" + "/".join(pointer_escape(str(part)) for part in parts)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _hash(value: Any) -> str:
    material = json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _version_family(canonical_id: str) -> tuple[str, str] | None:
    match = _VERSIONED_ID.match(str(canonical_id))
    if match is None:
        return None
    return match.group("prefix"), match.group("suffix")


def _has_other_version(
    canonical_by_kind: Mapping[tuple[str, str], str],
    expected_kind: str,
    target_id: str,
) -> bool:
    family = _version_family(target_id)
    if family is None:
        return False
    return any(
        kind == expected_kind
        and candidate != target_id
        and _version_family(candidate) == family
        for kind, candidate in canonical_by_kind
    )


def _edge_status_message(status: str, target_id: str, expected_kind: str) -> str:
    if status == "resolved":
        return "같은 compiled snapshot에서 참조가 해소됨"
    if status == "wrong_kind":
        return f"{target_id!r}가 존재하지만 {expected_kind} 선언이 아님"
    if status == "wrong_version":
        return f"{expected_kind} {target_id!r}의 요청 버전이 등록되지 않음"
    if status == "signature_mismatch":
        return f"{target_id!r} 참조의 signature가 선언과 일치하지 않음"
    return f"{expected_kind} {target_id!r}를 같은 snapshot에서 찾을 수 없음"


def _node_description(kind: str, raw: Any) -> str:
    if not isinstance(raw, Mapping):
        return f"{kind} 선언"
    if kind == "predicate":
        return f"{raw.get('layer', 'ontology')} predicate · {raw.get('status', 'status 없음')}"
    if kind == "entity":
        return f"identity keys: {', '.join(map(str, raw.get('keys', []))) or '없음'}"
    if kind == "pack":
        return f"claims {len(raw.get('claims', {}))}개"
    if kind == "claim":
        return f"roles {len(raw.get('roles', {}))}개"
    if kind == "profile":
        return f"source {raw.get('source', '없음')} · mappings {len(raw.get('mappings', []))}개"
    if kind == "mapping":
        return f"claim {raw.get('use', '없음')}"
    if kind == "binding":
        return f"{raw.get('kind', 'unknown')} binding"
    if kind in {"preparer", "mapper"}:
        return f"implementation {raw.get('implementation_id', '없음')}"
    if kind == "source_plan":
        return f"relation {raw.get('relation', '없음')}"
    if kind == "verified_join":
        return "물리 UNIQUE 검증을 거친 virtual join"
    if kind == "table":
        return f"columns {len(raw.get('columns', {}))}개"
    return f"{kind} 선언"


@dataclass(frozen=True)
class ExplorerNode:
    key: str
    canonical_id: str
    kind: str
    version: int | None
    config_file: str
    json_pointer: str
    config_path: str
    raw: Any
    compiled: Any
    definition_hash: str
    bundle_path: tuple[Any, ...]

    def to_mapping(self, *, include_definition: bool = True) -> dict[str, Any]:
        result = {
            "key": self.key,
            "canonical_id": self.canonical_id,
            "kind": self.kind,
            "version": self.version,
            "config_file": self.config_file,
            "json_pointer": self.json_pointer,
            "config_path": self.config_path,
            "definition_hash": self.definition_hash,
            "compile_status": "valid",
            "description": _node_description(self.kind, self.raw),
        }
        if include_definition:
            result["raw"] = _plain(self.raw)
            result["compiled"] = _plain(self.compiled)
        return result


@dataclass(frozen=True)
class ReferenceEdge:
    edge_id: str
    from_key: str
    to_key: str | None
    target_id: str
    expected_kind: str
    reference_kind: str
    json_pointer: str
    status: str
    message: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_key": self.from_key,
            "to_key": self.to_key,
            "target_id": self.target_id,
            "expected_kind": self.expected_kind,
            "reference_kind": self.reference_kind,
            "json_pointer": self.json_pointer,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True)
class ExplorerIndex:
    snapshot_hash: str
    bundle_hash: str
    nodes: Mapping[str, ExplorerNode]
    edges: tuple[ReferenceEdge, ...]
    outbound: Mapping[str, tuple[ReferenceEdge, ...]]
    inbound: Mapping[str, tuple[ReferenceEdge, ...]]

    def node(self, key: str) -> ExplorerNode:
        try:
            return self.nodes[key]
        except KeyError as exc:
            raise ConfigExplorerError(
                "unknown_selection", "selection",
                f"selection {key!r} does not exist in this snapshot",
            ) from exc


class _IndexBuilder:
    def __init__(self, snapshot_hash: str, bundle_hash: str):
        self.snapshot_hash = snapshot_hash
        self.bundle_hash = bundle_hash
        self.nodes: dict[str, ExplorerNode] = {}
        self.edge_specs: list[tuple[str, str, str, str, str, str | None]] = []

    def add_node(
        self,
        kind: str,
        canonical_id: str,
        raw: Any,
        compiled: Any,
        bundle_path: Sequence[Any],
        *,
        config_file: str,
        json_pointer: str,
        version: int | None = None,
    ) -> str:
        key = node_key(kind, canonical_id)
        if key in self.nodes:
            raise ConfigExplorerError(
                "duplicate_registry_identity", json_pointer,
                f"duplicate explorer identity {key!r}",
            )
        self.nodes[key] = ExplorerNode(
            key=key,
            canonical_id=canonical_id,
            kind=kind,
            version=version,
            config_file=config_file,
            json_pointer=json_pointer,
            config_path=f"{config_file}#{json_pointer}",
            raw=_plain(raw),
            compiled=_plain(compiled),
            definition_hash=_hash(compiled),
            bundle_path=tuple(bundle_path),
        )
        return key

    def add_edge(
        self,
        from_key: str,
        target_id: str,
        expected_kind: str,
        reference_kind: str,
        json_pointer: str,
        *,
        status: str | None = None,
    ) -> None:
        self.edge_specs.append(
            (from_key, str(target_id), expected_kind, reference_kind, json_pointer, status))

    def finish(self) -> ExplorerIndex:
        canonical_by_kind = {
            (node.kind, node.canonical_id): node.key for node in self.nodes.values()
        }
        keys_by_canonical: dict[str, list[str]] = {}
        for node in self.nodes.values():
            keys_by_canonical.setdefault(node.canonical_id, []).append(node.key)

        edges: list[ReferenceEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for from_key, target_id, expected_kind, ref_kind, ref_pointer, forced_status in sorted(
            self.edge_specs,
            key=lambda item: (item[0], item[4], item[3], item[1], item[5] or ""),
        ):
            to_key = canonical_by_kind.get((expected_kind, target_id))
            if forced_status is not None:
                status = forced_status
            elif to_key is not None:
                status = "resolved"
            elif target_id in keys_by_canonical:
                status = "wrong_kind"
            elif _has_other_version(canonical_by_kind, expected_kind, target_id):
                status = "wrong_version"
            else:
                status = "unresolved"
            identity = (from_key, ref_kind, ref_pointer)
            if identity in seen:
                raise ConfigExplorerError(
                    "duplicate_reference_edge", ref_pointer,
                    "the same reference edge was extracted more than once",
                )
            seen.add(identity)
            edge_id = sha256(json.dumps(
                [from_key, to_key, target_id, expected_kind, ref_kind, ref_pointer],
                ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()[:20]
            edges.append(ReferenceEdge(
                edge_id=edge_id,
                from_key=from_key,
                to_key=to_key,
                target_id=target_id,
                expected_kind=expected_kind,
                reference_kind=ref_kind,
                json_pointer=ref_pointer,
                status=status,
                message=_edge_status_message(status, target_id, expected_kind),
            ))

        outbound: dict[str, list[ReferenceEdge]] = {key: [] for key in self.nodes}
        inbound: dict[str, list[ReferenceEdge]] = {key: [] for key in self.nodes}
        for edge in edges:
            outbound[edge.from_key].append(edge)
            if edge.to_key is not None:
                inbound[edge.to_key].append(edge)
        return ExplorerIndex(
            snapshot_hash=self.snapshot_hash,
            bundle_hash=self.bundle_hash,
            nodes=MappingProxyType(dict(sorted(self.nodes.items()))),
            edges=tuple(edges),
            outbound=MappingProxyType({
                key: tuple(value) for key, value in sorted(outbound.items())
            }),
            inbound=MappingProxyType({
                key: tuple(value) for key, value in sorted(inbound.items())
            }),
        )


def _setup_catalog(setup: Any) -> Mapping[str, Any]:
    """The physical catalog this setup was VALIDATED against, never a fresh guess.

    🔴 NO SILENT FALLBACK TO THE LIVE FILE.  A setup validated against one catalog and
    displayed against another is a screen that agrees with nothing -- and it would show
    the operator's production tables underneath a sample's declarations.  A carrier that
    does not hold one is refused by name, which is a bug report; loading the live file
    here would have been a false green.
    """
    catalog = getattr(setup, "catalog", None)
    if not isinstance(catalog, Mapping):
        raise ConfigExplorerError(
            "physical_catalog_missing", "setup.catalog",
            f"the setup carries no physical catalog; it must be loaded with the "
            f"{setup_bundle.PHYSICAL_CATALOG_FILENAME} shape it was validated against")
    return catalog


def build_explorer_index(setup: Any) -> ExplorerIndex:
    """Build one deterministic graph from one compiled cutover setup."""
    snapshot = setup.snapshot
    bundle = setup.bundle.to_mapping()
    builder = _IndexBuilder(snapshot.snapshot_sha256, snapshot.bundle_sha256)
    registries = snapshot.registries
    # Same constant `deletion_plan` classifies against, so "this screen writes that file"
    # cannot drift apart from "this screen produced that node".
    ledger_file = setup_bundle.CONFIG_FILENAME

    for predicate_id, raw in sorted(bundle["vocabulary"].items()):
        compiled = registries["vocabulary"].to_mapping()[predicate_id]
        p = pointer("vocabulary", predicate_id)
        key = builder.add_node(
            "predicate", predicate_id, raw, compiled,
            ("vocabulary", predicate_id), config_file=ledger_file,
            json_pointer=p, version=compiled.get("version"),
        )
        for index, entity_id in enumerate(raw.get("subjects", [])):
            builder.add_edge(
                key, entity_id, "entity", "subject_entity",
                pointer("vocabulary", predicate_id, "subjects", index),
            )
        obj = raw.get("object") or {}
        for index, entity_id in enumerate(obj.get("types", [])):
            builder.add_edge(
                key, entity_id, "entity", "object_entity",
                pointer("vocabulary", predicate_id, "object", "types", index),
            )

    for entity_id, raw in sorted(bundle["entities"].items()):
        compiled = registries["entities"].to_mapping()[entity_id]
        builder.add_node(
            "entity", entity_id, raw, compiled, ("entities", entity_id),
            config_file=ledger_file, json_pointer=pointer("entities", entity_id),
            version=compiled.get("version"),
        )

    pack_compiled = registries["packs"].to_mapping()
    for pack_id, raw in sorted(bundle["packs"].items()):
        compiled = pack_compiled[pack_id]
        pack_key = builder.add_node(
            "pack", pack_id, raw, compiled, ("packs", pack_id),
            config_file=ledger_file, json_pointer=pointer("packs", pack_id),
            version=compiled.get("version"),
        )
        for claim_id, claim in sorted(raw.get("claims", {}).items()):
            claim_ref = f"{pack_id}/{claim_id}"
            claim_pointer = pointer("packs", pack_id, "claims", claim_id)
            claim_compiled = compiled["claims"][claim_id]
            claim_key = builder.add_node(
                "claim", claim_ref, claim, claim_compiled,
                ("packs", pack_id, "claims", claim_id),
                config_file=ledger_file, json_pointer=claim_pointer,
            )
            builder.add_edge(
                pack_key, claim_ref, "claim", "contains_claim", claim_pointer)
            predicate_id = claim.get("emit", {}).get("predicate")
            if predicate_id is not None:
                builder.add_edge(
                    claim_key, predicate_id, "predicate", "emits_predicate",
                    pointer("packs", pack_id, "claims", claim_id, "emit", "predicate"),
                )

    preparer_compiled = registries["source_preparers"].to_mapping()
    for preparer_id, raw in sorted(bundle["source_preparers"].items()):
        compiled = preparer_compiled[preparer_id]
        builder.add_node(
            "preparer", preparer_id, raw, compiled,
            ("source_preparers", preparer_id), config_file=ledger_file,
            json_pointer=pointer("source_preparers", preparer_id),
            version=compiled.get("version"),
        )

    mapper_compiled = registries["mappers"].to_mapping()
    for mapper_id, raw in sorted(bundle["mappers"].items()):
        compiled = mapper_compiled[mapper_id]
        mapper_key = builder.add_node(
            "mapper", mapper_id, raw, compiled, ("mappers", mapper_id),
            config_file=ledger_file, json_pointer=pointer("mappers", mapper_id),
            version=compiled.get("version"),
        )
        for index, claim_ref in enumerate(raw.get("emits", [])):
            builder.add_edge(
                mapper_key, claim_ref, "claim", "mapper_emits",
                pointer("mappers", mapper_id, "emits", index),
            )

    profile_compiled = registries["profiles"].to_mapping()
    for profile_id, raw in sorted(bundle["profiles"].items()):
        compiled = profile_compiled[profile_id]
        profile_key = builder.add_node(
            "profile", profile_id, raw, compiled, ("profiles", profile_id),
            config_file=ledger_file, json_pointer=pointer("profiles", profile_id),
            version=compiled.get("version"),
        )
        builder.add_edge(
            profile_key, raw.get("source", ""), "source_plan", "profile_source",
            pointer("profiles", profile_id, "source"),
        )
        for index, pack_id in enumerate(raw.get("packs", [])):
            builder.add_edge(
                profile_key, pack_id, "pack", "profile_pack",
                pointer("profiles", profile_id, "packs", index),
            )
        for index, mapping in enumerate(raw.get("mappings", [])):
            mapping_id = str(mapping.get("mapping_id", index))
            mapping_ref = f"{profile_id}#mapping:{mapping_id}"
            mapping_pointer = pointer("profiles", profile_id, "mappings", index)
            mapping_key = builder.add_node(
                "mapping", mapping_ref, mapping,
                compiled["mappings"][index],
                ("profiles", profile_id, "mappings", index),
                config_file=ledger_file, json_pointer=mapping_pointer,
            )
            builder.add_edge(
                profile_key, mapping_ref, "mapping", "contains_mapping",
                mapping_pointer,
            )
            builder.add_edge(
                mapping_key, mapping.get("use", ""), "claim", "mapping_claim",
                pointer("profiles", profile_id, "mappings", index, "use"),
            )
            compiled_bindings = compiled["mappings"][index].get("bindings", {})
            for role_id, binding in sorted(mapping.get("bind", {}).items()):
                binding_ref = f"{mapping_ref}#binding:{role_id}"
                binding_pointer = pointer(
                    "profiles", profile_id, "mappings", index, "bind", role_id)
                binding_key = builder.add_node(
                    "binding", binding_ref, binding,
                    compiled_bindings.get(role_id, binding),
                    ("profiles", profile_id, "mappings", index, "bind", role_id),
                    config_file=ledger_file, json_pointer=binding_pointer,
                )
                builder.add_edge(
                    mapping_key, binding_ref, "binding", "mapping_binding",
                    binding_pointer,
                )
                for entity_pointer, entity_id in _entity_binding_refs(
                    binding,
                    ("profiles", profile_id, "mappings", index, "bind", role_id),
                ):
                    builder.add_edge(
                        binding_key, entity_id, "entity", "binding_entity",
                        entity_pointer,
                    )

    # 🔴 TABLE NODES COME FROM `table_config.json` NOW, NOT FROM THE LEDGER FILE.
    # Two consequences worth stating because both are deliberate:
    #  * `config_file` is no longer `ledger_config.json`, so `config_drafts` routes an
    #    edit attempt to its existing `unsupported_draft_target` refusal.  A table is not
    #    editable HERE because it is not authored here -- the operator edits
    #    `table_config.json`, where the change also reaches ingestion, the grid, and the
    #    drift check.
    #  * Only relations this setup actually REFERENCES become nodes.  The catalog declares
    #    every table in the system; making a node per catalog entry would fill the graph
    #    with tables the ledger has nothing to say about.  The referenced set is exactly
    #    what the retired `tables` section held, which is why the graph does not change
    #    shape for a config that was already correct.
    table_file = setup_bundle.PHYSICAL_CATALOG_FILENAME
    catalog = _setup_catalog(setup)
    referenced: set[str] = set()
    for raw in bundle["sources"].values():
        relation = raw.get("relation")
        if isinstance(relation, str):
            referenced.add(relation)
    for raw in bundle["virtual_joins"].values():
        for field in ("left_table", "right_table"):
            relation = raw.get(field)
            if isinstance(relation, str):
                referenced.add(relation)
    for table_id in sorted(referenced):
        # A referenced-but-undeclared relation is already a load-time refusal
        # (`unknown_relation`), so reaching here with a miss means the caller built an
        # index from an unvalidated bundle.  Skip rather than invent an empty table: a
        # node with no columns reads as "declared, and empty", which is the false green
        # this whole change exists to remove.
        raw = catalog.get(table_id)
        if raw is None:
            continue
        builder.add_node(
            "table", table_id, raw, raw, ("__physical_catalog__", table_id),
            config_file=table_file, json_pointer=pointer(table_id),
        )

    join_compiled = registries["verified_joins"].to_mapping()
    join_file = ledger_file
    for join_id, raw in sorted(bundle["virtual_joins"].items()):
        compiled = join_compiled.get(join_id, raw)
        builder.add_node(
            "verified_join", join_id, raw, compiled,
            ("virtual_joins", join_id), config_file=join_file,
            json_pointer=pointer("virtual_joins", join_id),
        )

    source_compiled = registries["sources"].to_mapping()
    for source_id, raw in sorted(bundle["sources"].items()):
        compiled = source_compiled[source_id]
        source_key = builder.add_node(
            "source_plan", source_id, raw, compiled, ("sources", source_id),
            config_file=ledger_file, json_pointer=pointer("sources", source_id),
        )
        builder.add_edge(
            source_key, raw.get("relation", ""), "table", "source_relation",
            pointer("sources", source_id, "relation"),
        )
        builder.add_edge(
            source_key, raw.get("profile_id", ""), "profile", "source_profile",
            pointer("sources", source_id, "profile_id"),
        )
        driver = raw.get("driver", {})
        builder.add_edge(
            source_key, driver.get("mapper_id", ""), "mapper", "source_mapper",
            pointer("sources", source_id, "driver", "mapper_id"),
        )
        preparation = driver.get("preparation", {})
        builder.add_edge(
            source_key, preparation.get("preparer_id", ""), "preparer",
            "source_preparer",
            pointer("sources", source_id, "driver", "preparation", "preparer_id"),
        )
        for index, join_id in enumerate(
            preparation.get("inherit_virtual_join_rules", []),
        ):
            builder.add_edge(
                source_key, join_id, "verified_join", "source_verified_join",
                pointer(
                    "sources", source_id, "driver", "preparation",
                    "inherit_virtual_join_rules", index,
                ),
            )
    return builder.finish()


def _entity_binding_refs(value: Any, base: Sequence[Any]) -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        entity_type = value.get("entity_type")
        if isinstance(entity_type, str):
            yield pointer(*base, "entity_type"), entity_type
        for key in sorted(value, key=str):
            yield from _entity_binding_refs(value[key], (*base, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _entity_binding_refs(item, (*base, index))


def definition_diff(
    active: ExplorerIndex,
    preview: ExplorerIndex,
) -> Mapping[str, str]:
    result: dict[str, str] = {}
    all_keys = sorted(set(active.nodes) | set(preview.nodes))
    for key in all_keys:
        if key not in active.nodes:
            result[key] = "added"
        elif key not in preview.nodes:
            result[key] = "removed"
        elif active.nodes[key].definition_hash != preview.nodes[key].definition_hash:
            result[key] = "modified"
        else:
            result[key] = "unchanged"
    return MappingProxyType(result)


def reference_diff(
    active: ExplorerIndex,
    preview: ExplorerIndex,
) -> Mapping[str, str]:
    def slot(edge: ReferenceEdge) -> tuple[str, str, str]:
        return edge.from_key, edge.reference_kind, edge.json_pointer

    def content(edge: ReferenceEdge) -> tuple[str | None, str, str, str, str | None]:
        return (
            edge.to_key, edge.target_id, edge.expected_kind, edge.status, edge.message,
        )

    active_by_slot = {slot(edge): edge for edge in active.edges}
    preview_by_slot = {slot(edge): edge for edge in preview.edges}
    result: dict[str, str] = {}
    for logical_slot in sorted(set(active_by_slot) | set(preview_by_slot)):
        active_edge = active_by_slot.get(logical_slot)
        preview_edge = preview_by_slot.get(logical_slot)
        if active_edge is None:
            result[preview_edge.edge_id] = "added"
        elif preview_edge is None:
            result[active_edge.edge_id] = "removed"
        elif content(active_edge) != content(preview_edge):
            result[preview_edge.edge_id] = "modified"
        else:
            result[preview_edge.edge_id] = "unchanged"
    return MappingProxyType(dict(sorted(result.items())))


def _path_candidates(index: ExplorerIndex, selection: str, limit: int = 12
                     ) -> list[dict[str, Any]]:
    """Return separate inbound paths; never merge branches into a fictional chain."""
    queue = deque([((selection,), tuple())])
    paths: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    while queue and len(paths) < limit:
        nodes, edge_ids = queue.popleft()
        current = nodes[0]
        # Only `limit` paths can be returned. Enqueuing an unbounded high-degree inbound
        # fan-in would inflate memory even though every item after the limit is discarded.
        inbound = [
            edge for edge in index.inbound[current] if edge.status == "resolved"
        ][:limit]
        if not inbound or len(nodes) >= 7:
            paths.append((nodes, edge_ids))
            continue
        expanded = False
        for edge in inbound:
            if edge.from_key in nodes:
                continue
            queue.append(((edge.from_key, *nodes), (edge.edge_id, *edge_ids)))
            expanded = True
        if not expanded:
            paths.append((nodes, edge_ids))
    if not paths:
        paths = [((selection,), tuple())]
    return [
        {"path_id": _hash([list(nodes), list(edges)])[:16],
         "node_keys": list(nodes), "edge_ids": list(edges)}
        for nodes, edges in paths
    ]


def explorer_view(
    index: ExplorerIndex,
    *,
    context_token: str,
    selection: str | None = None,
    query: str = "",
    page: int = 1,
    limit: int = 100,
    reference_limit: int = 200,
    diff: Mapping[str, str] | None = None,
    edge_diff: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if page < 1:
        raise ConfigExplorerError("invalid_page", "page", "must be at least 1")
    if limit < 1 or limit > 500:
        raise ConfigExplorerError("invalid_limit", "limit", "must be between 1 and 500")
    if reference_limit < 1 or reference_limit > 500:
        raise ConfigExplorerError(
            "invalid_reference_limit", "reference_limit", "must be between 1 and 500")
    ordered = sorted(
        index.nodes.values(),
        key=lambda node: (KIND_ORDER.get(node.kind, 99), node.canonical_id, node.key),
    )
    needle = query.strip().casefold()
    if needle:
        ordered = [node for node in ordered if needle in node.canonical_id.casefold()
                   or needle in node.kind.casefold()]
    total = len(ordered)
    start = (page - 1) * limit
    items = ordered[start:start + limit]
    if selection is None:
        selection = items[0].key if items else (
            next(iter(index.nodes)) if index.nodes else None)
    if selection is None:
        raise ConfigExplorerError(
            "empty_snapshot", "selection", "snapshot contains no explorer declarations")
    selected = index.node(selection)
    node_diff = diff or {}
    ref_diff = edge_diff or {}

    def node_summary(node: ExplorerNode) -> dict[str, Any]:
        value = node.to_mapping(include_definition=False)
        value["change_status"] = node_diff.get(node.key, "active")
        return value

    all_outbound = index.outbound[selected.key]
    all_inbound = index.inbound[selected.key]
    visible_outbound = all_outbound[:reference_limit]
    visible_inbound = all_inbound[:reference_limit]
    neighborhood_keys = {selected.key}
    for edge in (*visible_outbound, *visible_inbound):
        neighborhood_keys.add(edge.from_key)
        if edge.to_key:
            neighborhood_keys.add(edge.to_key)
    paths = _path_candidates(index, selected.key)
    for path_item in paths:
        neighborhood_keys.update(path_item["node_keys"])

    checks = integrity_checks(index, selected.key)
    selection_mapping = selected.to_mapping(include_definition=True)
    selection_mapping["context_token"] = context_token
    selection_mapping["change_status"] = node_diff.get(selected.key, "active")
    item_mappings = [node_summary(node) for node in items]
    neighborhood_mappings = [
        node_summary(index.nodes[key]) for key in sorted(neighborhood_keys)
    ]
    outbound_mappings = [edge.to_mapping() for edge in visible_outbound]
    inbound_mappings = [edge.to_mapping() for edge in visible_inbound]
    for item in (*outbound_mappings, *inbound_mappings):
        item["change_status"] = ref_diff.get(item["edge_id"], "active")
    for item in paths:
        item["context_token"] = context_token
    for item in checks:
        item["context_token"] = context_token
    for collection in (
        item_mappings, neighborhood_mappings, outbound_mappings, inbound_mappings,
    ):
        for item in collection:
            item["context_token"] = context_token
    return {
        "context_token": context_token,
        "snapshot_hash": index.snapshot_hash,
        "selection": selection_mapping,
        "items": item_mappings,
        "page": page,
        "limit": limit,
        "total": total,
        "outbound": outbound_mappings,
        "used_by": inbound_mappings,
        "outbound_total": len(all_outbound),
        "used_by_total": len(all_inbound),
        "reference_limit": reference_limit,
        "references_truncated": (
            len(all_outbound) > reference_limit or len(all_inbound) > reference_limit),
        "path_candidates": paths,
        "nodes": neighborhood_mappings,
        "integrity": checks,
        "changes": [
            {"key": key, "change_status": status, "context_token": context_token}
            for key, status in sorted(node_diff.items()) if status != "unchanged"
        ],
        "edge_changes": [
            {"edge_id": key, "change_status": status, "context_token": context_token}
            for key, status in sorted(ref_diff.items()) if status != "unchanged"
        ],
    }


def integrity_checks(index: ExplorerIndex, selection: str) -> list[dict[str, str]]:
    node = index.node(selection)
    edges = (*index.outbound[selection], *index.inbound[selection])
    unresolved = sum(edge.status != "resolved" for edge in edges)
    common = [{
        "code": "reference_resolution",
        "status": "valid" if unresolved == 0 else "invalid",
        "message": f"직접 참조 {len(edges)}건 · 미해소 {unresolved}건",
    }]
    if node.kind == "predicate":
        common.append({"code": "predicate_signature", "status": "valid",
                       "message": "subject/object/qualifier signature가 compile됨"})
    elif node.kind == "entity":
        common.append({"code": "entity_identity", "status": "valid",
                       "message": "identity key와 사용처가 compile됨"})
    elif node.kind in {"pack", "claim"}:
        common.append({"code": "pack_emission", "status": "valid",
                       "message": "Role과 emission 계약이 compile됨"})
    elif node.kind in {"profile", "mapping"}:
        common.append({"code": "profile_binding", "status": "valid",
                       "message": "source·Pack·Role binding이 compile됨"})
    elif node.kind == "source_plan":
        common.append({"code": "source_plan", "status": "valid",
                       "message": "relation·cursor·preparer·mapper 계약이 compile됨"})
    else:
        common.append({"code": "kind_specific", "status": "not_applicable",
                       "message": f"{node.kind}에는 추가 signature 검사가 적용되지 않음"})
    return common
