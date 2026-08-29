# ✅ [A 구현자] **둘 다 착지 — `1c0925ca`. 그리고 «빈 DB» 게이트가 셋째를 물고 나왔습니다** (2026-08-29 11:5x)

## ① 인덱스 — 코드가 라이브를 «묘사하게» 했습니다
```
전   DEDUPE_COLUMNS = (… "subject_keys", "coalesce(object_payload,'{}'::jsonb)", …, "source_raw_ref")
후   DEDUPE_COLUMNS = (… "md5(subject_keys::text)",
                        "md5(coalesce(object_payload,'{}'::jsonb)::text)", …, "md5(source_raw_ref)")
길이 «7» 그대로 -> envelope.py 의 identity 거울과 그 시험(test_ledger_l1_unit.py:126) 안 건드려짐
⛔ DROP/재생성 «0» · md5 충돌 가드 «0» (지시대로)
```
지시하신 「사실은 주석에」는 그대로 남겼습니다 — 유일성이 이제 «다이제스트 기준»이고,
`insert_atoms` 의 `ON CONFLICT DO NOTHING` 이 무표적이라 충돌하면 «조용히 버려진다».

### 게이트 ① — 빈 DB에서 만들어 «문자열로» 비교
눈으로 「같아 보인다」 금지라 하셔서 `pg_indexes.indexdef` 를 둘 다 뽑아 `==` 로 비교했습니다.
```
LIVE   CREATE UNIQUE INDEX uq_ledger_atom ON ONLY public.ledger_events USING btree
       (occurred_at, predicate, subject_type, md5((subject_keys)::text),
        md5((COALESCE(object_payload, '{}'::jsonb))::text), source_translator_ver, md5(source_raw_ref))
FRESH  «완전히 동일한 문자열»
EQUAL  True
```
🔴 **임시 DB(`assy_uqidx_probe`)를 만들어 쓰고 «지웠습니다».** 라이브 DB에는 이 게이트로
   한 바이트도 안 썼습니다(라이브에서는 `pg_indexes` 를 «읽기»만).

### 게이트 ② — 라이브에 `ensure_schema` -> 변화 «0»
스냅샷 → 실행 → 스냅샷으로 «수»로 확인했습니다(「안 바뀐 것 같다」 금지).
```
ledger_events + ledger_translator_cursor 의 인덱스   전 «9» · 후 «9»
added «none» · removed «none» · changed «none»       -> CHANGE 0: True
```

### 🔴 게이트 ①이 물고 나온 셋째 — 보고만 하고 «안 고쳤습니다»
```
빈 DB에서 ensure_schema 가 «죽습니다»:
   psycopg2.errors.UndefinedObject: "gin_trgm_ops" ... (gin 접근 방법에 없음)
   -> schema.py:361 의 trigram 인덱스가 «pg_trgm 확장»을 요구하는데,
      ensure_schema 안에 CREATE EXTENSION 이 «없습니다»
라이브   확장이 이미 깔려 있어 «안 보입니다»
새 환경   uq_ledger_atom «앞에서» 통째로 멈춥니다 — 이번 라운드가 고친 것과 «같은 부류»입니다
          (라이브에 있어서 안 보이는 전제)
제가 한 것   프로브에서만 `CREATE EXTENSION IF NOT EXISTS pg_trgm` 을 «먼저» 깔고 쟀습니다.
             그래야 게이트 ①이 답을 냅니다. 코드는 «안 건드렸습니다» — 지시 밖입니다
```
👉 이건 판정이 필요합니다: `ensure_schema` 가 확장을 스스로 깔지, 배포 문서가 전제로 적을지.

## ② 고아 상수 셋 — 다시 세고 지웠습니다
지시대로 «한 번 더» 세었고, 심볼 훑기의 사각(문자열 조립·`getattr`)까지 봤습니다.
```
훑은 범위   server · client2 · contracts · docs · task   (.tmp · _archive · .codex_tmp · worktree 제외)
결과        NODE_TABLE_COLUMNS 5 · EDGE_TABLE_COLUMNS 5 · PROPERTY_TABLE_COLUMNS 5
            그런데 «코드 히트는 각 1건»(자기 선언)이고 나머지 넷은 전부 «산문»입니다:
              CODE_MAP.md ×2 · PROJECT_STATUS.md ×1 · IMPLEMENTER_ORDERS.md ×1
문자열 조립  `"..._TABLE_COLUMNS"` · `getattr(...)` 로 이 이름을 부르는 자리 «0» (라이브 트리)
=> 코드 소비자 «0» 확인. 13줄 삭제
```

## 게이트 ③ — 이 파일들을 지나는 시험
```
tests/test_ledger_l1_unit.py + tests/test_ledger_subgraph.py   64 passed · 1 failed · 1 skipped
수집                                                            4,256 «그대로»
```
### ⚠️ 그 빨강 하나는 «제 것이 아닙니다» — 대조군으로 갈랐습니다
```
test_ledger_l1_unit.py::test_the_shipped_declaration_carries_the_product_owner_ruling
   E  KeyError: 'occurred_at_timezone'   (assert declared["occurred_at_timezone"] == "Asia/Seoul")
대조   제 두 파일을 «HEAD 로 되돌리고» 같은 시험 -> «똑같이 실패»
=> 선언의 키에 대한 것이고 schema.py · ledger_subgraph.py 어느 쪽도 그 키를 안 만집니다.
   안 고쳤습니다 — 다른 자리의 판정입니다
```
