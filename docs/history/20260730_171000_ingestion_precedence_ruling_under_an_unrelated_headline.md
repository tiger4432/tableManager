# 사용자 판정이 남의 제목 밑에 실렸다 — 그리고 「빠른 경로가 자기 비용을 말한다」

> **일자:** 2026-07-30 오후 | **관련 커밋:** `a5eb934` (한 커밋에 두 항목) · 보드 근거 `docs/process/PROJECT_STATUS.md` F7 행 | **담당:** server-pm(구현) · 총괄(판정 전달)
> **대상:** `server/parsers/advanced_ingester.py` · `server/value_suggest.py` · `server/scripts/setup_db_performance.py` · `server/tests/test_filename_rules_declaration.py` · `server/tests/test_value_suggest.py` · `docs/guide/config/suggest_config.md`
> **스위트:** 이 커밋이 손댄 세 테스트 파일을 HEAD(`8cf9455`)에서 재실행 — `test_value_suggest.py` + `test_filename_rules_declaration.py` + `test_admin_auth.py` **240 passed**. 커밋 메시지는 전체 스위트 총계를 남기지 않았다.

## 이 항목이 먼저 기록하는 것: 제목과 내용이 갈렸다

커밋 제목은 **전부 제안 인덱스(F7) 이야기**다. 그런데 본문의 앞 절반은
**인제션 우선순위 판정**이다 — 같은 컬럼이 `header_rules`와 `filename_rules` 양쪽에
선언됐을 때 어느 쪽이 이기는가에 대한 **사용자 판정**이고, 인덱스와는 아무 관계가 없다.

그래서 이 저장소에서 「사용자가 병합 순서를 뒤집은 날」을 찾으려는 사람은
`git log --oneline`에서 그것을 볼 수 없다. `feat(suggest)`를 열어야 나온다.
**히스토리가 이 항목을 따로 기록하는 이유가 그것이다** — 제목만으로는 닿지 못한다.

같은 계급이 하루 안에 두 번 더 관측됐다(둘 다 총괄 자신의 것):
`8a7e080`이 *"1ⓗ는 `7873070`이 아니라 `ae2811c`"*를 적었고,
`9c95303`은 **일부러 빈 커밋**으로 「내 변경이 남의 커밋 메시지 밑에 실렸다」를 적었다.

## 판정: 병합 순서가 `header < filename < row` → `filename < header < row`

근거는 사용자가 준 것 그대로다 — **파일 안에 적힌 값은 그 파일이 스스로 주장하는 것이고,
폴더명은 파일을 옮기면 바뀌는 외부 맥락이다.** 「파일이 정본」이 헤더까지 확장되고,
헤더와 경로 사이에서는 경로가 약한 주장이 된다.

```python
# 종전:  merged = {**header_metadata, **filename_data, **row_data}
merged = {**filename_data, **header_metadata, **row_data}
```

### 뒤집기가 **새로 만들 뻔했던** 결함

`extract_header_metadata`는 헤더 규칙의 캐스팅이 실패하면 그 컬럼에 **`None`을 저장한다.**
새 순서에서 그 `None`은 경로 값 **위에** 앉는다. 즉 헤더 규칙의 `type:` 하나가 잘못돼 있으면
**멀쩡한 경로 값이 조용히 지워진다.** 뒤집기 자체가 만드는 손실이었고, fill 패스를
**내림차순 우선순위로** 다시 읽어서 막았다.

```python
# 값을 실제로 나르는 가장 강한 원천이 fill도 이긴다 — 아니면 fill이 위 순서와 모순된다.
fill = header_metadata.get(col)
if fill is None:
    fill = filename_data.get(col)
```

### 세는 대상이 뒤집혔다: `path_overrides_header` → `path_value_discarded`

헤더가 이기는 것은 이제 **판정 그 자체**이므로 경고할 일이 아니다(로그도 WARNING → INFO).
운영자가 볼 수 없는 것은 그 반대편이다 — **자기가 선언한 폴더 규칙이 값을 만들었는데
아무 효과가 없었다**는 사실. 그래서 세는 것은 **폐기**다.

```python
if col in filename_data and header_metadata.get(col) is not None \
        and filename_data[col] != header_metadata[col]:
```

`is not None`이 하중을 받는다. 캐스팅 실패로 헤더가 `None`이면 위 fill 패스가
**경로 값을 살려 두므로**, 거기서 폐기를 기록하면 **일어나지 않은 손실을 보고하게 된다.**
변이 3건이 각 절반을 독립적으로 고정한다 — 병합 순서를 변이시켜도 fill 테스트는 죽지 않고
그 반대도 마찬가지다.

## F7: 「느린 성공」이라는 계급

F7의 인스턴스는 작았다. 임계(`index_min_rows`)를 넘긴 테이블 중 인덱스가 빠진 것은
`wafer_process` 하나뿐이었고, 나머지 다섯은 이미 전부 인덱싱돼 있었다. 인덱스 14개,
약 2.4 MB, INVALID 0건. 실측 `end_time` 302.5 → 21.6 ms, `wafer_id` 236.4 → 22.7 ms.

**총괄이 지목한 컬럼은 최악이 아니었다.** `knobs`는 247 ms에 `truncated: false`로 답했다 —
**완전하고, 느리고, 아무 말도 하지 않는** 응답이었다. 그것이 계급이다.

계급 쪽 수리: 성공 경로가 **언제나** `elapsed_ms`를 나르고, 임계를 넘으면 `slow_reason`이
**타임아웃 경로가 쓰던 바로 그 인덱스 조언을 재사용**한다. 그 조언이 종전에 느린 성공에서
도달 불가였던 이유는 배선이 아니라 **문장이었다** — 모든 문장이 "조회 시간 초과"로 시작했고,
그것은 답이 도착한 요청에 대해 거짓이다. **프레이밍이 진단을 실패 경로에 가둬 놓고 있었다.**

### 라운드 안에서 잡힌 측정 오류 둘 — 수리보다 이쪽이 더 남는다

1. **첫 임계 50 ms는 p95를 「건강한 상한」으로 오인해 나온 값이었다.** 19.9 ms라는 상한은
   21회 반복에서 최대 148 ms까지 갔고, 50 ms는 **정상적으로 인덱싱된 컬럼 두 개에서 발화했다.**
   두 분포는 꼬리에서 겹치고 **단일 지연 임계로는 분리되지 않는다.** 그래서 기본값은
   200 ms — 건강한 표본 전부보다 위이고, 망가진 14개 중 6개를 여전히 잡는다. 수리가
   테이블 단위로 한 번에 이루어지므로 그 정도면 충분하다는 근거였다. `slow_reason`은
   **거친 경보**로, `elapsed_ms`는 **정밀 채널**로 문서화됐다.
2. **`time.monotonic()`이 이 플랫폼에서 15.625 ms로 분해된다.** 이 필드가 존재하는 유일한
   비교에 약 31%의 양자화 잡음을 얹는다. `elapsed_ms`만 `perf_counter`로 옮기고
   데드라인은 **일부러 `monotonic`에 남겼다** — 1500 ms 예산에 15 ms 거칠기는 1%다.

### 계획 형태 검사기 — 그리고 「초록만 본 검사기는 미검증이다」

`classify_seek_plan`은 노드 타입을 절대 읽지 않고 `Index Cond`를 `Rows Removed by Filter`와
대조해 세 가지 판정을 낸다. 기존 검사에 구멍이 있던 게 아니라 **계획 형태 검사 자체가
존재하지 않았다.** 두 가지가 기록할 값이 있다.

- **`Filter:` 줄은 결함이 아니다.** 건강한 계획에도 있고 0행을 버린다. "Filter가 있으면
  기각"이라는 순진한 규칙은 **건강한 컬럼 전부를 떨어뜨린다.**
- **검증기는 엔드포인트가 실제로 발행하는 문장을 설명한다** — `text_seek_query`로 추출해
  공유한다. 질의를 재조립하는 검증기는 **아무도 돌리지 않는 질의**를 검사하고, 그 표류는
  눈에 보이지 않는다.

라이브 DB에서 `SET LOCAL enable_indexscan = off`로 **양방향 실증**했다: 인덱스 on → `ok`,
버린 행 0; off → `no_index_cond` + `filter_discards`, `bonding_map`에서 548,978행 폐기.

그 검증기의 **첫 실행**은 "33/33 range-shaped, 15 skipped"를 보고했고 그것은 전수 커버리지처럼
읽힌다. 건너뛴 것 중 하나가 `graph_nodes.identity_key` — **실재하는 두 번째 소비자**였고,
조회가 `DYNAMIC_TABLES`만 걸었기 때문에 빠졌다. 이제 skip은 사유별로 항목화되고
**스캔 0건은 실패로 보고된다.** *그 문장 구조가 F7 결함 자체와 같은 모양이다 —
완전해 보이는 답이 완전하지 않았다.*

## 그때 남아 있던 것

- **`_stop_reason`은 기제를 그대로 두고 docstring만 정직해졌다.** 경계를 씌우려면 프로브
  ~21회마다 `statement_timeout`을 다시 세팅해야 하고, 그것은 왕복 1회씩을 **모든 건강한
  요청에 세금으로** 물려 이미 열화된 상태에서만 발생하는 최악을 조인다. 실제 상한은
  `2 × timeout_ms`이고 docstring이 그렇게 적는다.
- **`perf_counter` 선택을 설명하는 주석이 폐기된 임계를 인용한 채 남았다.** HEAD의
  `server/value_suggest.py`에서 그 주석은 *"a MEASUREMENT compared against a 50 ms threshold"*
  와 *"a 60 ms answer could report 48"*을 말하지만, 같은 파일의 기본값은
  `"slow_warn_ms": 200`이다. 라운드 도중 임계가 50 → 200으로 바뀌면서 근거 문장이
  따라가지 못한 자리다. 양자화 논지 자체는 유효하고 숫자만 옛 임계의 것이다.
