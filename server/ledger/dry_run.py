"""「이 선언이 낳을 원자」 - the REAL translators, over a connection that cannot write.

⚠️ AS OF 2026-08-18 THIS MODULE NO LONGER DOES THAT FOR SOURCES. The four v1
translator classes were retired, so `preview()` raises `DryRunUnavailable` and the
route answers a named refusal. Everything below describes the design the restored
preview must satisfy - it is a specification now, not a description. Read it that way.
`ledger.setup.preview_selected_cursor_batch` already previews with zero writes (the
atom-baseline harness drives it); no HTTP route calls it yet. `begin_read_only` and
its two PostgreSQL tests were deliberately kept, because that is the structural
zero-writes guarantee the v2 preview will need.

Ruling R-2026-08-15-M ⑥ makes the dry run the second of three save steps and the brief
spells out what it may not be: 「드라이런을 «샘플 미리보기»로 대충 하지 말 것 - 실제
번역기를 태운다. 가짜 미리보기는 조용한 거짓말이다.」 A preview that renders what the
declaration *says* rather than what the translator *does* is worse than none, because the
operator would approve a declaration on the strength of a screen that agreed with them by
construction.

WHAT IS REUSED, AND WHY THE DRIVER LOOP IS NOT
-----------------------------------------------
Everything that decides what an atom IS comes from `backfill`: its fetch functions, its
page/group cutting, its molecule grouping, the three translator classes, and
`gate.screen_molecule`. What is NOT reused is `backfill`'s driver loop, and the reason is
that the loop's job is precisely the part a dry run must not do - advance a cursor and
flush a batch. Reusing it with a `write=False` flag would put the write path one boolean
away from a preview, and this project has already paid for a flag that decides whether
something is real.

🔴 ZERO WRITES IS STRUCTURAL, NOT A PROMISE
--------------------------------------------
The connection's transaction is opened with `SET TRANSACTION READ ONLY` before anything
else runs, and `begin_read_only()` reads it back from PostgreSQL rather than trusting
that the statement was sent. Any INSERT/UPDATE/DDL on that transaction - including
`ensure_schema`'s `CREATE TABLE`, which is why it is deliberately not called - raises
`read-only sql transaction` (SQLSTATE 25006). The guarantee therefore does not depend on
this module never calling a writer; it depends on PostgreSQL refusing one.

TRANSACTION-SCOPED, NOT SESSION-SCOPED, and that is a pooling fact rather than a taste:
`engine.raw_connection()` hands back a POOLED connection, so
`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` would follow the connection back
into the pool and make somebody else's write fail. `SET TRANSACTION` dies with its
transaction, so a leaked one is impossible.

WHY IT ALWAYS READS FROM THE HEAD OF THE SOURCE
------------------------------------------------
The cursor is not consulted. The question the screen asks is "what does THIS DECLARATION
produce", not "what is left to do" - and on a source that is already fully translated a
cursor-respecting preview would show nothing at all, which reads as「선언이 아무것도 안
낳는다」when the truth is「이미 다 했다」. The consequence is worth naming rather than
hiding: registers the ledger already holds are suppressed by the translator exactly as
they would be in a real run, so `registers_suppressed` is reported.
"""
from __future__ import annotations

from collections.abc import Mapping
import logging

logger = logging.getLogger("Ledger.DryRun")

#: How many SOURCE ROWS a preview reads. The brief says「소스 N행(예: 20행)」. Capped
#: rather than free, because this runs on the request path against a table that may hold
#: ten million rows and the page fetch is `LIMIT n` on a keyset - cheap at 20, and not a
#: thing an operator should be able to turn into a full scan by typing a big number.
DEFAULT_ROWS = 20
MAX_ROWS = 200

#: How many atoms come back in the envelope list. The COUNTS are always complete; this
#: caps only the rendering, and `truncated` says so rather than the list ending quietly.
MAX_ATOMS_RENDERED = 200


class DryRunUnavailable(RuntimeError):
    """The preview could not run at all. Carries the operator's sentence."""

    def __init__(self, detail_ko: str, detail_en: str = ""):
        super().__init__(detail_en or detail_ko)
        self.detail_ko = detail_ko


def begin_read_only(connection):
    """Open this connection's transaction READ ONLY and prove it took.

    Returns what PostgreSQL says, not what we asked for. `SHOW transaction_read_only`
    is the server's own answer, so a statement that silently did not apply (a driver in
    autocommit, a connection already inside a transaction) shows up here instead of
    showing up as a write.
    """
    # 🔴 `SET TRANSACTION` must be the FIRST statement of a transaction, and this
    # connection comes from a POOL. A connection handed back with work still open would
    # make the statement raise 25001 - and a raw driver error here would surface as a
    # 500 rather than as「쓰기 0을 보장할 수 없어 중단했습니다」. Ending whatever was open
    # costs one round trip and there is nothing of ours to lose: we have not run yet.
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SHOW transaction_read_only")
        return str(cursor.fetchone()[0]).lower() == "on"


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def envelope_of(atom) -> dict:
    """One atom, in ENVELOPE FORM. The brief's words:「원자 봉투 그대로」.

    Nothing is renamed, summarised or prettified. `derivation` and `molecule_ref` ride
    along because they are what the gate judged the atom BY - an operator looking at a
    preview needs to see which declared rule claimed the atom, and that field is exactly
    where a rule the config did not declare would be refused.
    """
    source_event_id = atom.source_event_id
    source_event_state = atom.source_event_state
    if source_event_id is None and source_event_state is None:
        from .envelope import source_event_identity
        source_event_id, source_event_state = source_event_identity(
            atom.source_who, atom.occurred_at,
            molecule_ref=atom.molecule_ref,
            source_raw_ref=atom.source_raw_ref)
    return {
        "source_event_id": str(source_event_id),
        "source_event_state": source_event_state,
        "subject_type": atom.subject_type,
        "subject_keys": atom.subject_keys,
        "predicate": atom.predicate,
        "object_kind": atom.object_kind,
        "object_payload": atom.object_payload,
        "occurred_at": _iso(atom.occurred_at),
        "source_who": atom.source_who,
        "source_translator_ver": atom.source_translator_ver,
        "source_raw_ref": atom.source_raw_ref,
        "supersedes": atom.supersedes,
        "derivation": atom.derivation,
        "molecule_ref": atom.molecule_ref,
    }


def _existing_registrations(store, connection, subjects, notes):
    """Registers the ledger already holds. A missing ledger is a NOTE, not a failure.

    A fresh box has no `ledger_events` table until the first real run creates it, and a
    preview that died there would be unusable exactly when it is most useful - before
    anything has ever been translated.
    """
    if not subjects:
        return set()
    try:
        return store.existing_registrations(connection, subjects)
    except Exception as exc:
        connection.rollback()
        begin_read_only(connection)
        notes.append(
            "원장 테이블을 아직 읽을 수 없어 기존 등록을 대조하지 못했습니다 — 미리보기의 "
            "register 원자 수는 실제 실행보다 많을 수 있습니다.")
        logger.info("[DryRun] existing_registrations unavailable: %s", exc)
        return set()




def preview(engine, cfg, source, rows: int = DEFAULT_ROWS) -> dict:
    """Refuse by name: the v1 translators this preview drove no longer exist.

    🔴 THIS IS A NAMED REFUSAL, NOT A REGRESSION IN DISGUISE. Every one of the four
    grammars this module previewed (`lineage`, `observation`, `declared`, `transfer`)
    reached its answer by importing and running a translator class, and all four were
    deleted on 2026-08-18. Until 2026-08-18 the four `_preview_*` functions still carried
    those imports at the top of their bodies -- BEFORE the guards that were supposed to
    decide whether the module was needed -- so this entry point raised
    `ModuleNotFoundError` and `POST /admin/ledger/dry-run` answered 500 for every source
    kind. `main.py` already turns `DryRunUnavailable` into a `declaration_rejected`
    refusal the screen can render, so the operator now reads a sentence instead.

    ⚠️ THE SCREEN'S STEP 2 IS DOWN UNTIL THE v2 PREVIEW IS WIRED, and nothing here
    disguises that. The v2 path can already do this work without a database write --
    `ledger.setup.preview_selected_cursor_batch` is what the atom-baseline harness drives
    -- but no HTTP route calls it yet. Restoring a REAL preview means routing this entry
    point at that function, not re-adding a renderer: a preview that shows what the
    declaration says rather than what the executor does is the "가짜 미리보기" the ruling
    that created this module forbids.
    """
    del engine, cfg, rows
    # The sentence below said "1단과 3단은 그대로 동작합니다" until 2026-08-18, and it was
    # FALSE for sources: `/admin/ledger/save` requires `declaration_token`, and that token is
    # only ever minted in a successful dry-run response - i.e. on the line this raise skips.
    # So a source cannot be saved either; the save refuses with `dry_run_stale`. A refusal
    # that misstates what still works sends the operator to hit a second, different-looking
    # failure, which is worse than the one it was reporting.  Predicates are genuinely
    # unaffected: `main._ledger_predicate_dry_run` returns before this function is called.
    raise DryRunUnavailable(
        f"'{source}' 드라이런을 실행할 번역기가 없습니다 - v1 번역기 4종이 "
        f"2026-08-18에 은퇴했고 v2 미리보기는 아직 이 화면에 연결되지 않았습니다. "
        f"저장(3단)도 함께 막힙니다 - 저장 토큰이 드라이런에서만 나옵니다. "
        f"선언 검증(1단)과 술어 드라이런은 그대로 동작합니다.",
        f"no executor for dry-run of source {source!r}: the v1 translators were retired "
        f"on 2026-08-18 and the v2 preview is not wired to this route yet")
