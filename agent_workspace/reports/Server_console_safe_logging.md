# Server — CONSOLE-SAFE: a log line the terminal cannot encode must degrade, not die

Tier T2. Lane: server-pm. Not committed; four paths staged with `git add <path>`.
Every observation below was measured on **this box** (Windows 11, conda env
`assy_manager`), against synthetic `io.TextIOWrapper(..., encoding="cp949")`
streams — not against the operator's production console.

---

## 1. Headline: the primitive I was told to lift **never worked**

The brief said `_ConsoleSafeHandler` (`server/map_alignment.py:2327`) "does exactly
this job — lift it and reuse it. Do not write a second spelling." It does not do
the job. Its rescue branch is unreachable:

```python
def emit(self, record):
    try:
        super().emit(record)          # logging.StreamHandler.emit
    except UnicodeEncodeError:        # <- never fires
        ...
```

`logging.StreamHandler.emit` in CPython ends with `except Exception:
self.handleError(record)`. The `UnicodeEncodeError` is caught **inside** the
super call and converted into a `--- Logging error ---` dump on stderr. Nothing
propagates, so the wrapper's rescue is dead code. Its docstring correctly
diagnosed the disease and then prescribed a placebo.

Measured, one record carrying U+2014 through a real logger against a cp949
stream (`CSAFE_repro.py`):

| handler | bytes to console | stderr traceback |
|---|---|---|
| stock `logging.StreamHandler` | **0** | 819 chars |
| existing `_ConsoleSafeHandler` | **0** | 1590 chars |

The existing handler was strictly worse — same lost line, twice the noise
(one extra frame in the traceback).

This is the load-bearing correction to the brief. I lifted the class as
instructed, kept its name and its reasoning, and **fixed it** — I did not write a
second spelling.

## 2. What changed

**Home chosen: `server/utils/logger.py`.** Not a new module — this is already the
file where every process's console handler is constructed, so putting the class
anywhere else would have left the fix one import away from the thing it fixes.

### `server/utils/logger.py`
- New `class ConsoleSafeHandler(logging.StreamHandler)`. It performs the write
  itself and puts the rescue **around the write**, which is the only place the
  error is catchable:
  ```python
  try:
      stream.write(msg + self.terminator)
  except UnicodeEncodeError:
      enc = getattr(stream, "encoding", None) or "ascii"
      stream.write(msg.encode(enc, "replace").decode(enc, "replace") + self.terminator)
  ```
  It keeps `except RecursionError: raise` and the outer `handleError` so every
  non-encoding failure behaves exactly as stock. `emit` touches nothing but the
  standard `StreamHandler` surface, deliberately, so it can be bound onto foreign
  handlers.
- New `make_console_safe(handler)` for handlers **this codebase did not
  construct** (uvicorn's). It binds the same `emit` onto the instance via
  `types.MethodType`, so the owner's handler object, formatter and filters
  survive. It returns non-`StreamHandler`s, `FileHandler`s and already-safe
  handlers untouched.
- `get_process_logger` line ~193 now builds `ConsoleSafeHandler(sys.stdout)`.
  **This one line covers all six children** the launcher starts — Backend FastAPI
  Server, File Ingestion Watcher, Graph DB Sync Worker, Chained Ingestion Worker,
  Auto Update Scheduler, and the Launcher process itself. Verified by grep: every
  entry point (`main.py:21`, `run_watcher.py:14`, `run_chain_worker.py:11`,
  `run_graph_sync.py:11`, `run_auto_update.py:23`, `chain_ingestion_worker.py:44`,
  `graph_sync_worker.py:14`, `run_decoupled_app.py:24`) gets its console handler
  from this one call, and `basicConfig`/`StreamHandler` appear nowhere else in
  `server/` outside tests.

### `server/main.py`
The **second** console in the web-server process. uvicorn installs its own
handlers on `uvicorn`/`uvicorn.error`/`uvicorn.access` with `propagate=False`, so
they never reach the root handler above. The existing loop that re-formats them
now also calls `make_console_safe(handler)` on each.

### `server/map_alignment.py`
Class body removed; `_ConsoleSafeHandler = ConsoleSafeHandler` alias kept so the
two existing references (`:2367` construction, `:2162` docstring) read the same.
Its diagnostics logger keeps working — and now actually rescues, which it did not
before.

**`server/parsers/directory_watcher.py` was NOT opened or edited** (off-limits per
the brief) and the fix did not need it — as predicted, this was logging
configuration, not a call site. `server/database/crud.py` and `client2/`
untouched. No log strings edited; no lint rule added.

## 3. Verification

**The failure was asserted before the cure.** `CSAFE_repro.py` above.

`server/tests/test_console_safe_logging.py` (new, 18 cases). Per the brief I did
**not** run pytest — other lanes are active. I ran every case through a hand-rolled
harness (`CSAFE_dryrun.py`) that emulates `parametrize` and the fixtures:
**18/18 pass**. Please serialize a real pytest run.

`test_the_old_shape_does_not_work` pins §1 as a test, so nobody re-derives the
`super().emit()` shape believing it is a fix.

**Mutation check** (`CSAFE_mutate.py`, `ConsoleSafeHandler.emit` reverted to
`logging.StreamHandler.emit` at runtime — no source edit, so no CRLF hazard):

| test | under mutation |
|---|---|
| `test_console_safe_handler_keeps_the_sentence` | **RED** |
| `test_the_whole_class_...('em dash')` | **RED** |
| `test_the_whole_class_...('emoji')` | **RED** |
| `test_make_console_safe_rescues_a_foreign_handler` | **RED** |
| `test_utf8_console_is_untouched` | green (by design — asserts no change) |
| `test_encodable_output_is_byte_identical_to_stock` | green (by design) |
| `test_stock_handler_loses_the_whole_line` | green (by design — asserts the defect) |

**End-to-end, real `get_process_logger`, cp949 console** (subprocess, `ASSY_DATA_ROOT`
pointed at scratch): console handler class `ConsoleSafeHandler`, **110 bytes
written, 0 chars of stderr noise**, text reads
`[Watcher] ... WARNING - legacy workspace config ? use paths.py (설정 이전)` —
the em dash became `?`, the Korean survived intact.

**§4 of the brief — the file half — confirmed, not assumed.** Same run, the file
handler's `encoding` is `utf-8` and the raw bytes on disk contain `e2 80 94`; the
decoded line carries U+2014 **intact** alongside the Korean. `test_file_half_
keeps_the_character` asserts both. The stream's own encoding is used for the
console; **utf-8 is never forced** — `test_utf8_console_is_untouched` shows a utf-8
terminal keeps every character unchanged.

## 4. The neighbours — measured, and I was wrong about one

The brief named U+2013, U+2026 and emoji. **Membership in "unencodable in cp949"
is not what intuition says**, and my own test caught me: I added U+2192 `→` to the
rescued set and it went red because **cp949 encodes it fine**. Census from this box:

| char | cp949 | status |
|---|---|---|
| U+2014 em dash `—` | unencodable | **covered** (the reported defect) |
| U+2013 en dash `–` | unencodable | **covered** |
| U+2022 bullet `•` | unencodable | **covered** |
| emoji U+1F534 | unencodable | **covered** |
| **U+2026 ellipsis `…`** | **ENCODABLE** | **never was a defect** |
| **U+2192 arrow `→`** | **ENCODABLE** | **never was a defect** |
| **U+2019 curly quote `’`** | **ENCODABLE** | **never was a defect** |

So: two of the three neighbours the brief named are covered; **U+2026 was a false
member of the class.** Asserting a rescue for it would have asserted a fiction, so
the encodable group is covered by `test_encodable_output_is_byte_identical_to_stock`
(byte-identical to stock) instead.

**Not covered, deliberately:** a character cp949 *can* encode but the console
*font* cannot draw (no exception is raised — there is nothing for a handler to
catch); and any failure that is not a `UnicodeEncodeError`, which still degrades
to `handleError` exactly as stock.

## 5. Open / for the lead

1. **Docs are out of scope per the brief, so I changed none.** Two rows will now
   be stale and want an owner:
   - `docs/architecture/CODE_MAP.md:1935` — the `server/utils/logger.py` row still
     says "145줄" and lists only `ColoredProcessFormatter` / `get_process_logger`.
     code-mapper's file.
   - `docs/architecture/PRIMITIVES.md` — `ConsoleSafeHandler` / `make_console_safe`
     is a new shared primitive with no catalogue entry. doc-keeper's file.
2. `server/map_alignment.py` already carried a **staged** change from another lane
   when I started (`M ` in the session-start status). My edit is on top of it.
3. Proposed memory lesson for `agent_workspace/memory/server-pm.md`:
   > **함정**: 이미 있는 프리미티브를 재사용하라는 지시를 「그것이 동작한다」로 읽는다.
   > `_ConsoleSafeHandler`는 `super().emit()`을 `except UnicodeEncodeError`로 감쌌는데,
   > `logging.StreamHandler.emit`이 그 예외를 자기가 삼켜 `handleError`로 보내므로
   > **그 분기는 도달 불가능한 죽은 코드**였다. 진단 docstring은 정확했고 처방만 위약이었다.
   > **올바른 방법**: 재사용 대상 프리미티브도 **결함을 주입해 한 번 울려 보고** 나서 lift한다.
   > 「기존 코드가 있다」는 「기존 코드가 동작한다」가 아니다.
4. Proposed history draft: *"the console-safe handler that was already there and
   had never worked"* — the em dash incident, the unreachable `except`, the one
   line in `get_process_logger` that covers six processes, and the cp949 census
   that removed U+2026 from the defect class.

## 6. Staged paths

- `C:\Users\kk980\Developments\assyManager\server\utils\logger.py`
- `C:\Users\kk980\Developments\assyManager\server\main.py`
- `C:\Users\kk980\Developments\assyManager\server\map_alignment.py`
- `C:\Users\kk980\Developments\assyManager\server\tests\test_console_safe_logging.py`
