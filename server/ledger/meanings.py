"""The meaning table's rows (e38466810, owner 10-20 「뜻은 표에」): one row per entity and per predicate the operating
world declares, made blank here; the LLM drafts a blank meaning in its own layer and a person's value wins.

`fill_blank_meanings` is the one writer of those rows. It runs where the declaration is read again in the process
that writes - `config_watcher`'s ontology row, the API's (총괄 10-21: a save, a hand edit and the Reload button alike).
It writes only the rows missing, through the write door, so running it again writes nothing. A row whose entity or
predicate left the declaration stays.
"""
import logging

logger = logging.getLogger("Ledger.Meanings")

#: The layer the blank rows' key cells are written under - not a person, not the chain.
FILLER_SOURCE = "ledger_declaration"
ENTITY, PREDICATE = "entity", "predicate"


def declared_names(declaration):
    """-> [(target_kind, bare name)] of a declaration: its entities, then its predicates, each in file order."""
    from declaration_names import bare_name

    out = []
    for kind, section in ((ENTITY, "entities"), (PREDICATE, "vocabulary")):
        for name in dict.fromkeys(bare_name(name) for name in ((declaration or {}).get(section) or {})):
            if name:
                out.append((kind, name))
    return out


def fill_blank_meanings(engine):
    """The operating world's declared names that have no meaning row get a blank one. -> rows written; None when the
    meaning table is not installed (said once a call: `install_product_tables.py --apply`)."""
    from sqlalchemy.orm import Session

    import product_tables
    from database import crud, models, schemas
    from ledger import trace_router

    table = product_tables.MEANING_TABLE
    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        logger.warning("[Meanings] %s is not in table_config.json - no meaning rows made; install it with "
                       "server/scripts/install_product_tables.py --apply", table)
        return None
    names = declared_names(trace_router._declaration())
    with Session(bind=engine) as db:
        held = {(row.target_kind, row.target_name) for row in db.query(model.target_kind, model.target_name)}
        missing = [(kind, name) for kind, name in names if (kind, name) not in held]
        if not missing:
            return 0
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"target_kind": kind, "target_name": name},
                                      source_name=FILLER_SOURCE, updated_by=FILLER_SOURCE)
            for kind, name in missing]))
        db.commit()
    logger.info("[Meanings] %d blank meaning row(s) made for the declaration's new names (%s)", len(missing),
                ", ".join("%s %s" % pair for pair in missing[:10]) + (" ..." if len(missing) > 10 else ""))
    return len(missing)
