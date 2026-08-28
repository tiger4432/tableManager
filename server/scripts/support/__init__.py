"""Configuration for the synthetic seed scripts, and for nothing else.

Moved here 2026-08-28: measured, every caller of every accessor is a `seed_syn_*` script and
no production module reads it. It sat under `ledger_api/` and `config/` as if it were part
of the ontology, which made it look like a second declaration to keep in step with the
first. It is not: the ontology fields it carried are already in the atoms (`run_uid` holds
the method) and the rest describe physical tables the seeds read.
"""
