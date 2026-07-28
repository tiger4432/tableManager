# `auto_update_control.json` 세팅 — 수집기 on/off 토글

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Ingester
> 상위: [폴더 인덱스](./README.md) · 수집기 체계 정본은 [AUTO_UPDATE_GUIDE](../AUTO_UPDATE_GUIDE.md) · 절차 요약은 [CONFIG_GUIDE §3-S3](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  IO module: server/utils/auto_update_control.py (format {"disabled": [...]}, fail-open on missing/corrupt,
    key regex "<ws>/<file>.py" :SCRIPT_KEY_RE, atomic write tmp+os.replace, threading lock)
  scheduler reads every cycle; web API computes active live: server/main.py:3629
  routes (admin-gated): GET /admin/auto-update/status :3611, POST /admin/auto-update/toggle :3644,
    POST /admin/auto-update/run-now :3679 (strict — 503 when ASSY_ADMIN_TOKEN unset)
-->

## 1. 언제 이 파일을 만지는가

- **수집기(auto_update 스크립트)를 끄거나 켤 때** — 점검·장애 중 특정 수집만 멈추고 싶을 때
- **직접 편집하지 않습니다.** 이 파일은 config 관례 위치에 있지만 **쓰기는 API 전용**입니다 — API가 락 + 원자적 쓰기(tmp+replace)로 갱신하므로 손편집은 동시 쓰기에 덮일 수 있습니다.
- 수집기 **추가**는 이 파일이 아닙니다 — `<ws>/auto_update/<name>.py` 파일 배치 자체가 등록이고, 스케줄은 스크립트 **주석**의 `schedule`(cron)입니다 → [AUTO_UPDATE_GUIDE](../AUTO_UPDATE_GUIDE.md).

## 2. 세팅 절차 (API로)

1. 현재 상태 확인:
   ```bash
   curl "http://<host>:8080/admin/auto-update/status" -H "X-Admin-Token: <토큰>"
   ```
2. 끄기/켜기 — 키 형식은 `<워크스페이스>/<파일명>.py` 하나뿐(공백·한글 파일명 허용, 형식 위반은 400):
   ```bash
   curl -X POST "http://<host>:8080/admin/auto-update/toggle" \
     -H "X-Admin-Token: <토큰>" -H "Content-Type: application/json" \
     -d '{"script": "bonding_map/fetch_data.py", "active": false}'
   ```
3. 꺼진 상태에서도 1회 즉시 실행이 필요하면:
   ```bash
   curl -X POST "http://<host>:8080/admin/auto-update/run-now" \
     -H "X-Admin-Token: <토큰>" -H "Content-Type: application/json" \
     -d '{"script": "bonding_map/fetch_data.py"}'
   ```
   `run-now`는 **`active=false`여도 실행됩니다**(수동 실행 = 명시적 의도). ⚠️ 이 라우트는 strict 게이트 — `ASSY_ADMIN_TOKEN` 미설정 서버에서는 503입니다.

반영은 즉시입니다 — `active`는 상태 파일이 아니라 **항상 이 제어 파일에서 실시간 계산**되고, 스케줄러는 매 사이클 다시 읽습니다. 재기동·reload 불필요.

## 3. 반영 확인

```bash
curl "http://<host>:8080/admin/auto-update/status" -H "X-Admin-Token: <토큰>"
```

해당 스크립트의 `active` 필드가 바뀌었는지 확인합니다. 끈 수집기는 다음 스케줄 사이클부터 스킵됩니다(스케줄러 로그에서도 확인 가능). `scheduler_status.json`을 열어 보는 것은 참고일 뿐 — 그 파일은 스케줄러의 **출력**이며 다음 사이클에 덮어써집니다.

## 4. 잘못됐을 때

토글 실수는 같은 API로 되돌리면 끝입니다. 파일이 손상됐다면 — **fail-open**이라 전부 active로 동작합니다(수집이 멈추는 쪽으로 죽지 않음). 스냅샷 복원도 가능합니다:

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore auto_update_control_<yymmdd>.json.bak --yes
```

→ [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)

## 5. 키 참조

```json
{ "disabled": ["<워크스페이스>/<파일명>.py", ...] }
```

| 키 | 의미 |
|---|---|
| `disabled[]` | 비활성 수집기 키 목록 — **여기 없는 것이 전부 active** (파일 부재/손상 = 전부 active) |

키는 경로 구분자·`..` 금지(`<ws>/<file>.py` 정확히 한 단계). 목록에 넣고 빼는 것이 토글의 전부이며, 그 외 필드는 없습니다.
