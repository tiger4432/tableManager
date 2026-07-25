"""Enrichment Queue generic dedup mapper (docs/spec/ENRICHMENT_QUEUE_SPEC.md §6).

Source 테이블 변경 이벤트(outbox payload 배치)에서 **decision_key 유니크 조합**을 추출해
derived_table에 키당 1행을 upsert하는 체인 맵퍼다. `enrichment_config.load_enrichment_chain_rules()`
가 파생한 체인 룰(`mapper_module: "enrichment_mapper"`)을 통해 체인 워커가 호출한다.

핵심 불변식:
- **target_fields는 절대 updates에 포함하지 않는다** (사람이 채운 값 보존 1차 방어).
  2차 방어는 레이어링 자체 — 이 맵퍼의 source는 `chain_ingestion`(우선순위 99)이라
  설령 값이 실리더라도 user(priority 0)를 이길 수 없다(crud.compute_priority_value).
- **증분 처리**: 이번 배치 payload의 행만 본다(원본 풀스캔 금지). count 집계만
  "영향받은 키 한정" 재계산(청킹된 GROUP BY)으로 수행해 재인제션에도 멱등이다.

주의: 이 모듈은 저장소 추적 인프라 코드다(사용자 영역 `server/mappers/*`가 아님).
SYSTEM_RELOAD의 mappers.* 캐시 무효화 대상이 아니므로 콜드 스타트 재발도 없다.
"""
import logging

logger = logging.getLogger("Chain.enrichment_dedup")

# 재계산 쿼리 키 청킹 (헌장: 1000만 행 테이블 기준 — 키 IN 목록 상한)
RECOUNT_KEY_CHUNK = 500


def _cell_value(data: dict, col: str):
    """outbox payload의 data[col] 셀(dict 또는 스칼라)에서 실제 값을 꺼낸다."""
    cell = data.get(col)
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def _recount_affected_keys(db, source_table: str, decision_key: list, key_raw_values: dict) -> dict:
    """영향받은 판단키들만 대상으로 원본 테이블 건수를 재계산한다(멱등 count).

    key_raw_values: {clean_key_tuple: typed_raw_tuple} — typed 값으로 바인딩해 컬럼 타입과 일치시킨다.
    확장성: 유니크 키 수는 배치 행 수보다 훨씬 작다(압축비). 키 500개 청크의
    `(k1,..) IN (...) GROUP BY` 쿼리만 수행 — 전량 스캔 없음. 판단키 컬럼 인덱스 권장
    (가이드 참조: docs/guide/chain_ingestion_guide.md §Enrichment).
    """
    from sqlalchemy import func, tuple_
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(source_table)
    if model is None:
        raise ValueError(f"Source table model '{source_table}' is not initialized.")
    cols = [getattr(model, k) for k in decision_key]

    counts = {}
    items = list(key_raw_values.items())
    for i in range(0, len(items), RECOUNT_KEY_CHUNK):
        chunk = items[i:i + RECOUNT_KEY_CHUNK]
        if len(cols) == 1:
            cond = cols[0].in_([raw[0] for _, raw in chunk])
        else:
            cond = tuple_(*cols).in_([tuple(raw) for _, raw in chunk])
        rows = db.query(*cols, func.count().label("cnt")).filter(cond).group_by(*cols).all()
        for row in rows:
            key = tuple(crud.clean_str_value(v) for v in row[:-1])
            counts[key] = int(row[-1])
    return counts


def map_enrichment_dedup(db, payloads, rule=None):
    """배치 payload → derived_table 키당 1행 upsert 목록(GeneralUpdateBatch 형태) 생성.

    :param payloads: outbox payload dict 리스트 (is_batch=True 경로)
    :param rule: 체인 룰 dict — `rule["enrichment"]`에 전체 enrichment 규칙이 내장됨
                 (chain_ingestion_worker.execute_custom_mapper가 rule 인자를 지원하는
                 맵퍼에게만 선택적으로 전달)
    """
    if not payloads:
        return {"updates": []}
    enrich = (rule or {}).get("enrichment")
    if not enrich:
        logger.error("[Enrichment] chain rule is missing embedded 'enrichment' config; skipping batch")
        return {"updates": []}

    from database import crud

    source_table = enrich["source_table"]
    derived_table = enrich["derived_table"]
    decision_key = enrich["decision_key"]
    target_fields = set(enrich.get("target_fields", []))
    list_columns = enrich.get("list_columns", [])
    aggregations = enrich.get("aggregations", {})

    derived_cfg = crud.TABLE_CONFIG.get(derived_table, {})
    derived_cols = set(derived_cfg.get("column_types", {}).keys())
    comp_src = derived_cfg.get("composite_key_source")
    comp_sep = derived_cfg.get("composite_key_separator", "_")
    bk_col = derived_cfg.get("business_key")
    source_col_types = crud.TABLE_CONFIG.get(source_table, {}).get("column_types", {})

    # 1) 배치에서 decision_key 유니크 조합 추출 (증분 — payload의 변경 행만)
    groups = {}          # clean_key_tuple -> {"reps": {list_col: 값}}
    key_raw_values = {}  # clean_key_tuple -> typed_raw_tuple (count 재계산 바인딩용)
    skipped = 0
    for p in payloads:
        data = p.get("data") or {}
        clean_vals, raw_vals = [], []
        valid = True
        for k in decision_key:
            v = _cell_value(data, k)
            sv = crud.clean_str_value(v)
            if sv == "":
                valid = False
                break
            clean_vals.append(sv)
            raw_vals.append(crud.cast_value_by_type(sv, source_col_types.get(k, "string"), k))
        if not valid:
            skipped += 1
            continue
        key = tuple(clean_vals)
        g = groups.setdefault(key, {"reps": {}})
        key_raw_values.setdefault(key, tuple(raw_vals))
        # 표시 단서(list_columns): 배치 내 마지막 non-blank 값을 대표값으로
        for col in list_columns:
            if col in aggregations or col in target_fields:
                continue
            v = _cell_value(data, col)
            if v is not None and str(v).strip() != "":
                g["reps"][col] = v
    if skipped:
        logger.warning(
            f"[Enrichment:{enrich.get('name')}] {skipped} row(s) skipped: blank decision_key value(s)"
        )
    if not groups:
        return {"updates": []}

    # 2) count 집계 — 영향 키 한정 재계산(멱등: 재인제션에도 이중 카운트 없음)
    counts = {}
    count_cols = [c for c, fn in aggregations.items() if fn == "count"]
    if count_cols:
        counts = _recount_affected_keys(db, source_table, decision_key, key_raw_values)

    # 3) 키당 1행 upsert 아이템 구성 — target_fields는 절대 포함하지 않는다.
    #    기존 키: decision/list 컬럼 값이 동일하면 has_changed=False로 무변경 처리되고,
    #    집계/단서만 실질 갱신된다. 신규 키: 행 생성 + target은 미설정(NULL)로 남는다.
    updates = []
    for key, g in groups.items():
        key_map = dict(zip(decision_key, key))
        upd_cols = {}
        for k, v in key_map.items():
            if k in derived_cols and k not in target_fields:
                upd_cols[k] = v
        for col, v in g["reps"].items():
            if col in derived_cols and col not in target_fields:
                upd_cols[col] = v
        for col in count_cols:
            if col in derived_cols and col not in target_fields:
                upd_cols[col] = counts.get(key, 0)

        item = {
            "updates": upd_cols,
            "source_name": "chain_ingestion",
            "updated_by": "chain_worker",
        }
        # business_key_val 선(先)조립 — apply_batch_updates의 벌크 프리페치(row/CellSource 캐시)가
        # business_key_val 기준이므로 여기서 확정해야 기존 행 조회가 N+1 없이 배치된다.
        if comp_src and all(crud.clean_str_value(key_map.get(c)) != "" for c in comp_src):
            joined = comp_sep.join(crud.clean_str_value(key_map[c]) for c in comp_src)
        elif bk_col and bk_col in key_map:
            joined = key_map[bk_col]
        else:
            # 방어적 폴백(로더가 키 계약을 검증하므로 정상 경로에선 도달하지 않음)
            joined = comp_sep.join(key)
        item["business_key_val"] = joined
        if bk_col and bk_col in derived_cols and bk_col not in upd_cols and bk_col not in target_fields:
            upd_cols[bk_col] = joined
        updates.append(item)

    logger.info(
        f"[Enrichment:{enrich.get('name')}] {len(payloads)} source row(s) -> "
        f"{len(updates)} unique decision key(s) upserted into '{derived_table}'"
    )
    return {"updates": updates, "silent": False}
