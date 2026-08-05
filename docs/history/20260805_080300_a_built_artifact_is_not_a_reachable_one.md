# 빌드된 산출물과 닿을 수 있는 산출물은 다르다 — 그리고 바깥에서 보면 두 실패가 똑같이 생겼다

> **커밋:** `39b43ab` (2026-08-05 08:03) | **일자:** 2026-08-05 아침
> **선행:** [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9`) · [`20260805_074100`](./20260805_074100_the_modules_landed_without_their_registration_and_the_fallback_would_have_hidden_it.md)(`580387c` — 같은 계급의 누락을 22분 전에 닫은 커밋)
> **담당:** server 구현
> **대상:** `server/main.py`(**+26**, 삭제 0) ― **1파일, 전량 추가**
> **스위트:** 커밋 메시지에 결과 없음.

## 배경 — 번들도 있고 API도 등록됐는데 페이지가 404였다

`cab77e7`이 `dist`에 번들을 냈고 `580387c`가 API 라우트를 등록했다. 그런데 이
서버는 **페이지를 페이지별 명시 라우트로 서빙한다**, 그리고 Map Editor 2에는
그것이 없었다. 열면 **404**.

> **빌드된 산출물과 닿을 수 있는 산출물은 다르다. 그리고 바깥에서 보면 두 실패는
> 똑같이 생겼다 — 아무것도 안 뜬다.**

이 라운드에서 「냈는데 배선을 안 했다」가 **연속 두 번**이다. 앞의 것은 API
등록(`580387c`), 이번은 페이지 라우트다.

## 수리

레거시 맵 에디터 페이지 라우트 바로 뒤, `if os.path.exists(client2_dist_path):`
블록 **안에** 들어간다.

```python
@app.get("/map-editor2")
@app.get("/map_editor2.html")
def serve_map_editor2_page():
```

본문은 `no-store`/`no-cache`/`Pragma`/`Expires` 헤더 · `dist`의
`map_editor2.html`에 대한 `FileResponse` · 개발용 폴백(`../client2/map_editor2.html`) ·
그것도 없으면 `404 "Map Editor 2 page not found. Please build frontend first."`다.

**레거시 `/map_editor.html`은 이 diff에서 손대지 않았다** — 유효 다이 저작과
오버레이는 계속 거기서 돈다.

## 그때 남아 있던 것

- 두 실패가 같은 모양이라는 것이 이 커밋의 값이다. 이 시점 화면에서 페이지가
  안 뜨는 이유는 **최소 셋**이었다 — 번들 없음 · 페이지 라우트 없음 · API 라우트
  없음. 셋 다 서로 다른 커밋에서 닫혔다.
