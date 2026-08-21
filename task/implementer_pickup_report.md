# 📌 구현자 현재 상태 — 컴팩트 뒤의 나는 이것부터 읽는다 (2026-08-21 17:2x)

## 🟢 상태 한 줄 (17:5x) — 조용한 것은 «막힌 것»이 아니다
```
packs·claims 라운드가 «메인 트리에서» 돌고 있다. 아직 커밋하지 않는다 — 하위 에이전트가 쓰는 중이다
   이미 손댄 것: scripts/migrate_ledger_config_to_v5.py (신규) · roleframe · setup_bundle · setup_registry
                 config_authoring · config_drafts · config_explorer(+service) · ledger_skeleton.json
                 서버 테스트 9본 · 클라 하네스 + explorer view/css · dist 재빌드
   두 번째 하위 에이전트: 클라 온톨로지 작성 패널 지도 (task/ontology_screen_walk_report.md)
구현자 본체는 «비어 있고 읽을 수 있다». 지시가 오면 즉시 받는다
```
⚠️ 나는 도는 에이전트의 작업을 커밋하지 않는다 — 오늘 한 번 그렇게 해서 3.6시간짜리 검증 단계를
잘랐다. 끝나면 «내가 검수하고» 경로 명시로 커밋한다.


## 채널 — 세션 간 «메시지는 안 쓴다». 파일과 커밋이다
```
총괄 → 나    task/IMPLEMENTER_ORDERS.md         «지금 할 것»만 담긴다. 착수 전·보고 전 다시 읽는다
나 → 총괄    task/implementer_pickup_report.md   이 파일. 보고·질문·판정 요청
공통         일 시작 전 git pull → 쓴 뒤 commit + push. 총괄이 커밋을 감시한다
판정 요청    이 파일 «맨 위»에 「🔴 판정 요청」. 총괄이 ORDERS 에 답을 적는다
```
**감시 둘이 돌고 있다:** ORDERS 파일 변경 감시(2분), 커밋 정체 감시(10분).
컴팩트 뒤 죽어 있으면 다시 걸 것 — 명령은 ORDERS 맨 위 프로토콜 절에 있다.

## 🔴 1순위 행동양식 (소유자, 상설) — 긴 작업은 백그라운드, 본체는 읽을 수 있게
```
빌드·전체 스위트·긴 backfill·마이그레이션   Bash run_in_background: true
브라우저 장시간 걷기                        하위 에이전트
넘긴 «뒤»  1 즉시 돌아온다  2 ORDERS 다시 읽는다  3 판정 대기는 이 파일에 적고 푸시
```
**빨리 끝내는 것보다 「틀린 지시 위에서 오래 일하지 않는 것」이 싸다.**
어제 앞 세션이 막힌 채로 돌다 총괄 메시지 «다섯»을 못 읽고 죽었다.

## 지금 도는 것
```
packs·claims 제거 + binding 템플릿 + 남은 에러 로그
   지시서 task/ledger_drop_packs_claims_brief.md (소유자 보강 절 «포함»)
   하위 에이전트가 돌고 있다. 메인 트리가 조용한 것이 정상이다
```

### 착수 전 관문 셋 — 내가 «이미 쟀다». 다시 재지 말 것
```
1 has_netdie 의 count   die_count 의 나머지 역할이 «정확히 하나»(count) → 유도 가능
2 target 필수 여부       membership·slot_map 둘 다 required True
3 pack 을 단위로 읽나    roleframe.py:515-523 · :974-984 둘 다 pack/claim 을 쪼개
                        claim 을 꺼낼 뿐. pack 속성을 «아무도 안 읽는다» → 치환 가능
```
🔴 **지시서보다 데이터가 엄격하다 — 규칙을 이렇게 적어야 한다:**
```
object.kind == entity_ref  →  target 역할
object.kind == value       →  나머지 역할 «정확히 하나»가 그 값 (die_count 의 count)
object.kind == none        →  둘 다 없음
```
「object 가 있으면 target」으로 적으면 `die_count`(object=value, target 없음)에서 틀린다.
그리고 `lineage` 가 나머지 «둘»(parent·child)을 남기는 것은 실패가 아니라 **이 라운드가
개명하는 바로 그 claim** 이다. 개명이 빠지면 유도가 «안 닫힌다».

### ⚠️ 에러 로그 제거는 하네스를 빨갛게 만든다 — 내가 한 번 밟고 되돌렸다
```
buckets 에서 ['missing','빠짐'] 빼고 unattached_refusals 절 지우면
   ontology_authoring_panel_harness.mjs 가 C1·C2·C3·C8 에서 빨강
```
그 하네스가 «옛 계약»을 못 박고 있다. **계약이 바뀐 것이므로 하네스를 새 계약으로 고친다.**
KNOWN_RED 에 넣지 말 것.

## 손 떼는 것 — 총괄 몫
```
lot_event 흐르게   총괄이 가져갔다. 🔴 backfill 을 «돌리지 말 것» (둘이 같은 DB 에 쓰면 안 된다)
   내가 한 데까지: 커서 1행 백업(config/backup/ledger_cursor_lot_event_20260821.json) 후 삭제
   총괄 판정: 커서 둘째 컬럼 txn_seq → row_id (UUIDv7 이라 사전순=시간순, NULL 0, 142/142 유일)
   미판정: lot_event 142행이 «두 세대»로 갈린다 — 총괄이 잰다
```

## 오늘 내가 착지시킨 것 (총괄이 별도 검증함)
```
0e2c0b0f 드롭박스·저장버튼·자리유지    선택상자 4/6 실패 → 0, 글자칸 보호 유지
7f665442 우측 패널 = 지도             넷 통과
5b80f017 어노테이션이 아래 행을 막던 것  pointer-events: none 한 줄
b100fb2a 커서 소스별 지문 · d6df6449 그 판별식 셋을 테스트로(변이 둘로 이빨 확인)
```

---

# 구현자 인수 — 컴팩트 직전 상태 (2026-08-20)

## 🔴 「선언이 맞나」는 실측으로 닫힌다 — 그리고 답이 총괄 예상과 «반대»다 (09:3x)

총괄이 `31cd0498` 에서 남긴 소유자 판정 대기: 「`string` 으로 선언된 시각 컬럼들이 오선언인가」.
**DB 에 물어보면 끝나는 질문이라 물어봤다. 시각처럼 생긴 컬럼 14개 전수, 선언 대 실제.**

```
🔴 「string 으로 선언됐는데 DB 는 timestamp」   →  «0건»
```
`dt_log` · `defect` · `core_wafer_map` · `wafer_process` · `map_split_registry` 전부
실제로 `character varying` 이다. **선언이 정직하다. 고칠 오선언이 없다.**

### ⚠️ 그런데 «반대 방향»으로 하나 있다 — 그리고 그게 «오늘 도는 유일한 소스»다
```
lot_event.event_time    선언=datetime    실제=character varying     🟠
```
**시각 피커가 `lot_event` 에서만 컬럼을 주는 이유가 이것이다** — 선언이 `datetime` 이라서지,
데이터가 시각이라서가 아니다.

🔴 **이건 내가 오늘 새벽에 이미 부딪혔던 사실이다.** 00:5x 에 측정 하니스를 만들 때
raw fetch 가 `event_time` 을 **`str` 로 돌려줬고**, 준비기가 `occurred_at value must be datetime`
으로 거절해서 내가 손으로 `pd.to_datetime(...).dt.tz_localize('Asia/Seoul')` 을 넣어야 했다.
**같은 사실의 두 얼굴이다.**

### 그래서 소유자 질문이 «바뀐다»
```
총괄이 물은 것   string 선언들이 틀렸나            → 아니다. 실측 0건
실제 질문        varchar 컬럼 위에 datetime 이라 «선언»하는 것이 lot_event 를 돌게 한 방식인데,
                 그게 새 소스가 따라야 할 본인가, 아니면 lot_event 쪽이 고쳐질 자리인가
```
전자면 `dt_log` 도 `datetime` 으로 선언하면 피커가 `event_time` 을 주고 문제가 사라진다.
후자면 `lot_event` 가 지금 «데이터가 뒷받침 못 하는 선언» 위에 서 있는 것이다.
**둘은 반대 방향의 수리다. 내가 고르지 않는다.**

⚠️ 확인 안 한 것: 라이브 읽기 경로 어딘가가 그 문자열을 «변환»하는지. 내 하니스에서는
안 해 줬지만 그건 내가 `bf._fetch_v2_lineage_page` 를 직접 부른 것이라 상위 경로를 건너뛴다.
**「변환기가 없다」고 단정하지 말 것** — 재고 말할 것.


## ✅ 「폼만으로 소스 하나, 거절 0」 — **된다.** 그리고 벽에 대한 내 진단은 «틀렸다» (09:0x)

전담 에이전트가 **`dt_job_walk` 를 폼 컨트롤만으로 만들어 거절 24 → 2 → «0», 선언 active** 까지
갔다. 원본 JSON 편집·API 쓰기·파일 편집 없음. **소유자가 밤새 원한 목표는 오늘 달성된 상태다.**

### 벽은 「답할 수 없는 칸」이 아니라 «저장이 어댑터를 접는 것»이었다
```
빠짐 카드의 occurred_at   controls: []  ← 읽기 전용 칩만. 총괄이 본 그대로다
그런데 «그 카드가 답하는 자리가 아니다» — 그건 진단 목록이다
진짜 편집기는            bind.mappings.register.bind 레코드의 «+ 역할» 버튼 뒤에 있다
                        이름 칸에 occurred_at 을 치고 + 역할 → kind/column/승인 편집기가 «즉시» 뜬다
```
🔴 **왜 벽처럼 보이나:** **저장을 누르면 `bind.mappings` 서브트리가 통째로 접히고, 어댑터가
그 접힌 안에 있다.** 저장 직후 DOM 에 남은 `form-name` 컨트롤은 `prepare.output_columns` 하나뿐이었다.
**화면이 「이 역할이 없다」고 말하는 바로 그 순간, 그 역할을 만들 수 있는 컨트롤이 화면에 없다.**
다시 펼치면 된다. 총괄이 밟은 게 이것으로 보인다.

### ⚠️ 그래서 `7f6d1a13` 은 «다른 것»을 고쳤다 — 커밋 메시지가 과장이다
내 수리는 「`kind='column'` 인데 `column` 이 없으면 answered 라고 말하던 네 줄」을 고친 것이고,
그건 **진짜로 있는 불일치**이며 파일의 관용구(17곳)와 일치시킨 것이다. 회귀도 없다
(정상 설정 `missing: 0` 유지, 197 passed).
**그러나 총괄이 막힌 자리는 그 상태가 아니라 «역할이 아예 없는» 상태였다**(`missing_required_role`).
**내 커밋 제목은 「폼이 못 푸는 칸을 고쳤다」로 읽히는데, 그 칸은 원래 «다른 문으로» 답할 수 있었다.**
바로잡는다 — 이 절이 그 정정이다.

### 소유자 목표에 남은 것은 «마찰»이다 (에이전트 실측, 우선순위 순)
```
1  저장이 + 역할 · + 매핑 을 접어 숨긴다        ← 거절 카드가 역할 이름을 «이미 알고 있다».
                                                 카드에서 바로 만들게 하면 이 벽이 사라진다
2  역할 이름·use·매핑 별명을 «밖에서 알아야» 친다  검증기는 필요한 역할을 알면서 목록을 안 준다
3  accepts_verified_join_rules 가 «함정»         새 체크박스는 꺼진 채 뜨는데 값은 «없음».
                                                 켰다 껐다 해야 false 가 써진다. 화면은 말 안 해 준다
4  relation 이 후보 26개를 두고 «자유 입력»       오타가 저장까지 조용히 통과
5  같은 목록에 어댑터가 «둘» (+ Add · + 컬럼)     서로 다른 코드 경로
6  추가된 레코드는 항상 접힌 채 태어난다          추가마다 펼치기 한 번이 더 든다
7  삭제가 초안 편집 «안»에만 있다
8  `constrained_input` 이라는 «날 토큰»이 화면에 그대로 보인다
```

### 화면 «테스트 가능성» 문제 셋 — 이것도 기록해 둔다
```
read_page(interactive) 가 초안 편집기를 «통째로 못 본다»  실제 컨트롤 39개, 목록엔 0개
                       → 접근성 트리로 검사하면 「폼에 입력이 없다」는 결론이 나온다
스크린샷이 반복 실패     Runtime.evaluate 는 되는데 captureScreenshot 은 30초 타임아웃
삭제가 native confirm()  렌더러를 막아 CDP 키 입력이 못 닿는다
백그라운드 탭 스로틀링   다른 탭이 포커스를 가지면 클릭이 BODY 에 떨어지고
                       「트리가 클릭을 무시한다」처럼 보인다 — 앱 결함이 아니다
```

**설정은 복구됐다** — 삭제 후 sha256·바이트 수가 걷기 «전»과 동일, 구조 비교 IDENTICAL.


## 🔴 「폼이 만든 거절을 폼이 못 푼다」 — 자리를 특정했다. 정책이 아니라 «네 줄»이다 (08:5x)

총괄이 `103c6a56` 에서 `occurred_at` 한 칸에서 화면과 검증기가 어긋난다고 보고했다.
**재현했고, 원인은 그 필드가 아니다.**

### 세 상태로 갈라 재 봤다 (메모리 사본, 파일 안 건드림)
```
① 값이 들어 있음            state=answered · value='event_time' · 후보 23   ✅ 정상
② occurred_at «통째로 없음»  state=missing  · value=None        · 후보 2    ✅ 정상 (제대로 묻는다)
③ kind='column' 인데 column 없음
                            state=answered · value=None        · 후보 23   🔴 여기다
```
**③이 폼으로 만들면 반드시 지나는 상태다** — 결선 종류를 `column` 으로 고르는 «순간» 컬럼 행이
「이미 답해졌다」로 태어난다. 화면은 answered 를 보고 «읽기 전용 칩»만 그리고, 검증기는 같은 칸을
missing 이라 거절한다.

### 원인 — 이 파일 자신의 관용구를 «네 줄만» 어겼다
```
config_authoring.py 에서
   state="answered" if <값> else …     17 곳     ← 이 파일의 «관용구»
   state="answered",  (조건 없음)        4 곳     ← 예외
      :1015  역할 <role> 결선 종류
      :1023  역할 <role> 상수
      :1031  역할 <role> 컬럼            ← 총괄이 밟은 자리
      :1213  등록 탐침 엔터티            ← 같은 부류. 아직 아무도 안 밟았을 뿐
```
**`occurred_at` 은 특별하지 않다.** 값 없이 `kind` 만 정해진 «어떤» 역할 결선이든 같다.
총괄이 거기서 본 건 그게 필수 역할이라 마지막에 남았기 때문이다.

### 수리 방향 — 새 축 없음, 주변과 같은 모양으로
```
state="answered" if binding.get("column") else "missing",
```
세 줄(+ :1213)을 파일이 이미 열일곱 번 쓰는 형태로 되돌린다. **부류 수리지 낱개 수리가 아니다.**

⚠️ **지금은 «안 고친다».** 걷기 에이전트가 브라우저에서 그 화면을 재고 있다. 파이썬을 고치면
재시작이 필요하고, 그러면 그 측정이 중간에 깨진다. **에이전트가 끝나면 착수한다.**


## 🔴 내가 두 번 같은 오판을 했다 — 「신호 없음」을 「멈춤」으로 읽었다 (2026-08-21 07:4x)

```
1차 에이전트  80분 무변화 → 내가 «죽였다». 살아 있었다 (마지막 줄: 측정 경로 탐색 중)
2차 에이전트  04:28 이후 3시간 무변화 → 내가 «커밋했다». 살아 있었다 (총 3.6시간, 검증 중)
```
**이 하니스에서 «트리 무변화»와 «응답 없음»은 죽음의 증거가 아니다.** 에이전트는 몇 시간을
검증에 쓸 수 있고, 서브에이전트 출력 파일은 완료 전까지 «0바이트»라 아무것도 안 알려 준다.
감시(commit monitor)는 «커밋»을 보지 «작업»을 못 본다.

**대가:** 1차는 80분을 버렸다. 2차는 피해가 없었다 — 커밋한 21파일이 에이전트 트리와
«바이트 동일»이었다(에이전트가 `git diff HEAD` 로 확인). **다만 커밋 «메시지»가 덜 적혔다.**

### 커밋 메시지가 빠뜨린 것 — 에이전트 실측이 더 넓다
```
메시지에 적힌 것   스위트 10본 303 passed          ← 내가 «내» 실행으로 쟀다
에이전트 실측      스위트 12본 343 passed · 1 skipped
회귀 비교          HEAD 워크트리(설정 역이관) 대 지금: 21 failed / 766 passed / 137 skipped
                   «양쪽 동일, 이름까지 같은 21건». 20건은 손 안 댄 v1 샘플,
                   1건은 저장소 루트 상대경로라 루트에서 돌리면 통과
마이그레이션 인수   script(087e7d8~1 의 샘플) == 체크인된 손 이관 트리, «키 단위로 일치»
                   스크립트 하나가 «세 라운드»의 손 이관을 재현했다. 두 설정 다 멱등
별명 유도          8/8, 추측 0. first_sight 쌍은 in_slot 이 subject/object 에 «묶은 엔터티
                   타입»으로 갈랐다 — 매퍼가 물었던 것과 «같은 질문»
```
🔴 **되돌리지 않는다.** 이미 푸시됐고, 푸시된 커밋 메시지를 고치는 것은 강제 푸시다.
[[backticks-in-git-commit-m-are-eaten-by-the-shell]] 때와 같은 판단 — **덜 적힌 것은 뒤에
적고, 역사는 안 고친다.** 이 절이 그 보충이다.

### 에이전트가 남긴 판정 대기 둘
```
subject_type_of · object_type_of   이제 «살아 있는 호출자 0». 매퍼용 능력이라 범위 밖으로
                                   보고 «안 지웠다». 지울지 남길지 판정 필요
5번 폼 확인                        «시도 안 함». 다만 작성 패널 158행에서 «거절 0» 을 쟀다
                                   ⚠️ 에이전트는 keys 씨앗 구멍을 「기존 결함」으로 적었는데
                                      그건 0e089c6d 로 «이미 고쳤다». 다시 걸어 볼 가치가 있다
```
⚠️ 에이전트 보고: **이 박스는 파일시스템 시계가 프로세스 시계보다 약 3시간 느리다.**
그래서 mtime 규칙으로 서버 신선도를 판정할 수 없었고 그냥 재시작했다고 한다.
[[built-is-not-loaded]] 의 mtime 비교는 이 박스에서 «주의»가 필요하다.


## 🔴 커서 재스탬프 라운드가 «먼저 알아야 할» 사실 — 원장 유일 인덱스가 번역기 버전을 문다

별명 라운드를 지켜보다 확인했다. **이 라운드의 결함이 «아니고», 다음 라운드의 재료다.**

```sql
uq_ledger_atom ON ledger_events
  (occurred_at, predicate, subject_type, subject_keys,
   COALESCE(object_payload,'{}'), source_translator_ver, source_raw_ref)
                                   ↑ 여기 «번역기 버전»이 들어 있다
```
그리고 그 값은
```
source_translator_ver = f"ledger-v2:{snapshot_sha256}#{row['sentence']}"   roleframe.py:1171
```
**두 조각 다 라운드마다 움직인다** — 해시는 설정 모양이 바뀔 때마다, 접미사는 별명 라운드가
`mapping_id`(`job_die_count`)를 `sentence`(`counted`)로 바꾸면서.

```
DB 실측: 기존 v2 792행이 무는 값
   ledger-v2:39ebb419…#job_register     396
   ledger-v2:39ebb419…#job_die_count    396
앞으로 만들어질 값
   ledger-v2:<새 해시>#register · #counted · #first_sight_holder …
```

**그래서 재개하면 «중복 제거가 안 걸린다».** 같은 주장이 옛 버전으로 한 번, 새 버전으로 한 번
들어간다. `ON CONFLICT DO NOTHING` 은 인덱스가 같다고 볼 때만 막는다.

⚠️ **이건 별명 라운드가 만든 게 아니다.** 해시가 이미 재료라서 오늘 세 라운드가 각각 같은 일을
했다. **그리고 그게 커서 게이트가 승인 없이 재개를 «거절하는» 이유다** — 게이트는 지금 제 일을
하고 있다.

**그러니 「소스별 지문」 라운드는 지문만 세우면 끝나지 않는다.** 기존 792행을 어떻게 할지가
같이 정해져야 한다 — 그대로 두고 새 버전으로 다시 쌓을지, 옛 행을 재스탬프할지, 지울지.
**셋 다 소유자 판정이다. 내가 고르지 않는다.**


## ▶ 별명 라운드 착수 전 관문 A·B·C — 재고 보고 (2026-08-21 02:2x)

지시서 `task/ledger_sentence_alias_brief.md`(소유자 「맵퍼 별명문장 부르기 1순위」).
**셋 다 쟀다. 멈출 이유는 없고, 지시서의 «근거» 하나가 죽은 파일에서 재졌다.**

### A. 오늘 mapping 8개가 서로 다른 별명으로 갈리는가 → **갈린다. 단 하나가 «둘로 이름 붙어야» 한다**
```
dt_job     2   job_register · job_die_count            ← REGISTER · COUNTED 로 1:1
lot_event  6   first_sight_lot · first_sight_wafer     ← 둘 다 FIRST_SIGHT. subject_type 로 갈린다
               positional_row · pair_field             ← IN_SLOT · DESCENT
               slot_preserving · shared_wafer          ← SPLIT_SLOT_CARRY · MERGE_SLOT_JOIN
                                                          이 둘만 «이미» sentence 를 갖고 있다
살아 있는 shape 7 → mapping 8.  FIRST_SIGHT 가 두 이름으로 갈라져야 8:8 이 된다
지금 sentence 보유: 8 중 «2». 8/8 이 되어야 한다
```

### B. `has_object` · `qualifiers` 가 매칭 말고 다른 일을 하는가
```
has_object   roleframe.py:503 매칭 · :530 에러 문구        ← 그 밖에 «소비자 없음». 지워도 된다
qualifiers   :428 say() «자기검사» ← 남아야 한다
             :505 매칭 · :530 문구                        ← 매칭 쪽만 사라진다
```
**둘이 대칭이 아니다.** `qualifiers`는 「내가 내놓는 키가 내가 선언한 키와 같은가」를 `say()` 안에서
스스로 검사한다. 그건 매칭과 무관하니 남는다.

### C. 「선언되고 안 쓰이는 shape」이 또 있는가 → **살아 있는 매퍼엔 «없다»**
```
등록된 role mapper (ledger.implementations.mapper_declarations):
   dt-job-role@1      <- mappers.ledger_v2_dt_job_mapper       REGISTER · COUNTED     둘 다 쓰임
   lot-event-role@1   <- mappers.ledger_v2_lot_event_role_mapper  5개 전부 쓰임
   declarative-role@1 <- ledger.roleframe
```

### ⚠️ 지시서의 근거 하나가 «죽은 파일»에서 재졌다
지시서: 「구조 매칭은 이미 금 가 있다 — `ledger_dt_job_mapper.py:24-25` 의 `COUNTED` 와
`FIRST_WORK` 가 구조가 동일하고 `FIRST_WORK` 는 안 쓰인다」.

**그 파일은 «등록되지 않는다».** v2 실행 경로가 쓰는 것은 `ledger_v2_dt_job_mapper.py`이고
거기엔 `FIRST_WORK` 가 없다. (그 죽은 파일엔 `RESITER` 오타도 그대로 있다.)

🔴 **그래도 결론은 «더 강한» 살아 있는 증거로 선다.** live `lot_event` 에서 `FIRST_SIGHT` 가
두 번 나가고 `subject_type=holder` / `item` 으로 갈린다(:210, :220). **구조만으로는 «오늘 이미»
mapping 을 못 고르고, 그래서 selector 인자가 존재한다.** 잠든 충돌이 아니라 «도는» 반례다.

### 딸려 나온 사실 — 착지 확인 3번의 현재값
```
say() 에 subject_type·object_type 인자를 쓰는 자리: :210 :220 :224 :229 :242 …  «0건이 아니다»
matcher 는 이미 sentence 를 «최후 동점 처리»로 쓴다 (roleframe.py:519-525) — 배선 일부는 있다
```

**판정 대기: 위 A 의 「FIRST_SIGHT 를 둘로 이름 붙인다」를 매퍼가 하는 게 맞는지만 확인되면 착수.**


## 🔴 「원자 696」은 «설정 모양의 성질이 아니다» — 직접 재서 기제를 찾았다 (2026-08-21 00:5x)

세 라운드의 합격 기준에 박혀 있는 숫자다. **다섯 번 되물었는데, 이제 다시 안 물어도 된다 —
왜 값이 흔들리는지 «코드로» 나왔다.**

```
preview_cursor_batch(...)                       runtime_v2.py:93-94
    normalized  = _known_registrations(known_registrations)
    event_atoms = _filtered_event_atoms(event_results, normalized)

register 를 내는 소스는 known_registrations 를 «필수»로 요구한다:
    "sources emitting register require an explicit existing-registration snapshot"
```
**이미 등록된 주체는 걸러진다.** 그래서 원자 수는 «등록 스냅샷»에 따라 움직인다.

### 내 실측 (라이브 DB · 스냅샷 f20483d4 · DB 쓰기 0)
```
행 38 · 등록 스냅샷 «빈 것»   →  분자 19 · 원자 «701» · incomplete 0
에이전트: 행 40 · 빈 스냅샷   →  분자 20 · 원자 «731» · incomplete 0
지시서:   696                  ←  등록 스냅샷이 «있던» 때의 값
```
**696 · 701 · 731 은 각자의 입력에 대해 다 맞는 값이다.** 셋을 가르는 것은
①읽은 행 수 ②등록 스냅샷 둘뿐이고, **설정 모양은 셋 중 어느 것도 아니다.**

### 그래서 합격 기준은 «상수»가 아니라 «불변»이어야 한다
```
안 된다   원자가 696 이어야 한다     ← 입력이 안 적혀 있어 «재현 불가능»하다
된다      같은 행 · 같은 등록 스냅샷으로 변경 «전/후»를 각각 재서 원자 수가 같을 것
          (흡수 라운드에서 에이전트가 실제로 그렇게 했다 — HEAD 워크트리 731 대 지금 731)
```
⚠️ 세 지시서(①②③ · 별명)의 시험 문구를 이걸로 바꿔야 한다. 안 바꾸면 **재현 불가능한 상수**에
라운드가 막힌다.

### 재현 방법 (다음 사람이 다시 안 헤매게)
```python
setup = load_setup(); plan = setup.snapshot.source_plans['lot_event']
pages = bf.walk_group_pages(lambda p: bf._fetch_v2_lineage_page(read, plan, p, 40),
                            lambda pv: bf._fetch_v2_lineage_group(read, plan, pv),
                            bf._page_key(plan), None, 40)
complete, _, _ = next(iter(pages)); f = bf._v2_frame(complete)
f['event_time'] = pd.to_datetime(f['event_time']).dt.tz_localize('Asia/Seoul')  # 없으면 거절 둘
cur = {c: f.iloc[-1][c] for c in plan.driver.cursor_columns}                    # 커서는 «마지막 행»에서
preview_selected_cursor_batch(setup, 'lot_event', f, cur, NoJoinReader(),
                              known_registrations=())                           # 이 인자가 숫자를 정한다
```
거치는 거절 셋은 전부 «내 하니스» 문제였지 제품 결함이 아니다:
`cursor must contain exactly physical columns` → `occurred_at value must be datetime`
→ `time Role must be a timezone-aware datetime`.


## 🔴 ③ 착수 전 관문 — **A·C 에 실행 소비자가 «있다». 멈춤.** (2026-08-21 00:0x)

지시서 `ledger_config_shape_brief.md` ③이 「하나라도 실행 소비자가 있으면 멈추고 보고」라 했고,
**있다.**

### A. `MapperDescriptor.emits` — 실행이 읽는다
```
roleframe.py:914   if row["claim_ref"] not in descriptor.emits:
                       raise RoleFrameError("unsupported_claim", …)
```
`validate_role_frame`(:859) 안 — 매퍼 «출력»을 받는 경계다. 검증기가 아니라 실행 경로.

### C. `claim_ref` — `compile_role_frame` «말고» 소비자가 많다
```
:292,437  claim_ref=mapping.claim_ref          emission 생성
:534      mapping.claim_ref.split("/",1)       claim 을 찾는다
:842      "claim_ref": emission.claim_ref      frame 행에 실린다
:910      row["claim_ref"] != mapping.claim_ref   → invalid_claim_ref
:914      not in descriptor.emits                  → unsupported_claim
:918      _claim(snapshot, row["claim_ref"], …)    → ClaimDescriptor 로 roles 를 검사
:47,151   frame 의 «필수 컬럼» 목록
```

### ⚠️ 지시서 전제가 «엉뚱한 함수»에서 재졌다
지시서: 「`compile_role_frame` 은 mapping 을 찾아 놓고 `claim_ref` 와 대조하지 않는다」.
`compile_role_frame`(:1075)만 보면 맞다. **그 대조는 바로 옆 `validate_role_frame`(:910)에 있다.**
같은 데이터가 두 함수를 다 지난다. [[a-snippet-reproduced-out-of-context-is-not-the-behaviour]]

### B. `profile.packs` — 실행 소비자는 못 찾았다
`roleframe.py:537,980`은 `snapshot.packs`(팩 레지스트리)를 읽지 `profile.pack_ids`가 아니다.
`profile_chain_mapper.py:172`의 `profile.packs`는 legacy 객체다. 검증 게이트는 있다
(`setup_bundle.py:1661` 「Pack X is not listed by profile.packs」).

### 내 판단 — 「못 한다」가 아니라 «다른 일»이다
`claim_ref`를 `mapping_id`에서 «유도»하고 `emits`를 `use`에서 «유도»하면 :910·:914는
**동어반복**이 되고, 매퍼가 모르는 `mapping_id`를 내는 경우는 이미 :906 `unknown_mapping`이 잡는다.
**지시서 논리는 거기까지 성립한다.** 다만 그건 「중복 제거」가 아니라 **«가드 둘을 걷어내고
유도로 대체»**다. 지시서 자신이 「그때는 출처를 바꾸는 일이 된다」고 적어 둔 그 경우다.

### 소유자 판정 받은 것 (총괄 전달)
```
간다     bind { mappings: [ … ] }    필드 하나짜리 레코드 «그대로»
안 간다  bind: [ … ]                 목록으로 접지 않는다
```

### 아직 답 없는 둘
```
①  approval_status 생략 여부 — 「가·나·다」. 권고 «나»
    (침묵이 «권한을 주는» 유일한 필드다. binding_origin 부재는 아무것도 안 준다)
원자 «696» — 실측 731. 네 번째 요청. ①②③ 시험에 전부 박혀 있어 세 라운드가 낡은 숫자에 막힌다
```


## ▶ 다음 라운드 ①② — 착수 «전» 관문에서 멈춰 있다 (23:00, 총괄 판정 대기)

지시서: `task/ledger_config_shape_brief.md`. ①(승인 메타 생략) + ②(read·prepare·map·bind) 한 커밋.

### A. 두 필드의 «값 집합» → 통과
```
라이브   approval_status {'approved': 40}   binding_origin {'user_declared': 40}   (749줄)
샘플     approval_status {'approved': 45}   binding_origin {'user_declared': 45}   (698줄)
```
다른 값 0건. **생략이 뜻을 지우지 않는다.**

### 🔴 B. 소비자 → «있고, 물어뜯는다». 그래서 멈췄다
```
roleframe.py:800      binding.get("approval_status") != "approved" → 실행 경로 거절
setup_bundle.py:1841  같은 검사를 검증기에서 한 번 더
setup_bundle.py:1129/1132/1136   두 필드가 종류 3종 «전부»의 required 튜플에 있다
setup_bundle.py:1162~1171        값 집합 검사 + origin=="system_suggested" 면 suggestion_reason 강제
source_profile.py:280 legacy 기본값 = binding_origin USER_DECLARED · approval_status «PENDING»
_BINDING_ORIGINS   {user_declared, system_suggested, imported}
_APPROVAL_STATUSES {pending, approved, rejected}
```

### 🔴 두 필드는 «대칭이 아니다» — 이게 판정의 핵심이다
```
binding_origin   부재 → user_declared 로 읽으면 «아무것도 주지 않는다».
                 system_suggested 갈래(= suggestion_reason 강제)는 적는 사람에게만 열린다. 안전
approval_status  부재 → approved 로 읽으면 «가장 센 것을 준다».
                 지금은 「승인이라고 말해야 승인」인데 「말 안 하면 승인」으로 뒤집힌다
```
**원칙 한 줄: 생략의 기본값은 «아무것도 주지 않는 값»일 때만 된다.**
`user_declared`는 자격이 있고 `approved`는 없다.

**내 권고 = 「나」**: `binding_origin`만 생략(80줄 중 40줄), `approval_status`는 남긴다.
효과 절반·위험 0. 판정은 총괄·소유자 몫.

### ⚠️ 지시서 5번 숫자가 낡았다
「원자 696이 아니면 착지 금지」인데 흡수 라운드 실측이 **731**이다(등록 스냅샷이 없어
first-sight 원자가 전부 뜬다). **고치지 않으면 다음 라운드가 낡은 숫자에 막힌다.**
이 건은 아직 판정을 못 받았다 — 세 번째 요청이다.


## ▶ 씨앗 수리 착지 `0e089c6d` — 내 검수 (22:42). 브라우저 걷기만 «대기»

**커밋:** 소스 2 + dist 4 = 6파일. `client2/src/ontology_skeleton.js`(emptyOf) ·
`server/ledger/config_authoring.py`(empty_value). 푸시 안 함.

### 내가 직접 잰 것 — 서버 쪽은 끝났다
```
바인딩 씨앗 (수리 후)   {}          ← 전에는 {"keys": {}}
소유자 «원래» 불편은 그대로 고쳐져 있다:
  vocabulary   {"subjects": [], "object": {"qualifiers": {"required": [], "optional": []}}}
  entities     {"keys": []}
  packs        {"claims": {}}
  sources      {"profile": {"packs": [], "mappings": []}, "driver": {...}}
```

**「딱 하나만 바뀌었다」는 닫힌 논증이다** — 워크트리 없이 증명된다. 스켈레톤의 `when` 게이트는
8군데뿐이고, 그중 `required:true`는 넷(`column`·`value`·`entity_type`·`keys`),
앞의 셋은 **leaf**라 `empty_value`가 «원래부터 안 씨앗한다». **컨테이너는 `keys` 하나뿐이다.**
나머지 넷(`types`·`entity`·`value`·`columns`)은 `required:false`라 애초에 대상이 아니다.

⚠️ **내가 하마터면 없는 회귀를 보고할 뻔했다.** 첫 측정에서 `empty_declaration('predicate')` 등이
전부 `{}`로 나와 「소유자 원래 수정이 날아갔다」로 보였다. **절 이름이 아니라 «종류» 이름을 넣은
내 실수였다** — 절은 `entities`·`vocabulary`·`packs`·`sources`다. 바른 이름으로 다시 재니 멀쩡했다.
[[an-empty-database-answers-every-question-with-absence]]와 같은 모양: **틀린 키는 모든 질문에
「없다」로 답한다.**

### ⬜ 남은 것 — 폼 걷기 «내 손으로». 지금은 못 한다
```
라이브 설정 sources: ['dt_job', 'lot_event', 'zz_lead2']   ← 총괄이 «지금» 걷는 중 (22:41:34 기록)
```
**설정 파일 하나에 두 세션이 동시에 쓰면 섞인다.** 총괄 프로브가 빠지면 내가 걷는다.
에이전트 보고는 「수리 전 2 → 수리 후 0」이고, 게이트가 만족되면(`kind=entity`) 렌더러가
`keys` 이름칸을 그려 주므로 add-and-remove 없이 한 번에 된다고 한다 — **그 두 줄이 내가 재야 할 것.**


## ▶ 지금 (22:00) — 씨앗 수리가 돈다, 그리고 «서버 재시작하지 말 것»

```
소유자 판정   「씨앗을 종류맞게줘」 — 두 방향 중 ①. 「지우는 문」은 «안 만든다»
에이전트      21:5x 투입, 도는 중. config_authoring.py 를 지금 쓰고 있다(mtime 21:55)
              자기 라운드 안에서 재시작하도록 지시서에 박아 뒀다
```
🔴 **내가 지금 서버를 올리면 반쯤 쓰인 파일을 문다. 에이전트가 끝날 때까지 손대지 않는다.**

### 고칠 자리는 이미 찾아 뒀다 — 새 축을 «만들지 않는다»
스켈레톤 `defs.binding`이 이미 조건을 선언하고 있다:
```
column       required:true  when {field:"kind", is:"column"}
value        required:true  when {field:"kind", is:"constant"}
entity_type  required:true  when {field:"kind", is:"entity"}
keys         required:true  when {field:"kind", is:"entity"}    ← 넷 중 «유일한 컨테이너»
```
씨앗 두 곳이 `required === true`만 보고 **`when`을 안 본다** — 서버 `empty_value`
(`config_authoring.py:384`)와 클라 `emptyOf`(`ontology_skeleton.js:99`). 둘은 «같은 규칙을
일부러 두 번 쓴 것»이라 **같이 고쳐야 한다.** 종류 목록을 코드에 박지 말고 «게이트를 읽는다» —
`when`은 스켈레톤에 8군데 있고, 게이트를 읽으면 **부류 전체가 한 번에 맞는다.**

⚠️ **되돌아올 수 있는 것:** `empty_value`는 소유자 불편(「qualifier 안넣을건데 이거 기본으로
키 안들어가 있어서 에러남」) 때문에 생겼다. 종류를 entity로 «고른 뒤»엔 `keys`가 제대로 생겨야
하고, 안 그러면 그 불편이 돌아온다. 「무조건 안 만들기」로 도망가지 말라고 지시서에 박았다.

### ✅ 서버 시계 소동 — 화면은 «안 깨졌었다». 총괄 철회
총괄이 「서버가 옛것이라 소유자 화면이 깨졌다」고 했는데 **프로세스 시작 시각을 «커밋 시각»과
견준 것이었다.** 로드를 정하는 건 **파일 mtime**이다.
```
파일 mtime 20:35~20:39  →  서버 기동 20:58  →  커밋 21:31
실측: /view 200 · plan 200 · refusals 0 · missing 0 · 브라우저 4 layers · 선언 14개
```
**커밋 시각은 확인을 마친 뒤 찍는 «나중» 사건이다.** [[built-is-not-loaded]] 메모에 총괄이 정정해 뒀다.

### 아직 답 안 온 판정 둘
```
d64f047e 푸시 여부 · 그리고 씨앗 수리를 별도 커밋으로 얹을지 합칠지
6번 원자 731 vs 지시서 696  (방법은 지시서보다 낫다고 본다 — 고정 숫자 대신 «전후 불변»)
```


## ▶ 프로필 흡수 — `d64f047e` 커밋됨(«푸시 안 함»). 내 검수 결과 (21:35)

**내가 브라우저에서 직접 잰 것 — 1·2·3번 통과:**
```
1번  dt_job 트리   깊이1에 「프로필」RECORD · 그 안 깊이2에 packs · mappings
                   같은 깊이1에 driver, 그 안에 준비기·매퍼 → 셋 다 소스 «안»에 있다
2번  좌측 인덱스   PROFILES 그룹 «없음» · 「선언 · 14개」 (16 − 프로필2)
                   그룹 5개: ENTITIES · PACKS · VOCABULARY · SOURCE PLANS · TABLES
3번  척추          「4 layers · complete」 · 엔터티 · 낱말 · 팩 · 소스
서버              PID 4564 · 20:58 기동 > 편집 파일 mtime 최대 20:40  → 흡수된 코드가 돈다
커밋              22 파일, 의도한 것만. 마이그레이션 스크립트 «없음» · SETUP_VERSION «3»
라이브 설정        top = entities · packs · sources · vocabulary  (profiles 절 없음)
                   두 소스 다 profile:{mappings,packs} · profile_id 잔재 없음
```

### 🔴 5번 — **통과 못 했다. 이 라운드의 «목표»였다**
거절 2건: `unknown_field` at `…bind.occurred_at.keys` · `…bind.subject.keys.dt_job.keys`.

**앞 라운드의 거절 둘(`profile_id`)은 «사라졌다»** — 소스를 한 번의 행위로 만들게 됐고, 지난번
막혔던 역할 추가 컨트롤도 돈다. **목표의 절반은 닿았다.** 남은 것은 다른 결함이다:
새 바인딩이 종류와 무관하게 `{"keys": {}}`로 씨앗을 받고, 폼으로 그걸 «지울 수가 없다».

**「회귀 아님」을 내가 직접 확인했다 (에이전트 말을 그대로 안 믿고):**
```
empty_value({"use":"binding"}, defs)  →  {"keys": {}}      ← 지금 트리
스켈레톤 defs, 흡수 «전»(d64f047e^)과 «바이트 동일»        ← True
```
씨앗 동작과 그 선언이 이 커밋으로 안 바뀌었다. **같은 결함이 새 주소에서 보이는 것이다.**

### ⚠️ 6번 — 통과라는데 «숫자가 지시서와 다르다». 총괄 판정 필요
```
지시서   원자 696 · incomplete 0 · DB 쓰기 0 이어야 한다
실측     40행 → 분자 20 · 원자 «731» · incomplete 0 · DB 쓰기 0
```
에이전트 설명: 696은 등록 스냅샷이 있던 상태의 값이고, 지금은 first-sight 원자가 전부 떠서
731이다. 그래서 **HEAD 워크트리와 지금 트리를 «같은 40행»에 각각 돌려 731 대 731**로 맞췄고,
스냅샷 해시 접두사를 빼면 원자 payload가 바이트 동일이라고 한다(`#mapping_id` 여섯 개 다 그대로).

**방법 자체는 지시서보다 낫다**(고정 숫자가 아니라 «전후 불변»을 재는 것이므로). 다만 지시서가
못 박은 숫자를 못 냈으니 **내가 통과로 처리하지 않고 판정을 올린다.**

### 그 밖
```
4번 versioned   profile@ 이 «코드 0줄»로 빠졌다 (4종 → 3종). 주석 한 줄만 고쳤다고 한다
7번 삭제 미리보기  dt_job 15 · lot_event 41 · 0 retained · 0 blocked — 흡수 전후 동일
ProfileDescriptor.version  «지웠다». 프로필 본문에 버전을 선언할 자리가 없어졌으므로
                 상수나 남의 숫자를 넣으면 해시에 실려 「프로필은 버전이 있다」는 거짓말이 된다
테스트          서버 305 passed / 1 skipped (11본) · 클라 하네스 4본 초록
```


## ▶ 지금 도는 것 — 프로필 흡수 (21:02 기준)

```
지시서 정본   task/ledger_profile_absorption_brief.md
에이전트      20:58 투입, 도는 중. 087e7d8 을 «본»으로 삼으라고 붙였다
내 몫         완료되면 브라우저로 7개 확인 «직접» + 통째 커밋
```
**착수 전 관문 A·B 는 내가 재고 넘어갔다. 둘 다 소비자 «없음» — 멈출 이유가 없었다.**

### A. 프로필을 «id로» 참조하는 곳이 소스 말고 또 있는가 → **없다**
v2 프로필을 실제로 해소하는 곳은 `setup_registry.py:892`(`profiles[item["profile_id"]]`)
하나뿐이고, 그건 지시서가 이미 아는 자리다. 나머지 `bundle.profiles.…`는 전부 검증기·저작·
탐색기의 «경로 문자열»이다.

⚠️ **grep에 두 번째 소비자가 잡혀서 끝까지 팠는데 «다른 프로필»이었다.**
```
ledger/config.py · chain_mapper.py 의 chain_mapper.profile_id
  profiles 출처가 source_profile.validate_profile_section  ← v2 번들이 «아니다»
  읽는 파일도 v1 로더의 paths.CONFIG_DIR/ledger_config.json ← 이 박스에 «없다»
  결정적으로 chain_mapper 를 «선언한 설정이 어디에도 없다»
     (server/config/ 전수 grep 0건 · v2 라이브도 False)
```
**이름이 같아서 소비자로 보였을 뿐이다.** 여기서 멈췄으면 라운드를 헛돌았다.

### B. 프로필 id 의 @버전을 «읽는» 곳이 있는가 → **없다. 단, 재고 나서 안다**
「보이는 것」으로 판정하지 않고 원자의 버전 문자열을 실제로 뜯었다:
```
source_translator_ver = f"ledger-v2:{snapshot_sha256}#{mapping.mapping_id}"   roleframe.py:1175
DB 실측 distinct 2건   …#job_register · …#job_die_count
```
**해시 뒤는 프로필 id 가 아니라 `mapping_id` 다.** `mappings[]` 안에 있고 지시서가 「한 글자도
안 바꾼다」고 한 것이라 흡수해도 그대로다.

`ProfileDescriptor.version`은 `_versioned_parts(profile_id)`로 채워지지만
(`setup_registry.py:787`) **실행 경로가 안 읽는다** — `roleframe`·`source_preparation`은
`profile.mappings` · `profile.source_id` · `profile.config_path`만 쓴다.
「profile 근처의 `.version`」은 전부 legacy `source_profile`의 «팩» 버전이었다.

⚠️ **딸려 나온 것:** 흡수하면 `ProfileDescriptor.version`이 채울 근거를 잃는다. 읽는 곳이
없으니 지우는 게 맞아 보이지만 구현 판단이라 「지우든 남기든 하나 골라 근거를 보고하라」로 넘겼다.

⚠️ **내 실수 하나 기록:** A·B를 «메시지로만» 보고하고 이 파일에 안 적었다. 그래서 밖에서는
20:14 이후 멈춘 것으로 보였다. **파일이 정본이다 — 판정 재료는 메시지 말고 여기에 먼저 적는다.**

---


## ✅ 병합 착지 — `087e7d8`, 푸시까지 끝 (20:14)

```
24 파일 · +781 / -811 · dist 넷은 rename 둘로 접혀 들어갔다(옛 둘 삭제 + 새 둘 추가)
빠진 것 확인: dt_map_derivation · map_alignment · map_overlay · seed_dt_index_walk ·
              task/*.md  ← 전부 트리에 그대로 남아 있다
내가 돌린 테스트: 건드린 9본 → 297 passed · 1 skipped · 0 failed
```

## 🔴 커밋 «뒤» 실측 — 소유자 판정의 재료 (총괄 ④)

### A. 관계 없는 선언을 고치면 해시가 움직이는가 → **움직인다. 그리고 남의 커서까지 막는다**
```
아무도 안 쓰는 낱말 하나를 «추가»만 해도   snapshot_sha256 바뀜
커서 검사는 소스별이 아니라 «전역» 해시와 비교한다
   expected = f"ledger-v2:{setup.snapshot.snapshot_sha256}"   (backfill.py:335)
→ 화면에서 무엇을 고치든 «모든» v2 소스의 백필이 cursor_snapshot_reset_required 로 막힌다
```
⚠️ 이것이 「원자를 하나도 못 바꾸는 변경이 커서를 막는다」의 실측이다 — `setup_registry.py:617`의
주석이 옛날에 `chains`·`enrichments`를 뺀 바로 그 이유다. **다만 화장 수준(키 순서)은 안 움직인다.**

### B. 그래서 이게 얼마나 큰 일인가 → **792행짜리 일이다. 작은 쪽 끝이다**
```
원장 전체                     221,563 행
ledger-v2: 로 시작하는 행         792 행   (전체의 0.36%, distinct 버전 2)
커서 12개 중 v2 는 «1개»(dt_job). 나머지 11개는 v1 시대 (lot_event 포함)
dt_job 커서 자체 계수: molecules_done 836 · atoms_written 805 · deduped 427
```
**600만행 append 가 아니라 800행 append 다.** 재개 판정의 반경은 소스 하나·커서 하나다.

---


**이 파일이 정본이다. 컴팩트 뒤의 나는 대화를 못 읽고 이것만 읽는다.**

---

## 🔴 먼저 — 화면이 「선언 · 0개」로 보이면 그건 «고장이 아니다»

```
라이브 설정   이미 이관됨   source_preparers · mappers 절이 «없다»
                            driver.mapper = 본문 · driver.preparation = 준비기 본문
:8080 서버    PID 27044, 14:59 기동   ← 이관보다 «먼저» 뜬 프로세스, 옛 파이썬
```

**옛 검증기가 새 설정을 읽으면 전부 거절한다.** 원인을 찾지 말 것 — **서버를 재시작하면 된다.**
소유자가 재시작을 승인했다(「서버 꺾다켜도됨」).

```
cd server && python -m uvicorn main:app --host "" --port 8080
```
(같은 명령으로 이미 한 번 재시작했다. 파이썬을 고치면 «항상» 재시작이 필요하다 — `--reload` 없음.)

---

## ⓪ 재시작 «했다» — 그리고 여기까지 통과했다 (19:16)

```
:8080  PID 42488 · 19:16:54 기동   ← 이관·병합 «뒤». 화면 살아났다
```
**위 「0개로 보이면 고장이 아니다」는 이제 해소된 상태다.** 다시 0개로 보이면 그때는 진짜로 볼 것.

**일곱 확인 중 이미 통과한 것:**
```
4번  좌측 인덱스   Entities·Packs·Vocabulary·Profiles·Source plans·Tables
                   준비기·매퍼 그룹 «없음» · 선언 16개 (이전 20 − 준비기2 − 매퍼2)
5번  척추          5층 · 엔터티·낱말·팩·프로필·소스 · 「5 layers · complete」
③   versioned     authorable = entity@ pack@ predicate@ profile@ source_plan
                   → 준비기·매퍼가 «코드 0줄로» 빠졌다. 설계가 옳았다. 고칠 것 없음
```

**1·2·3번도 통과했다 (19:40 실측).** 남은 것은 **6·7번**, 그리고 **경로 후보 제거**.

```
1번  dt_job 트리   driver 밑 깊이2에 「준비기」RECORD · 「매퍼」RECORD  ← «그 안에» 떴다
2번  준비기 후보    lot_event 8개 = lot_event 물리 컬럼 그대로
3번  매퍼 후보      lot_event 14개 = 물리 8 ∪ 준비기.output_columns 6
                   더 붙은 6개: lot · slots · wafers · row_identity ·
                                event_group_key · __source_event_incomplete
                   → 설정의 output_columns와 «정확히» 같은 여섯. 이게 이 변경의 목표였다
```

🔴 **판별식은 lot_event뿐이다.** dt_job은 준비기가 통과형(`output_columns: []`)이라
준비기 후보 23 · 매퍼 후보 23으로 **두 규칙이 같은 답을 낸다.** dt_job만 봤으면 아무것도
증명 못 한 것이고, 실제로 8↔14로 «갈라지는» 것은 lot_event 한 곳이다. 다시 잴 때도 lot_event로.

⚠️ **3번은 «화면 그림»이 아니라 화면이 읽는 payload에서 쟀다** — 브라우저 안에서
`/admin/ontology-explorer/authoring/plan?selection=source|dt_job`을 페이지 토큰으로 부른 값이고,
`row.candidates`가 그대로 렌더 입력이다. 다만 **오늘 두 소스 다 매퍼 input_columns가 `derived`**라
피커가 «안 뜬다**(`renderRow`는 `state !== 'derived'`일 때만 후보 상자를 그린다).
**즉 3번을 그림으로 보려면 6번(폼으로 새 소스 만들기)을 타야 한다 — 둘은 한 걸음이다.**

✅ **앞서 「preparation·mapper 이름을 못 찾았다」고 적은 것은 결함이 아니었다. 두 겹으로 내가 틀렸다.**
① 선택자가 한 층을 건넜다 — 맞는 건 `.oe-node-row` 안에서 `.oe-node-label > .oe-node-name`.
② **그리고 트리는 «키»가 아니라 스켈레톤의 «라벨»을 그린다 — 화면 글자는 「준비기」·「매퍼」다.**
   선택자를 고쳐도 `preparation`으로 grep했으면 또 0건이었다. 이름으로 찾을 땐 라벨로 찾을 것.

## 🔴 7번 backfill — «막혔다». 내가 풀 수 있는 종류가 아니다 (19:50 실측)

두 소스 다 거절이고, **거절 이유가 서로 다르다.**

```
lot_event  legacy_cursor_reset_required
           저장된 커서 키 {event_time} ≠ 선언 {event_time, txn_seq}
           translator_ver = lot_event/1/rules:34311f15   ← «v1 시대» 커서
           → 병합과 무관한 «기존» 상태다. preflight가 이미 「의도된 안전장치」라 적어 뒀다
             (scripts/ledger_deploy_preflight.py:146)

dt_job     cursor_snapshot_reset_required
           저장된 translator_ver = ledger-v2:39ebb419…  ← v2 커서는 맞다
           그런데 지금 스냅샷 해시와 다르다
```

**dt_job 쪽이 이 병합이 만든 것이다.** `snapshot_sha256`의 재료에 `bundle_sha256`
(= 번들 직렬화 «전체»의 해시)이 들어간다(`setup_registry.py:601,615`). 병합은 절을 지우고 본문을
안으로 옮기므로 직렬화 «모양»이 바뀌고, 따라서 해시가 «반드시» 움직인다. 원자가 하나도 안 바뀌어도.

⚠️ **되돌릴 방법이 코드에 없다.** `--reset-cursor`는 config·DB를 열어 보기도 «전에» 무조건
`destructive_approval_required`로 거절한다(`backfill.py:869`). 승인 능력 자체가 아직 없다.

**코드가 스스로 적어 둔 우회로는 하나뿐이다** — preflight:
「시연은 «다른 source_id»로 선언하면 커서 없이 바로 됩니다」. 새 id는 커서 행이 없으니 두 검사를
다 안 탄다. **다만 그건 원장에 원자를 «쓴다».** 소유자 DB에 쓰는 일이라 내가 혼자 정하지 않는다.

✅ **앞서 「이 화면으로 설정을 고칠 때마다 같은 일이 난다」고 적은 것은 «틀렸다». 재서 확인했다.**

```
① 키 순서만 뒤섞음 (의미 완전 동일)   snapshot_sha256 «그대로» · bundle_sha256도 «그대로»
② timezone → UTC (원자가 바뀜)        snapshot_sha256 «바뀜»
```
**직렬화가 정규화돼 있어서 `bundle_sha256`은 «텍스트»를 따라가지 않는다.** 뜻이 바뀔 때만 움직인다 —
설계 의도대로다. 화장 수준 편집은 커서를 막지 않는다.

**그럼 이 병합은 왜 움직이나 — `bundle_sha256` 탓이 «아니다».** 병합 뒤 레지스트리의 «키»가
선언 이름에서 소스 이름으로 바뀐다:
```
registries[source_preparers]  전: direct-join@1 …    후: dt_job · lot_event
registries[mappers]           전: dt-job-role@1 …    후: dt_job · lot_event
```
`registries`는 `_semantic_plain`을 거친 «의미» 재료다. **거기가 바뀌므로 `bundle_sha256`을 빼도
해시는 똑같이 움직인다. 이 병합에서 커서 무효화는 «피할 수 없다».**

**총괄 반론 뒤 한 겹 더 팠다 — 「이름은 원자를 못 바꾼다」는 «오늘은» 맞고, «영원히»는 아니다.**

```
mapper_id     원자 경로(roleframe·runtime_v2·store)에 «참조 0건». 못 바꾼다
preparer_id   event frame 에 찍힌다 (SOURCE_PREPARER_ATTR) — 그러나 «읽는 곳이 없고»,
              role frame 이 넘기는 attr 목록에 없어서 컴파일러 경계에서 «버려진다»
                 REQUIRED    source_id · source_event_id · molecule_ref ·
                             source_raw_ref · setup_snapshot_hash
                 PASSTHROUGH assy_manager.source_event_incomplete   ← 이 둘뿐
```

🔴 **그런데 «단 하나» 새는 자리가 있다.** `source_raw_ref`는 보존되고, 그 재료인
`provenance_base`의 각 항목이 `"preparer": f"{preparer_id}#…"`를 담는다
(`source_preparation.py:852`). 그리고 `source_raw_ref` → `source_event_identity()` →
**`source_event_id`**, 즉 원자의 «정체»다.

```
provenance_base 는 verified join 이 있을 때만 채워진다
오늘 두 소스 다 verified join 이 «없다» (backfill 이 있으면 먼저 거절하는데, 통과했다)
→ 오늘은 preparer_id 가 원자에 «안» 닿는다
→ 누군가 verified join 을 선언하는 «날» 닿는다
```

**그러니 「이름이니까 해시에서 빼도 된다」는 오늘만 참인 명제다.** 빼면 verified join 이
생기는 날 조용히 틀린다 — 이 프로젝트가 이미 여러 번 당한 모양이다.

⚠️ **그리고 뺀다고 해결되지도 않는다.** `bundle_sha256`이 재료에 남아 있고, 병합은 절을
지우는 «구조» 변경이라(키 순서 같은 텍스트 변경과 다르다) 그것만으로도 해시가 움직인다.
레지스트리 둘을 빼도 커서는 그대로 막힌다.

**결론: 해시 설계를 손댈 일이 아니다.

## ✅ 경로 후보 제거 — 검수 끝 (20:02, 새 dist `admin-B8b_8hUS.js`로 재확인)

브라우저에서 **소스·프로필·팩 셋 다** 열어 봤다. 지시서가 요구한 그대로다.

```
            현재 경로            경로 후보     Integrity 「이 정의를 사용하는 곳」
dt_job      SOURCE_PLAN/dt_job   «없음»        1 · dt-job@1  (profile_source · resolved)
dt-job@1    PROFILE/dt-job@1     «없음»        1 · dt_job    (source_profile · resolved)
lot-lineage@1 PACK/lot-lineage@1 «없음»        1 · lot-event@1 (profile_pack · resolved)
```
body 전체 텍스트에도 「경로 후보」 0건. 「참조 검사」는 세 곳 다 **미해소 0건**까지 말한다.

**「지우면서 잃은 것이 없나」는 코드에도 근거가 남아 있다** (`config_explorer.py` RETIRED 주석):
라이브 설정에서 **92개 엣지**가 후보 경로 재료였고 그중 Integrity의 `used_by`에 없던 것 **0개**,
**62개 선택 중 48개가 후보 1개뿐**(= 열거가 레인을 하나도 안 보탬). 게다가 후보는
`status == "resolved"`로 걸러져서 **미해소 참조를 «보여줄 수가 없었고», Integrity는 항상 보여준다.**
잃은 것은 여러 홉의 «합성»뿐이고, 각 홉은 눌러서 그 홉의 패널이 답한다.

**총괄의 6번 걷기 흔적도 깨끗하다** — `merge_walk_probe` 소스·프로필 둘 다 지워졌고
지문은 낱말5 · 엔터티3 · 팩2 · 프로필2 · 소스2로 돌아왔다.

## ⑨ 병합 에이전트 완료 (20:02) — 커밋 «직전» 상태

**내가 직접 돌린 것:** 건드린 테스트 9본 → **297 passed · 1 skipped · 0 failed** (10.6s).

**에이전트가 채운, 내가 못 만들던 기준선:** HEAD에 워크트리를 파서 설정을 «역»이관하고 같은
backfill 명령을 돌렸다 → `lot_event`는 **똑같이 거절**(기존 박스 상태, 회귀 아님),
`dt_job`은 그 기준선에선 **완주**하고 여기선 스냅샷 해시로 거절. 내 분석과 일치한다.

🔴 **7번의 «의미»는 쓰지 않고 채워졌다** — 진짜 `lot_event` 40행을
`preview_selected_cursor_batch`에 태워 **분자 20 · 원자 696 · incomplete 0**.
인라인된 준비기가 프레임을 만들고 인라인된 매퍼가 원자를 냈다. **DB에 한 줄도 안 썼다.**

### ⚠️ 6번이 «어긋난다» — 커밋 메시지에 「통과」를 적기 전에 총괄 판정을 받을 것
```
총괄      ✅ 「저장했습니다」 · 거절 0
에이전트  거절 6 → 2 (0 아님). 남은 둘 다 profile_id.
          새 소스는 자기를 가리키는 새 프로필이 필요한데, 그 프로필을 폼으로 만들다
          bind 의 역할 추가 컨트롤에서 이름이 안 박혀 멈췄다고 한다
```
**내가 확인한 것: 그 컨트롤은 이번 변경이 안 건드렸다.** 클라 디프가 6줄·25줄뿐이고 `bind`
관련은 주석 한 줄, 서버도 null 가드 하나뿐이다. **막힌 게 사실이어도 이 병합의 회귀는 아니다.**
다만 **「폼만으로 끝까지 간다」는 아직 증명 안 된 상태다.**

### 커밋 경로 — 에이전트가 준 목록, 그대로 쓸 것
```
같이 간다   client2/dist/{admin.html,index.html} · dist/assets 새 둘(?? 로 뜬다)
            client2/src/ontology_explorer{,_store,_view}.js · client2/tests/ontology_explorer_harness.mjs
            server/config/sample/ontology/transfer_explorer/ledger_config.json
            server/ledger/{config_authoring,config_explorer,config_explorer_service,setup_bundle,setup_registry}.py
            server/ledger/ledger_skeleton.json
            server/tests/ 9본
🔴 빼야 한다  server/{dt_map_derivation,map_alignment,map_overlay}.py ·
            server/scripts/seed_dt_index_walk.py     ← 줄바꿈 잡음, 내 것 아님
            task/*.md                                 ← 문서, 별도 커밋
            server/config/ontology/ledger_config.json ← gitignore. 이관돼 있고 «커밋 안 된다»
```
⚠️ **옛 dist 자산 둘은 `D`(삭제)로 뜬다** — `admin-BsLkF8EI.js` · `main-CwfinSe_.js`.
새 것 둘은 `??`다. 넷 다 명시해야 dist가 반쪽으로 착지하지 않는다.

## ① 지금 어디까지 왔나 — 소스플랜 병합

**지시서(정본): `task/ledger_source_plan_merge_brief.md`** — 소유자 판정, 실측, 일곱 확인,
「하지 않는 것」 표, 그리고 끝에 붙은 **「경로 후보 제거」**까지 전부 거기 있다.

**끝난 것(미커밋):** 라이브 설정 이관 · 샘플 이관 · 스켈레톤 · 검증기 · 레지스트리 · 테스트 다수.
**안 끝난 것:** 서버 재시작 후 **일곱 확인 전부**, 그리고 커밋.

⚠️ **통째로 착지한다.** 조각내면 라이브 설정이 어느 쪽으로도 안 읽힌다. 지시서의 명시적 규칙이다.

## ② 미커밋 변경 (2026-08-20 기준)

```
server/config/sample/ontology/transfer_explorer/ledger_config.json
server/ledger/config_authoring.py · config_explorer.py · ledger_skeleton.json
server/ledger/setup_bundle.py · setup_registry.py
server/tests/  test_ledger_roleframe · setup_boundary · setup_bundle · setup_registry
               · skeleton · source_preparation
server/config/ontology/ledger_config.json   ← 소유자 라이브 설정, «이관됨». gitignore 대상
```
**`git add -a`/`-A` 금지.** 커밋은 경로를 명시해서 하고, `commit`에도 경로를 붙인다
(안 붙이면 남이 스테이지한 것이 전부 따라간다 — 실제 사고 있었음).

## ③ 다음 한 걸음

1. **서버 재시작** (위 명령)
2. **지시서의 일곱 확인을 화면에서** — 특히 **3번**(매퍼 input_columns 후보가
   `relation ∪ 준비기.output_columns`에서 나오는가 — 이게 이 변경의 «목표»)과
   **7번** `python -m ledger.backfill --source lot_event --max-batches 1`
   ⚠️ 7번을 빼지 말 것. 저장된다고 읽기 경로가 도는 게 아니다.
3. **③ versioned 시험** — 준비기·매퍼가 `versioned`에서 «코드 0줄로» 빠져야 한다.
   빠지면 설계가 옳았던 것이고, 고쳐야 하면 **그 자리가 결함**이니 보고할 것.
4. **경로 후보 제거** — 지우기 «전에» Integrity가 같은 질문에 답하는지 확인.
   경로 후보에만 있던 사실이 있으면 Integrity로 옮기고 지운다.
5. 시험 선언은 만든 자리에서 삭제. 지문 확인: 낱말5 · 엔터티3 · 팩2 · 프로필2 · 소스2
   (준비기·매퍼는 이제 «없다» — 새 지문을 보고에 적을 것)

## ④ 이 화면에서 이미 배운 것 — 반복하지 말 것

- **파이썬 고쳤으면 재시작.** 오늘 이걸로 네 번 헛돌았다.
- **클라 고쳤으면 빌드.** `cd client2 && npm run build`. 소스에 있고 dist에 없으면 사용자에겐 없다.
- **커밋 메시지는 `-F` 파일로.** `-m` 안의 백틱은 셸이 «실행»해서 식별자가 사라진다(실제로 당했다).
- **배치를 옮기면 수치 전에 스크린샷.** 트리 좌표만 재고 척추가 깨진 걸 소유자가 먼저 봤다.
- **계측기를 먼저 의심.** 대비 스캔이 「다크 100건 실패」를 냈는데 내 파서가 틀렸다.
- **공유 클래스 확인.** `.oe-node-name`·`.oe-node-kind`는 트리와 참조 플로우가 같이 쓴다.
- **파일이 정본.** 메시지는 잘려서 온다. 「남은 것」을 말하기 전에 지시서를 훑는다.

## ⑤ 판정 대기 / 취소

```
취소   6b-T9 이름 바꾸기 — 소유자 「그건 그냥 하지 말라해」. 착수 안 함, 되돌릴 것 없음
대기   없음 (병합이 유일한 진행 건)
```

## ⑥ 채널

총괄 = 포크 세션 「Ontology Manager」. **소유자 지시: 총괄과 소통하고 소유자에게 직접 보고하지 말 것.**
메시지는 새기 쉬우니 **이 파일에도 같이 쓴다.** 하위 에이전트는 **자기 브라우저 탭을 새로 열게** 한다.
