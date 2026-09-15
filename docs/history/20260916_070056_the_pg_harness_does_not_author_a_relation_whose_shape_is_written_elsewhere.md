# 하니스가 «모양이 다른 곳에 적힌» 릴레이션을 짓지 않는다 — `kind: view` 의 사본이 원장 자신의 파티션 jsonb DDL 보다 «먼저» 서 있었고, 그래서 오류 29 가 «내용 결함»의 옷을 입었다 (S-260)

> **커밋:** `01b9d85d` — test(pg): the harness does not author a relation whose shape is written elsewhere (S-260)
> **일자:** 2026-09-16 07:00
> **레인:** 구현자 — 컴팩트 뒤 재개 브리프 `fe8e5daa`(06:43)로 깸(06:57) → 밤 착지 여섯 «검수» → 이 라운드 → 총괄 닫힘 `ce56b2d1`
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL(격리 DB). **운영이 아니다.**
> **스위트:** `server/scripts/run_pg_tests.py` — 전 **1 failed / 73 passed / 29 errors** → 후 **103 passed / 0 failed / 0 errors**(커밋 본문). 총괄이 «직접» 같은 수를 다시 쟀다(보드 `ce56b2d1`). 새 게이트 시험 **3**.

## ① 왜 — 픽스처의 사본이 그 표의 «진짜 저자»보다 먼저 도착했다

`pg_engine` 은 `Base.metadata` 의 «모든» 표를 스크래치 스키마로 복사해 `create_all` 했다. 그런데 `init_dynamic_models` 는 `kind: view` 항목도 «매핑»한다 — 그 항목의 `column_types` 는 «읽는 쪽이 보는 것»을 적은 것이다. 그래서 스크래치에 varchar `ledger_events` 가 섰고, 제품 자신의 `ensure_schema` 가 거기에 `CHECK jsonb_typeof(object_payload)` 를 붙이다 죽었다. 그 표의 진짜 저자는 원장의 «파티션 jsonb DDL» 이다.

🔴 **그리고 그 29 는 `failed` 가 아니라 `errors` 로 돌아왔다.** 픽스처 결함이 내용 결함의 옷을 입는 방식이 그것이다 — S-257 보고가 그 29 를 «내용»으로 읽어 그렇게 적었고, 총괄의 S-259 지시도 «같은 전제»로 나갔다. 보드 `ce56b2d1` 가 그 절반을 정정한다: 시험 29 중 13 은 정말로 죽은 물음을 재고 있었으므로 S-259 작업 자체는 유효했고, 「PG 실행이 «내용» 결함을 드러냈다」가 «절반만» 참이었다.

⚠️ **평범한 스위트는 이것을 «볼 수 없었다».** 스위트는 `sqlite:///:memory:` 에 고정돼 이 증명들이 건너뛰고, 새 체크아웃에는 `table_config.json` 이 «아예 없다». 거기서의 「초록」은 「이 박스가 가진 카탈로그가 로드된 적이 없다」는 뜻이었다.

## ② 변경 — 물어보는 상대가 «DB 가 아니라 선언»이고, 그 낱말엔 저자가 하나다

```python
# server/tests/conftest.py
def creatable_tables(metadata, catalogue=None):
    """The tables of `metadata` whose SHAPE this harness is entitled to author (S-260)."""
    from ledger.setup_bundle import catalog_kind
    if catalogue is None:
        from database import crud
        catalogue = crud.TABLE_CONFIG
    return [table for table in metadata.tables.values()
            if catalog_kind((catalogue or {}).get(table.name)) != "view"]

# pg_engine — 거절된 것은 «침묵 대신 이름»으로
creatable = creatable_tables(Base.metadata)
declined = sorted(set(Base.metadata.tables) - {t.name for t in creatable})
if declined:
    print("[pg_engine] not built here, declared `kind: view` (%d): %s"
          % (len(declined), ", ".join(declined)))
for table in creatable:
    table.to_metadata(scratch, schema=None)
```

`models.sync_dynamic_tables_schema` 는 이 물음을 `inspector.get_view_names()` 로 묻는다 — 그때는 릴레이션이 «이미 있기» 때문이다. 픽스처에서는 «아무것도 없어서» 카탈로그만 답할 수 있고, 그 낱말의 기본값을 정하는 자리는 `setup_bundle.catalog_kind` «하나»다(S-187). 카탈로그가 «들고 있지 않은» 이름은 표다 — 프레임워크 자신의 릴레이션들, 즉 스크래치 스키마를 이루는 것들이 그래서 계속 지어진다.

거절된 릴레이션을 «한 줄로 이름 부르는» 것은 장식이 아니다. 나중에 그중 하나를 못 찾는 증명이 설명 없는 `UndefinedTable` 대신 이 줄을 읽는다.

## ③ 게이트 — 재현이 «불가능한 곳»에서 성질을 잰다

```python
# server/tests/test_the_pg_harness_does_not_author_a_declared_view.py
def _two_relations():
    """One relation of each kind, otherwise identical - so the KIND is what decides."""
    metadata = MetaData(); Table("plain_tbl", metadata, Column("id", String))
    Table("read_only_vw", metadata, Column("id", String)); return metadata

built = {t.name for t in creatable_tables(_two_relations(), {"read_only_vw": {"kind": "view"}})}
assert built == {"plain_tbl"}                                          # 🔴 게이트
built = {t.name for t in creatable_tables(_two_relations(), {})}
assert built == {"plain_tbl", "read_only_vw"}                          # ⛔ 회귀선 — 카탈로그에 «없는» 것은 지어진다
assert "catalog_kind" in creatable_tables.__code__.co_names            # ⚠️ 다섯째 철자 금지(S-187)
```

판정자에게 «박스의 카탈로그가 아니라 카탈로그를 먹인다» — 성질이 「결함을 재현할 수 없는 곳」에서 성립해야 하기 때문이다. 셋째 단언은 `kind` 의 기본값을 «코드 객체»로 못 박는다: S-187 이 그 기본값을 한 자리로 모은 이유가 네 자리가 각자 `str(x.get("kind") or "table")` 을 적고 있었기 때문이고, 하니스가 «다섯째»를 적으면 그 하니스가 다시 릴레이션을 짓는 쪽으로 어긋난다.

## ④ 아키텍처 영향

- PG 하니스의 스크래치 스키마 «모집단»이 「매핑된 모든 표」에서 「카탈로그가 view 라 부르지 «않는» 표」로 좁혀졌다. 무엇을 만들지는 이제 «선언»이 답한다.
- `ledger_events` 가 「물리 표인데 `kind: view` 로 선언돼 쓰기 문이 거절한다」(S-186)는 사실이, 시험 하니스 쪽에서도 «같은 선언»으로 읽힌다 — 두 곳이 갈라질 자리가 하나 줄었다.
- `kind` 기본값의 철자는 여전히 `catalog_kind` «하나»이고, 그것이 «강제되는 자리»는 위 셋째 단언이다.

## ⑤ 그때 남아 있던 것

- 이 성질은 «카탈로그가 있는 박스»에서만 실제로 발화한다. 새 체크아웃에는 `table_config.json` 이 없어 `creatable_tables` 가 거절할 것이 «하나도 없다» — 그래서 게이트 셋이 카탈로그를 손으로 먹이고, 그 셋이 이 성질의 «상시» 증명 전부다.
- 「이 박스의 `kind: view` 열하나 중 열은 운영자가 쓴 SQL 뷰, 하나가 `ledger_events`」는 «이 박스 카탈로그»의 수다. 커밋의 docstring 이 그렇게 적는다.
- 29 를 「내용 결함」으로 읽은 보고와 그 전제로 나간 지시는 이 커밋 시점에 «이미 착지해 있었다»(S-259: `cbc9ea4d` · `15ffc565` · `46451370`). 전제의 절반이 거짓이었다는 사실은 보드에만 적혔다.
- 이 항목의 103 · 73 · 29 는 «이 박스의 PostgreSQL»에서 잰 수다.

---
📎 이 항목의 수(103 · 1/73/29 · 3 · 11)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 이 하니스가 자리를 얻은 날: `20260916_022404_the_postgresql_only_proofs_get_a_seat_and_the_first_run_showed_what_skipping_had_hidden.md`(S-256) · 그 첫 실행이 낸 빨강을 정리한 날: `20260916_023822_the_scratch_search_path_has_one_spelling_the_bk_proof_asks_its_author_and_the_pg_seat_runs_only_when_asked.md`(S-257/S-258).
