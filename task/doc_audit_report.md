# Doc Audit — 2026-08-21 night, after the three-agent sync round

> **Auditor:** doc-auditor (read-only). No doc, source or config was modified.
> **Measured against:** working tree at `e383b3a`, live `server/config/ontology/ledger_config.json`
> (`setup_version: 5`, top keys `[setup_version, vocabulary, entities, sources]`).
> **Scope:** the four commits of tonight's sync round (`d098a7c5`, `cd6b1955`, `7eb11dde`,
> `11562872`) plus the four rot sites named in the brief.

## Verdict: **CONDITIONAL**

The three agents' own output is the *cleanest* part of the corpus — every anchor doc-keeper
registered tonight resolves, and the SSOT edit is correct. What fails is the **reading path
into the corpus**: the documented entry point (`docs/README.md`) marks a closed plan
directory as Living, and the handover doc it calls 정본 puts a file teaching
`setup_version: 2` on the mandatory start-of-work reading list. A new session is armed with
the retired grammar before it reads a line of code.

One finding is a live code fault, not doc rot: six read-side routes return 503 because the
resolver falls back to a v1 sample.

---

## Findings, ranked by how likely someone acts wrongly on them

### 1. `FORK_SESSION_BRIEF.md:97` puts a `setup_version: 2` document on the mandatory reading list — `fix`

`docs/process/FORK_SESSION_BRIEF.md` §3 「먼저 읽을 정본」 lines 95–97:

```
4. `ledger_v2_redesign_plan_20260817/README.md`
5. `ledger_v2_redesign_plan_20260817/00_MASTER_PLAN.md`
6. `ledger_v2_redesign_plan_20260817/CONFIG_CANON.md`
```

`CONFIG_CANON.md:39` reads `"setup_version": 2,` and `:62-71` lists seven sections
including `packs` and `profiles`. `:99` teaches `profiles.use → packs/claim`. Measured
live: `setup_version` is **5** and the sections are **three**
(`server/ledger/setup_bundle.py:20` `SETUP_VERSION = 5`;
`LOGICAL_SECTIONS = ("vocabulary", "entities", "sources")`).

Item 3 on the same list — `docs/guide/ONTOLOGY_LEDGER_SETUP.md` — is correct and says the
manifest shape 은퇴했다. **The brief hands the reader the right doc and then three that
contradict it, and the wrong ones are read last.**

`docs/README.md:14` marks this brief 🟢 「현재 인수인계 정본」, so this is an A-trigger
pointing at C-grade content. This is the single change worth making before another session
starts.

### 2. `CODE_MAP.md:2278` — the boot-path claim is false, and the module count that would have caught it is short by eight — `fix`

The claim (refreshed lane, `a729a7f` baseline):

> **부팅 경로 무접촉이라는 의도된 뜻은 여전히 참이다** — import가 함수 안에 있어 웹 서버
> 기동은 `server/ledger/`를 열지 않는다.

Measured. `server/ledger_selection.py:13` is a **module-scope** import (verified with
`cat -A`, zero indentation):

```python
from ledger import vocabulary as ledger_vocabulary
```

and `server/ledger_trace_router.py:30` imports `ledger_selection` at module scope, and
`server/main.py:179` imports the router. Booting the web server opens `server/ledger/`.

The same line says the router imports 「읽기 측 **7모듈**」 and names seven. Measured:
**15** module-scope imports (`ledger_trace_router.py:22–36`). The eight it omits are
`enrichment_actions`, `ledger_catalog`, `ledger_composition`, `ledger_explorer`,
`ledger_journey`, `ledger_selection`, `ledger_subgraph`, `ledger_trends` — and
`ledger_selection` is precisely the member that falsifies the sentence next to it. The
count and the assertion are one defect.

`docs/process/OPERATOR_RUNBOOK.md:118` already retracted this exact claim on 2026-08-18
(「종전 이 자리의 근거였던 «부팅 시 `server/ledger`를 import하는 프로세스가 없다»는
«거짓»이 됐습니다」) and writes out the same chain. Two docs, opposite answers, and the
retraction is three days older than the assertion. Same stale claim also lives in source at
`server/ledger_trace_router.py:53-55`, which cites a runbook note that no longer says that.

### 3. `docs/README.md:23` and `SYSTEM_OVERVIEW.md:188` present a closed plan directory as current — `archive`

`docs/README.md:23` lists `ledger_v2_redesign_plan_20260817/README.md` in the 🟢 block,
whose legend is 「Living(최신·검증됨)」, described as 「승인된 원장 설정/compiler 구조」.

`SYSTEM_OVERVIEW.md:188` links twelve files from that directory, naming
`CONFIG_CANON.md` **「config 정본」** and `TARGET_ARCHITECTURE_AND_SSOT.md`
**「목표 구조/정본」** — in the same table cell that correctly states
`setup_version: 5` with the `relation·read·prepare·map·bind` clause. One cell asserts the
current shape and calls canon a file asserting the retired one.

Four further docs call `TARGET_ARCHITECTURE_AND_SSOT.md` 정본:
`LEDGER_FRAME_CHAIN_MAPPER.md:14`, `guide/config/virtual_join_rules.md:33`,
`spec/LEDGER_TECHNICAL_SPEC.md:838`, `process/DOC_OWNERSHIP.md:419`. That file's §2/§8 name
five config paths, four of which do not exist on disk
(`server/config/ontology/manifest.json`, `catalog/tables.json`,
`catalog/virtual_joins.json`, `dataflows/chains.json`).

Grading of all 26 files in that directory is in the table at the end: **A = 0, B = 5,
C = 21**.

### 4. Six read-side routes return 503 because the resolver falls back to a v1 sample — **code fault**, `fix` (not a doc defect)

Reproduced by running the loader:

```
LOAD RAISED: LedgerConfigError '…/server/config/sample/ledger_config.json.sample
  .profiles["dt-job@1"].mappings[0].use: pack 'dt-job@1' is not declared in packs [unknown_pack]'
```

Chain, each anchor resolved to its enclosing function:
`ledger_trace_router.py:112` calls `ledger_trace.trace()` with no `config=` →
`ledger_trace.py:1330` `load_resolver_config()` → `:355` folds in
`_declared_inference_derivations()` → `:383` `ledger_config.load()` →
`server/ledger/config.py:357` `load()`, whose `config_path()` is
`server/config/ledger_config.json` (**absent**) → `:359-368` falls back to
`server/config/sample/ledger_config.json.sample`, measured `setup_version: 3` with
`packs`/`profiles` → refused at `source_profile.py:972`.

Affected: `/trace` `/explore` `/explore_entity` `/journey` `/structure` `/coverage`.

Two defects, and fixing the path alone is not enough: the v5 config is reachable only
through `ledger.setup.DEFAULT_ONTOLOGY_ROOT` and `server/ledger/config.py` has no path to
it; and the fallback sample is internally inconsistent —
`_parse_pack_reference` (`source_profile.py:1018-1029`) `rpartition("@")`s `"dt-job@1"` to
`"dt-job"` while `_parse_use_reference` (`:1032-1039`) splits only on `/` and yields
`"dt-job@1"`, so the comparison at `:970` is permanently false.

**No doc names this.** `docs/guide/LEDGER_GUIDE.md:259-260` prescribes
「`coverage → structure → trace` 순서로 확인한다 … `absent`·`empty`·`ready` 상태를
구분한다」 — all three are in the 503 set, so an operator following the guide gets three
config refusals and never reaches the distinction the sentence is about.

### 5. `docs/guide/ledger/PRIMER.md` teaches `PACK` and `use` as live, and nothing in the live corpus links to it — `archive`

`PRIMER.md:30` row 6: 「**PACK** | 표준 문장 양식집 | Claim의 빈칸(role)을 받아 payload
철자로 컴파일」. `:25` row 3 teaches 「use lineage/split」. Both retired 2026-08-21 —
`setup_bundle.py:1088-1092` 「`packs` WENT THE SAME WAY on 2026-08-21 … AND `use` BECAME
`predicate` THE SAME DAY」; `setup_bundle.py:424 def predicate_claim` 「THIS FUNCTION IS
WHAT `packs` USED TO BE」. Header still reads `Status: 🟢 Living · Last-verified: 2026-08-19`.

**Verdict is `archive`, not `fix`, and the reason is the trigger.** Inbound links measured
across the whole repo: `_archive/ledger_setup_migration_plan/{README,00_MASTER_PLAN,
03_DICTIONARY_CAPABILITIES}.md` and one `docs/history/` entry. **Every document that calls
PRIMER 정본 is itself archived.** Nothing in the live corpus opens it, which is why it went
two days stale carrying a 🟢 badge. Repairing it buys a document nobody has a reason to
read; the honest options are archive it, or give it a trigger and then repair it.

### 6. `LEDGER_FRAME_CHAIN_MAPPER.md:109` describes a deleted file in the present tense — `fix`

> `server/mappers/ledger_lot_event_mapper.py`가 Ledger reader가 넘긴 논리 행을 사건별
> pandas frame으로 묶고 …

Deleted by `cac3acaa` (「drop the retired lot-event registration from the mapper
registry」); present only in `.claude/worktrees/`. The document has a 2026-08-21 correction
banner at :16, but it covers `profile_id`/`profiles`/`binding_origin` only — line 109 sits
below it, unlabelled.

`docs/process/DOC_OWNERSHIP.md:17` already states 「없는
`server/mappers/ledger_lot_event_mapper.py`를 실재하는 셋으로 교체」. One doc knows the file
is gone; its sibling still teaches it. The doc is `Status: FROZEN_FOR_REDESIGN ·
NOT_APPROVED` and its 「재개 정본」 pointer is the plan directory from finding 3, so
consider archiving the whole file rather than patching one line.

### 7. `DOC_OWNERSHIP.md:100` registers a deleted module as a new code path — `fix`

> 🔴 **[신규 코드 경로 하나 — 이 표가 처음 만나는 «종류»다]
> `server/ledger/declared_translator.py`는 …**

Deleted by `e47d3251` (「retire the five translators with the tests that measured them」).
Unlabelled, present tense, and this is the ownership registry — the table other agents read
to decide who owns what. Same file: `:87-88` names `server/ledger/cutover_v2.py` (absent),
though that entry *is* labelled 🗄️ and retracts itself, so only `:100` needs action.

Also in the same file, `:148` reports 「`client2/tests/contrast_harness.mjs`가 실존하지
않는다」 as an open item for the lead — still true, confirmed absent.

### 8. `IMPLEMENTER_HANDOVER.md:49` wires the empty-form path through a file that does not exist — `fix`

> …only the pack path (claims → roles → emit → object) is wired, through
> `client2/src/ontology_shapes.js`.

No such file. `client2/src/` has `ontology_skeleton.js`, whose header states the opposite
design: 「THIS FILE KNOWS NO SECTION NAMES. Not `packs`, not `claims`, not `emit`.」 The
rename/redesign landed in `4bc009a4` 「the form is generated from the skeleton」. So the
handover names both a dead filename **and** a dead architecture — the pack path it describes
as the wired one is the thing that was removed.

Not measured: whether an implementer session is currently reading this file. It has one
inbound reference from `task/`.

### 9. `SYSTEM_OVERVIEW.md:162` — a legacy row whose path is absent and whose basename collides with the live config — `fix`

> \| `server/config/ledger_config.json` \| 구 flat legacy 선언(`sources` 옆에 상위
> `profiles`를 둘 수 있고 …). 남아 있는 소비자는 어드민 dry-run 경로이며 백필은 읽지 않는다 \|

The path does not exist on disk. The row directly above it (`:161`) is
`server/config/ontology/ledger_config.json` and correctly says `profiles` retired. **Two
adjacent rows, same basename, opposite rules about `profiles`.** A reader who greps
`ledger_config.json` finds the v5 file and can land on either row.

Worse, the row is not merely dead: finding 4 shows the loader for that path silently falls
back to the `.sample` and refuses — so 「남아 있는 소비자는 어드민 dry-run 경로」 is
describing a path that 503s. Whether the row should be deleted or rewritten to name the
fallback is the lead's call; leaving both rows with the same basename is the part that
misleads.

Not measured: whether a production box has `server/config/ledger_config.json`.
`server/paths.py` makes `CONFIG_DIR` overridable by `ASSY_DATA_ROOT`, so this box's absence
is not evidence about production.

### 10. Dead relative links — `fix` (small)

Full link sweep over all 831 `docs/**.md` files. Only two classes survive:

- `docs/architecture/CODE_MAP.md:1896` and `:3008` — malformed markdown links whose target
  parses as the Korean particle `으`. Cosmetic, but they are the only two broken relative
  links in the entire live corpus.
- `docs/_archive/retired_graph_sync/ontology_mapping_guide.md:5,7,8,11,68,76` — six links to
  `../CONFIG_GUIDE.md`, `../LEDGER_GUIDE.md`, `../ONTOLOGY_LEDGER_SETUP.md`,
  `../ROLLBACK_PROCEDURE.md`. Broken by the move into `_archive/`. Already archived —
  `leave`.

Zero broken `file:///` links outside `docs/history/` (two there; history is append-only).
Zero orphans in `docs/history/` — the regenerated index covers all 690.

---

## Attacked and verified safe

This section is the load-bearing half of the verdict. Each of these looked like rot on the
first instrument and survived a second.

**doc-keeper's three new PRIMITIVES entries (`cd6b1955`) — all anchors resolve.**
- `POST /admin/ontology-explorer/test-run` — **my first grep said it did not exist.** That
  was a false negative: the route is declared with a router prefix
  (`server/ontology_config_explorer_router.py:17` `APIRouter(prefix="/admin/ontology-explorer")`,
  decorator at `:121`). Reporting the absence would have been exactly the fabricated-absence
  failure the brief warned about.
- `config_explorer_service.test_run` (`:555`) ✓, `backfill.preview_first_batch` (`:475`) ✓.
- `SOURCE_ROW_EXCLUDED_COLUMN = "__source_row_excluded"`
  (`server/ledger/source_preparation.py:46`) ✓, with the sibling
  `SOURCE_EVENT_INCOMPLETE_COLUMN` at `:45` exactly as described ✓.
- `server/scripts/audit_authoring_form.py` ✓ — reads `ledger/ledger_skeleton.json` (`:38`)
  and `config_authoring.authoring_plan` (`:173`) as claimed, and holds `DECLARING` as a
  constant (`:42`) as claimed.
- **The 「일곱 부류」 count is exact.** Counted the finding buckets at source rather than
  copying the number: `dropdown_missing`, `dropdown_undrawn`, `single_candidate`,
  `derived_conflicts`, `no_scaffold`, `not_in_skeleton`, `plan_silent` = **7**
  (`_leaf_total` is a counter, not a class). Each maps one-to-one onto the Korean
  description in PRIMITIVES.
- `predicate_claim` (`setup_bundle.py:424`), `_validate_mapper` (`:1031`),
  `_validate_profile` (`:1079`), `MapperDescriptor.emits` derived not declared
  (`setup_registry.py:218,234,922`) ✓.
- All seven cited commits resolve: `8bb0f5f1` `9b6c5da` `fd3dda05` `951f391e` `04c6aebf`
  `d64f047e` `a55f3059`.

**The SSOT edit (`d098a7c5`) is correct**, and so are all eight commit hashes it cites
(`9b6c5da0` `e795c706` `087e7d8` `d64f047e` `a55f3059` `2d1ad863` `2ec78b9` `347de78`).
`server/scripts/migrate_ledger_config_to_v4.py` exists as claimed, and
`migrate_ledger_config_to_v5.py` sits beside it.

**CODE_MAP's dead-file references are disciplined tombstones, not rot.** A naive path sweep
flagged `server/run_api.py`, `server/crud.py`, `server/schemas.py`,
`client2/enrichment.html`, `server/graph_orphans.py`, `server/graph_stale_edges.py`,
`server/graph_sync_worker.py`, `server/ontology_config.py`, `server/run_graph_sync.py`. Every
one is inside an explicit tombstone — `:501` 「그런 파일은 **없다**」, `:1365`/`:2115`
「파일이 없습니다」, `:854` 「`server/crud.py`는 존재하지 않는다」, `:711` 「라우트는 살아
있지만 서빙할 파일이 없다 — 항상 404」. **This corpus uses inline tombstones heavily, so
grep-only auditing over-reports it by roughly 10:1.** CODE_MAP's route counts also verify
exactly (`:2522` 16 → `grep -c '^@router\.'` = 16; `:2703` 15 → 15) as do six of seven
read-side line counts.

**`AUTO_UPDATE_GUIDE.md:165` describing `server/graph_orphans.py` as live** — flagged, then
found inside `<details>` under 「⚪ 이하 원문(역사 기록) — «무엇이 있었나»를 읽을 때만
펼치십시오」, preceded at `:160` by 「스윕 메서드와 `graph_orphans` 모듈은 2026-08-16
코드에서 제거됐습니다」. Verified against `server/tests/test_graph_branch_retired.py:199`,
which asserts `"self.maybe_sweep_graph_orphans()" not in src`. `leave, labelled legacy`.

**`ONTOLOGY_GRAPH_SPEC.md:268`** — present-tense 「어디서 도는가: auto-update 스케줄러
틱」 for the same dead sweep, but the doc opens with a per-section status table declaring
itself 정본 and marks 「§7.5e 재동기화/고아 스윕」 🗄️ **죽음**. Line 268 falls under that
section. `leave, labelled legacy` — marginal, a local ⚰️ would be cheap.

**`server/config/ledger_vocabulary.json`** (7 refs incl. `LEDGER_TECHNICAL_SPEC.md:441,563`)
— absent on disk, but `server/ledger/vocabulary.py:509 extension_path()` resolves it to
`paths.CONFIG_DIR` i.e. `server/config/`, and `POST /admin/ledger/save` exists
(`server/main.py:4977`). This is an **optional operator extension that has not been created
yet**; absence is the designed state. Docs are correct. Same reasoning clears
`finding_kinds.json` (DOC_OWNERSHIP:349 states 「선택 · `.sample` 없음」),
`ledger_journey.json`, `siblings_axes.json`, `notation_rules.json`.

**`OPERATOR_RUNBOOK.md:71-72`** naming absent
`ingestion_workspace/*/scripts/*_parser.py` — those are the *destination* of a copy
instruction the runbook is giving the operator. Not-yet-created is correct.
`CODE_MAP.md:45` on `ledger_resolver.json` explicitly declines to assert the file exists.

**`LEDGER_EVIDENCE_SUBGRAPH_SPEC.md` §5.1** — all ten parameters, defaults and ranges match
`ledger_trace_router.py:234-254` exactly; §5.3's four failure outcomes match `:285-291`.
Expected drift from an Aug-16 mtime; found none.

**Phantom routes `/api/ledger/actions`, `/compare`, `/worklist`** — absent from source, but
labelled as future work at both sites (`SCENARIO_CONSOLE_BRIEF.md:560-562` tags them S2/S3;
`frontend.md:580` 「서버 라우트도 … 아직입니다」). Not rot.

**CODE_MAP self-labels the read side as unaudited** (`:67` 「한 파일도 열지 않았다」, `:75`
「449커밋 구간이 지났으므로 밀렸다고 가정하라」). The brief's premise about this gap is
documented inside the document.

---

## Reading-trigger grading

### Live corpus — docs touched or implicated tonight

| Doc | Trigger | Grade | Action |
|---|---|---|---|
| `docs/README.md` | entry point, every session | **A** | fix `:23` (finding 3) |
| `docs/overview/SYSTEM_OVERVIEW.md` | every session | **A** | fix `:162`, `:188` |
| `docs/architecture/PRIMITIVES.md` | every session (「만들기 전에 여기부터」) | **A** | clean — verified tonight |
| `docs/architecture/CODE_MAP.md` | before reading source | **A** | fix `:2278`, `:1896`, `:3008` |
| `docs/process/FORK_SESSION_BRIEF.md` | every fork session | **A** | fix `:95-97` — highest priority |
| `docs/process/DOC_OWNERSHIP.md` | ownership questions | **B** | fix `:100` |
| `docs/guide/ONTOLOGY_LEDGER_SETUP.md` | writing a declaration | **B** | clean |
| `docs/spec/LEDGER_TECHNICAL_SPEC.md` | contract questions | **B** | clean on the points tested |
| `docs/guide/LEDGER_GUIDE.md` | operating the ledger | **B** | `:259-260` blocked by finding 4 |
| `docs/architecture/backend.md` | route/topology questions | **B** | clean on the points tested |
| `docs/process/OPERATOR_RUNBOOK.md` | incident/deploy | **B** | clean, and `:118` is ahead of CODE_MAP |
| `docs/architecture/LEDGER_FRAME_CHAIN_MAPPER.md` | none — FROZEN, pointer is stale | **C** | fix `:109` or archive whole |
| `docs/guide/ledger/PRIMER.md` | none — all callers archived | **C** | **archive** |
| `docs/process/IMPLEMENTER_HANDOVER.md` | one inbound from `task/` | **C→B** | fix `:49` if still in use |
| `docs/architecture/CONFIG_INHERITANCE.md` | none — zero inbound links | **C** | archive candidate |
| `docs/process/{ADMIN_SETUP_BRIEF, AUGMENTATION_SESSION_BRIEF, LEDGER_SETUP_REFORM_PLAN, LEDGER_SETUP_SCENARIO_REVIEW, SESSION_HANDOFF_2026-08-14, SETUP_PAIN_LOG}.md` | none — zero inbound links anywhere | **C** | archive candidates |
| `docs/spec/ONTOLOGY_GRAPH_SPEC.md` | design reference | **C/B** | leave, self-labelled per section |

### `ledger_v2_redesign_plan_20260817/` — 26 files, A = 0

Zero commits since 2026-08-18; stages 1–7 closed; the design has moved past it.

| Keep (B) | Why it still has a reader |
|---|---|
| `07_CUTOVER_RESET_AND_RETIREMENT.md` | §7.2/§7.3 hold the destructive-reset procedure — still the only place it is written |
| `MAPPER_DESIGN_PATTERN.md` | named 기준 계약 by the open task `task/lot_event_mapper_restandardization_pending.md:8`; its §7 example is stale and needs fixing |
| `STAGE_6_ACCEPTANCE_EVIDENCE.md` | audit trail — 「what parity was approved before cutover」; cited by `DOC_OWNERSHIP.md:89` |
| `STAGE_7_ACCEPTANCE_EVIDENCE.md` | audit trail; cited by `DOC_OWNERSHIP.md:88` |
| `README.md` | keep as a redirect stub only — eight inbound links would otherwise 404 |

**Archive (C) — 21 files:** `00_MASTER_PLAN`, `01_FREEZE_AND_HARDCODING_INVENTORY`,
`02_LEDGER_SETUP_BUNDLE`, `03_REGISTRIES_AND_CROSS_VALIDATION`,
`04_ROLEFRAME_AND_PACK_COMPILER`, `05_SOURCE_DRIVER_AND_JOIN_BOUNDARY`,
`06_SHADOW_PARITY_AND_POSTGRES_E2E`, `APPROVAL_GATES` (lift §7 into `07_` first),
`BASELINE_RESULTS`, `COMMON_RULES`, **`CONFIG_CANON`** (highest priority — it is on the
mandatory reading list), `CURRENT_CALL_GRAPH`, `HARDCODING_INVENTORY`,
`KEEP_MOVE_RETIRE_MATRIX`, `LEGACY_CONFIG_CONVERSION_REPORT`, `OPEN_DECISIONS`,
`STAGE_2`–`STAGE_5_ACCEPTANCE_EVIDENCE`, **`TARGET_ARCHITECTURE_AND_SSOT`** (second
priority — four live docs call it 정본).

Ten `server/…` paths cited across the directory do not exist, including the
`ledger_config.json` + `ledger_vocabulary.json` pair that `07_CUTOVER…md:24` and
`TARGET_ARCHITECTURE_AND_SSOT.md:193-196` promise are *preserved unchanged*. That promise is
already broken.

**Archive is a recommendation only — the move is the lead's decision.**

---

## Recommended order

1. `FORK_SESSION_BRIEF.md:95-97` — stop arming new sessions with `setup_version: 2`.
2. `SYSTEM_OVERVIEW.md:188` and `docs/README.md:23` — demote the plan directory.
3. `CODE_MAP.md:2278` — the boot-path claim and the 7-vs-15 count together.
4. Finding 4 is a **code** round, not a doc round: the resolver's config path.
5. The four 「정본」 pointers at `TARGET_ARCHITECTURE_AND_SSOT.md`.
6. Findings 5–9 individually.

---

## Lesson proposals for `agent_workspace/memory/doc-auditor.md`

Proposals only — not written to the memory file.

- **함정**: 경로가 디스크에 없다고 결함으로 세는 것. 이 코퍼스는 묘비(🪦·⚰️·`~~`·
  `<details>`·「파일이 없습니다」)를 본문 안에 촘촘히 쓴다 — 오늘 경로 스윕이 잡은 것의 약
  9할이 «이미 죽었다고 적혀 있는» 자리였다(CODE_MAP 아홉 건 전부).
  **올바른 방법**: 히트마다 그 줄과 위 3줄의 묘비 표지를 먼저 보고, 표지가 있으면
  「leave, labelled legacy」로 분리해 세라. 표지 없는 것만 결함이다.

- **함정**: 라우트·심볼을 grep 한 번으로 「없다」고 판정하는 것. 오늘
  `POST /admin/ontology-explorer/test-run`을 「존재하지 않음」으로 잡을 뻔했다 —
  `APIRouter(prefix=...)` 아래 `@router.post("/test-run")`이라 전체 경로 문자열이 소스에
  없다. **올바른 방법**: 부재를 주장하기 전에 **접두사 조립**을 확인한다 — 라우터 파일의
  `prefix=`를 먼저 읽고 나머지 조각으로 다시 grep.

- **함정**: 없는 config 파일을 결함으로 세는 것. `ledger_vocabulary.json`·
  `finding_kinds.json`·`ledger_resolver.json`은 **선택 확장**이라 부재가 설계된 상태다.
  **올바른 방법**: 파일이 없으면 그 파일명을 읽는 **코드의 부재 처리**를 먼저 본다 —
  fallback·기본값·`.sample`이 있으면 문서가 맞고 파일이 아직 없을 뿐이다.

- **함정**: 「N모듈」 개수 주장과 그 옆 문장을 따로 검수하는 것. CODE_MAP:2278에서 개수가
  8 모자랐고, **빠진 여덟 중 하나가 바로 옆 문장을 거짓으로 만드는 모듈**이었다.
  **올바른 방법**: 개수 주장을 만나면 구성원 집합을 소스에서 세어 **차집합을 이름으로**
  뽑고, 그 이름들이 주변 문장의 술어를 반증하는지 본다. 개수 오류와 서술 오류는 대개 같은
  결함이다.

- **함정**: 낡은 문서를 만나면 반사적으로 `fix`로 판정하는 것. PRIMER는 이틀 낡았지만
  **살아 있는 문서 중 그것을 여는 것이 하나도 없었다** — 정본이라 부르는 문서 셋이 전부
  `_archive/`에 있다. **올바른 방법**: `fix`를 내리기 전에 **인바운드 링크를 리포지터리
  전체에서** 세고, 호출자가 전부 아카이브면 판정은 `archive`다. 트리거 없는 문서를 고치는
  것이 문서가 다시 썩는 경로다.
