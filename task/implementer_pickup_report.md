# 구현자 인수 — 컴팩트 직전 상태 (2026-08-20)

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

**아직 안 본 것: 1·2·3·6·7번.** 특히 **3번**(매퍼 후보 = relation ∪ 준비기.output_columns)과
**7번** backfill. 그리고 **경로 후보 제거**.

⚠️ 마지막 측정에서 트리 행 68개는 떴는데 `preparation`·`mapper` 이름을 못 찾았다.
**이건 결함이 아니라 내 선택자가 틀렸을 가능성이 높다** — 이름은 `.oe-node-label` «안»에 있고
`:scope > .oe-node-name`으로 찾았다. **결함으로 적기 전에 선택자부터 고쳐 다시 셀 것.**

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
