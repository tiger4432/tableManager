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
- **부분 판단키는 살아남은 키로 일한다** (2026-08-05 사용자 재정). 거절되는 것은
  **아무것도 남지 않은 키**뿐이며, 그 판정은 `enrichment_config.key_is_wholly_blank`
  **하나**다. 이 함수가 파생 **행 생성**의 유일한 관문이므로, 라이브 증분(체인 워커)과
  소급 스윕(`enrichment_backfill`)은 같은 답을 낼 수밖에 없다 — backfill은 이 맵퍼를
  호출하지 자기 판정을 갖지 않는다.

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
    빈 판단키 컬럼의 raw 값은 None이며, 그 컬럼은 **동등 비교에 실리지 않는다**(아래).
    확장성: 유니크 키 수는 배치 행 수보다 훨씬 작다(압축비). 키 500개 청크의
    `(k1,..) IN (...) GROUP BY` 쿼리만 수행 — 전량 스캔 없음. 판단키 컬럼 인덱스 권장
    (가이드 참조: docs/guide/chain_ingestion_guide.md §Enrichment).

    A BLANK KEY COLUMN CANNOT BE MATCHED BY EQUALITY  [2026-08-05, partial-key ruling]
    Since a partial decision key produces a derived identity, some keys arrive
    with a blank component - and `IN` is the wrong operator for it twice over:
    SQL's `NULL = NULL` is unknown, and absence has two storages (`NULL` and
    `''`) that `clean_str_value` folds into one. Binding `""` therefore matched
    the `''` rows, missed the `NULL` rows, and wrote the undercount into a cell.

    So the keys are partitioned by WHICH components are blank, and each partition
    asks its blank columns with the system's shared emptiness predicate
    (`crud.blank_sql_condition` over `crud.column_text_sql` - the same funnel the
    operator's "Blank" grid filter runs through) while the surviving components
    keep the indexed tuple `IN`. A batch of complete keys - every key before this
    ruling - is ONE partition whose SQL is what it always was.

    확장성(1000만 행): 파티션 수는 배치에 실제로 나타난 blank 마스크 수뿐이고
    (실 config에선 1~2), 청킹은 그대로다. **모든 파티션에 살아있는 컬럼이 최소 하나
    있다** — 전부 빈 키는 위에서 이미 걸러졌으므로 — 따라서 접근 경로는 언제나
    인덱스를 타는 `IN`이고, 공백 술어는 그 위의 필터로만 얹힌다(공백 술어 자체는
    CASE라 단독으론 인덱스를 못 탄다).
    """
    from sqlalchemy import and_, func, tuple_
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(source_table)
    if model is None:
        raise ValueError(f"Source table model '{source_table}' is not initialized.")
    cols = [getattr(model, k) for k in decision_key]

    by_pattern = {}
    for clean_key, raw in key_raw_values.items():
        blank_at = tuple(i for i, v in enumerate(clean_key) if v == "")
        by_pattern.setdefault(blank_at, []).append(raw)

    counts = {}
    for blank_at, raws in by_pattern.items():
        blank_idx = set(blank_at)
        live_cols = [c for i, c in enumerate(cols) if i not in blank_idx]
        blank_conds = [crud.blank_sql_condition(crud.column_text_sql(cols[i]))
                       for i in blank_at]
        for i in range(0, len(raws), RECOUNT_KEY_CHUNK):
            chunk = raws[i:i + RECOUNT_KEY_CHUNK]
            conds = list(blank_conds)
            if live_cols:
                live = [tuple(v for j, v in enumerate(raw) if j not in blank_idx)
                        for raw in chunk]
                if len(live_cols) == 1:
                    conds.append(live_cols[0].in_([v[0] for v in live]))
                else:
                    conds.append(tuple_(*live_cols).in_(live))
            rows = (db.query(*cols, func.count().label("cnt"))
                    .filter(and_(*conds)).group_by(*cols).all())
            for row in rows:
                key = tuple(crud.clean_str_value(v) for v in row[:-1])
                # ACCUMULATE, not assign. `NULL` and `''` are two SQL groups and
                # one decision key: `clean_str_value` folds them, so a blank
                # component makes the GROUP BY hand back two rows for the same
                # key. Assignment silently reported whichever storage came last.
                counts[key] = counts.get(key, 0) + int(row[-1])
    return counts


def _result(updates, skipped_no_key: int, partial_keys: int,
            skipped_unexpressible_key: int = 0) -> dict:
    """맵퍼의 반환 계약 — **가산적**이다(체인 워커는 `updates`만 읽는다).

    스킵 계수가 실려 있는 이유는 회계가 아니라 **철자 하나**다.
    `enrichment_backfill`은 종전에 이 스킵 판정을 **자기 코드로 다시 썼고**(맵퍼가
    세기만 하고 돌려주지 않아서), 그래서 부분 키 재정이 backfill 한 줄만 고치면
    될 것처럼 보였다 — 실제로는 그 한 줄을 풀어도 맵퍼가 한 호출 뒤에 같은 행을
    버리므로 **쓰기는 그대로이고 dry-run 숫자만 거짓이 된다**(실측 확인). 이제
    판정도 계수도 여기 하나뿐이라 두 경로가 갈릴 자리가 없다.

    스킵은 **두 종류이고 절대 합치지 않는다**:
      `skipped_no_key`             — 판단키가 전무. 가리키는 것이 없다(산술).
      `skipped_unexpressible_key`  — 부분 키인데 **파생 테이블의 키 선언이 그
                                     정체성을 담지 못한다**. 데이터가 아니라
                                     **config** 문제이고 고치는 방법이 있다
                                     (`enrichment_config.partial_key_identity_supported`).
    """
    return {"updates": updates, "silent": False,
            "skipped_no_key": skipped_no_key, "partial_keys": partial_keys,
            "skipped_unexpressible_key": skipped_unexpressible_key}


def map_enrichment_dedup(db, payloads, rule=None):
    """배치 payload → derived_table 키당 1행 upsert 목록(GeneralUpdateBatch 형태) 생성.

    :param payloads: outbox payload dict 리스트 (is_batch=True 경로)
    :param rule: 체인 룰 dict — `rule["enrichment"]`에 전체 enrichment 규칙이 내장됨
                 (chain_ingestion_worker.execute_custom_mapper가 rule 인자를 지원하는
                 맵퍼에게만 선택적으로 전달)
    """
    if not payloads:
        return _result([], 0, 0, 0)
    enrich = (rule or {}).get("enrichment")
    if not enrich:
        logger.error("[Enrichment] chain rule is missing embedded 'enrichment' config; skipping batch")
        return _result([], 0, 0, 0)

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
    #
    # 부분 판단키는 **살아남은 키로 일한다** [2026-08-05 사용자 재정]. 종전에는 판단키
    # 컬럼이 하나라도 비면 행을 통째로 버렸고(`any`), 그래서 부분 키 소스 행은 파생 행
    # 자체가 생기지 않아 큐에 나타날 수도 없었다 — 재정이 `enrichment_candidates`(값
    # 판정)에만 닿고 **행 생성**에는 닿지 않았던 자리다. 거절은 이제 하나뿐이고 그것은
    # 정책이 아니라 산술이다: 아무것도 남지 않은 키는 가리키는 것이 없다.
    # 술어는 `enrichment_config.key_is_wholly_blank` 하나를 쓴다 — 라이브 증분과 소급
    # backfill이 같은 함수를 부르므로 갈릴 수 없다.
    #
    # 🔴 그리고 거절이 하나 더 있는데, **정책이 아니라 파생 테이블의 키 선언**이다.
    # 부분 키의 정체성을 최종 결정하는 것은 이 맵퍼가 아니라 `crud`이고, 세 가지 키
    # 계약 중 둘에서는 부분 키가 **빈 정체성**이 되거나 **온전한 키의 행 위로 조용히
    # 병합**된다(`enrichment_config.partial_key_identity_supported` 참조 — 실측). 담지
    # 못하는 계약에서는 부분 키 행을 만들지 않고 **이름 붙여 센다**. 조용한 덮어쓰기
    # 대신 고칠 수 있는 config 한 줄을 가리키는 쪽을 고른다.
    import enrichment_config

    partial_ok = enrichment_config.partial_key_identity_supported(decision_key, derived_cfg)

    groups = {}          # clean_key_tuple -> {"reps": {list_col: 값}}
    key_raw_values = {}  # clean_key_tuple -> typed_raw_tuple (count 재계산 바인딩용)
    skipped = 0
    unexpressible = 0
    for p in payloads:
        data = p.get("data") or {}
        clean_vals = [crud.clean_str_value(_cell_value(data, k)) for k in decision_key]
        key_values = dict(zip(decision_key, clean_vals))
        if enrichment_config.key_is_wholly_blank(enrich, key_values):
            skipped += 1
            continue
        if not partial_ok and enrichment_config.blank_key_columns(enrich, key_values):
            unexpressible += 1
            continue
        # 빈 컬럼의 raw는 None이다 — 타입 캐스트를 태우지 않는다. 재계산 쿼리가 그
        # 컬럼을 동등 비교가 아니라 공백 술어로 묻기 때문이며(`_recount_affected_keys`),
        # 빈 문자열을 number 컬럼 타입으로 캐스트하는 무의미한 경로도 함께 사라진다.
        raw_vals = [
            None if sv == ""
            else crud.cast_value_by_type(sv, source_col_types.get(k, "string"), k)
            for k, sv in zip(decision_key, clean_vals)
        ]
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
            f"[Enrichment:{enrich.get('name')}] {skipped} row(s) skipped: "
            f"NO decision_key value at all (every key column blank — nothing to match on)"
        )
    if unexpressible:
        logger.warning(
            f"[Enrichment:{enrich.get('name')}] {unexpressible} row(s) with a PARTIAL "
            f"decision key were NOT derived: table '{derived_table}' cannot give them "
            f"their own identity. Its key contract is "
            f"composite_key_source={derived_cfg.get('composite_key_source')!r} / "
            f"business_key={bk_col!r}, and on that contract crud composes the partial "
            f"key into an EMPTY identity or into the identity of a COMPLETE key (which "
            f"is then silently merged over). REPAIR: declare "
            f"\"composite_key_source\": {list(decision_key)!r} on '{derived_table}' in "
            f"table_config.json. Until then these rows stay in the source table only."
        )
    if not groups:
        return _result([], skipped, 0, unexpressible)

    # 2) count 집계 — 영향 키 한정 재계산(멱등: 재인제션에도 이중 카운트 없음)
    counts = {}
    count_cols = [c for c, fn in aggregations.items() if fn == "count"]
    if count_cols:
        counts = _recount_affected_keys(db, source_table, decision_key, key_raw_values)

    # 3) 키당 1행 upsert 아이템 구성 — target_fields는 절대 포함하지 않는다.
    #    기존 키: decision/list 컬럼 값이 동일하면 has_changed=False로 무변경 처리되고,
    #    집계/단서만 실질 갱신된다. 신규 키: 행 생성 + target은 미설정(NULL)로 남는다.
    updates = []
    partial_keys = 0
    for key, g in groups.items():
        key_map = dict(zip(decision_key, key))
        # 같은 술어 하나 — 아래 정체성 조립과 `partial_keys` 회계가 이것을 공유한다.
        blank_key_cols = enrichment_config.blank_key_columns(enrich, key_map)
        if blank_key_cols:
            partial_keys += 1
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
        #
        # 🔴 종전 comp_src 분기의 `all(... != "")` 가드가 사라졌다 — 부분 키가 **바로
        # 그 가드에 걸려** 선언을 못 타고 아래 폴백으로 떨어지던 자리다. 부분 키는
        # `partial_ok`(= comp_src가 판단키 전체를 덮음)일 때만 여기 도달하므로, 빈
        # 성분을 포함한 comp_src 조인이 곧 그 행의 정체성이고 **온전한 키와 같은 순서·
        # 같은 구분자**로 조립된다(정체성 철자가 두 개가 되지 않는다).
        # 온전한 키의 결과는 종전과 100% 동일하다: 성분이 전부 non-blank일 때 이 식은
        # 옛 식과 글자 그대로 같다.
        if comp_src:
            # 🔴 조립은 `crud.compose_business_key` 하나다 (S1). 여기서 따로 이어 붙이면
            #    같은 행이 두 철자를 갖게 되고 그날 오류는 «안 난다».
            #    빈 성분 판정은 «하지 않는다» — 부분 키를 그대로 조립하는 것이
            #    2026-08-05 소유자 재정이고, 그 판정은 위 `blank_key_cols` 가 «세기만» 한다.
            joined = crud.compose_business_key(
                derived_table, [key_map.get(c) for c in comp_src])
        elif bk_col and bk_col in key_map:
            joined = key_map[bk_col]
        else:
            # 방어적 폴백(로더가 키 계약을 검증하므로 정상 경로에선 도달하지 않음)
            #
            # 🔴 S1 확인 (2026-09-02): 이 갈래가 `crud.compose_business_key` 를 «안 쓰는»
            #    이유는 «도달 불가»이기 때문이다. `enrichment_config._validate_rule` 이
            #    「comp_src ⊆ decision_key 이거나 bk_col ∈ decision_key」를 어기는 규칙을
            #    «로드 시점에 거절»한다. `key_map` 은 decision_key 로 zip 되므로
            #    `bk_col ∈ decision_key` 는 곧 `bk_col in key_map` 이고, 따라서 로더를
            #    통과한 규칙에서는 위 두 갈래 중 하나가 «반드시» 잡는다.
            #    그리고 도달하더라도 «철자는 같다»: `key` 는 이미
            #    `tuple(crud.clean_str_value(...))` 이고 그 함수는 자기 출력에 멱등이므로,
            #    여기서 다시 태우든 안 태우든 같은 문자열이 나온다. 즉 이것은 정체성의
            #    «다섯째 철자»가 아니라 «닿지 않는 같은 철자»다.
            joined = comp_sep.join(key)
        item["business_key_val"] = joined
        if bk_col and bk_col in derived_cols and bk_col not in upd_cols and bk_col not in target_fields:
            upd_cols[bk_col] = joined
        updates.append(item)

    logger.info(
        f"[Enrichment:{enrich.get('name')}] {len(payloads)} source row(s) -> "
        f"{len(updates)} unique decision key(s) upserted into '{derived_table}' "
        f"({partial_keys} of them on a PARTIAL decision key)"
    )
    return _result(updates, skipped, partial_keys, unexpressible)
