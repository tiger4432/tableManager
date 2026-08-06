# 프리페치는 이미 그 행이 없다고 증명했고, 행마다 두 번씩 다시 물었다

**날짜:** 2026-08-07 · **레인:** P3-IMPL (집합 기반 쓰기 경로) · **Tier:** T2
**측정 상자:** 이 워크스테이션의 격리 `assy_qa` 스냅샷. **운영이 아니다.**

---

## 현상

100,000행 / 3 MB 맵 파일 하나를 표준 인제션 경로로 넣으면 **796.2초**가 걸리고
**301,100개의 SQL 문장**이 나갔다 — **데이터 행당 3.011문장**. 프로파일링 라운드
(`Server_P3_ingestion_profile.md`)의 실측으로 벽시계의 **65%가 데이터베이스가 아니라
Python/SQLAlchemy**였고, 1,000만 행으로 외삽하면 단일 스레드 20~30시간이다.

## 근본 원인 — 신원의 문이 둘, 배치되지 않는 flush 하나, 청크마다 다시 짓는 VALUES 절 하나

1. **`_get_or_create_row`가 프리페치의 증명을 안 읽었다.** `apply_batch_updates`는 청크
   시작에 `row_id IN (…) OR business_key_val IN (…)`으로 기존 행을 한 번에 당겨 온다.
   신규 파일의 행은 당연히 하나도 안 나오는데, 루프는 행마다 `get_row_by_business_key`로
   같은 질문을 다시 했다.
2. **문이 하나가 아니라 둘이었다.** 두 번째는 **복합 키 충돌 탐침**이다. 맵 CSV가 업무 키
   컬럼을 **빈 값으로** 실어 오면 행이 `business_key_val=''`로 만들어졌다가 조립된 키와
   어긋나므로 이 탐침이 **행마다** 발화한다. 첫 번째 문만 닫으면 3문장 중 1문장만 준다.
   두 SELECT 모두 인덱스 스캔이라 실행은 0.03~0.10 ms인데 **계획 시간이 그보다 길었다** —
   고칠 것은 계획이 아니라 문장 수였다.
3. **ORM flush가 행마다 INSERT를 냈다.** 원인은 `updated_at=func.now()`. 파라미터 집합에
   SQL 식이 들어가면 SQLAlchemy는 `insertmanyvalues`로 접지 못한다. **같은 flush에서 나가던
   아웃박스 행은 값이 평범해서 이미 배치되고 있었고**(10만 건에 데이터 49.3초 vs 아웃박스
   8.2초), 그 대비가 원인을 지목했다.
4. **`bulk_upsert_cell_sources`가 청크마다 다중행 VALUES 절을 새로 지었다.** 223초 중
   **163초가 그 구성**이고 SQL은 60초였다.

## 해결

```python
# crud.apply_batch_updates — 물었는데 아무것도 안 온 값만 담는다
_found_ids = {r.row_id for r in existing_rows_list}
_found_bks = {r.business_key_val for r in existing_rows_list if r.business_key_val}
probed_identity = ProbedIdentity(
    row_ids=frozenset(target_ids) - _found_ids,
    business_keys=frozenset(target_bks) - _found_bks,
)
```

🔴 **차집합이 정합성의 전부다.** 빼지 않으면 집합은 「물었다」밖에 말하지 못하고, 판정을
`row_cache`에 기대야 한다 — 그런데 **루프가 `row_cache`를 바꾼다**(업무 키를 개명하면 옛 키
항목을 지운다). 같은 배치 안에서 개명 뒤에 옛 키를 가리키는 항목이 오면 캐시가 비어 있고,
그것을 「없다」로 읽어 **중복 행을 만든다**. 차집합은 **프리페치 시점 DB에 대한 진술**이라
루프가 바꿀 수 없다(`no_autoflush` 안에서 아무것도 flush되지 않는다).

```python
# _get_or_create_row — updated_at을 INSERT에서 뺀다(server_default가 같은 값을 넣는다)
row = table_model(row_id=update_item.row_id or str(uuid6.uuid7()))
```

```python
# bulk_upsert_cell_sources — 문장은 한 번 컴파일하고 파라미터 목록을 넘긴다
if _is_executemany_safe(deduped_mappings):
    stmt = upsert_insert(models.CellSource).on_conflict_do_update(...)
    for chunk in _chunks(deduped_mappings, chunk_size):
        db.execute(stmt, chunk)
    return
```

그리고 누산기가 있는 배치 경로에서는 새 셀 메타 객체를 매핑 인스턴스가 아니라 이미 있던
`LightCellSource`/`LightCellOverwrite`로 만든다 — 그 객체는 세션에 안 들어가고 우선순위
계산에만 참여하므로. (5,000행에 ORM 인스턴스 생성 45,000회 중 35,000회가 이것이었다.)

## 검증 — 같은 입력, 같은 상자

| | 변경 전 | 변경 후 |
|---|---:|---:|
| 벽시계 | 796.2 s | **375.8 s** (2.12×) |
| ms / 행 | 7.962 | **3.758** |
| SQL 문장 | 301,100 | **1,200** (251×) |
| 문장 / 행 | 3.011 | **0.012** |
| 데이터 행 / `cell_sources` / `audit_logs` / `database_outbox` | 100,000 / 700,000 / 100,000 / 100,000 | **전부 동일** |

정합성 프로브 14종을 **실제 PostgreSQL**(격리 `assy_qa`)에서 통과 — 레이어링(`user`가 나중
파서를 이긴다), 재-Push 무중복, 공백 낀 업무 키, 충돌 병합, 아웃박스·감사 건수, replace_map
diff, 그리고 위의 개명 시나리오.

🔴 **그물이 울리는 것을 확인했다.** 변이 주입: ① 충돌 탐침을 무력화 →
`collision_merge_outside_prefetch`만 빨감 ② 차집합 제거 →
`rename_then_old_key_no_duplicate`만 빨감(다른 경로는 `row_cache`가 먼저 답하므로 **그것
하나만** 그 결함에 반응한다). 첫 시도의 변이 둘은 **조용했고**, 그 침묵이 차집합 결함을
찾아냈다 — 불충분한 변이와 견고한 테스트는 밖에서 똑같이 생겼다.

## 이 라운드에서 고치지 않은 것 (보고만)

- **저장 용량**: 1행이 ~10행 / ~2.57 KB, 1,000만 행이면 ~50 GB. 제품 소유자의 결정.
- **행마다 발화하던 충돌 탐침의 원인이 되는 「빈 키 컬럼」에 선재 결함이 둘 더 있다** —
  두 번째 Push가 `business_key_val`을 `''`로 지우고, 세 번째 Push가 행을 전부 복제한다.
  변경 전 코드에서 **동일하게** 재현된다(`P3I_dbg_bk.py`).
- **충돌 병합이 껍데기 행을 남긴다** — 아직 flush되지 않은 인스턴스에 `db.delete`를 부르고
  맨 `except: pass`가 삼킨다. 역시 변경 전과 동일.
- 백프레셔·`_classify_lane`의 바이트 기준·`cell_sources`의 파일명 소스 키.
