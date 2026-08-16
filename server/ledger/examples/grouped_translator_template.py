"""COPY TEMPLATE: a grouped source molecule -> ontology claims.

Search for ``CUSTOMIZE``.  Those four blocks are the intended edit surface.  Everything
else is lifecycle code inherited from ``SafeTranslatorTemplate``.

This example models one process job containing several wafer rows.  It is deliberately
not registered in ``backfill``: copying a template must never make example claims writable.
"""
from __future__ import annotations

from ledger import gate
from ledger.translator_pattern import ClaimDraft, SafeTranslatorTemplate, SourceMolecule


# CUSTOMIZE 1/4 -- use constants in BOTH the code and the contract below, so their spelling
# cannot drift inside this file.
PROFILE = "grouped_process_job"
PREDICATE = "processed_with"
DERIVATION = "job_row_observation"


# CUSTOMIZE 2/4 -- complete possible output, including branches a 20-row dry run may not hit.
# Registering a new runtime profile must hand this COMPLETE shape to Source Contract. It is
# not a second vocabulary: the compiler resolves it against the live vocabulary and refuses
# disagreement. This example is intentionally not registered, so copying it alone writes 0 rows.
POSSIBLE_EMISSIONS = ({
    "predicate": PREDICATE,
    "subject_types": ["Wafer"],
    "object_kind": "value",
    "payload_fields": ["step", "recipe", "equipment"],
    "derivations": [DERIVATION],
},)


def group_rows(source, rows):
    """CUSTOMIZE 3/4 -- rows -> indivisible molecules.

    The real fetch driver must page on this SAME ``job_id`` boundary; otherwise one job can
    be split between transactions.  This function only states grouping, not paging.
    """
    grouped = {}
    order = []
    for row in rows:
        job_id = str(row.get("job_id") or "").strip()
        if not job_id:
            # Grouping happens before a translator scope exists. The driver should refuse
            # this row by name or isolate it into a molecule that the translator refuses.
            job_id = f"<missing:{row.get('row_identity')}>"
        if job_id not in grouped:
            grouped[job_id] = []
            order.append(job_id)
        grouped[job_id].append(row)
    return [SourceMolecule(source, job_id, grouped[job_id],
                           grouped[job_id][0].get("event_time"))
            for job_id in order]


class GroupedProcessJobTranslator(SafeTranslatorTemplate):
    """CUSTOMIZE 4/4 -- turn domain rows into ClaimDraft values."""

    PROFILE = PROFILE
    POSSIBLE_EMISSIONS = POSSIBLE_EMISSIONS

    def claim_drafts(self, molecule, occurred_at):
        claims = []
        for row in molecule.rows:
            wafer = str(self.require(row, "wafer", "process row")).strip()
            step = str(self.require(row, "step", "process row")).strip()
            recipe = str(self.require(row, "recipe", "process row")).strip()
            claims.append(ClaimDraft(
                predicate=PREDICATE,
                subject_type="Wafer",
                subject_keys={"wafer": wafer},
                derivation=DERIVATION,
                object_kind="value",
                object_payload={
                    "step": step,
                    "recipe": recipe,
                    "equipment": row.get("equipment"),
                },
                rows=(row,),
            ))
        if not claims:
            self.refuse(gate.REFUSE_ATOMICITY,
                        f"job {molecule.key!r} contains no source rows", rows=0)
        return claims
