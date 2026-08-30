# 🛑 [A 구현자] **판정 받았고, 그 위에서 «지시서의 전제 하나»가 실측으로 깨집니다** (2026-08-30 23:1x)

22:3x 판정(범위를 «선언된 입력 컬럼»으로) 받았습니다. 그대로 짓기 시작했는데, **회수(withdraw)
쪽에서 지시서 문장 하나가 실측과 안 맞습니다.** 코드를 얹기 전에 올립니다.

## 지시서 문장
> `find the atoms this source wrote about the scope` … `withdraw them scoped by source AND
> by the named keys`

「이름 댄 키로」 회수하려면 **그 키가 원자에 있어야** 합니다. 없습니다.

## 실측 — 이 도구가 존재하는 이유인 소스 «넷», 전부 같은 모양
```
소스              subject   subject_keys                        qualifiers
dt_transfer       die       x · y · mat_id · mat_type           «없음»
bw_dt_seat        die       x · y · mat_id · mat_type           «없음»
transfer_event    die       x · y · mat_id · mat_type           «없음»
bonded_from       die       x · y · mat_id · mat_type           «없음»
```
🔴 **범위 컬럼(`core_wafer` · `dt_job` · `base_id`)이 원자에 «한 군데도» 없습니다.**
subject_keys 에도, qualifiers 에도. 원자는 「어느 다이인가」만 말하고 「어느 캐리어의 어느 행에서
왔는가」는 «안 말합니다».

## 그래서 원자 -> 소스 행의 «유일한» 연결은 `source_raw_ref` 입니다
```
bw_dt_seat    {"event":"…", "rows":["bonding_core_die:{\"base_id\":\"SYN-AUG-BW-001-01\",\"bx\":0.0,\"by\":7.0}"]}
dt_transfer   {"event":"…", "rows":["dt_log_transferable:{\"row_id\":\"019fbdeb-…\"}"]}
```
관계 이름 + 그 행의 «식별 키»가 들어 있습니다. 그리고 그걸 만드는 자리가 «하나»입니다 —
`ledger/roleframe.py:1223 _claim_source_raw_ref(event_ref, row_refs)`.

## 그래서 회수는 이 모양이 됩니다 — 두 걸음, 둘 다 선언 기반
```
1  SELECT <식별 컬럼> FROM <relation> WHERE <선언된 범위 컬럼> = ANY(%s)
   -> 범위에 든 «행의 식별». 여기서 판정하신 「선언된 입력 컬럼」 검증이 걸립니다(G7)
2  그 행들의 raw ref 를 «_claim_source_raw_ref 로» 만들어
   DELETE … WHERE source_who = %s AND source_raw_ref = ANY(%s)
   -> source_who 가 술어에 있으므로 S3(남의 원자) 는 여전히 구조적으로 불가
3  같은 행들만 다시 번역 (커서 안 건드림 — S1 그대로)
```
⚠️ **2 에서 ref 를 «제가 다시 조립하지 않습니다».** 그 함수를 부릅니다. 손으로 다시 만들면
   번역기가 쓴 것과 한 글자만 달라도 «0건 삭제 후 중복 생성»이 되고, 그건 조용합니다.

## 그런데 여기서 «묻고 갑니다» — 제가 정할 자리가 아닙니다
```
ⓐ dt_transfer 의 raw ref 는 row_id 만 듭니다.
   운영자가 부르는 이름은 core_wafer 인데, 원자에서 core_wafer 로 되짚을 길이 «없습니다».
   그래서 «반드시» 소스 관계를 한 번 읽어 core_wafer -> row_id 로 풉니다(1단계).
   -> 그 행이 «그 사이 지워졌으면» 그 원자는 범위로 못 찾습니다. 고아가 됩니다
   -> 이걸 「없는 행의 원자는 회수 대상이 아니다」로 둘지, 별도로 셀지 판정이 필요합니다

ⓑ 원자에 캐리어를 «심는» 대안(수식어에 core_wafer 를 싣기)은 «제안하지 않습니다».
   그건 재적재이고 선언 변경이며, 이번 라운드 밖입니다. 다만 그렇게 하면 회수가
   한 걸음이 된다는 것만 적어 둡니다
```
👉 ⓐ만 답 주시면 그대로 짓겠습니다. G1~G7 은 판정하신 그대로 갑니다.

---

# (앞선 측정 — 그대로 유효합니다)

S1 커서 안 건드림 · S2 `read` 안 바뀜(WHERE 하나) · S3 `source_who` 가 술어에 있어 구조적 격리 ·
S4 `deletes`/`restartable` 정직하게 기술 가능. 판정으로 승인받았습니다.

되돌림(`5a07ec40`)도 끝났고 두 게이트 파일은 119 passed · 2 skipped 입니다.
