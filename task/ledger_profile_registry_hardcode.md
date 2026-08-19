# The profile validator never reads the config's declared packs

**Found while checking three red tests. The red tests are the smallest symptom, not the point.**

Status: **diagnosed, not fixed.** It changes validation semantics for every config, so it
needs a ruling. Nothing in this file has been acted on.

## The error message is false

`ledger.config.validate()` refuses both the sample and **the owner's live config**:

```
config/ontology/ledger_config.json.profiles["dt-job@1"].mappings[0].use
    pack 'dt-job@1' is not declared in packs   [unknown_pack]
```

It is declared. Measured on the live file:

```
live packs declared   : ['dt-job@1', 'lot-lineage@1']
live profiles         : ['dt-job@1', 'lot-event@1']
every profile `use` reference -> declared in packs: True   (8 of 8 in the sample, likewise)
```

I first reported the message as if it were the cause. The lead refuted that; the refutation
holds, and this is what is underneath it.

## The mechanism

`validate_profile_section(cfg, path=...)` takes an optional `registries`. **Neither production
call site passes one** — `ledger/config.py:396` and `ledger/config.py:945`. So
`validate_profile` falls back to `_default_registries()`, and that registry is **hardcoded**
in `ledger/source_profile_builtins.py`. It knows exactly two packs:

```
built-in registry : lot-lineage@1 -> claims: [transition]
                    transfer@1    -> claims: [movement]
declared in file  : lot-lineage@1 -> claims: [register, membership, lineage, slot_map]
                    dt-job@1      -> ...
```

So the question "is this pack declared?" is asked of a list that has nothing to do with the
file being validated. The config's own `packs` section is not consulted anywhere on this path.
An empty registry answers every question with absence — the answer is "no" for everything the
operator actually declared, and it is right about nothing.

## Why nobody has noticed

The two production callers hand `validate()` a **single-source fragment**:

```python
ledger_config.validate({"sources": {name: declaration}}, ...)   # config_resolve_report.py:896
ledger_config.validate({"sources": {source: declaration}}, ...) # ledger_admin.py:251
```

`validate_profile_section` returns `{}` when there is no `profiles` key, so the refusal is
never reached. **Nothing in production currently validates a whole config.** The three red
tests are red precisely because they do.

The authoring screen's save path uses its own validator, not this one — which is why tonight's
walk saved a rebuilt pack with zero complaints while this was true the whole time.

## Why it matters anyway

- It is a **hardcode standing in for a declaration**, in the middle of a round whose stated
  finish line is 「다른 스키마 운영 환경에서 코드 0줄」. A second operator's packs cannot be
  known to a list compiled into the code.
- It is wrong **now**, and silent only because no reachable path walks it. The day anything
  validates a whole config — which is the direction the authoring screen is heading, with the
  validator as the only judge — it refuses the owner's own file.
- The message sends whoever hits it to the wrong place: it says a thing is undeclared while
  the file declares it, so the first hour goes into the file rather than the registry.

## What a fix would have to decide (not decided here)

Whether `validate()` builds the registry from the config's own `packs` section, or whether the
built-in registry stays authoritative and the config's `packs` are something else entirely.
That is a contract question about what a pack IS, not a patch — hence no code in this commit.
