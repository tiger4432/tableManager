# 관리자 라우트 16개에 자물쇠를 달았다 — 그런데 **더 큰 구멍은 그 옆의 정적 핸들러**였다

> 커밋 `90e284f` · 2026-07-27 20:03 · 도메인 Server(인증 경계) + Client(어드민 페이지)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 배포: [DEPLOY_SETUP](../guide/DEPLOY_SETUP.md) · 체크리스트: [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md)
> 선행: [조용한 성공 결함 둘](./20260727_181910_silent_success_exec_scoping_and_clipboard_precedence.md) (`512dca7` — 아래 "바인드 주소" 절의 증거가 여기서 나온다)
> 검수 기록: [QA_admin_token_gate_review_B](../../agent_workspace/reports/QA_admin_token_gate_review_B.md)

## 배경

`main.py`의 `/admin/*` 라우트 **16개에 인증이 하나도 없었다.** 이 파일의 `Depends`는 전부 `get_db`였다.

그중 둘이 체인으로 이어지면 그대로 원격 코드 실행이다.

- `POST /admin/scripts/code` — 임의의 파이썬 파일을 `mappers/`·`ingestion_workspace/`에 **쓴다.**
- `POST /admin/auto-update/run-now` — 그것을 **실행한다.**

**패킷을 라우팅할 수 있는 누구에게나 열려 있었다.** `GET` 라우트도 단순 정보가 아니다 — 소스 코드를 반환하고
파이프라인 표면을 열거한다.

운영은 소수가 쓰는 사내망 공유이므로 **로그인 시스템이 아니라 공유 비밀 하나**로 갔다.
사용자도, 세션도, 비밀번호 저장소도 없다. 환경변수 `ASSY_ADMIN_TOKEN` 하나를 `X-Admin-Token` 헤더로 제시한다.

## 변경 내용

### 게이트의 두 상태 — **잊어버린 설정이 구멍도 자물쇠도 되면 안 된다**

```python
# server/admin_auth.py
def _enforce(request, fail_closed):
    expected = configured_token()
    if expected is None:
        if fail_closed:
            raise HTTPException(status_code=503, detail=_UNSET_DETAIL)
        return
    presented = request.headers.get(ADMIN_TOKEN_HEADER)
    if not presented:
        raise HTTPException(status_code=401, detail=_MISSING_DETAIL,
                            headers=dict(_GATE_HEADERS))
    if not _matches(presented, expected):
        raise HTTPException(status_code=403, detail=_MISMATCH_DETAIL,
                            headers=dict(_GATE_HEADERS))
```

토큰이 **설정되지 않았을 때** 코드 실행 라우트 둘은 **503으로 거부**하고 나머지 관리자 라우트는 계속 서빙한다.
방향이 양쪽으로 잡혀 있다 — **설정을 잊었다고 구멍이 남아서도 안 되고, 그걸 고치러 갈 페이지에서 잠기게 해서도 안 된다.**
`/health`는 게이트 밖에 남았다. 감시 표면을 잠그면 그것이 의존하는 health 작업 자체가 무의미해진다.

비교는 `secrets.compare_digest`이고, 토큰 값은 로그·감사 행·에러 본문·트레이스백 어디에도 닿지 않는다.
헤더 이름을 `X-User`/`X-Transaction-ID`/`X-Source`와 **일부러 다르게** 둔 것도 그 일부다 —
컨텍스트 미들웨어가 읽는 이름이 아니므로 토큰이 `AuditLog` 행으로 실려 들어갈 수 없다.

### **게이트는 절반 이하였다** — 인증 없는 파일시스템 읽기

적대 검수 둘을 병렬로 돌렸고 **각자가 상대가 못 찾은 HIGH를 하나씩 찾았다. 그리고 둘 다 게이트 안에 없었다.**

`serve_static_or_index`가 사용자 제어 경로를 dist 디렉터리에 **격납 검사 없이** 이어 붙이고 있었다.
그 위의 프리픽스 거부 목록은 경로의 **시작**을 보므로 `../../`를 볼 수 없다.

게이트를 **완전히 설정한 상태에서** ASGI 레이어로 측정한 결과:

```
GET /admin/chain/rules                              -> 401
GET /../../server/config/table_config.json          -> 200   20,441 bytes
GET /../../../../../../Windows/win.ini              -> 200   (파일 그대로)
GET /../../server/admin_auth.py                     -> 200   (게이트 자신의 소스)
```

**새로 잠근 GET 라우트 셋이 지키는 바로 그 바이트를 옆문이 그대로 서빙하고 있었다.**
자물쇠가 열린 문 옆에서 문을 지키고 있던 셈이다. 선재 결함이고, 라이브였다.

```python
# server/main.py — 두 번째 격납 검사를 발명하지 않고, 이미 있던 모양을 재사용했다
dist_base = os.path.abspath(client2_dist_path)
target_path = os.path.abspath(os.path.join(dist_base, file_name))
if target_path != dist_base and not target_path.startswith(dist_base + os.sep):
    # 404, not 403: a static route must not confirm that the escape parsed.
    raise HTTPException(status_code=404)
```

판단 셋을 기록해 둔다.

- **`_resolve_admin_script_path`가 이미 갖고 있던 검사를 재사용했다.** 같은 연산의 두 번째 구현은 갈라진다.
- **문자 거부 목록으로는 이것을 할 수 없다.** `os.path.join`은 두 번째 인자가 절대경로(`/C:/Windows/win.ini`)나
  윈도우 드라이브 상대경로(`C:foo`)면 **베이스를 통째로 버린다.** 그래서 **해석된 결과만** 믿을 수 있다.
- **403이 아니라 404다.** 정적 라우트는 탈출이 파싱됐다는 사실조차 확인해 주면 안 된다.
- `/assets`는 **원래 안전했다** — Starlette가 손으로 짠 핸들러가 빠뜨린 그 검사를 한다.

### 두 번째 HIGH는 코드가 아니라 **배포 그 자체**였다

서빙되는 어드민 번들은 git에 추적되고 있고 **이 변경보다 앞선 것**이었다.
그 상태에서 토큰을 켰다면 결과는 **401 일곱 개와 프롬프트 없음**이다 —
프롬프트를 띄우는 코드가 **서버가 보내는 파일 안에 없기** 때문이다.

여기서 리빌드했고, `DEPLOY_SETUP`이 이제 토큰을 켜기 **전에** 번들에 대한
`grep -c X-Admin-Token`으로 게이트를 걸도록 절차를 바꿨다.

> **서버 쪽 인증을 켜는 변경은 클라이언트 산출물이 같이 나갔는지 확인하기 전에는 완료가 아니다.**
> 소스에는 있고 번들에는 없는 상태가 가장 나쁘다 — 코드 리뷰는 통과하고 운영에서만 부서진다.

### 운영자를 그날 밤 물었을 세 가지

1. **비ASCII 토큰은 절대 인증될 수 없다.** Starlette가 헤더를 **latin-1**로 디코드하는데 비교는 **utf-8**로 재인코딩한다.
   그런데 배너는 그 토큰이 **설정됨**이라고 보고했다.
   *"길고 추측 불가능하게"*라고만 적힌 가이드를 보고 한국어 토큰을 쓴 운영자는 **라우트 16개가 전부 잠기고,
   올바른 값을 넣어도 틀렸다는 답을 받는다.** 지금은 **시작 시점에 거부해 *미설정* 상태로 떨어뜨린다** —
   복구 불가능한 잠김 상태가 아니라. 배너가 ERROR 레벨로 원인을 지목한다.

   ```python
   def token_is_unusable():
       """True when a token IS set but can never authenticate."""
       raw = _raw_token()
       return bool(raw) and not raw.isascii()
   ```

2. **클라이언트가 모든 403에 프롬프트를 띄웠다** — 격리 가드가 내는 403까지 포함해서.
   그리고 **멀쩡히 저장돼 있던 토큰을 그다음에 타이핑된 것으로 덮어썼다.**
   격리 서버가 라이브 `mappers/` 트리에 쓰기를 거부하는 것은 토큰과 아무 상관이 없는데,
   그것을 인증 실패로 읽었다. 지금은 게이트가 자기 거부에만 `WWW-Authenticate: X-Admin-Token`을 달고
   클라이언트가 **그 헤더를 기준으로** 판단한다.
3. **프롬프트 취소가 빈 문자열을 저장했고, 30초 갱신이 영원히 다시 물었다.**
   이제 거절이 기록되고, 다시 묻게 하려면 페이지를 새로고침한다.

여기에 하나가 더 붙었다 — **토큰이 바뀌기 전에 이미 날아가 있던 응답은 새 토큰에 대해 아무것도 말하지 않는다.**
세대 카운터(`adminTokenGeneration`)가 없으면 "동시 요청 일곱 개에 프롬프트 하나"는 타이밍 운이고,
실제 모달이 몇 초 열려 있으면 **멀쩡한 토큰을 틀렸다고 지목하는 추가 프롬프트**가 뜬다.

### `/internal/events/*` — 인증 없는 **쓰기** 표면

읽기 전용 관리자 라우트에 자물쇠를 다는 동안 이쪽은 완전히 열려 있었다. **비대칭이 뒤집혀 있었다.**

`POST /internal/events/broadcast`는 임의의 dict를 **연결된 모든 클라이언트에 중계하고 audit 캐시에 주입한다.**
인증 없는 호스트가 **모든 운영자의 그리드에 날조된 값을 띄우고 타임라인에 날조된 행을 넣을 수 있었다.**
`SYSTEM_OVERVIEW` §1이 이것을 시스템이 느린 것보다 나쁘다고 규정한다 — 전파가 신뢰받지 못하면 정정이 멈추고
온톨로지가 틀린 채로 굳는다.

루프백 바인딩이 아니라 **같은 비밀로** 잠갔다. 서버는 이미 루프백에 바인딩하는데(다음 절)
**그것만으로는 충분하지 않았음이 분명하기** 때문이다.
워커는 런처의 환경을 상속하므로 추가 설정이 없다.

잠금은 **발신 데몬 세 곳 모두**에 적용했고, **각 발신자의 소스를 읽는 테스트**가 붙었다 —
이 저장소는 같은 결함을 데몬 단위로 다시 들여온 전력이 있다.

### 바인드 주소 — **해소가 아니라 열린 질문으로 기록한다**

- `run_decoupled_app.py`는 **`--host`를 넘기지 않는다.** 따라서 uvicorn 기본값인 루프백이다.
- `SERVER_STARTUP_GUIDE`는 **`--host 0.0.0.0`을 문서화한다.**

무엇이 실제로 도는지는 **관측이 정한다.** `navigator.clipboard`는 localhost에서 정의되어 있는데
사용자에게는 undefined였다(선행 항목 `512dca7`). 즉 **운영은 LAN 주소로 도달되고 있고,
위의 두 구멍은 실제로 노출돼 있었다.**

그러나 **런처와 가이드는 여전히 서로 다른 말을 한다.** 관측이 어느 쪽이 사는지를 정했을 뿐,
둘의 불일치 자체는 이 커밋에서 손대지 않았다. 가정으로 봉합하지 않고 **열린 질문으로 남긴다.**

## 검증

- 스위트 **699 passed** (커밋 메시지 기준선 668, **+31**).
- **경로 탈출을 인코딩 7종에 대해 ASGI 레이어에서 닫힘 확인**했고, `/index.html`은 계속 서빙된다.
- 라우트 커버리지 테스트가 FastAPI 앱을 **걸어 다니며** 모든 `/admin` 라우트가 `ADMIN_GATES`의 둘 중 하나로
  해석되는지 단언한다 — **나중에 추가되는 관리자 라우트는 무방비로 배포되는 대신 스위트를 실패시킨다.**

  ```python
  # server/admin_auth.py
  ADMIN_GATES = (require_admin_token, require_admin_token_strict)
  ```

기록해 둘 숫자 하나. **직전 커밋 `512dca7`은 스위트를 630으로 보고했는데 이 커밋은 기준선을 668로 적었다.**
둘 사이에 다른 커밋은 없다. 두 보고의 측정 시점·범위가 같지 않았다는 뜻이며, 어느 쪽이 틀렸는지는 여기서 판정하지 않는다 —
**커밋 메시지의 스위트 숫자를 커밋 간 델타 계산에 그대로 쓸 수 없다는 사실만 남긴다.**

## 아키텍처 영향

- 시스템에 **인증 경계가 처음 생겼다.** 그 경계는 `/admin/*`와 `/internal/events/*`이며,
  단일 공유 비밀 하나로 정의된다. 사람 단위 신원도 세션도 없다 — **의도된 범위다.**
- **미설정이 곧 열림이 아니다.** 게이트는 두 상태를 갖고, `require_admin_token`(미설정 시 통과)과
  `require_admin_token_strict`(미설정 시 503)의 구분이 그 계약이다.
- **거부의 출처가 상태 코드가 아니라 헤더로 식별된다.** `WWW-Authenticate: X-Admin-Token`이 붙은 403만이
  게이트가 낸 것이다. 같은 상태 코드를 자기 이유로 내는 핸들러(격리 가드)와 섞이지 않는다.
- 정적 핸들러가 **해석 후 격납 검사**를 한다. 이 저장소에서 그 검사의 정본은 `_resolve_admin_script_path`이고,
  정적 경로가 그것을 재사용한다.

## 그때 남아 있던 것

- **런처(`run_decoupled_app.py`)와 `SERVER_STARTUP_GUIDE`가 바인드 주소를 다르게 말한다.**
  관측으로 실제 노출은 확인됐지만 **둘의 불일치는 그대로다.**
- **데이터 변경 표면은 게이트 밖이다.** `/tables/**`의 POST/PUT/DELETE, `/map-presets`, `/graph/trace`,
  그리고 `@app.websocket("/ws")`는 이 커밋에서 인증이 붙지 않았다. **경계는 `/admin/*`와 `/internal/events/*`까지다.**
- **재기동 전에는 게이트가 걸려 있지 않다.** 이 커밋 시점에 서버는 새 빌드로 재기동되지 않았다.
- **토큰은 하나뿐이라 누가 무엇을 했는지 구분하지 못한다.** 감사 행의 행위자는 여전히 `X-User` 헤더가 말하는 값이고,
  그 값은 토큰과 무관하게 클라이언트가 정한다.
- **클라이언트는 토큰을 `localStorage`에 평문으로 보관한다**(`assy.adminToken`). 공유 PC에서는 다음 사용자가 읽는다.
- **`ASSY_ADMIN_TOKEN`이 실제 운영 환경에 설정됐는지는 이 커밋이 알 수 없다.** 코드와 절차는 준비됐고,
  설정 여부는 시작 배너가 보고한다.
