# -*- coding: utf-8 -*-
"""Paged catalogue of every registered entity type in the canonical ledger.

This is the instance picker for ``Ledger Graph``. It is generated from the
vocabulary and ``register`` atoms: no Lot-only list and no hand-maintained node
menu. Pages use the register B-tree; text filtering is admitted only when the
partial trigram index installed by the catalogue migration is present. That
refusal is intentional—a missing index may not turn a UI search into a
ten-million-row JSON text scan.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime

import ledger_explorer
from ledger_trace import _fetch


DEFAULT_LIMIT = 40
MAX_LIMIT = 100
MAX_QUERY_LENGTH = 120
MAX_CURSOR_BYTES = 2048
SEARCH_INDEX = "idx_ledger_register_search"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CatalogRequestError(ValueError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.detail = {"reason": reason, "message": message}


class CatalogUnavailable(RuntimeError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.detail = {"reason": reason, "message": message}


def _vocabulary():
    from ledger import vocabulary
    return vocabulary


def entity_types():
    vocabulary = _vocabulary()
    return [{
        "type": name,
        "label": entry.get("label_ko") or name,
        "keys": list(entry.get("keys") or []),
        "entity_class": entry.get("class"),
    } for name, entry in sorted(vocabulary.ENTITY_TYPES.items())
      if vocabulary.requires_register(name)]


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _encode_cursor(keys):
    raw = _canonical(keys).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(token):
    if token in (None, ""):
        return None
    token = str(token).strip()
    if len(token) > MAX_CURSOR_BYTES * 2:
        raise CatalogRequestError("cursor_invalid", "목록 커서가 너무 깁니다")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if not raw or len(raw) > MAX_CURSOR_BYTES:
            raise ValueError("empty or oversized")
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogRequestError("cursor_invalid", "목록 커서를 해석할 수 없습니다") from exc
    if not isinstance(value, dict) or not value:
        raise CatalogRequestError("cursor_invalid", "목록 커서의 개체 키가 비어 있습니다")
    return value


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else (
        str(value) if value is not None else None)


def _label(subject_type, keys):
    entry = _vocabulary().ENTITY_TYPES[subject_type]
    values = [str(keys.get(name)) for name in entry.get("keys") or []
              if keys.get(name) not in (None, "")]
    return " / ".join(values) or subject_type


def _validate_type(subject_type):
    types = {entry["type"]: entry for entry in entity_types()}
    if subject_type not in types:
        raise CatalogRequestError(
            "entity_type_not_catalogued",
            f"{subject_type!r}은 register 목록을 가진 개체 타입이 아닙니다")
    return types


def _require_search_index(connection):
    rows = _fetch(connection, "SELECT to_regclass(%(name)s) IS NOT NULL",
                  {"name": SEARCH_INDEX})
    if not rows or not rows[0][0]:
        raise CatalogUnavailable(
            "catalog_search_index_absent",
            f"개체 검색 인덱스 {SEARCH_INDEX}가 설치되지 않아 느린 전량 검색을 거절했습니다")


def entity_catalog(connection, subject_type="Lot", q=None, after=None,
                   limit=DEFAULT_LIMIT, relation="ledger_events"):
    """Return one keyset page for any vocabulary-declared issued entity type."""
    subject_type = str(subject_type or "").strip()
    types = _validate_type(subject_type)
    query = str(q or "").strip()
    if len(query) > MAX_QUERY_LENGTH:
        raise CatalogRequestError(
            "query_too_long", f"검색어는 {MAX_QUERY_LENGTH}자 이하여야 합니다")
    try:
        page_limit = int(limit if limit is not None else DEFAULT_LIMIT)
    except (TypeError, ValueError) as exc:
        raise CatalogRequestError("limit_invalid", "목록 크기는 정수여야 합니다") from exc
    if not 1 <= page_limit <= MAX_LIMIT:
        raise CatalogRequestError(
            "limit_invalid", f"목록 크기는 1..{MAX_LIMIT}이어야 합니다")
    cursor_keys = _decode_cursor(after)
    if not _IDENTIFIER.match(relation or ""):
        raise ValueError("relation must be a bare identifier")
    if query:
        _require_search_index(connection)

    params = {
        "subject_type": subject_type,
        "after": _canonical(cursor_keys) if cursor_keys is not None else None,
        "fetch": page_limit + 1,
    }
    search_sql = ""
    if query:
        params["pattern"] = f"%{query}%"
        search_sql = " AND subject_keys::text ILIKE %(pattern)s"
    cursor_sql = ""
    if cursor_keys is not None:
        cursor_sql = " AND subject_keys > CAST(%(after)s AS jsonb)"

    rows = _fetch(connection, f"""
        SELECT subject_keys,
               count(*)::bigint AS register_claims,
               min(occurred_at) AS first_at,
               max(occurred_at) AS last_at
        FROM {relation}
        WHERE subject_type = %(subject_type)s
          AND predicate = 'register'
          {cursor_sql}
          {search_sql}
        GROUP BY subject_keys
        ORDER BY subject_keys
        LIMIT %(fetch)s
    """, params)

    has_more = len(rows) > page_limit
    page = rows[:page_limit]
    items = []
    for row in page:
        keys = row[0]
        if isinstance(keys, str):
            keys = json.loads(keys)
        keys = dict(keys or {})
        items.append({
            "id": ledger_explorer.entity_id(subject_type, keys),
            "type": subject_type,
            "label": _label(subject_type, keys),
            "keys": keys,
            "register_claims": int(row[1] or 0),
            "first_at": _iso(row[2]),
            "last_at": _iso(row[3]),
        })
    return {
        "state": "ready" if items else "empty",
        "entity_type": subject_type,
        "entity_types": list(types.values()),
        "items": items,
        "page": {
            "limit": page_limit,
            "returned": len(items),
            "has_more": has_more,
            "next_cursor": _encode_cursor(page[-1][0]) if has_more and page else None,
        },
        "search": {
            "q": query,
            "match": "contains" if query else "all",
            "source": "register",
            "index": SEARCH_INDEX if query else "idx_ledger_register",
        },
    }
