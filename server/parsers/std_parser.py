"""표준 파서 (Std Parser) — 무스크립트 기본 인제션 경로.

테이블 스키마(`table_config.json`의 `column_types`)와 같은 컬럼 헤더를 가진
CSV/TSV/TXT 파일을 커스텀 파이프라인 스크립트 없이 바로 적재하기 위한 폴백 파서.

호출 규약 (directory_watcher.IngestionHandler._resolve_rows):
  - 커스텀 파이프라인 디스커버리가 **우선**이며, 어떤 스크립트도 매칭되지 않았을 때만 사용된다.
  - 반환된 (row_iterator, total_rows, skipped_no_key)는 기존 통합 경로(`_send_to_upsert` →
    `crud.apply_batch_updates`)로 그대로 흘러가므로 레이어링/소스 계보는 파이프라인 경로와 동일.

[확장성] 수십만 행 파일 대비 전량 메모리 로드를 하지 않는다:
  1-pass: 행 수 카운트(스트리밍, 인코딩 전체 검증 겸용) → 2-pass: 행 dict 스트리밍 yield.
  피크 메모리는 _send_to_upsert의 1000행 청크에 종속(O(chunk)).
"""

import csv
import logging
import os

logger = logging.getLogger("Watcher.StdParser")

# 표준 파서가 처리하는 확장자. 그 외(.xlsx, .html 등)는 커스텀 파이프라인 전용.
STD_SUPPORTED_EXTENSIONS = (".csv", ".txt", ".tsv")

# 한국 현장 파일 현실: BOM 포함 UTF-8 우선, 실패 시 CP949(EUC-KR 확장) 폴백.
_ENCODING_CANDIDATES = ("utf-8-sig", "cp949")

_SNIFF_SAMPLE_SIZE = 65536


def is_std_supported(file_path: str) -> bool:
    """표준 파서 대상 확장자인지 여부."""
    return os.path.splitext(file_path)[1].lower() in STD_SUPPORTED_EXTENSIONS


def _resolve_delimiter(ext: str, sample: str) -> str:
    """확장자별 구분자 결정. csv=콤마, tsv=탭, txt=Sniffer(실패 시 탭→콤마 순)."""
    if ext == ".csv":
        return ","
    if ext == ".tsv":
        return "\t"
    # .txt: sniff
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t").delimiter
    except csv.Error:
        return "\t" if "\t" in sample else ","


def _build_header_map(header: list, table_info: dict, table_name: str, file_path: str) -> list:
    """파일 헤더를 테이블의 **적재 대상 컬럼**과 대조해 컬럼 매핑을 만든다.

    - 알려진 컬럼만 채택(대소문자 무시 매칭), 미지 컬럼은 warning 후 무시(None 슬롯).
    - business_key 컬럼(또는 composite_key_source 전체)이 헤더에 없으면 ValueError로 처리 거부
      → 호출측(process_with_retry)에서 err/ 이동 + FileIngestionLog FAILED 기록.
    - [F5] 검증 기준은 적재 필터(`_send_to_upsert`의 `display_columns` 교집합)와 **동일 집합**이어야
      한다. column_types 기준으로 검증하면 column_types에만 있는 컬럼이 검증은 통과하고
      적재 단계에서 무음 탈락하는 불일치가 생긴다. display_columns가 비어 있는 비정상 config에서만
      column_types로 폴백한다(이 경우 적재도 어차피 전무 — 기존 파이프라인 경로와 동일한 전제).
    """
    basename = os.path.basename(file_path)
    column_types = table_info.get("column_types", {}) or {}
    loadable_cols = table_info.get("display_columns") or list(column_types.keys())
    canonical = {str(c).strip().lower(): c for c in loadable_cols}

    header_map = []
    unknown = []
    for cell in header:
        key = (cell or "").strip()
        col = canonical.get(key.lower())
        header_map.append(col)
        if col is None and key:
            unknown.append(key)

    if unknown:
        logger.warning(
            f"[{table_name}] Std parser: ignoring unknown column(s) not loadable for "
            f"table (display_columns 기준) '{basename}': {unknown}"
        )

    known = {c for c in header_map if c is not None}
    if not known:
        raise ValueError(
            f"Std parser rejected '{basename}': no header column matches "
            f"table '{table_name}' loadable columns {sorted(canonical.values())}."
        )

    bk_col = table_info.get("business_key")
    composite_src = table_info.get("composite_key_source")
    bk_ok = bool(bk_col) and bk_col in known
    composite_ok = bool(composite_src) and all(c in known for c in composite_src)
    if not (bk_ok or composite_ok):
        requirement = f"business_key column '{bk_col}'"
        if composite_src:
            requirement += f" or all composite_key_source columns {list(composite_src)}"
        raise ValueError(
            f"Std parser rejected '{basename}': required key column(s) missing from header — "
            f"expected {requirement}, but header only matched {sorted(known)}."
        )

    return header_map


def _resolve_key_groups(table_info: dict, known: set) -> list:
    """행 단위 키 존재 검사에 쓸 키 컬럼 그룹 목록을 만든다.

    [F1] 키 셀이 공백인 행이 무음 적재되면 `_get_or_create_row`가
    business_key_val=None 항목을 **매번 신규 행**으로 만들어 재드롭 때마다 고아 행이
    누적된다(업서트 불가). 그룹 중 하나라도 값이 전부 채워져 있으면 keyed로 판정:
      - (business_key,) — 단일 bk 직접 제공
      - tuple(composite_key_source) — crud가 키를 조립할 수 있는 소스 전체
    """
    groups = []
    bk_col = table_info.get("business_key")
    composite_src = table_info.get("composite_key_source")
    if bk_col and bk_col in known:
        groups.append((bk_col,))
    if composite_src and all(c in known for c in composite_src):
        groups.append(tuple(composite_src))
    return groups


def _row_has_key(row: dict, key_groups: list) -> bool:
    """어느 한 키 그룹의 컬럼 값이 전부 존재하면 True (공백/결측은 _map_record에서 None 정규화됨)."""
    return any(all(row.get(c) is not None for c in grp) for grp in key_groups)


def _map_record(record: list, header_map: list) -> dict | None:
    """CSV 레코드 1건을 canonical 컬럼 dict로 매핑. 유효 값이 하나도 없으면 None(스킵)."""
    row = {}
    has_value = False
    for idx, col in enumerate(header_map):
        if col is None:
            continue
        raw = record[idx] if idx < len(record) else None
        val = raw.strip() if isinstance(raw, str) else raw
        if val == "":
            val = None
        if val is not None:
            has_value = True
        row[col] = val
    return row if has_value else None


def _iter_rows(file_path: str, encoding: str, delimiter: str, header_map: list, key_groups: list):
    """데이터 행을 스트리밍으로 yield한다(전량 메모리 로드 없음). 키 결측 행은 1-pass와 동일 기준으로 스킵."""
    with open(file_path, "r", encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        next(reader, None)  # 헤더 스킵
        for record in reader:
            row = _map_record(record, header_map)
            if row is not None and _row_has_key(row, key_groups):
                yield row


def parse_std_file(file_path: str, table_info: dict, table_name: str):
    """표준 파서 메인 진입점.

    Returns:
        (row_iterator, total_rows, skipped_no_key)
          — 빈 파일/헤더만 있는 파일은 (빈 iterator, 0, 0).
          — skipped_no_key: [F1] 키 컬럼(단일 bk 또는 composite 소스 전체) 값이 공백/결측이라
            스킵된 행 수. 파일 전체를 거부하지 않는 이유: 소계/각주 행 하나 때문에
            정상 데이터 적재를 막지 않기 위함(스킵 사실은 완료 메시지·로그로 노출).
    Raises:
        ValueError — 헤더 검증 실패(키 컬럼 누락·매칭 컬럼 전무) 또는 지원 인코딩 전부 실패.
    """
    ext = os.path.splitext(file_path)[1].lower()
    basename = os.path.basename(file_path)
    last_decode_error = None

    for encoding in _ENCODING_CANDIDATES:
        try:
            with open(file_path, "r", encoding=encoding, newline="") as f:
                sample = f.read(_SNIFF_SAMPLE_SIZE)
                if not sample.strip():
                    logger.info(f"[{table_name}] Std parser: empty file, nothing to ingest: {basename}")
                    return iter(()), 0, 0

                delimiter = _resolve_delimiter(ext, sample)
                f.seek(0)
                reader = csv.reader(f, delimiter=delimiter)
                header = next(reader, None)
                if not header:
                    logger.info(f"[{table_name}] Std parser: no header row found, nothing to ingest: {basename}")
                    return iter(()), 0, 0

                header_map = _build_header_map(header, table_info, table_name, file_path)
                key_groups = _resolve_key_groups(table_info, {c for c in header_map if c is not None})

                # 1-pass: 유효 행 수 카운트(스트리밍). 이 패스가 파일 전체 디코딩 검증을 겸한다 —
                # 본문 중간에서 인코딩이 깨지면 여기서 UnicodeDecodeError → 다음 후보 인코딩 재시도.
                # [F1] 키 결측 행은 적재하지 않고 카운트만 한다(_iter_rows 2-pass와 동일 기준).
                total_rows = 0
                skipped_no_key = 0
                for record in reader:
                    row = _map_record(record, header_map)
                    if row is None:
                        continue
                    if not _row_has_key(row, key_groups):
                        skipped_no_key += 1
                        continue
                    total_rows += 1

            logger.info(
                f"[{table_name}] 🧰 Std parser accepted '{basename}' "
                f"(encoding={encoding}, delimiter={delimiter!r}, data_rows={total_rows}"
                + (f", skipped_no_key={skipped_no_key}" if skipped_no_key else "") + ")"
            )
            if skipped_no_key:
                logger.warning(
                    f"[{table_name}] Std parser: {skipped_no_key}행이 키 컬럼 공백/결측으로 스킵됨 "
                    f"(고아 행 방지): '{basename}'"
                )
            return _iter_rows(file_path, encoding, delimiter, header_map, key_groups), total_rows, skipped_no_key
        except UnicodeDecodeError as e:
            last_decode_error = e
            continue

    raise ValueError(
        f"Std parser failed to decode '{basename}' with supported encodings "
        f"{_ENCODING_CANDIDATES}: {last_decode_error}"
    )
