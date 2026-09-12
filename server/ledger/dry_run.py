"""The structural zero-writes guarantee a restored preview will need.

⚰️ THE PREVIEW ITSELF RETIRED 2026-09-13 (S-203). `preview()` had raised
`DryRunUnavailable` for every source since the four v1 translator classes left on
2026-08-18, and `POST /admin/ledger/dry-run` -- its only caller -- refused on both halves
(the predicate half from 2026-08-27). Client callers were zero. A door that only ever
refuses is a place for a false green to live, so the route, `preview`, `DryRunUnavailable`
and the renderers went together.

⚠️ WHAT THE PROSE HERE USED TO CLAIM, and did not: two comments said
`main._ledger_predicate_dry_run` returned before `preview` was reached. No such function
ever existed -- measured, definitions and calls both zero -- and reading one of them is
what nearly had this module recorded as half-alive.

🔴 `begin_read_only` STAYS, and it is the whole of what is left. Its two PostgreSQL tests
assert that PostgreSQL itself refuses the write, which is the guarantee a v2 preview has to
be built on; `ledger.setup.preview_selected_cursor_batch` already previews with zero writes
and no HTTP route calls it yet. Inlining this away would leave that guarantee unasserted.

Ruling R-2026-08-15-M ⑥ said what such a preview may not be: 「드라이런을 «샘플 미리보기»로
대충 하지 말 것 - 실제 번역기를 태운다. 가짜 미리보기는 조용한 거짓말이다.」 That line is why
nothing was left behind rendering a declaration's intentions in the executor's place.
"""
from __future__ import annotations

from collections.abc import Mapping
import logging

logger = logging.getLogger("Ledger.DryRun")

#: How many SOURCE ROWS a preview reads. The brief says「소스 N행(예: 20행)」. Capped
#: rather than free, because this runs on the request path against a table that may hold
#: ten million rows and the page fetch is `LIMIT n` on a keyset - cheap at 20, and not a
#: thing an operator should be able to turn into a full scan by typing a big number.

#: How many atoms come back in the envelope list. The COUNTS are always complete; this
#: caps only the rendering, and `truncated` says so rather than the list ending quietly.


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

