# Doc repair — the "three deliberately left shapes" block after `92547c3`

Scope kept: **`docs/spec/LEDGER_TECHNICAL_SPEC.md`** and **`docs/guide/LEDGER_GUIDE.md`** only.
`LEDGER_RULINGS.md`, `PROJECT_STATUS.md`, `PRIMITIVES.md`, `CODE_MAP.md`, `docs/README.md` and everything
under `server/**` / `client2/**` were **read only**. Nothing committed, staged, stashed. No database touched.

---

## 0. WHERE THE CODE DISAGREES WITH WHAT WAS WRITTEN ABOUT IT (read first)

### ⚠️ A — a sentence the commit falsified that neither the commit message nor `RHbis_three_siblings.md` named

Both the spec (§3.3-bis table) and the guide (§1.1 translator row) carried:

> **일방향 문은 `translate` 하나** — `lot_event_translator.translate`가 `try/except MoleculeRefused`로
> 예외를 **다시 값으로** 바꾸는 유일한 자리다.

**That is now false.** There are two, at different layers:

| 자리 | 무엇을 잡나 | 값으로 |
|---|---|---|
| `server/ledger/lot_event_translator.py` — `translate`의 `except` | 번역기가 **원자를 만드는 도중** 낸 거절 | `(None, report)` |
| `server/ledger/backfill.py` — 분자 루프의 `except gate.MoleculeRefused` | **게이트 심사(`screen_molecule`)**가 낸 거절 | `refused = True` + `_forget_registers` |

The lane's report §3 says only *"Its `try` / `except gate.MoleculeRefused` stays — that is `f313279`'s
one-way door and the ruling does not touch it"*, which is true of the translator and silent about the
new second door. **This is not a defect**: the driver's handler sits *outside* `pending.extend(kept)`, so
an unwind cannot leave atoms behind, and the arm counts the molecule as refused. But the invariant as
the docs stated it ("exactly one place") no longer describes the tree, and the invariant that actually
holds is different — *no swallowing expression exists below **each** door*. Rewritten that way in the spec.

🔴 **The same false sentence exists twice in `PRIMITIVES.md` and is outside my edit scope** — see §2.

### ✅ B — claims I re-measured rather than inherited; all held

| 주장 | 실측 |
|---|---|
| `with gate.building_molecule(` in production: 1 before / 1 after | **1** — `server/ledger/backfill.py:252`. ⚠️ a second grep hit, `lot_event_translator.py:352`, is **inside the `RuntimeError` message string**, not a scope |
| translator classes | **1** — `LotEventTranslator`, `lot_event_translator.py:188` |
| callers of `backfill.run` | its own CLI `main()` (`backfill.py:409`) + **7** call sites in `server/tests/test_ledger_l1_pg.py`. **Daemons / routes / workers / scheduler: 0** (no module outside `server/ledger/` imports it; every other `backfill` hit in `server/` is `enrichment_backfill`, unrelated) |
| production callers of `screen_molecule` | **1** — `backfill.py:256`, inside the scope |
| `_advance_cursor` extension | present and required-keyword, `store.py` — and `LEDGER_RULINGS.md:270` already records it as **approved** |

**No place found where the code contradicts the commit message.** The message's own two corrections
(item ① narrower, item ③ a relocation that wires nothing) match the tree.

---

## 1. Every location found

### Edited (in scope)

| 위치 | 무엇이 틀렸었나 | 무엇을 했나 |
|---|---|---|
| `docs/spec/LEDGER_TECHNICAL_SPEC.md` — 헤더 배지 | `Last-verified: 2026-08-13` | `2026-08-14 (R-H-bis 착지 92547c3)` + 「이번 라운드」 신설, 직전 라운드로 강등. 뒤집을 때 틀리기 쉬운 둘(①의 좁음 · ③의 미배선)을 배지에 명시 |
| 〃 §1.5-bis 표 | `reasons` 계약 없음 | 행 추가 — `write_batch`·`_advance_cursor` 둘 다 **키워드 전용 필수**, 명시적 `None`도 `TypeError`, 정당한 값은 명시적 `{}` |
| 〃 §3.3-bis 표, `building_molecule` 행 | 누가 여는지 안 적혀 있었다 | **공유 드라이버(`backfill.run`)가 연다**, translate와 screen을 같은 스코프에, `_build` 단언은 **둘째 그물** |
| 〃 §3.3-bis 표, 「일방향 문」 행 | §0-A | 문이 둘·층이 다름 + 실제 불변식으로 재작성 |
| 〃 **§3.3의 「의도적으로 남긴 모양 셋」 블록** | **셋 다 거짓** | 자리에는 **은퇴 표지 + 옛 셋이 무엇이었는지**를 남기고(검색으로 도달하는 사람을 위해) 본문은 **§3.3-ter 신설**로 이관 |
| 〃 **§3.3-ter 신설** | — | 3열 표(옛 문장 / 지금 / 🔴 **그대로 뒤집으면 틀리는 지점**) + 「③은 착지했으나 배선되지 않았다」 단락(번역기 1·호출자 CLI `main()`뿐·값어치는 미래의 `RuntimeError`) + 「①은 단위 테스트만으로 정착 안 된다」 단락(주입 시 게이트 2 대 드라이버 0 → `refusals_unaccounted` 음수) |
| 〃 §3.3-bis 증명 방법 문단 | 방법이 반쪽 착지만 | ⚠️ **「예외가 던져진다」는 공유 주입 하네스 «안에서» 못 주장한다**(둘 다 `AssertionError`를 성공으로 침) + 단언은 `pytest.raises` 블록 **밖**에서 `caught.value`에 |
| `docs/guide/LEDGER_GUIDE.md` — 헤더 | `Last-verified` · 라운드 | `2026-08-14` + 이번 라운드 신설(직전 강등) |
| 〃 §1.1 `gate.py` 행 | 심사 거절이 값이라고 읽힌다 | 거절 팔만 예외 · **「할 말 없음」의 `[]`는 반환 유지** · 스코프는 드라이버가 연다 |
| 〃 §1.1 `lot_event_translator.py` 행 | 「이 파일이 스코프 안에서 돈다」 + 일방향 문 하나 | **열지 않고 «요구»한다** · 안 열면 `RuntimeError`(메시지가 누가 여는지와 철자를 댄다) · 문이 둘임을 spec으로 링크 |
| 〃 §1.1 `store.py` 행 | `reasons` 없음 | 필수 키워드 인자 + 명시적 `{}` |
| 〃 §1.1 `backfill.py` 행 | 스코프 소유가 안 적혀 있었다 | **분자 스코프를 여는 자리**로 명기 + ⚠️ **오늘 이 드라이버를 부르는 것은 자기 CLI `main()`뿐** |
| 〃 §2 쓰기 경로 그림 | `kept[] (또는 [])` — 거절과 무발화가 한 칸 | 스코프를 **그림에** 그렸다(`with` 안에 translate+screen, `except`가 아래로) + 거절/무발화 구분 + `write_batch(…, reasons=…)` |
| 〃 §2.2 | 심사 거절이 아직 반환값 | 문단 추가 — 심사도 같은 문법 · ⚠️ **「이제 언제나 raise」로 읽지 말 것** · 단위 테스트만으로 안 되는 이유(게이트 2 대 드라이버 0) |
| 〃 **§3 ③ 「번역기 작성 — `lot_event_translator`의 모양을 그대로」** | 🔴 **가장 위험했던 자리.** 베낄 모양이 `with`를 들고 있던 시절 그대로라, 지시대로 베낀 두 번째 작성자가 **오늘 `RuntimeError`를 맞는다** | 첫 항목으로 **「스코프를 열지 마라」** 신설 + 손으로 모는 호출부용 2줄 철자 + 「이 문장 하나가 오늘 이 항목의 전부」(번역기 1·CLI만) · 심사 거절은 반환값이 아니라는 항목 추가 · 클래스 스케치 주석 |
| 〃 §3 ⑥ 검증 기대치 표 | — | 행 둘 추가 — 손으로 몰 때 스코프를 연다(**양팔 다** 태울 것) · 「예외가 던져진다」는 주입 하네스 안에서 못 주장 |

### Found and deliberately NOT edited

| 위치 | 상태 | 왜 안 고쳤나 |
|---|---|---|
| `docs/architecture/PRIMITIVES.md:1084` | 🔴 **거짓** — 「일방향 문은 `lot_event_translator.translate` 하나」 | **편집 범위 밖**(지시서: 두 파일만). 평소엔 내 전담 파일이라 **총괄 승인 한 줄이면 즉시 고친다** |
| `docs/architecture/PRIMITIVES.md:1092` | 🔴 **거짓** — 함정 줄 「일방향 문은 «하나»여야 한다 … 정확히 하나(`translate`의 `except`)」 | 〃. **원칙 자체는 살아 있고 철자만 바뀐다** — 「각 문 아래에 삼킬 표현식이 없어야 한다」 |
| `docs/architecture/PRIMITIVES.md:1093` | 🔴 **거짓** — 「⚠️ 두 번째 구현자는 «스코프를 열어야만» 물려받는다 … 알려진 잔여 위험으로 적어 둔 것이다」 | 〃. R-H-bis 3이 정확히 이 위험을 닫았다. **카탈로그가 이제 「미해결」이라고 가르친다** |
| `docs/architecture/CODE_MAP.md:2282` | 🟠 낡음 — `screen_molecule(...) -> (kept, report)` 시그니처에 `declared_subject_types` 없음(R-D 때부터)이고 **raise 갈래 없음** | **code-mapper 소관**(2026-07-27 분할) |
| `docs/architecture/CODE_MAP.md:2325` | 🟠 낡음 — `write_batch(..., refused=0, incomplete=0)`에 `reasons` 없음 | 〃 |
| `docs/process/LEDGER_RULINGS.md:249-272` | ✅ **이미 정확하다** | 별도 세션 소유(지시). 확인만 했다: `:265`의 마감 문단이 ①의 좁음·③의 이동/미배선·`_advance_cursor` 승인을 **전부** 정확히 적고 있다. **내가 쓴 두 문서가 그 판정문과 어긋나지 않게 맞췄다** |
| `docs/process/PROJECT_STATUS.md:53·119-131` | 🟠 낡음 — R-H-bis 3건이 아직 **⏸ 대기열**로 서 있고 `04bc0ce`(판정 커밋)를 달고 있다. 구현은 `92547c3` | **총괄 전담.** ⚠️ `:124-131`의 항목 ①②③은 **판정 원문**이라 그 자체로 틀린 것은 아니지만, ①을 「예외로 통일」로만 읽으면 **무발화의 `[]`까지 예외화**하게 된다 — 옮길 때 §3.3-ter의 셋째 열을 같이 실어 주기를 권한다 |
| `docs/README.md:53` 원장 행 | 🟠 부분 — 「5차」까지만 서술(R-H는 있고 R-H-bis는 없다) | **편집 범위 밖.** 서술 자체는 아직 거짓이 아니다(R-H 이야기를 하고 있다). 한 줄 추가 권고 |
| `docs/qa/FEATURE_CHECKLIST.md:204` (L1-bis) | 🟢 아직 참 | 점검 항목은 전부 유효하고, ⑤가 이미 **하네스가 `AssertionError`를 성공으로 친다**를 싣고 있다. ⚠️ 다만 **「손으로 모는 테스트는 스코프를 연다」** 항목이 없다 — 있으면 좋다(그 파일은 이 라운드에 **다른 레인이 수정 중**이라 손대지 않았다) |
| `docs/guide/LEDGER_GUIDE.md:229` · `spec §3.5-bis` 「`screen_molecule`의 넷째 인자는 필수」 | 🟢 참 | R-D 이야기이고 이번 변경과 무관 |
| `docs/history/20260813_140756_...md:70` 「의도적으로 남긴 것」 | 🟢 그대로 둔다 | 히스토리는 **append-only**이고 그날의 사실이다. doc-historian 소관이기도 하다 |
| `docs/process/SCENARIO_CONSOLE_BRIEF.md:86-87` | ⚪ 정보성 | 「G3가 R-H-bis의 스코프 구조를 쓴다」 — 착지했으므로 오히려 참이 됐다 |
| `server/ledger/*.py` docstrings | ✅ **이미 정확하다** | `gate.py`·`backfill.py`·`lot_event_translator.py`·`store.py` 넷 다 이번 커밋에서 함께 고쳐졌고, **닫힌 결함을 현재형으로 서술하는 문장이 남아 있지 않다**(PRIMITIVES §7의 그 함정 항목 기준으로 확인) |

---

## 2. 총괄께 — 판단이 필요한 것

1. 🔴 **`PRIMITIVES.md` 세 줄이 지금 거짓을 가르친다**(`:1084`·`:1092`·`:1093`). 그 파일은 **에이전트가 매 착수마다 읽는 A등급 문서**라 우선순위가 높다. 이번 지시서가 두 파일로 못박았기에 손대지 않았다 — **한 줄 승인이면 바로 고친다.** 특히 `:1093`은 **닫힌 위험을 「알려진 잔여 위험」으로** 적고 있어, 다음 사람이 이미 있는 구조를 다시 만들 자리다.
2. 🟠 **`CODE_MAP.md` 두 줄**(`:2282`·`:2325`) — code-mapper 라운드에 실어 주십시오. `write_batch`는 **시그니처가 실제로 바뀐** 자리라 코드맵이 그대로면 호출부를 짜는 사람이 `TypeError`를 만난다.
3. ⚪ **보드**: R-H-bis 항목을 ⏸ 대기열에서 내리실 때 커밋은 `92547c3`(판정은 `04bc0ce`)이고, ③은 **「착지·미배선」**으로 적는 것이 정확합니다.
4. ⚪ **`docs/README.md`** 원장 행에 R-H-bis 한 줄 — 다른 레인이 그 파일을 만지고 있지 않다면 다음 라운드에 넣겠습니다.
5. ✅ **SSOT(`SYSTEM_OVERVIEW.md`) 무변경** — 이번 변경은 프로세스 토폴로지도 경계 계약도 건드리지 않습니다(원장은 여전히 어느 부팅 경로도 import하지 않습니다).
6. 💡 **PRIMITIVES 갱신 제안(직접 추가 안 함)**: §7 「거절을 반환값으로 신호하지 마라」 항목에 함정 한 줄 —
   *🔴 **스코프를 «누가 여는가»가 그 규칙이 구전인지 구조인지를 가른다.** 조립하는 쪽이 열면 두 번째 작성자는 그 파일을 읽고 «알아채야» 물려받는다. **분자를 도는 공유 루프**가 열면 규칙이 구조가 된다. ⚠️ **다만 그 이전은 「착지」이지 「배선」이 아니다** — 오늘 그 드라이버를 부르는 호출자 수를 세어 함께 적어라.*
