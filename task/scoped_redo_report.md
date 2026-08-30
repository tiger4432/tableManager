# 📏 [A 구현자] **착수 전 측정 — 멈춤 조건 넷 «다 통과». 그리고 되돌림 완료** (2026-08-30 22:2x)

## ① `5a07ec40` 되돌림 — 끝났습니다
```
커밋   프레임 기작 세 번째이자 마지막 제거
흔적   frame_keys · _declared_frames · _frame_expand   다섯 파일에 «0»
충돌   d306b450 이 그 사이 샘플을 건드렸는데 «자동 병합»됐고, 그 소스(lot_slot_wafer)는 살아 있습니다
시험   test_ledger_setup_bundle + test_ledger_subgraph  «119 passed · 2 skipped» (라운드 전 수)
```
「두 id」 관찰은 보드로 갔으니 코드에서 빠져도 남습니다.

---

# 착수 전 측정 — S1~S4

## S1 `--reset-cursor` 를 열어야 하나 → **아니오. 커서를 «건드릴 일이 없습니다»**
```
범위 재번역이 필요한 것   ⓐ 그 범위의 원자를 지우고  ⓑ 그 행만 다시 읽는다
커서가 하는 일            «소스 전체»의 워터마크 — ⓑ 와 무관합니다
=> 범위 읽기는 커서를 «읽지도 쓰지도» 않습니다. 가드는 그대로 둡니다
```

## S2 `read` 에 필터 축을 더해야 하나 → **아니오. 이미 있는 축을 넓히면 됩니다**
```
지금   _fetch_v2_lineage_rows(connection, plan, *, after=None, group_value=None, limit=None)
       group_value 가 있으면  WHERE <page_key> = %s
       after 가 있으면        WHERE <page_key> > %s
page_key = 커서의 «첫 컬럼» (_page_key)
=> 범위는 「그 컬럼의 값 여럿」입니다. `= %s` 를 `= ANY(%s)` 로 넓히는 것이고,
   «새 축»이 아니라 이미 그 컬럼으로 필터하는 자리입니다. `read` 는 한 글자도 안 바뀝니다
```
🔴 그리고 이게 실제로 운영자가 부르는 이름인지 확인했습니다 — 라이브 15 소스의 page key:
```
bw_dt_seat        base_id      ← «캐리어». 지시서가 말한 「carrier/lot 목록」이 그대로 이것입니다
lot_slot_move     event_time
dt_job            dt_job
die_inspection    run_uid
void_observation  void_uid
process_param_*   param_id     ← 합성 id. 표현은 되지만 «사람이 부르는 이름»은 아닙니다
```
⚠️ 그래서 범위 표현이 소스마다 «자연스러움이 다릅니다». 캐리어로 부르고 싶은 소스는 되고,
   합성 키뿐인 소스는 운영자가 그 id 를 알아야 합니다. 이건 설계 결함이 아니라 «선언의 모양»입니다.

## S3 남의 원자를 가져가나 → **아니오, 술어에 `source_who` 가 «들어가면»**
```
지금 있는 삭제   ledger/backfill.py:407   DELETE FROM ledger_events WHERE source_who = %s
                 -> 소스 «전체». 범위가 없습니다
범위 삭제        WHERE source_who = %s AND <범위 술어>
=> `source_who` 가 술어의 «일부»라 다른 소스 원자는 구조적으로 못 건드립니다.
   G4 가 그걸 «태워서» 확인합니다 (한 주어를 두 소스가 말하게 두고 한쪽만 다시)
```

## S4 `deletes` · `restartable` 을 정직하게 쓸 수 있나 → **예**
```
deletes      "ledger_events rows this source wrote about the named scope"  (정확히 그것뿐)
restartable  True — 페이지마다 커밋하므로 중단해도 이어서 됩니다
```

---

## 그래서 만들 것 — 등록부에 «연산을 더하는 것»뿐입니다
```
⛔ 두 번째 등록부 «안 만듭니다» — server/retroactive.py 의 OPERATIONS 에 항목을 더합니다
⛔ --limit 에 새 뜻 «안 붙입니다» — 범위는 별도 파라미터입니다
없던 것 하나   「행을 지목하는 것」 = 범위 파라미터. 그것만 더합니다
```
```
ledger_rescope   params  [source, scope(csv)]
                 count   그 범위에 그 소스가 쓴 원자 수 (exact — 세는 질의가 정확합니다)
                 run     ⓐ 그 술어로 삭제 → ⓑ 그 page key 값들만 다시 읽어 번역
                 deletes "ledger_events rows this source wrote about the named scope"
```
체인 쪽은 `replay_rule` 의 `limit` «옆»에 선택을 붙입니다 — 지시대로 `limit` 의 뜻은 안 건드립니다.

👉 **설계가 이 모양으로 맞으면 그대로 갑니다.** 특히 S2 의 「범위 = page key 값 목록」이
   의도하신 「업무 키」와 다르면 지금 말씀해 주십시오 — 그 위에 코드를 얹기 전에 갈리는 자리입니다.
