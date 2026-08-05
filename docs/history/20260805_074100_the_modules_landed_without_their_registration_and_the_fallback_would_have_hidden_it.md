# 모듈이 등록 없이 착지했다 — 그리고 폴백이 그것을 가려 줬을 것이다

> **커밋:** `580387c` (2026-08-05 07:41) | **일자:** 2026-08-05 아침
> **선행:** [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9`, **1분 전** — 이 커밋이 메우는 누락을 만든 커밋)
> **담당:** server 구현
> **대상:** `server/main.py`(**+149**, 삭제 0) ― **1파일, 전량 추가**
> **스위트:** 커밋 메시지에 결과 없음.

## 배경 — 새 checkout에서는 엔드포인트가 존재하지 않았다

`cab8ed9`가 서버 모듈 둘을 착지시키면서 **라우트 등록을 같이 내지 않았다.**
그래서 새로 clone한 트리에서는 Map Editor 2가 캡처된 페이로드로 폴백하고,
**왜 그런지는 아무것도 말하지 않았을 것이다** — 폴백은 상태 코드가 없는 fetch
오류에서만 열리는데, 라우트가 없으면 404가 나서 다시 던져지고 화면에 이름이
뜬다는 것이 `cab8ed9`의 설계였다. 즉 **가장 잘 풀려도 화면에 라우트 이름이 뜨고,
안 풀리면 캡처가 라이브 행세를 한다.**

## 결정 단위의 소유권을 여기에 하드코딩하지 않는다

GET이 파라미터를 **규칙 자신의 `decision_key`**에 대고 검증한다.

```python
        allowed = set(decl.get("decision_key", []))
        invalid = sorted(k for k in parsed.keys() if k not in allowed)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"'params' keys must be decision_key columns only; invalid: {invalid}")
```

> **결정 단위가 무엇인가는 `enrichment_rules.json`이 소유한다.** 라우트가 컬럼
> 이름을 알고 있으면 소유자가 둘이 된다.

## 쓰기는 하나이고, 그 하나에는 GET 쌍둥이가 없다

```python
@app.get("/api/maps/alignment/view")
def get_map_alignment_view(rule: str, map_table: str, params: str = None,
                           reference: str = None, include_cells: bool = True, ...)

@app.post("/api/maps/alignment/confirm")
def confirm_map_alignment(payload: dict = Body(...), db: Session = Depends(get_db)):
```

POST는 `rule` 누락 · `decision_key`가 dict가 아님 · 미선언 키 · `frames`가 dict가
아님 · `sources`가 list가 아님 · `confirmed_by` 공백에 **400**, 모르는 규칙에
**404**를 낸다.

## 그때 남아 있던 것

- **API는 이제 존재하지만 페이지는 아니다.** `map_editor2.html`을 서빙하는
  라우트는 22분 뒤 `39b43ab`까지 없다 — [`20260805_080300`](./20260805_080300_a_built_artifact_is_not_a_reachable_one.md) 참조.
- 「모듈을 냈는데 배선을 안 냈다」는 이 라운드에서 **세 번 반복된다** — 여기서
  서버 라우트, 이어서 페이지 라우트, 그리고 오후에 클라가 서버 제안을 안 읽는
  형태로.
