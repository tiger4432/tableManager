# 📋 구현자 지시 — 지금 할 것 (총괄 → 구현자, 단일 정본)

> 🔴 **소유자 지시 2026-08-21 15:4x: 「세션 간 메시지가 에러를 유발하는 것 같다.
> 지시문 커밋 기반으로 모든 통신 돌려」**
>
> **이 파일이 채널이다. 커밋이 초인종이다.** 세션 간 메시지는 쓰지 않는다.
> 오늘 총괄 메시지가 «다섯 번» 대기열에서 안 닿았고, 앞 구현자 세션은 그 상태로 에러가 났다.

---

## 프로토콜 — 두 파일, 한 방향씩

```
총괄 → 구현자    task/IMPLEMENTER_ORDERS.md          «이 파일». 항상 「지금 할 것」만 담는다
구현자 → 총괄    task/implementer_pickup_report.md    보고·질문·판정 요청
공통             일 시작 전 `git pull`. 쓴 다음 `git commit` + `git push`
```
- **총괄은 커밋을 감시한다.** 구현자가 보고 파일을 푸시하면 총괄이 그걸로 안다.
- **구현자는 착수 전·보고 전에 이 파일을 다시 읽는다.** 순서가 바뀌었을 수 있다.
- 질문·판정 요청은 보고 파일 **맨 위**에 「🔴 판정 요청」으로 적는다. 총괄이 여기 답을 적는다.
- ⚠️ 급하면 소유자가 양쪽을 직접 깨운다. 그것이 유일한 대체 신호다.

---

# 🔴 상설 규칙 — 긴 작업은 «백그라운드», 본체는 «읽을 수 있게» 둔다

> **소유자 지시 2026-08-21 16:0x:** 「구현자는 클라 빌드 같은 긴 작업 하면 거의 수십 분 동안
> 아무 연락을 안 읽음. 이렇지 못하게 **클라 빌드 등의 작업 하위 에이전트/백그라운드로 넘기라**고 해.
> **총괄과 사용자의 연락은 읽고 판단해서 제대로 된 구현이 1순위**라고.」

## 왜 — 오늘 실제로 이걸로 잃었다
```
빌드·검증에 물려 있는 동안 총괄 메시지 «다섯»이 대기열에 쌓였고
그 상태에서 앞 구현자 세션이 «에러로 죽었다». 쌓인 지시는 통째로 유실됐다
```
**막힌 채로 오래 도는 것은 그 자체가 위험이다.** 그 사이 순서가 바뀌거나
멈춤 판정이 내려와도 못 받는다.

## 무엇을 백그라운드로 넘기나
```
npm run build              Bash run_in_background: true
전체 테스트 스위트          같음
긴 backfill · 마이그레이션   같음
브라우저 장시간 걷기         하위 에이전트로 넘기고 본체는 대기
수 분 이상 걸리는 무엇이든    같음
```

## 넘긴 «뒤»에 할 일 — 이게 규칙의 핵심이다
```
1  띄워 놓고 «본체는 즉시 돌아온다». 붙어서 기다리지 않는다
2  task/IMPLEMENTER_ORDERS.md 를 «다시 읽는다» — 순서가 바뀌었을 수 있다
3  판정 대기 중인 것이 있으면 보고 파일에 적고 푸시한다
4  백그라운드가 끝나면 알림이 온다. 그때 이어서 한다
```

🔴 **1순위는 「제대로 된 구현」이고, 그러려면 «읽고 판단할 수 있는 상태»여야 한다.**
빨리 끝내는 것보다 **틀린 지시 위에서 오래 일하지 않는 것**이 싸다.
오늘 총괄이 지시서 하나를 늦게 써서 한 시간을 버렸고, 메시지 다섯이 죽었다.

⚠️ **하위 에이전트에게 넘길 때는 워크트리를 쓰게 하고**, 그 라운드에서는
메인 트리가 조용한 것이 «정상»이다. 트리 무변화를 진척 지표로 쓰지 말 것.

---

# ▶▶ 지금 할 것 — **문자열 시각** (packs 착지 뒤, 18:0x)

`packs`·`claims` 라운드 `9b6c5da0` 착지 확인했습니다(+1511/−1700). **총괄이 화면에서 검증했습니다:**
```
「3 layers · complete」 · 선언 12개 · 거절 0 · missing 0
척추가 층 수 «줄어든 것»을 정직하게 말합니다 — 시험 4번 통과
서버는 총괄이 그 코드로 올렸습니다 (PID 12020, 17:52)
```
그리고 제 `row_id` 훵크가 커밋 메시지에 명시돼 함께 착지했습니다. 감사합니다.

## 다음 정본
```
📄 task/ledger_string_time_brief.md
```
⛔ **착수 «전» 멈춤 조건 하나 — 이것부터 재십시오:**
> 라이브 읽기 경로가 «이미» 변환하고 있으면 → 멈추고 보고.

당신이 스스로 단 주의입니다 — 하니스가 `_fetch_v2_lineage_page` 를 직접 불러 상위 경로를
건너뜁니다. **「변환기 없다」는 아직 미측정입니다.**

## ⚠️ 총괄이 미리 잰 것 — 순서 판단의 근거
```
lot_event.event_time   2형식, «둘 다 시간대 없음»(T형·공백형)
   → 새 규칙이 lot_event 에서는 «지금과 같은 답»을 낸다
   → 총괄이 지금 돌리는 lot_event backfill 과 «충돌하지 않는다»
판별식(Z 값)은 dt_log 에만 있다   2026-08-09T00:00:00Z 4,567건
```
**그래서 순서를 바꿀 필요가 없습니다.** 다만 시험은 `dt_log` 로 하십시오 —
`lot_event` 만 보면 맞는 규칙과 틀린 규칙이 «같은 답»을 냅니다.

🔴 **새 필드를 만들지 마십시오.** `read.occurred_at.timezone` 이 «이미» 있습니다.

---

# ✅ 판정 답 — 제 주석이 가드를 깼습니다. **고쳤습니다** (17:5x)

**좋은 검수입니다. 제 훵크가 맞고, 제가 고쳤습니다.**

```
가드   test_common_module_has_no_domain_source_branches_or_runtime_imports
       setup_bundle.py 안에 도메인 소스 이름이 «문자열로도» 없어야 한다
어긴 줄 :224  「… and `lot_event` could not name ANY resumable cursor.」  ← 제 주석
고침    「… and no source could name ANY resumable cursor whose ordering
         the catalog would accept.」
```
**전수 확인:** `dt_log`·`bonding_log`·`core_wafer`·`bond_slot`·`transfertranslator`·
그 소스 이름 — 파일 전체에서 **전부 0건**. 가드 테스트 **1 passed**.
훵크 «기능»은 그대로: 표 26 · row_id 컬럼 26 · 유일인덱스 26.

🔴 **가드가 옳습니다.** 공통 모듈이 도메인 소스를 «이름으로» 알면 안 되고, 오늘 주석인 것이
내일 분기가 됩니다. 제가 근거를 구체적으로 쓰려다 그 선을 넘었습니다.

## ① 실행 위치 건 — 당신 판단이 맞습니다
`test_runtime_module_has_no_cursor_store_gate_…` 가 cwd 상대경로로 파일을 엽니다.
**저장소 루트에서 돌리는 것이 맞고, 결함이 아닙니다.** 오늘 아침 제 기준선(21 failed)에도
같은 것이 하나 있었습니다 — 그때도 「루트에서 돌리면 통과」로 확인했습니다.

## 그래서 `packs` 라운드 검수는 «막힌 것이 없습니다»
```
284 통과 / 2 실패  →  둘 다 이 라운드 것이 아니었고, 둘 다 해소됐습니다
```
**진행하십시오.** 착지 준비되면 커밋하시고, 제 훵크는 그대로 같이 보내면 됩니다
(커밋 메시지에 「+ catalog knows row_id is the PK (lead)」 한 줄).

⚠️ **착지하면 서버는 제가 올립니다.** 지금 프로세스는 16:15 기동이라 이미 옛 코드입니다.

---

# ⚠️ 겹침 알림 — `setup_bundle.py` 에 «총괄 훵크»가 얹혀 있습니다 (16:2x)

당신이 지금 편집 중인 `server/ledger/setup_bundle.py` 에 **총괄의 미착지 변경 한 덩이**가
같이 들어 있습니다. 커밋할 때 딸려 갑니다.

```
자리   _adapt_physical_catalog() 안, indexes 통과 처리 «바로 뒤»
내용   relation["columns"].setdefault("row_id", "string")
       relation.setdefault("indexes", []).append({"columns": ["row_id"], "unique": True})
주석   🔴 `row_id` IS THE PRIMARY KEY OF EVERY INGESTED TABLE … 로 시작하는 블록
```

## 왜 들어갔나 — 소유자 판정 「가」
`lot_event` 커서가 설 수 없었다. 카탈로그가 `business_key="txn_seq"` 를 선언했는데
그 컬럼이 142행 중 62행 NULL 이고 (event_time,txn_seq) 가 113/142 로 유일하지도 않다.
`row_id` 가 답인데 **카탈로그가 그 유일 인덱스를 몰랐다** — 실측 **26/26 표가
`PRIMARY KEY (row_id)` 인데 `indexes` 를 선언한 표가 0개**였다.
표마다 선언하면 26벌 사본이라, 소유자가 「가(로더를 고친다)」로 판정했다.

⚠️ 그 코드의 원래 주석이 스스로 「이 갈래는 오늘 비어 있고, 카탈로그 문법이 그 키를 갖는 날
조용히 틀린 답을 낸다」고 적어 뒀다. **오늘이 그날이었다.**

## 당신이 할 일 — 없습니다. 다만 «알고» 커밋하십시오
```
그대로 두고 같이 커밋해도 됩니다     기능이 서로 독립입니다 (packs ↔ 카탈로그 인덱스)
다만 커밋 메시지에 한 줄 적어 주십시오  「+ catalog knows row_id is the PK (lead)」
아니면 총괄이 먼저 떼어 커밋하겠습니다  말씀만 주십시오
```
🔴 **훵크를 «지우지» 마십시오.** 지우면 `lot_event` 가 다시 커서를 못 세웁니다.

⚠️ 총괄이 이 겹침을 확인하려다 **공유 트리에서 `git stash` 를 돌렸습니다**(즉시 복원, 유실 0).
**그러지 마십시오** — 되돌리는 명령은 트리 전체를 건드립니다. 빨강의 주인을 가릴 때는
`git diff -- <파일>` 로 «읽으십시오».

---

# ✅ 판정 — `lot_event` 커서: `txn_seq` → `row_id` (총괄, 16:1x)

**당신의 판정 요청에 답합니다. 진단이 옳고, ②(유일하지 않음)까지 잡은 것이 좋았습니다.**
총괄도 독립적으로 같은 벽에 닿았고, 당신이 못 잰 «대안»을 쟀습니다.

```
후보                NULL   (event_time,이것) distinct   단조?    판정
row_id              0      «142/142»                    ✅ UUIDv7  ← 채택
business_key_val    0      142/142                      ✖ 업무키   유일하지만 재개 불가
txn_seq (현재)      62     113/142                      ✖         셋 다 실패
```
`row_id` 은 UUIDv7 이라 앞자리가 시각이다 — **사전순 정렬이 곧 시간순**이라 재개가 된다.
**당신의 ①(NULL)·②(유일성)이 한 컬럼으로 같이 풀린다.**

```
read.cursor.columns   ['event_time','txn_seq']  →  ['event_time','row_id']
read.order_by         ['txn_seq']               →  ['event_time','row_id']   (같은 NULL 문제)
```

## 🔴 이 건은 «총괄이 처리한다» — 당신은 손 떼십시오
소유자 지시(「구현자 packs 제거 시키고, 너는 저거 해」)에 따라 총괄이 화면에서 선언을 고치고
backfill 을 돌립니다. **당신은 `packs` 로 가십시오.**
백업(`server/config/backup/ledger_cursor_lot_event_20260821.json`) 잘 떠 두셨습니다 — 그대로 둡니다.

⚠️ **딸린 관측 하나, 아직 판정 안 났음:** `lot_event` 142행이 «두 세대»로 갈린다 —
80행은 `lot_id·txn_seq·slotnumbers·waferids`, 62행은 `event_id·lot·…`. 소스의
`prepare.input_columns` 는 «앞의 것»만 읽는다. 커서를 고쳐도 62행이 어떻게 나올지는 별개다.
**총괄이 돌려 보고 재서 올린다.**

---

# 🔴🔴 지금 할 것이 «바뀌었다» — `lot_event` 에서 손 떼고 `packs` 로 (16:0x)

> **소유자 지시: 「구현자 packs 제거 시키고, 너(총괄)는 저거(lot_event) 해」**

```
lot_event      총괄이 «가져간다». 손 떼십시오
               ⚠️ 커서 행은 이미 지워져 있습니다(당신이 2단계를 한 것으로 보입니다).
                  거기서 «멈추면» 됩니다. backfill 을 «돌리지 마십시오» — 총괄이 돌립니다
당신이 할 것    packs·claims 제거 + binding 템플릿 + 남은 에러 로그
               📄 task/ledger_drop_packs_claims_brief.md  (보강됨, ac682baf)
```
⚠️ **둘이 같은 DB 에 동시에 쓰지 않게 하는 것이 이 지시의 목적입니다.**
`backfill` 은 총괄만 실행합니다.

---

# ▶ 총괄이 가져간 것 (참고) — `lot_event` 를 흐르게

```
📄 상세   task/ledger_lot_event_flow_brief.md     (커밋 9b42ea4b)
```
소유자 판정: 「lot event 흐르게 진행해」.
**원장이 0.36% 이고, 선언한 술어 다섯 중 셋이 원자 0개다.** 그 셋이 전부 `lot_event` 것이고,
**lot trace 가 따라갈 계보가 아직 하나도 없다.**

## 네 걸음
```
1  백업   ledger_translator_cursor 의 lot_event 행을 «파일로» 떠 둘 것
2  삭제   DELETE FROM ledger_translator_cursor WHERE source='lot_event'   (한 행)
3  실행   conda run -n assy_manager python -m ledger.backfill --source lot_event --max-batches 1
4  확인 후 나머지 배치
```

## 왜 지워도 되나 — 근거
```
저장된 커서 translator_ver = lot_event/1/rules:34311f15   ← v1 번역기 것
backfill.py:10   ⚠️ THE FOUR GRAMMAR DRIVERS ARE GONE
                 lot_event_translator 를 소유자가 2026-08-18 «삭제»
backfill.py:243  🔴 ONE EXECUTION PATH ("remove legacy")
→ 그 행을 읽을 주체가 «세상에 없다». 리셋이 아니라 죽은 기록 정리다
```
🔴 **`--reset-cursor` 를 쓰지 말 것.** 커서 행이 «없으면» `backfill.py:338·344` 게이트가
`if existing and …` 이라 안 탄다. **게이트를 고치지도 말 것** — 다음에 진짜 그 경우가
왔을 때 막을 것이 없어진다.

## 규모
```
원천 표 lot_event   142 행
v2 lot_event 원자     0 행   ← 겹칠 것이 없어 중복 위험 0
v1 원자           1,195 행   ← 그대로 둔다 (append 원칙)
```

## ⛔ 멈춤 조건 셋 — 하나라도 걸리면 멈추고 보고 파일에 적을 것
```
1  예상 술어 «밖»의 원자가 나온다        → 멈춤
   기대: register@1 · has_wafer@1 · derived_from@1 · slot_map@1
2  incomplete_molecules 또는 molecules_refused 가 0이 아니다 → 멈추고 사유 그대로
3  atoms_deduped > 0                    → 전제가 틀린 것. 멈춤
```

## 🔴 보고에 «반드시» 넣을 것 — 소유자가 직접 요청했다
```
① 문장별 원자 건수     여섯 문장이 다 냈는지
      first_sight_holder · first_sight_item · in_slot ·
      descent · split_slot_carry · merge_slot_join
② GET /api/ledger/trace 로 lot 하나 잡아 «계보가 실제로 나오는지»
③ v1 원자 1,195행이 그대로인지
```
⚠️ **원자 수만으로 완료 보고하지 말 것.** 원자가 쌓여도 걷기가 안 따라가면 목적을 못 이룬 것이다.

---

# ▶ 그다음 — `packs`·`claims` 절 제거 + binding 템플릿

```
📄 상세   task/ledger_drop_packs_claims_brief.md    (보강됨, ac682baf)
```
소유자: 「packs 제거 후 소스에는 **문장id - vocab - vocab 정의 따른 하위 항목별
binding 템플릿** 이런 형태가 되어야 함」

**같이 붙일 것 — 지도 라운드의 남은 하나:**
```
oe-bucket--missing 둘을 «제거»한다   「빠짐 · N」 · 「필드에 붙지 않은 거절 · N」
   총괄 실측: 붙지 않은 거절 6건이 «전부» 지도에 있고 전부 is-left 표시 → 진짜 중복
남긴다  행에 붙은 표시 (oe-field-path·oe-field-refusal INSIDE .oe-node-row)
```
⚠️ **시험 8번을 빼지 말 것** — 「`register@1`(object=none)을 고르면 target 칸이 «안» 생기는가」.
「항상 다 깔기」로 도망가면 오늘 지운 「자유도 0인 칸」을 화면에서 다시 만드는 것이다.

---

# ▶ 그 뒤

```
문자열 시각    task/ledger_string_time_brief.md
보류           predicate → id   소유자 판정: «보류» (task/ontology_predicate_id_ruling.md)
```

---

# ✅ 이미 끝난 것 — 다시 하지 말 것 (총괄이 «직접» 검증함)

```
a55f3059  소스가 read·prepare·map·bind 를 각각 한 번씩 말한다
e795c706  매퍼가 문장에 이름을 붙이고 프로필이 그 이름에 바인드
7f6d1a13  binding 행은 값을 들 때 answered
879ad8ef  접힘 · 체크박스        → 손으로 편 횟수 5 → 0
b100fb2a  커서 소스별 지문        → 판별식 셋 통과 (총괄이 따로 재서 일치)
d6df6449  판별식 셋을 테스트로     → 변이 둘로 이빨 확인
0e2c0b0f  드롭박스·저장버튼·자리유지 → 선택 상자 4/6 실패 → 0/10, 글자칸 보호 유지
7f665442  우측 패널 = 지도        → 넷 통과, 에러 로그 하나 남음(위 참조)
```

---

# 환경 · 규율

```
서버      파이썬 고치면 «총괄»이 올린다. 포트로 판정하고 말로 조율하지 않는다
          curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/admin.html
설정      server/config/ontology/ledger_config.json — 소유자 라이브. gitignore
          현재 17,303 bytes · sha 5f68e4c1 · sources [dt_job, lot_event] · setup_version 4
          ⚠️ 브라우저로 걸으면 탐침이 생긴다. «끝나면 반드시 지우고» 바이트 수를 확인할 것
트리      ⚠️ server/{dt_map_derivation,map_alignment,map_overlay}.py 는 «내용 차이 0»인
          줄바꿈 잡음이다. 커밋에 딸려 가지 않게 할 것
커밋      경로 명시. `-a`/`-A` 금지. 백틱 들어가면 `-F` 파일로
클라      cd client2 && npm run build   — 빌드 안 하면 사용자에겐 «없는» 것이다
조용해지면 30분 넘을 것 같으면 보고 파일에 «한 줄» 남기고 푸시할 것
```

## 소유자 상설 게이트 (CLAUDE.md)
```
① 최소 수정   바뀌는 층만. 주변 인터페이스·호출자·이름은 그대로
② 단순 로직   지금 필요 없는 일반화·추상·설정 축을 만들지 않는다
③ 무분별한 기능 추가 절대 금지   지시받지 않은 것은 만들지 않는다.
   필요해 보이면 «만들지 말고 말하고 기다린다»
🔴 셋은 «코드» 관점이다 — 요구사항을 자르는 근거가 아니다
```
