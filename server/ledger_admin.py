"""admin으로 소스를 원장에 잇고 어휘를 늘린다 — 문법 검증과 저장(1단·3단).

판정 정본은 `docs/process/LEDGER_RULINGS.md` **R-2026-08-15-M**이고, 이 모듈은 그 판정의
①③⑥ 중 «드라이런이 아닌 나머지»다(드라이런 2단은 `ledger/dry_run.py`).

왜 이 파일이 있는가
    소유자 목표: 「내가 소스 테이블 하나 새로 만들어서 어휘 추가까지 하는 것」을 **코드 0줄·
    재기동 0회**로. 지금까지 그 길은 파일을 직접 열어 고치는 것뿐이었고, 그 편집에는 문법
    검사도 미리보기도 백업도 없었다.

저장은 항상 3단, 예외 없음 (R-M ⑥)
    1) **문법 검증** — 서명 완결성, SQL 식별자 규칙, 참조 무결, 어휘 중복.
    2) **드라이런** — 쓰기 0으로 실제 번역기를 태운다(`ledger/dry_run.py`).
    3) **저장 → reload → 「먹었는가」** — 백업 후 원자적 교체, `POST /admin/reload-configs`가
       하는 캐시 교체, 그리고 `/admin/config/resolve`의 **기존** 조립기가 만든 한 문장.

🔴 SQL 식별자 규칙이 «보안»이 아니라 «게이트»인 이유
    `backfill`의 페치들은 관계명·컬럼명을 **문자열 보간 자리**에 넣는다
    (`f"SELECT {columns['wafer']} ... FROM {source}"`). 파라미터화할 수 없는 자리이므로
    (식별자는 바인드 파라미터가 아니다) 규칙은 **저장 전에** 걸어야 한다. 이 화면이 없던
    어제까지는 그 자리를 사람이 손으로 채웠고, 오늘부터는 HTTP 요청이 채운다 — 그래서 이
    검사는 이 라운드가 «새로 만든» 위험에 대한 게이트다.

🔴 삭제 경로 없음 (R-M ③)
    술어는 지워지지 않는다. 원자가 이미 그 낱말로 누워 있기 때문이다. `retire_predicate`가
    `status: retired` + `superseded_by`를 쓰고, 은퇴는 읽기를 막지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime

logger = logging.getLogger("Ledger.Admin")

#: 저장 대상 둘. 화면의 층 1(소스)과 층 2(어휘)에 각각 대응한다.
TARGET_SOURCE = "source"
TARGET_PREDICATE = "predicate"
TARGETS = (TARGET_SOURCE, TARGET_PREDICATE)

#: 🔴 닫힌 거절 코드 집합. 게이트의 거절 사유가 닫혀 있는 것과 같은 이유다 — 호출 자리에서
#: 지어낸 코드는 화면이 렌더할 수 없는 사유다. `vocabulary.DECL_REFUSALS`가 어휘 쪽 절반이고
#: 아래가 소스 쪽 절반이며, 라우트는 합집합을 응답의 `vocabulary`로 내보낸다.
REFUSAL_CODES = (
    "signature_incomplete", "invalid_identifier", "unknown_relation", "unknown_column",
    "undeclared_entity_type", "undeclared_object_kind", "duplicate_predicate",
    "canonical_layer_forbidden", "not_editable", "unsupported_kind",
    "declaration_rejected", "dry_run_stale", "retire_target_unknown", "invalid_value",
    "traversable_true_unavailable", "duplicate_source", "undeclared_table",
    "stale_base",
)

#: PostgreSQL의 «따옴표 없는» 식별자. 소문자·숫자·밑줄만, 문자로 시작. 큰따옴표 식별자를
#: 허용하지 않는 것은 좁아서가 아니라 **보간 자리**이기 때문이다: 따옴표를 허용하는 순간
#: 이스케이프 규칙을 이 파일이 구현해야 하고, 그 구현이 틀리면 조용히 틀린다.
IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

#: 관계 이름의 상한. PostgreSQL의 `NAMEDATALEN-1`.
IDENTIFIER_MAX = 63


def violation(code: str, field, detail_ko: str, detail_en: str = "") -> dict:
    if code not in REFUSAL_CODES:
        raise ValueError(f"'{code}' is not a declared refusal code ({REFUSAL_CODES})")
    return {"code": code, "field": field, "detail_ko": detail_ko,
            "detail_en": detail_en or detail_ko}


# ---------------------------------------------------------------------------
# 1단 — 문법 검증
# ---------------------------------------------------------------------------

def check_identifier(value, field) -> list:
    """식별자 하나. 보간 자리에 들어가도 되는가."""
    text = "" if value is None else str(value)
    if not text.strip():
        return [violation("invalid_identifier", field,
                          f"{field}가 비었습니다.", f"{field} is blank")]
    if len(text) > IDENTIFIER_MAX:
        return [violation("invalid_identifier", field,
                          f"{field}('{text}')가 {IDENTIFIER_MAX}자를 넘습니다.",
                          f"{field} exceeds {IDENTIFIER_MAX} characters")]
    if not IDENTIFIER_RE.match(text):
        return [violation(
            "invalid_identifier", field,
            f"{field}('{text}')는 SQL 식별자 규칙에 맞지 않습니다 — 소문자·숫자·밑줄만 "
            f"쓰고 문자나 밑줄로 시작해야 합니다. 이 이름은 질의에 **그대로** 박히는 "
            f"자리라 따옴표로 감싸지 않습니다.",
            f"{field} {text!r} is not a bare SQL identifier")]
    return []


def _identifier_positions(source, declaration) -> list:
    """`(field, value, relation)` — 검사해야 할 모든 보간 자리.

    `relation`이 `None`이면 참조 무결 검사에서 «소스 테이블»을 뜻한다. 관측 소스의
    `occurred_at_column`이 **run 관계 위에** 있다는 것이 이 함수가 존재하는 이유다:
    한 목록으로 뭉뚱그리면 그 컬럼을 소스 테이블에서 찾다가 없는 컬럼이라고 거절한다.
    """
    from ledger import config as ledger_config

    kind = declaration.get("kind", ledger_config.SOURCE_KIND_LINEAGE)
    columns = declaration.get("columns") or {}
    out = [("source", source, "__self__")]
    for logical, physical in columns.items():
        if str(logical).startswith("__") or physical is None:
            continue
        out.append((f"columns.{logical}", physical, None))

    if kind == ledger_config.SOURCE_KIND_OBSERVATION:
        run = declaration.get("run") or {}
        relation = run.get("relation")
        out.append(("run.relation", relation, "__self__"))
        out.append(("run.key_column", run.get("key_column"), relation))
        if run.get("method_column"):
            out.append(("run.method_column", run.get("method_column"), relation))
        # 🔴 관측 소스의 시각 컬럼은 run 관계 위에 있다(`fetch_runs`가 그렇게 읽는다).
        out.append(("occurred_at_column", declaration.get("occurred_at_column"),
                    relation))
        for index, column in enumerate(
                (declaration.get("watermark") or {}).get("columns") or []):
            out.append((f"watermark.columns[{index}]", column, None))
    else:
        out.append(("occurred_at_column", declaration.get("occurred_at_column"), None))

    if kind == ledger_config.SOURCE_KIND_DECLARED:
        # 🔴 이 문법은 컬럼 이름을 **`emit` 안에서** `"$col"`로 말하므로, 식별자 검사도
        # 거기서 걷어 와야 한다. 안 걷으면 화면이 저장한 `$가짜컬럼`이 검증을 통과하고
        # 백필 때 행마다 거절로 나타난다 — 저장 시점에 알 수 있는 것을 실행 시점으로
        # 미루는 것이고, 이 라운드가 없애려는 바로 그 지연이다.
        for index, column in enumerate(
                (declaration.get("watermark") or {}).get("columns") or []):
            out.append((f"watermark.columns[{index}]", column, None))
        for index, rule in enumerate(declaration.get("emit") or []):
            if not isinstance(rule, dict):
                continue
            where = f"emit[{index}]"
            when = rule.get("when")
            if isinstance(when, dict) and when.get("column"):
                out.append((f"{where}.when.column", when["column"], None))
            for field, value in _column_refs(rule):
                out.append((f"{where}.{field}", value, None))

    if kind == ledger_config.SOURCE_KIND_TRANSFER:
        group = declaration.get("group") or {}
        out.append(("group.column", group.get("column"), None))
        out.append(("group.row_order_column", group.get("row_order_column"), None))
        container = declaration.get("container") or {}
        relation = container.get("relation")
        if str(relation or "").strip():
            out.append(("container.relation", relation, "__self__"))
            for field in ("key_column", "lot_column", "slot_column"):
                out.append((f"container.{field}", container.get(field), relation))
    return out


def _column_refs(node, path="") -> list:
    """`emit` 규칙 안의 `"$col"` 토큰 전부 — `(경로, 컬럼명)` 목록.

    중첩 payload를 재귀로 훑는다. `"$$"`는 리터럴 `$`의 이스케이프이므로 컬럼이 아니다
    (번역기의 `resolve`와 **같은 규칙**이고, 두 곳이 갈라지면 저장은 통과하는데 실행은
    거절하는 선언이 생긴다).
    """
    from ledger.config import COLUMN_REF_PREFIX

    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).startswith("__"):
                continue
            out.extend(_column_refs(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_column_refs(value, f"{path}[{index}]"))
    elif isinstance(node, str) and node.startswith(COLUMN_REF_PREFIX) \
            and not node.startswith(COLUMN_REF_PREFIX * 2):
        out.append((path, node[len(COLUMN_REF_PREFIX):]))
    return out


def relation_columns(db, relation: str) -> set:
    """`information_schema`에서 컬럼 이름 집합. 관계가 없으면 `None`.

    **카탈로그만 읽는다** — 행을 세지 않으므로 비용이 테이블 크기와 무관하다. 1,000만 행
    테이블에서도 요청 경로에 앉아도 되는 이유이고, `/admin/config/virtual-join/verify`가
    같은 자세로 서 있는 근거와 같다.
    """
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t"),
        {"t": relation}).fetchall()
    if not rows:
        return None
    return {row[0] for row in rows}


def check_source_declaration(db, source: str, declaration: dict) -> list:
    """소스 선언 1건의 문법 위반 전부. 빈 목록 = 저장해도 된다."""
    from ledger import config as ledger_config

    out = []
    if not isinstance(declaration, dict):
        return [violation("declaration_rejected", None, "선언은 객체여야 합니다.",
                          "declaration must be an object")]

    # ---- 🔴 FIRST: the source table must be one `table_config.json` declares (owner,
    #      2026-08-15). Before the column checks, because it is the ROOT refusal — if the
    #      table is not declared, every column complaint under it is noise pointing at the
    #      wrong fix. And it is checked HERE rather than only in the picker because hiding
    #      undeclared tables from a dropdown is advice: the raw JSON editor is a second
    #      door into the same save.
    if source not in declared_tables():
        return [violation(
            "undeclared_table", "source",
            f"'{source}'은 `table_config.json`에 선언되지 않은 테이블입니다. 먼저 거기 "
            f"선언하세요 — 선언되지 않은 테이블은 키 컬럼도 인제션도 체인도 없어서, "
            f"원장에 이으면 시스템의 나머지가 지목할 수 없는 행에 대한 원자를 만들게 "
            f"됩니다.",
            f"{source!r} is not declared in table_config.json")]

    kind = declaration.get("kind", ledger_config.SOURCE_KIND_LINEAGE)
    if kind not in ledger_config.SOURCE_KINDS:
        return [violation(
            "unsupported_kind", "kind",
            f"kind '{kind}'는 번역기가 없는 종류입니다. 지금 실행할 수 있는 문법은 "
            f"{', '.join(sorted(ledger_config.SOURCE_KINDS))}뿐입니다. 어느 문법에도 안 "
            f"맞으면 억지로 밀어 넣지 말고 새 kind 판정으로 올려야 합니다.",
            f"kind {kind!r} has no translator")]

    # ---- SQL 식별자: 참조 무결보다 먼저. 규칙에 안 맞는 이름을 information_schema에
    #      물으면 「없는 컬럼」이라는 **틀린 사유**를 돌려주게 된다.
    positions = _identifier_positions(source, declaration)
    for field, value, _relation in positions:
        if value is None and field.startswith(("run.", "container.")):
            continue
        out.extend(check_identifier(value, field))
    if out:
        return out

    # ---- 선언 자체의 문법. 후보 소스 «하나만» 담은 config에 대고 돌린다: 파일 안의 다른
    #      소스가 깨져 있어도 이 선언이 남의 사유로 거절당하지 않게.
    try:
        ledger_config.validate({"sources": {source: declaration}},
                               origin="<admin candidate>")
    except ledger_config.LedgerConfigError as exc:
        # 메시지는 `ledger/config.py`가 만든 것을 그대로 싣는다. 그 파일이 각 규칙의 «왜»를
        # 이미 문장으로 들고 있고, 여기서 다시 쓰면 두 문장이 갈라진다.
        return [violation("declaration_rejected", None, str(exc), str(exc))]

    # ---- 참조 무결. 관계가 실재하는가, 컬럼이 그 관계 위에 있는가.
    cache = {}

    def columns_of(relation):
        if relation not in cache:
            cache[relation] = relation_columns(db, relation)
        return cache[relation]

    missing_relations = set()
    for field, value, relation in positions:
        if value is None:
            continue
        if relation == "__self__":
            if columns_of(str(value)) is None:
                missing_relations.add(str(value))
                out.append(violation(
                    "unknown_relation", field,
                    f"'{value}' 테이블이 현재 스키마에 없습니다. 먼저 테이블을 만들거나 "
                    f"(파일 인제션 화면 소관) 이름을 확인하세요.",
                    f"relation {value!r} does not exist"))
            continue
        target = str(relation) if relation else str(source)
        if target in missing_relations:
            continue                     # 이미 「테이블이 없다」고 말했다. 두 번 말하지 않는다.
        known = columns_of(target)
        if known is None:
            continue
        if str(value) not in known:
            out.append(violation(
                "unknown_column", field,
                f"'{target}'에 '{value}' 컬럼이 없습니다.",
                f"column {value!r} not found on {target!r}"))

    # ---- 주어 타입: 어휘가 소유한다. `validate`가 이미 물지만, 사유 코드가 화면에
    #      구분돼 나가야 폼이 어느 칸을 빨갛게 칠할지 안다.
    from ledger import vocabulary
    for member in declaration.get("subject_types") or []:
        if member not in vocabulary.ENTITY_TYPES:
            out.append(violation(
                "undeclared_entity_type", "subject_types",
                f"'{member}'는 선언된 개체 타입이 아닙니다.",
                f"{member!r} is not a declared entity type"))

    return out


# ---------------------------------------------------------------------------
# 후보 config — 드라이런이 태울 «아직 저장 안 된» 선언
# ---------------------------------------------------------------------------

def candidate_config(source: str, declaration: dict) -> dict:
    """디스크의 config에서 **버전과 배치만** 물려받고 이 소스 하나만 담은 config.

    🔴 소스 하나만 담는 이유는 `check_source_declaration`이 그러는 이유와 같다: 파일 안의
    다른 소스가 깨져 있으면 `validate`가 파일 전체를 거절하고, 그러면 이 선언의 미리보기가
    남의 오타 때문에 안 뜬다.

    `translator_version`은 (소스 서브트리 + config version)의 해시이므로, 여기서 나오는
    `source_translator_ver`는 저장 후 실제 실행이 찍을 값과 **바이트 동일**하다 — 미리보기의
    원자가 진짜 원자와 같은 출처 문자열을 달고 나온다는 뜻이고, 그것이 이 미리보기를
    「진짜」로 만드는 조건 중 하나다.
    """
    from ledger import config as ledger_config

    version, batch = 1, {}
    try:
        live = ledger_config.load()
        version = live.get("version", 1)
        batch = live.get("batch") or {}
    except Exception as exc:
        logger.info("[LedgerAdmin] live config unreadable, defaulting version: %s", exc)
    return {"version": version, "batch": batch,
            "sources": {source: declaration},
            "__origin__": "<admin candidate>"}


def file_fingerprint(path: str) -> str:
    """The file's CONTENT hash — the base a save says it was editing.

    🔴 WHY THIS EXISTS, AND WHY THE STRICT ADMIN TOKEN IS NOT IT. `POST /admin/scripts/code`
    is gated by `require_admin_token_strict`, but that token is AUTHENTICATION — it answers
    「are you allowed to write」and says nothing about 「is the thing you edited still the
    thing on disk」. That path has no optimistic lock at all: two operators who open the
    same file both write, and the second silently erases the first.

    `declaration_token` is not it either — it binds a save to the declaration that was
    DRY RUN, which is a freshness check on the operator's own preview. Two operators can
    each dry-run their own edit and both tokens are valid.

    So concurrency needs its own answer, and this is it: the raw editor reads the file with
    its fingerprint, sends it back on save, and a mismatch is refused by name. Config files
    are gitignored by design, so a clobbered edit has no history to be recovered from —
    which is exactly why this cannot be left to「operators will coordinate」.
    """
    if not os.path.exists(path):
        return "sha256:absent"
    with open(path, "rb") as handle:
        return "sha256:" + hashlib.sha256(handle.read()).hexdigest()


def source_raw_view(source: str = None) -> dict:
    """The raw JSON an operator edits, plus the base fingerprint the save will check.

    🔴 PER SOURCE, NOT THE WHOLE FILE — the decision, and the reasoning is a clobber
    surface: whole-file editing makes every save a rewrite of every OTHER source's
    declaration, so two operators working on two unrelated tables collide by construction.
    Per source, they collide only when they are genuinely editing the same thing, and then
    the fingerprint catches it. It also composes with the path that already exists: the
    form and the raw editor produce the SAME `{target, name, declaration}` save, so the
    three-step discipline is one implementation rather than two that drift.

    The whole file is still READABLE here (`document`) so the operator can see their edit
    in context; it is simply not the unit of writing.
    """
    path = sources_path()
    read_path = path
    if not os.path.exists(read_path) and os.path.exists(read_path + ".sample"):
        read_path = read_path + ".sample"
    document, error = {}, None
    try:
        document = _read_json(read_path, {})
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"
    sources = (document.get("sources") or {}) if isinstance(document, dict) else {}
    out = {
        "config_path": path,
        "read_path": read_path,
        "base": file_fingerprint(read_path),
        "sources": sorted(s for s in sources if not str(s).startswith("__")),
        "error": error,
        "editable_unit": "source",
        "note_ko": "편집 단위는 «소스 하나»입니다. 파일 전체를 덮어쓰면 다른 사람이 방금 "
                   "선언한 소스가 말없이 사라지기 때문입니다. 저장은 폼과 똑같이 3단"
                   "(문법 검증 → 드라이런 → 저장)을 거칩니다.",
    }
    if source is not None:
        out["source"] = source
        out["declaration"] = sources.get(source)
        out["raw"] = json.dumps(sources.get(source), ensure_ascii=False, indent=2)
    return out


def parse_raw_declaration(raw: str):
    """Operator JSON -> a declaration, or a `declaration_rejected` violation naming the line.

    A raw editor's most common failure is a trailing comma at 3am, and 「JSON이 잘못됐다」
    without a position sends the operator hunting through a 200-line blob.
    """
    if isinstance(raw, dict):
        return raw, None
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        line = getattr(exc, "lineno", None)
        column = getattr(exc, "colno", None)
        where = f" ({line}행 {column}열)" if line else ""
        return None, violation(
            "declaration_rejected", "raw",
            f"JSON을 읽지 못했습니다{where}: {exc.msg if hasattr(exc, 'msg') else exc}. "
            f"드라이런을 돌릴 수 없으니 저장도 하지 않습니다 — 파싱되지 않는 선언은 "
            f"무엇을 낳을지 보여 줄 수가 없습니다.",
            f"raw declaration is not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        return None, violation(
            "declaration_rejected", "raw",
            "선언은 JSON 객체여야 합니다(배열이나 값이 아니라).",
            "raw declaration must be a JSON object")
    return parsed, None


def declaration_token(target: str, name: str, declaration) -> str:
    """이 «정확한» 선언의 지문. 저장은 같은 지문의 드라이런을 요구한다(R-M ⑥).

    🔴 이것이 「드라이런 없는 저장 버튼은 만들지 않는다」를 **클라이언트의 관례가 아니라
    서버의 규칙으로** 만드는 자리다. 화면이 드라이런을 건너뛰거나, 드라이런 뒤에 선언을 한 자
    고치고 저장하면 지문이 어긋나고 저장은 `dry_run_stale`로 거절된다 — 즉 「본 것」과
    「저장되는 것」이 다를 수 없다.

    ⚠️ **범위를 정확히 말해 둔다: 이것은 «실수로 건너뛰는 것»을 막고 «고의로 우회하는 것»은
    막지 않는다.** 지문이 선언의 순수 함수이므로 해시를 직접 구현한 호출자는 드라이런 없이도
    맞는 값을 만들 수 있다. 그것을 막으려면 서버가 발급한 논스를 들고 있어야 하는데, 논스는
    워커 프로세스가 둘 이상이면 발급한 프로세스와 저장하는 프로세스가 달라져 **정상 저장이
    간헐적으로 거절된다.** 이미 strict 관리자 토큰을 쥔 호출자의 고의 우회는 이 관문이 막으려는
    실패 양식이 아니므로, 프로세스 수와 무관하게 도는 결정적 지문을 택했다 — 그리고 그 선택을
    「구조적으로 불가능」이라고 적지 않는 것이 이 문단의 목적이다.
    """
    material = json.dumps({"target": target, "name": name, "declaration": declaration},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 3단 — 저장(백업 → 원자적 교체)
# ---------------------------------------------------------------------------

def _atomic_write(path: str, payload: dict) -> str:
    """임시 파일에 쓰고 `os.replace`로 갈아 끼운다. 반환값은 백업 경로(없으면 "").

    부분적으로 쓰인 config는 **다섯 프로세스가 동시에 읽는** 파일이라 최악이다: 리로드가
    반쯤 쓰인 JSON을 읽으면 어휘가 통째로 사라지고, 어휘가 없는 게이트는 모든 원자를
    거절한다. `os.replace`는 같은 볼륨에서 원자적이므로 독자는 옛 파일이나 새 파일 중
    하나를 보고, 그 사이는 없다.
    """
    backup = ""
    if os.path.exists(path):
        backup = f"{path}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(path, backup)       # 사본이 곧 undo (R-2026-08-13-G)
    temporary = f"{path}.tmp.{os.getpid()}"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return backup


def _read_json(path: str, default: dict) -> dict:
    """🔴 DEEP copy of the default, not `dict(default)`.

    A shallow copy shares the nested `predicates` object with the module constant below,
    so the FIRST save on a box with no file yet would write the new predicate INTO
    `_EMPTY_VOCABULARY` - and every later "there is no file" default in that process
    would silently already contain it. The bug is invisible on any box that has the file.
    """
    if not os.path.exists(path):
        return copy.deepcopy(default)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def sources_path() -> str:
    from ledger import config as ledger_config
    return ledger_config.config_path()


def vocabulary_path() -> str:
    from ledger import vocabulary
    return vocabulary.extension_path()


def check_base(path: str, base: str):
    """A `stale_base` violation, or `None`. Skipped when the caller sent no base.

    Not required, deliberately: the FORM path builds its declaration from a rendered view
    and has no single file it claims to be based on, while the RAW path hands the operator
    a blob and must. Requiring it everywhere would have made the form send a value it does
    not mean, and a field that is sent because it is required is a field nobody checks.
    """
    if not base:
        return None
    current = file_fingerprint(path)
    if base == current:
        return None
    return violation(
        "stale_base", None,
        "이 파일은 당신이 연 뒤에 바뀌었습니다 — 다른 사람이 먼저 저장했거나 파일이 직접 "
        "편집됐습니다. 지금 저장하면 그 변경이 «말없이» 사라집니다(config 파일은 설계상 "
        "git 이력이 없어 되돌릴 수 없습니다). 다시 읽어 편집 내용을 얹은 뒤 저장하세요.",
        f"base fingerprint {base} does not match current {current}")


def save_source(source: str, declaration: dict) -> dict:
    """`ledger_config.json`의 `sources`에 이 선언을 넣는다. 파일의 나머지는 그대로."""
    path = sources_path()
    document = _read_json(path, {"version": 1, "sources": {}})
    if not isinstance(document.get("sources"), dict):
        document["sources"] = {}
    replaced = source in document["sources"]
    document["sources"][source] = declaration
    backup = _atomic_write(path, document)
    return {"path": path, "backup": backup, "replaced": replaced}


#: 확장 파일이 없을 때 만들어 주는 최소 문서. `__doc`는 이 저장소의 config 주석 관례다.
_EMPTY_VOCABULARY = {
    "__doc": ("Ontology-layer predicates declared by the operator (ruling "
              "R-2026-08-15-M). The canonical layer lives in server/ledger/vocabulary.py "
              "and is NOT extensible from here. Entries are append-only: retire with "
              "status/superseded_by, never delete."),
    "version": 1,
    "predicates": {},
}


def save_predicate(name: str, declaration: dict) -> dict:
    path = vocabulary_path()
    document = _read_json(path, _EMPTY_VOCABULARY)
    if not isinstance(document.get("predicates"), dict):
        document["predicates"] = {}
    replaced = name in document["predicates"]
    document["predicates"][name] = declaration
    backup = _atomic_write(path, document)
    return {"path": path, "backup": backup, "replaced": replaced}


def retire_predicate(name: str, superseded_by=None) -> dict:
    """R-M ③. 지우지 않고 은퇴시킨다 — 원자가 이미 그 낱말로 누워 있다.

    코드가 싣는 술어는 여기서 은퇴시킬 수 없다: 그것은 판정 사안이고, 이 함수는 화면이
    부르는 함수다.
    """
    from ledger import vocabulary

    if name in vocabulary.PREDICATES:
        raise ValueError(
            f"'{name}'은 코드가 싣는 술어라 화면에서 은퇴시킬 수 없습니다 — 판정과 코드 "
            f"변경이 필요합니다.")
    path = vocabulary_path()
    document = _read_json(path, _EMPTY_VOCABULARY)
    entry = (document.get("predicates") or {}).get(name)
    if entry is None:
        raise KeyError(name)
    entry["status"] = "retired"
    entry["superseded_by"] = superseded_by
    document["predicates"][name] = entry
    backup = _atomic_write(path, document)
    return {"path": path, "backup": backup, "entry": entry}


# ---------------------------------------------------------------------------
# 읽기 — 화면이 폼을 «서버 선언에서» 만들도록
# ---------------------------------------------------------------------------

#: 삼상태의 한국어. 여기서 나가는 이유는 `label_ko`가 어휘에서 나가는 이유와 같다 —
#: 클라이언트가 들고 있으면 서버가 상태를 하나 늘리는 날 화면만 모른다.
TRAVERSABLE_STATES = (
    {"value": True, "label_ko": "재귀 — 걷기가 이 엣지를 통과한다"},
    {"value": False, "label_ko": "도달만 — 주석으로 가져오되 통과하지 않는다"},
    {"value": None, "label_ko": "미수집 — 걷기가 아예 가져오지 않는다(범위 지정 질의 전용)"},
)

KIND_LABELS = {
    "lineage": "랏 이벤트 — 행 쌍 하나가 한 사건(분할·병합·트랙인)",
    "observation": "관측 — 한 행이 한 발화(보이드·박리 등 불량 관측)",
    "transfer": "이동 — 한 그룹(잡 런)이 한 사건(DT 픽킹·본딩)",
    "declared": "선언형 — 한 행이 «선언한 대로» 원자 1~N개(대장·참조표. 코드 0줄)",
}


def kinds_view() -> list:
    from ledger import config as ledger_config

    return [
        {"kind": ledger_config.SOURCE_KIND_LINEAGE,
         "label_ko": KIND_LABELS["lineage"],
         "required_columns": list(ledger_config.LINEAGE_REQUIRED_COLUMNS),
         "optional_columns": ["equipment"],
         "required_blocks": ["vocabulary"]},
        {"kind": ledger_config.SOURCE_KIND_OBSERVATION,
         "label_ko": KIND_LABELS["observation"],
         "required_columns": list(ledger_config.OBSERVATION_REQUIRED_COLUMNS),
         "optional_columns": list(ledger_config.OBSERVATION_OPTIONAL_COLUMNS),
         "required_blocks": ["finding_kind", "run", "watermark"]},
        {"kind": ledger_config.SOURCE_KIND_TRANSFER,
         "label_ko": KIND_LABELS["transfer"],
         "required_columns": list(ledger_config.TRANSFER_REQUIRED_COLUMNS),
         "optional_columns": list(ledger_config.TRANSFER_OPTIONAL_COLUMNS),
         "required_blocks": ["group", "container"]},
        # 🔴 넷째 문법. 다른 셋과 달리 **파이썬 클래스가 없다** — 행→원자 사상이 `emit`
        # 선언 자체다. 그래서 화면이 폼을 만들 재료가 컬럼 목록이 아니라 «문법»이고,
        # 아래 세 목록이 그 문법의 전부다(연산자·시각 기준·값 참조 규칙).
        {"kind": ledger_config.SOURCE_KIND_DECLARED,
         "label_ko": KIND_LABELS["declared"],
         "required_columns": list(ledger_config.DECLARED_REQUIRED_COLUMNS),
         "optional_columns": [],
         "required_blocks": ["watermark", "emit", "occurred_at_basis"],
         "emit_rule_fields": ["rule", "predicate", "class", "subject", "object", "when"],
         "when_operators": sorted(ledger_config.WHEN_OPERATORS),
         # 🔴 규칙마다 «해소 등급»을 고른다(설계 §6: 2 관측 / 3 추론). 기본값 없음.
         # 이 선택을 개발자에게 미루면 그는 «남의 의도»를 추측하게 되고, 그 사이 화면을
         # 쓰는 것만으로 빌드가 빨개진다. 규칙을 쓰는 사람만이 답을 안다.
         "classes": [
             {"value": ledger_config.EMIT_CLASS_OBSERVATION, "rank": 2,
              "label_ko": "관측 — 이 행이 그렇게 «말했다»",
              "help_ko": "원자의 내용이 눈앞의 행에서 왔습니다. 번역기는 모양만 바꿨고 "
                         "행에 없던 것을 더하지 않았습니다."},
             {"value": ledger_config.EMIT_CLASS_INFERENCE, "rank": 3,
              "label_ko": "추론 — 행이 말하지 않은 «규칙»에 기댄다",
              "help_ko": "원자의 내용이 관례·기본값·규칙에서 왔습니다. 나중에 실측이 "
                         "나오면 그 실측이 «자동으로» 이깁니다 — 아무도 무언가를 "
                         "철회하지 않아도."}],
         "occurred_at_bases": [
             {"value": "claim_time",
              "label_ko": "주장 시각 — 이 컬럼이 «배정·승인된 순간»이 맞다"},
             {"value": "row_created",
              "label_ko": "행 생성 시각 — 승인 시각이 아니라 행이 생긴 때다(그렇게 실린다)"}],
         "column_ref_prefix": ledger_config.COLUMN_REF_PREFIX,
         "note_ko": "값은 `$컬럼`이면 그 행의 컬럼, 아니면 리터럴입니다(`$$`는 «$» 자체). "
                    "리스트 열 분해·위치 짝짓기는 이 문법의 범위 밖입니다 — 그건 선언이 "
                    "아니라 작은 프로그래밍 언어가 됩니다."},
    ]


#: 판정은 났지만 번역기가 없는 종류(R-M ⑤). 목록에서 지우지 않고 **왜 못 고르는지와 함께**
#: 내보낸다: 없는 선택지는 화면이 「이 시스템은 그런 걸 못 한다」로 읽히고, 사유가 붙은
#: 선택지는 「아직 안 왔다」로 읽힌다. 이 둘은 다른 사실이다.
UNSUPPORTED_KINDS = (
    # ⚠️ 이것은 위 `declared`와 **다른 것**이다. `declared`는 소스 «행»을 보고 번역하고,
    # 이쪽은 원장을 «걸어서» 조건을 평가해 3류 추론을 만든다(근거 원자 id 필수). 두 판정이
    # 하루 차이로 같은 「넷째」 자리를 말했고, 나중 것(브리핑 §6-2 = `declared`)이 정본이라
    # 이 항목은 이름을 유지한 채 미구현으로 남는다.
    {"kind": "derivation",
     "detail_ko": "원장을 «걸어서» 조건을 평가하는 추론 규칙(3류·근거 원자 필수)은 아직 "
                  "번역기가 없습니다(판정 R-2026-08-15-M ⑤). 소스 «행»을 선언대로 "
                  "번역하는 것이 목적이면 그건 `declared` 문법입니다 — 그쪽은 지금 "
                  "됩니다."},
)


def sources_view() -> dict:
    from ledger import config as ledger_config

    path = ledger_config.config_path()
    document, error = {}, None
    try:
        document = _read_json(path, {})
        if not os.path.exists(path) and os.path.exists(path + ".sample"):
            document = _read_json(path + ".sample", {})
            path = path + ".sample"
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"
    return {
        "kinds": kinds_view(),
        "unsupported_kinds": [dict(k) for k in UNSUPPORTED_KINDS],
        "sources": (document.get("sources") or {}),
        "config_path": path,
        "error": error,
    }


def vocabulary_view() -> dict:
    from ledger import vocabulary

    predicates = []
    for name, sig in sorted(vocabulary.all_predicates().items()):
        origin = sig.get("origin")
        predicates.append({
            "name": name,
            "origin": origin,
            # 편집 가능한 것은 **선언 출처의 ontology 항목뿐**이다. canonical은 R-M ①,
            # 코드가 싣는 ontology 항목은 코드라서.
            "editable": origin == "config",
            "layer": sig.get("layer"),
            "label_ko": sig.get("label_ko"),
            "status": sig.get("status"),
            "since": sig.get("since"),
            "subject": list(sig.get("subject") or []),
            "object": sig.get("object"),
            "qualifiers": list(sig.get("qualifiers") or []),
            "traversable": sig.get("traversable"),
            "direction": sig.get("direction"),
            "superseded_by": sig.get("superseded_by"),
            "unit": sig.get("unit"),
            "semi_ref": sig.get("semi_ref"),
        })
    entity_types = [
        {"name": name, "label_ko": entry.get("label_ko"), "class": entry.get("class"),
         "keys": list(entry.get("keys") or []),
         "requires_register": vocabulary.requires_register(name)}
        for name, entry in sorted(vocabulary.ENTITY_TYPES.items())]
    return {
        "predicates": predicates,
        "entity_types": entity_types,
        "object_kinds": sorted(vocabulary.OBJECT_KINDS),
        "walk_directions": sorted(vocabulary.WALK_DIRECTIONS),
        "traversable_states": [dict(s) for s in TRAVERSABLE_STATES],
        "statuses": list(vocabulary.PREDICATE_STATUSES),
        "signature_fields": list(vocabulary.SIGNATURE_FIELDS),
        "editable_layer": vocabulary.EDITABLE_LAYER,
        "canonical_layer": vocabulary.LAYER_CANONICAL,
        "config_path": vocabulary.extension_path(),
        "extension": vocabulary.extension_status(),
        "refusal_codes": sorted(set(REFUSAL_CODES) | set(vocabulary.DECL_REFUSALS)),
    }


def declared_tables() -> list:
    """`table_config.json`이 선언한 테이블 이름. 소스로 고를 수 있는 «전부»."""
    from database import crud

    return sorted(name for name in (crud.TABLE_CONFIG or {})
                  if not str(name).startswith("__"))


def relations_view(db, query: str = None, limit: int = 200) -> dict:
    """소스로 고를 수 있는 테이블과 그 컬럼 (소유자 지시 2026-08-15).

    🔴 목록은 `table_config.json`이 선언한 것«만»이다 — DB에 있다고 다 쓸 수 있는 게
    아니다. 이유는 권한이 아니라 **주소 지정**이다: table_config에 없는 테이블은 시스템의
    나머지가 모르는 테이블이라 키 컬럼도, 인제션도, 체인도 없다. 그걸 원장에 이으면
    **아무도 지목할 수 없는 행에 대한 원자**를 찍게 된다. 선언된 집합이 곧 시스템이
    말할 수 있는 집합이다.

    🔴 **그러나 나머지를 조용히 없애지 않는다.** 검색어가 실재하는 DB 테이블에 맞는데
    미선언이면 그 사실을 이름과 함께 돌려준다. 자기가 DB에서 «보고 있는» 테이블 이름을
    쳤는데 빈 목록이 오면 운영자는 「화면이 고장났다」를 배우고, 사유 문장이 오면
    「다음에 뭘 해야 하는지」를 배운다. 이 저장소의 거절 사다리 그대로 — 거절은 다음
    행동을 지목한다.

    컬럼은 여전히 `information_schema`가 답한다. 「무슨 컬럼이 있나」는 카탈로그의 일이고,
    table_config의 `column_types`는 인제션이 «쓰는» 컬럼이지 테이블에 «있는» 컬럼의
    전수가 아니다 — 그걸로 컬럼 픽커를 만들면 실재하는 컬럼이 목록에서 빠진다.
    """
    from sqlalchemy import text

    limit = max(1, min(int(limit or 200), 1000))
    needle = str(query or "").strip().lower()
    declared = declared_tables()
    matched = [name for name in declared if not needle or needle in name.lower()]
    shown = matched[:limit]

    grouped = {name: [] for name in shown}
    missing = []
    if shown:
        rows = db.execute(text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ANY(:names) "
            "ORDER BY table_name, ordinal_position"), {"names": shown}).fetchall()
        for table, column, data_type in rows:
            grouped[table].append({"name": column, "type": data_type})
        # 선언은 됐는데 물리 테이블이 아직 없는 경우도 이름을 준다. 폼이 그것을 고르면
        # `unknown_relation`으로 거절되는데, 고르기 «전에» 말해 주는 편이 낫다.
        missing = sorted(name for name in shown if not grouped[name])

    # 🔴 미선언이지만 «실재하는» 테이블 — 이름과 다음 행동을 함께.
    undeclared = []
    if needle:
        rows = db.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name LIKE :q "
            "ORDER BY table_name LIMIT :limit"),
            {"q": f"%{needle}%", "limit": limit}).fetchall()
        declared_set = set(declared)
        undeclared = [
            {"name": row[0],
             "detail_ko": f"테이블 미등록 — 먼저 `table_config.json`에 '{row[0]}'을 "
                          f"선언하세요. 선언되지 않은 테이블은 키 컬럼도 인제션도 없어서, "
                          f"원장에 이으면 시스템의 나머지가 지목할 수 없는 행에 대한 "
                          f"원자를 만들게 됩니다."}
            for row in rows if row[0] not in declared_set]

    return {
        "relations": [{"name": name, "columns": grouped[name],
                       "declared": True, "exists": bool(grouped[name])}
                      for name in shown],
        "undeclared": undeclared,
        "missing_relations": missing,
        "declared_total": len(declared),
        "source": "table_config.json",
        "truncated": len(matched) > len(shown),
    }
