"""The CSV export's row ceiling was applied to the RESPONSE HEADER and nothing else.

`total_count = min(total_count, 1000000)` capped the size estimate; the streaming
statement had no `.limit()` at all. So a 2,000,000-row table advertised "최대 100만 행",
sent 2,000,000, and drove the client's progress bar past 100% on the way. An advertised
ceiling that is not enforced is worse than no ceiling: it is a promise the reader has no
way to check.

DECISION: exceeding the cap REFUSES (413), it does not truncate.

A truncated CSV opens perfectly in Excel and is simply short - there is no room in the
file itself to say so, and the response headers are invisible once the browser has
written a download. Refusal happens BEFORE the first byte, so no partial file exists.
This is the same call the route already makes for a misaligned header ("컬럼이 밀린
CSV를 내보내지 않습니다") and for the same reason.

What is pinned here:

  * Over the cap -> 413, and NO CSV body.
  * Exactly AT the cap -> streams. Without this arm an off-by-one that refused every
    export would pass the test above.
  * The cap is read from ONE declaration, not a literal in the enforcement.
  * `X-Total-Rows` tells the truth. It used to be `min(count, 1000000)`, i.e. it
    under-reported the very thing the export was about to send too much of.
"""
import csv
import io

import pytest

import main as main_mod

TABLE = "raw_table_1"  # conftest seeds 10 rows


@pytest.fixture(autouse=True)
def _clean_cache():
    main_mod.TABLE_COUNT_CACHE.clear()
    yield
    main_mod.TABLE_COUNT_CACHE.clear()


def _export(client, **params):
    return client.get(f"/tables/{TABLE}/export", params=params)


def test_over_the_cap_is_refused_and_nothing_is_streamed(client, monkeypatch):
    monkeypatch.setattr(main_mod, "EXPORT_MAX_ROWS", 4)

    r = _export(client)

    assert r.status_code == 413, f"expected a refusal, got {r.status_code}"
    # The refusal must NAME both numbers - "too big" without the actual size leaves
    # the operator guessing how far to narrow the filter.
    assert "10" in r.text and "4" in r.text, r.text
    # 🔴 And it must not have handed over a file. A 413 carrying CSV would be the
    #    silent truncation this refusal exists to avoid, wearing an error code.
    assert "text/csv" not in r.headers.get("content-type", "")
    assert "EQP_" not in r.text


def test_exactly_at_the_cap_still_exports(client, monkeypatch):
    """The other arm. An off-by-one refusing everything would pass the test above."""
    monkeypatch.setattr(main_mod, "EXPORT_MAX_ROWS", 10)

    r = _export(client)

    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert len(rows) - 1 == 10, f"expected 10 data rows, got {len(rows) - 1}"


def test_the_export_is_bounded_by_the_declaration_not_a_literal(client, monkeypatch):
    """Two different declarations produce two different verdicts over one fixture.

    This is what makes the number a DECLARATION. A second hardcoded copy in the
    enforcement would keep answering the same way no matter what this is set to.
    """
    monkeypatch.setattr(main_mod, "EXPORT_MAX_ROWS", 9)
    assert _export(client).status_code == 413
    monkeypatch.setattr(main_mod, "EXPORT_MAX_ROWS", 11)
    assert _export(client).status_code == 200


def test_the_row_count_header_is_the_true_count(client, monkeypatch):
    """It was `min(count, 1000000)`: the header under-reported exactly when the body
    over-delivered, so the progress bar ran past 100% on the export that needed it."""
    monkeypatch.setattr(main_mod, "EXPORT_MAX_ROWS", 1_000_000)

    r = _export(client)

    assert r.status_code == 200
    assert r.headers["X-Total-Rows"] == "10"
    assert int(r.headers["X-Estimated-Content-Length"]) > 0
