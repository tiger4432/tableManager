# 서버 API 표면 지도 — 이름 체계 점검 (2026-09-04, 총괄)

> 출처: **도는 서버가 스스로 신고한 `GET /openapi.json`** (grep 아님).
> 측정 시각 기준 `pid 66708 · 08:06:59` 기동본. **구 그래프 분기 삭제(`8ffe23d7`)는 아직 미반영** —
> 재기동 전이라 아래 `/graph/*` 여섯은 «곧 사라질» 것이 찍혀 있습니다.

```
경로 113 · 오퍼레이션 117
```

## 1. 접두별 분포

| 접두 | 수 | 성격 |
|---|---:|---|
| `/admin/**` | 45 | 어드민 화면이 쓰는 전부 (토큰 게이트) |
| `/tables/**` | 21 | 그리드·표 CRUD·이력·업로드 — 운영 제품의 본체 |
| `/api/maps/**` | 7 | 맵 정렬·오버레이·페인트 규칙 |
| `/graph/**` | 6 | ⚰️ 은퇴 스텁(410). 삭제 착지, 재기동 대기 |
| `/internal/**` | 4 | 프로세스 간 이벤트 (외부 아님) |
| `/api/ledger/**` | 3 | **온톨로지 읽기 — declaration · gaps · subgraph** |
| `/api/transfer-plan/**` | 3 | 이송 계획 |
| `/enrichment/**` | 3 | 보강 |
| `/api/map-presets`, `/map-presets` | 2+2 | 🔴 **같은 것이 두 이름** |
| `/audit_logs/**` | 2 | 감사 로그 |
| 낱개 | 나머지 | `/health` · `/dashboard/summary` · `/api/effort/config` · `/api/desktop/download` · `/api/download/client` · `/api/bonding-plan/core-summary` · `/api/graph/sync` |
| 정적 페이지 | 7 | `/` · `/{file_name}` · `*.html` · `/map-editor` · `/map-editor2` |

---

## 🔴 2. 발견 — 이름 체계가 «세 축»에서 갈려 있습니다

### ① `/api` 접두가 «일관되지 않습니다» — 그리고 이건 미관 문제가 아닙니다
```
접두 있음   /api/ledger · /api/maps · /api/transfer-plan · /api/map-presets
           /api/bonding-plan · /api/desktop · /api/download · /api/effort · /api/graph/sync
접두 없음   /tables (21) · /admin (45) · /graph (6) · /enrichment · /audit_logs
           /dashboard · /internal · /health
```
🔴 **왜 기능 문제인가** — 구현자 실측(2026-09-04): **`/api` 가 «아닌» 알 수 없는 경로는
`404` 가 아니라 SPA catch-all 의 `200 text/html` 을 돌려줍니다.**
```
=> 오타 난 경로가 «조용히 200». 클라의 res.ok 가 true -> HTML 을 JSON 으로 파싱 -> 「알 수 없는 오류」
=> 즉 `/api` 는 «부재를 정직하게 말하는 유일한 이름공간»입니다
```
📌 실제 대가: 총괄이 같은 날 `/api/graph/mapping-summary`(404) 를 재고 「게이트가 죽었다」고
   보고했는데, 진짜 경로는 `/graph/mapping-summary`(410 + 이유 + 후속 + 판정번호)였습니다.
   **접두 불일치가 측정 오류를 하나 만들었습니다.**

### ② 같은 자원이 두 이름
```
/map-presets          GET/POST · DELETE /{preset_key}
/api/map-presets      GET/POST · DELETE /{preset_key}      🔴 중복 표면
/map-editor  ↔  /map_editor.html          하이픈 라우트 + 언더스코어 페이지
/map-editor2 ↔  /map_editor2.html
```

### ③ 하이픈과 언더스코어가 한 트리에
```
하이픈     auto-update · map-presets · transfer-plan · ontology-explorer · run-now
          retry-failed · dry-run · chip-trace · file-ingestion · reload-configs
언더스코어  audit_logs · row_ids · batch_delete · map_editor.html · {table}/data
```

### ④ 온톨로지 표면이 «세 접두»에 흩어져 있습니다
```
읽기·걷기   /api/ledger/{declaration,gaps,subgraph}          3
저작        /admin/ontology-explorer/**                     15
관리        /admin/ledger/{config/raw,dry-run,relations,sources}  4
```
같은 도메인인데 세 이름입니다. 「엔티티·어휘·walk」의 데이터 축은 `/api/ledger/subgraph`
«하나»로 잘 모였는데, **저작·관리 축은 안 모였습니다.**

### ⑤ 명사와 동사 혼재
```
명사(자원)  /tables/{t}/rows · /admin/outbox/failed · /api/ledger/subgraph
동사(행위)  /admin/reload-configs · /admin/auto-update/run-now · /admin/outbox/retry-failed
          /admin/retroactive/{op}/run · /api/graph/sync · /admin/ledger/dry-run
```
POST 에 붙은 동사는 정당합니다(연산이니까). 다만 «GET 에도» 동사가 있습니다 —
`/admin/ledger/dry-run` · `/admin/enrichment/auto-confirm/dry-run` · `/admin/transfer-plan/dry-run`.

---

## 3. 규모가 말하는 것
```
/admin 45개가 한 접두에      main.py 6,118줄과 같은 사실입니다
/tables 21개                 운영 제품의 본체. 이름 규칙이 가장 «일관»된 구역이기도 합니다
                            ({table_name} 하위로 자원이 정연하게 갈립니다)
```

## 🔴 3-bis. 문서를 읽는 사람이 «치는 이름»과 코드의 변수명이 다릅니다
```
walk 라우트   node_id: str = Query(..., alias="id")
             -> URL 인자는 «id». `node_id` 는 파이썬 «변수명»입니다
```
📌 제가 이 문서와 지시서 둘에 `node_id` 로 적었고, 구현자가 그걸 믿고 «422 를 여섯 번»
   받았습니다. FastAPI 의 `alias=` 는 시그니처만 봐서는 안 보입니다.
👉 규칙: **인자·선언 형식은 «와이어 이름»으로 적는다.** 확인은 `openapi.json` 의
   `parameters[].name` 이지 소스의 변수명이 아닙니다.

## 4. 아직 «없는» 것 (지시 내림, 2026-09-04)
```
주어·술어·목적어로 원자를 «찾는» 자리
   ledger_atom 은 predicate · subject_type/keys · object_payload 로 이미 갈려 있는데
   그걸 Query 로 받는 라우트가 «0». walk 은 씨앗(node_id)이 필수라 우회 불가
   -> GET /api/ledger/atoms/summary?by=predicate|subject_type|source  (비용 선측정 후)
```

---

## ⚠️ 이 문서를 읽는 법
- **운영 주장 아님.** 이 박스에서 도는 프로세스가 신고한 «표면»입니다.
  경로와 이름은 코드가 정하므로 운영에도 참이지만, «어느 것이 실제로 쓰이나»는 여기 없습니다.
- 재기동하면 `/graph/**` 여섯과 `/api/graph/sync` 가 사라집니다. 그때 수는 117 → 110.
