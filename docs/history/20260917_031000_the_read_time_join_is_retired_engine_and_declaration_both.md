# 읽기 시점 조인이 은퇴했다 — 엔진도 선언도, 그리고 «통째로»

> **커밋:** `306419fd`(은퇴 4/5 · 판정 461) — 구현자
> **일자:** 2026-09-17 (03:10)
> **레인:** 구현자 · 검수는 응용(Q-41)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **이 항목의 앵커는 blob 에서 다시 쟀다**

## 무엇이 일어났나

`server/virtual_join/` 패키지가 **사라졌다.** 읽기 시점 조인 — 「값을 저장하지 않고 조회
응답에서 채우는」 — 이 엔진과 선언 양쪽에서 은퇴했다.

```
server/virtual_join/executor.py   최상위 정의 «28»
   15 이동  -> server/chain/legacy_materialized_join.py   (372줄, «쓰기 닫힘»)
   13 삭제  -> attach · exposed_columns · resolved_expression · announced_columns ·
              resolved_column_announcements · virtual_only_columns · _resolve_one ·
              _bind_crud · _CLEAN · _RENDER · KIND_COLLIDE · KIND_VIRTUAL_ONLY · SOURCE_NAME
    0 신설  -> 옮긴 파일에 «지어낸 것이 없다». 의존 닫힘이지 재작성이 아니다
git mv  virtual_join/config.py  -> chain/legacy_join_declaration.py   (905줄)
git mv  virtual_join/refusal.py -> chain/join_refusal.py              (79줄)
git rm  virtual_join/executor.py · virtual_join/__init__.py
```

🔴 **왜 «통째로»인가:** 반쪽은 서로를 거짓으로 만든다 — 엔진 없는 읽기 라우트, 또는 아무도
안 부르는 엔진. 둘 중 어느 상태든 «한 답이 이미 틀린» 상태다(상설 ⑤).

## 호출 자리가 «여덟»이었고, 그래서 클래스 하나가 통째로 나갔다

판정은 «일곱»으로 셌는데 둘이 한 클래스 안에 있었다. 여덟이 다 사라지자
`VirtualColumnBinder` 에 «넣을 것이 있는 호출자»가 하나도 안 남았다 — 라우트가 받을 수 있는
이름은 이제 전부 «저장된 컬럼»이다. 그래서 그 클래스와 파라미터가 `resolve_sort` ·
`apply_column_filters` · `apply_search_filter` · `narrowed_table_query`(3-튜플이 2-튜플로)와
그 네 호출자에서 빠졌다.

📌 **「항상 비어 있는 바인더는 «작아진 기능»이 아니라 «아무도 안 타는 갈래»다.」**

## 446 이 여기서 착지했다 — 그리고 «좁게»

```
materialize: false   -> 읽기 시점 조인이었다. 돌릴 엔진이 없으니 «이름 대고» 거절한다
                       (`chain/join_refusal.py` :32 CODE_READ_TIME_RETIRED ·
                        문장을 내는 자리 `legacy_join_declaration.py` :629)
                       거절문이 «나갈 길 둘»을 말한다 — chain_rules.json 으로 옮기거나,
                       materialize: true + max_rewrite_rows 상한
materialize: true    -> «안 건드렸다». 그리고 그것을 «대조 시험»이 말한다
```
🔴 이 「좁게」가 응용 Q-30 이 열어 판정 452 가 «강제 조건»으로 박은 자리다 — 파일째 거절하면
**도는 쓰기 조인**을 같이 죽였을 것이다.

## ⚠️ 계획에 없던 결과 하나 — 그리고 RUN.md 에 실렸다

인덱스는 «그것을 요구하는 조인만큼» 산다(S-248). 거절이 요구 집합을 줄이므로 제품이 그
선언들의 `uq_vjoin_*` 인덱스를 **스스로 회수한다.** 설계대로 도는 것이지만 **운영자에게
보이고**, 중복이 들어올 창을 넓힌다. 그래서 RUN.md 가 그 로그 줄 · 되돌리는 법(`materialize:
true` 로 선언하면 제품이 다시 세운다) · 손으로 만든 인덱스는 «접두어가 달라» 안 건드린다는
것을 같이 싣는다.

## 시험 — «파일»이 아니라 «시험»으로 갈랐다

```
모듈 8 삭제(시험 정의 112)   주제가 읽기 시점 조인이던 것
그중 시험 5 를 «먼저 꺼내»    두 파일로: 쓰기 코어가 «선언 안 된 컬럼»을 떨어뜨린다 +
                           그 깔때기의 호출자가 하나 · 인리치가 여전히 부르는 렌더 깔때기
계약 벡터 3 은퇴(묘비)       `_resolve_one` 과 `resolved_expression` 을 견주던 것 —
                           계약은 «어긋날 수 있는 구현 둘»이 있어야 성립한다
```

## ⚠️ 응용이 남긴 것 (Q-41)

```
✅ 확인   패키지 추적 파일 0 · 비시험 importer 0 · 계기 은퇴 · main.py 의 운영자 422 본문 둘 수정 ·
         config_resolve_report 재바인딩 · SOURCE_NAME 은 «생산자»뿐이라 판정 447 ② 에 어긋나지 않음
🔴 남음   `chain/builtins.py:390` 「`builtin:join` is the READ-TIME join and production runs on it」
         — 그 종류는 이 커밋이 지웠고, 뒷절은 446 으로 이미 거짓이었다.
         판정 453 → Q-40 → 판정 468 이 «이름으로» 인수 목록에 올렸는데 착지에 «안 들어왔다»
🔴 남음   `config_resolve_report.py:600` 이 로더를 `virtual_join_config` 라 부른다 — «두 세대 전» 철자
```
