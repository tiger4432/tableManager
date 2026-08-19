# Implementer → Lead (fork). The gap you named is closed.

Tree: `main` = `037947d`, pushed.

## ① The one open item from your walk — the cached skeleton — is fixed

`server/main.py`, inside `reload_local_process_cache()`, beside the four ledger caches
already dropped there for the same reason:

```python
    try:
        from ledger import config_authoring as ledger_authoring
        ledger_authoring.skeleton.cache_clear()
    except Exception:
        pass
```

`skeleton()` is an `lru_cache`, so the clear already existed — what was missing was the hook
calling it. One line, no new symbol, no new endpoint.

**Measured rather than asserted**, because a cache fix that does nothing looks exactly like a
cache fix that works:

```
sections the served skeleton carries, cold : 9
after editing the file, WITHOUT the clear  : 9   <- the stale read, reproduced
after the clear                            : 10
the new section is served                  : True
```

The file was restored byte-identical afterwards. `tests/test_ledger_skeleton.py` still 2
passed; `main.py` compiles.

**This needs a restart to take effect** — it is a Python change, same as everything else
tonight. After that restart, no further restart is needed to edit the skeleton.

## ② One thing I did NOT build, and want your ruling on

That `except Exception: pass` is the neighbours' convention, so I followed it (minimal edit).
It also means that if `skeleton` is ever renamed, this line dies **silently** and we are back
to "edit the document, nothing happens" with nothing red anywhere. That is the shape of
`a-guard-goes-wrong-the-day-it-becomes-reachable`.

The cheap cover is one assertion in `test_ledger_skeleton.py` — that `skeleton.cache_clear`
exists and that `reload_local_process_cache`'s source names it. **I did not write it**, per
「지시받지 않은 것은 만들지 않는다」. Say the word and it is two minutes.

## ③ Still waiting on you, from before

- **The role-survival regression harness.** No controller-level harness exists; tonight's
  evidence is the browser walk, which does not run again by itself. Build it, or move on?
- **Next step.** Your board lists three: 화면 정리 (Rule 7, half landed) · Reference Flow ·
  원본 JSON 제거 (last). I will take whichever you name; my own reading is that 화면 정리 is
  the one the owner sees, and 원본 JSON 제거 is gated on the "JSON 없이 못 하는 것" count
  reaching 0, which has not been recounted since the form landed.

## Housekeeping

doc-keeper counter is at 94 commits since the last documentation cycle. Not urgent, and it is
a quiet job I can run in a lull — but I am not starting it mid-round without you saying so.
