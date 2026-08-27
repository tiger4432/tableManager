"""Compile one ledger source into the contract an operator actually needs.

``ledger_config.json`` says how a source is wired, a translator implements the
row/group -> atom shape, and ``vocabulary`` judges whether those atoms are legal.  Those
three remain separate runtime responsibilities, but they are *one authoring question*.
This module joins them into one read model and refuses combinations that can only fail at
runtime.

It deliberately contains no persistence.  The admin dry-run is the mutation gate and
uses this compiler before it touches the real translator.  That keeps "what will this
source say?" identical in the form, the preview, and the save path.
"""
from __future__ import annotations

from . import config


PROFILE_META = {
    config.SOURCE_KIND_LINEAGE: {
        "profile": "paired_lineage",
        "implementation": "ledger.lot_event_translator.LotEventTranslator",
        "molecule": "같은 사건시각·event type·부모·자식으로 짝지은 행 묶음",
        "operator": "두 행 결합 + 위치 목록 짝짓기",
    },
    config.SOURCE_KIND_OBSERVATION: {
        "profile": "finding_observation",
        "implementation": "ledger.observation_translator.ObservationTranslator",
        "molecule": "원천 한 행",
        "operator": "검사 run을 결합한 관측 발화",
    },
    config.SOURCE_KIND_TRANSFER: {
        "profile": "grouped_transfer",
        "implementation": "ledger.transfer_translator.TransferTranslator",
        "molecule": "선언한 group column 값 하나",
        "operator": "이동 행 묶음을 원천 wafer별 수량으로 접기",
    },
    config.SOURCE_KIND_DECLARED: {
        "profile": "declared_row_emitter",
        "implementation": "ledger.declared_translator.DeclaredTranslator",
        "molecule": "원천 한 행",
        "operator": "emit 선언을 그대로 실행",
    },
}


def _emission(predicate, subjects, object_kind=None, object_types=(), qualifiers=(),
              payload_fields=(), derivations=(), configured_by=None, event_types=()):
    return {
        "predicate": predicate,
        "subject_types": sorted(set(subjects)),
        "object_kind": object_kind,
        "object_types": sorted(set(object_types)),
        "qualifiers": sorted(set(qualifiers)),
        "payload_fields": sorted(set(payload_fields)),
        "derivations": sorted(set(derivations)),
        "configured_by": configured_by,
        "event_types": sorted(set(event_types)),
    }


def _declared_signature(predicate):
    """One predicate's declared shape, or `None`. 🔴 REPLACES `vocabulary.signature`.

    The declaration is the authority since 2026-08-27 and carries the same three things this
    module reads - `subjects`, `object`, `status`. Ids are versioned there (`observed@1`) and
    bare on an atom, so the version comes off on the way past, exactly as `_runtime_id` does
    it for the emit path. An unreadable declaration answers `None`, which this module already
    treats as「undeclared」rather than as an error.
    """
    try:
        declared = (config.load() or {}).get("vocabulary") or {}
    except Exception:
        return None
    for key, item in declared.items():
        if str(key).split("@", 1)[0] == predicate:
            return item
    return None


def _declared_subjects(signature):
    """`{"die@1"}` -> `{"die"}`, lowercased.

    The case folds for the same reason `ledger/config.py` folds it: the declaration's
    address and the spelling on an atom are the same name at different depths, and a
    declaration written `"Lot"` must not be a different type from `lot@1`.
    """
    return {str(name).split("@", 1)[0].strip().lower()
            for name in (signature.get("subjects") or ())}


def _register_emission(subjects, configured_by="register_entity_types", event_types=()):
    # 🔴 THE `requires_register` FILTER LEFT WITH THE v1 VOCABULARY. It kept only the
    # types that word list called「issued」, and the declaration has no such field - it names
    # entities and their keys, nothing else. So the operator's own list is taken at its word,
    # which is what「선언이 정본」means here: the declaration said these types register.
    issued = list(subjects)
    if not issued:
        return None
    return _emission("register", issued, derivations=("first_sight",),
                     configured_by=configured_by, event_types=event_types)


def _lineage_emissions(source_cfg):
    rules = source_cfg.get("vocabulary") or {}
    out = []
    register_events = [name for name, rule in rules.items()
                       if rule.get("emit_register", True)]
    register = (_register_emission(
        set(source_cfg.get("register_entity_types") or ()) & {"Lot", "Wafer"},
        "vocabulary.*.emit_register", register_events) if register_events else None)
    if register:
        out.append(register)

    membership_events = [name for name, rule in rules.items()
                         if rule.get("emit_has_wafer", True)]
    if membership_events:
        out.append(_emission(
            "has_wafer", ("Lot",), "entity_ref", ("Wafer",), ("slot",),
            derivations=("positional_row",), configured_by="vocabulary.*.emit_has_wafer",
            event_types=membership_events))

    lineage_events = [name for name, rule in rules.items()
                      if rule.get("lineage", "none") == "parent_child"]
    if lineage_events:
        out.append(_emission(
            "derived_from", ("Lot",), "entity_ref", ("Lot",),
            derivations=("pair_field",), configured_by="vocabulary.*.lineage",
            event_types=lineage_events))

    pairings = {rule.get("slot_pairing", "none") for rule in rules.values()}
    pairings.discard("none")
    if pairings:
        pairing_events = [name for name, rule in rules.items()
                          if rule.get("slot_pairing", "none") != "none"]
        out.append(_emission(
            "slot_map", ("Lot",), "entity_ref", ("Lot",),
            ("from", "to", "wafer"), derivations=pairings,
            configured_by="vocabulary.*.slot_pairing", event_types=pairing_events))
    return out


def _observation_emissions(source_cfg):
    out = []
    register = _register_emission(
        set(source_cfg.get("register_entity_types") or ()) & {"Wafer"})
    if register:
        out.append(register)
    out.append(_emission(
        config.OBSERVATION_PREDICATE, ("Wafer",), "value",
        payload_fields=("finding_kind", "method", "run_uid", "die", "inchip",
                        "extent", "unit", "class", "synthetic"),
        derivations=(config.DERIVATION_OBSERVATION_ROW,), configured_by="finding_kind"))
    return out


def _transfer_emissions(source_cfg):
    out = []
    register = _register_emission(
        set(source_cfg.get("register_entity_types") or ()) & {"Wafer"})
    if register:
        out.append(register)
    derivations = {config.DERIVATION_TRANSFER_JOB}
    container = source_cfg.get("container") or {}
    if container.get("relation"):
        derivations.add(config.DERIVATION_TRANSFER_CONFIRMED)
    out.append(_emission(
        config.TRANSFER_PREDICATE, ("Wafer",), "value",
        payload_fields=("from", "to", "qty", "container_recorded"),
        derivations=derivations, configured_by="group + container"))
    return out


def _declared_emissions(source_cfg):
    out = []
    subject_types = {str((rule.get("subject") or {}).get("type") or "").strip()
                     for rule in source_cfg.get("emit") or []}
    subject_types.discard("")
    register = _register_emission(
        subject_types & set(source_cfg.get("register_entity_types") or ()))
    if register:
        out.append(register)

    for index, rule in enumerate(source_cfg.get("emit") or []):
        subject_type = str((rule.get("subject") or {}).get("type") or "").strip()
        declared_object = rule.get("object")
        object_kind, object_types, qualifiers, payload_fields = None, (), (), ()
        if isinstance(declared_object, dict):
            object_kind = declared_object.get("kind")
            if object_kind == "entity_ref":
                object_types = (declared_object.get("type"),)
                qualifiers = tuple((declared_object.get("qualifiers") or {}).keys())
            elif object_kind == "value":
                payload_fields = tuple((declared_object.get("payload") or {}).keys())
                if source_cfg.get("occurred_at_basis"):
                    payload_fields += ("occurred_at_basis",)
                if source_cfg.get("synthetic"):
                    payload_fields += ("synthetic",)
        out.append(_emission(
            str(rule.get("predicate") or "").strip(), (subject_type,), object_kind,
            object_types, qualifiers, payload_fields,
            derivations=(str(rule.get("rule") or "").strip(),),
            configured_by=f"emit[{index}]"))
    return out


def emissions(source_cfg):
    kind = source_cfg.get("kind", config.SOURCE_KIND_LINEAGE)
    if kind == config.SOURCE_KIND_OBSERVATION:
        return _observation_emissions(source_cfg)
    if kind == config.SOURCE_KIND_TRANSFER:
        return _transfer_emissions(source_cfg)
    if kind == config.SOURCE_KIND_DECLARED:
        return _declared_emissions(source_cfg)
    return _lineage_emissions(source_cfg)


def _source_compatibility(source, source_cfg, emission):
    """Check the coded profile against this source declaration, not only vocabulary.

    The live vocabulary can allow a claim that this particular source did not enable.
    Without this half, a typo such as a coded ``#derivation`` absent from the declaration
    survives Source Contract and is refused only after rows are read.
    """
    candidate = {"sources": {source: source_cfg}}
    allowed_subjects = set(config.declared_subject_types(candidate, source))
    allowed_derivations = set(config.declared_derivations(candidate, source))
    issues = []

    extra_subjects = set(emission["subject_types"]) - allowed_subjects
    if extra_subjects:
        issues.append({
            "code": "subject_not_enabled_by_source",
            "detail_ko": (
                f"번역기는 주어 {', '.join(sorted(extra_subjects))}를 만들지만 "
                "이 소스의 subject_types에는 없습니다."),
        })

    extra_derivations = set(emission["derivations"]) - allowed_derivations
    if extra_derivations:
        issues.append({
            "code": "derivation_not_enabled_by_source",
            "detail_ko": (
                f"번역기는 파생 {', '.join(sorted(extra_derivations))}를 만들지만 "
                "이 소스 선언은 허용하지 않습니다."),
        })
    return issues


def _compatibility(source, source_cfg, emission):
    predicate = emission["predicate"]
    signature = _declared_signature(predicate)
    issues = _source_compatibility(source, source_cfg, emission)
    if signature is None:
        issues.append({
            "code": "predicate_undeclared",
            "detail_ko": f"번역기는 '{predicate}' Claim을 만들지만 vocabulary에 서명이 없습니다.",
        })
        return "undeclared", None, issues

    if str(signature.get("status") or "active") != "active":
        issues.append({
            "code": "predicate_not_emittable",
            "detail_ko": f"'{predicate}'는 vocabulary에 있지만 현재 발화 가능한 상태가 아닙니다.",
        })

    allowed_subjects = _declared_subjects(signature)
    missing_subjects = {str(t).strip().lower()
                        for t in emission["subject_types"]} - allowed_subjects
    if missing_subjects:
        issues.append({
            "code": "subject_signature_mismatch",
            "detail_ko": (f"'{predicate}' 번역기가 주어 {', '.join(sorted(missing_subjects))}를 "
                          "만들지만 vocabulary 서명이 허용하지 않습니다."),
        })

    declared_object = signature.get("object")
    declared_kind = declared_object.get("kind") if isinstance(declared_object, dict) else None
    # 🔴 "none" AND None ARE THE SAME OBJECT KIND, spelled at two depths. The v1 word
    # list wrote `object: None` for an objectless predicate; the declaration writes
    # `object: {"kind": "none"}` - the same fact, said in the grammar every other predicate
    # uses. Without this, `register` - the one predicate that HAS no object - reports a
    # signature mismatch against its own declaration.
    if declared_kind == "none":
        declared_kind = None
    if emission["object_kind"] != declared_kind:
        issues.append({
            "code": "object_signature_mismatch",
            "detail_ko": (f"'{predicate}' 번역기의 목적어는 {emission['object_kind']!r}인데 "
                          f"vocabulary 서명은 {declared_kind!r}입니다."),
        })
    elif declared_kind == "entity_ref":
        allowed_types = set(declared_object.get("types") or ())
        missing_types = set(emission["object_types"]) - allowed_types
        if missing_types:
            issues.append({
                "code": "object_type_signature_mismatch",
                "detail_ko": (f"'{predicate}' 목적어 타입 {', '.join(sorted(missing_types))}를 "
                              "vocabulary 서명이 허용하지 않습니다."),
            })
        declared_qualifiers = set(signature.get("qualifiers") or ())
        emitted_qualifiers = set(emission["qualifiers"])
        if emitted_qualifiers != declared_qualifiers:
            issues.append({
                "code": "qualifier_signature_mismatch",
                "detail_ko": (f"'{predicate}' qualifier가 번역기 "
                              f"{sorted(emitted_qualifiers)} / vocabulary "
                              f"{sorted(declared_qualifiers)}로 다릅니다."),
            })
    elif declared_kind == "value":
        required = set(declared_object.get("required") or ())
        missing = required - set(emission["payload_fields"])
        if missing:
            issues.append({
                "code": "required_payload_not_emitted",
                "detail_ko": (f"'{predicate}' vocabulary 필수값 {', '.join(sorted(missing))}을 "
                              "번역기 선언이 만들지 않습니다."),
            })

    public_signature = {
        key: signature.get(key) for key in (
            "origin", "layer", "status", "subject", "object", "qualifiers",
            "traversable", "direction", "since", "superseded_by")
        if key in signature
    }
    return ("ready" if not issues else "incompatible"), public_signature, issues


def compile_source(source, source_cfg):
    """Return the joined source -> translator -> vocabulary authoring contract."""
    source_cfg = source_cfg if isinstance(source_cfg, dict) else {}
    kind = source_cfg.get("kind", config.SOURCE_KIND_LINEAGE)
    translator = dict(PROFILE_META.get(kind) or {
        "profile": str(kind), "implementation": None, "molecule": None,
        "operator": None,
    })
    translator["kind"] = kind

    compiled = []
    all_issues = []
    for emitted in emissions(source_cfg):
        state, signature, issues = _compatibility(source, source_cfg, emitted)
        row = dict(emitted)
        row.update(state=state, vocabulary=signature, issues=issues)
        compiled.append(row)
        all_issues.extend(dict(issue, predicate=emitted["predicate"],
                               configured_by=emitted.get("configured_by"))
                          for issue in issues)

    state = "ready" if not all_issues else "incompatible"
    return {
        "source": source,
        "state": state,
        "translator": translator,
        "columns": dict(source_cfg.get("columns") or {}),
        "emissions": compiled,
        "issues": all_issues,
        "sentence_ko": (
            f"'{source}'는 {translator['profile']} 번역기로 Claim {len(compiled)}종을 발화하며 "
            f"vocabulary와 {'맞물립니다' if state == 'ready' else '맞지 않습니다'}."
        ),
    }
