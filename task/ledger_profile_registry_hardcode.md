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

---

# The two branches, measured (lead, 06:25). No code, no decision.

The implementer went quiet again after the diagnosis, so I measured this myself. Every line
below is a count or a `file:line`, not an expectation.

## Branch B collapses first, so measure it first

**B was: the built-in registry is authoritative and the file's `packs` means something else.**

It does not survive one question — *who reads the file's `packs`?*

```
server/ledger/config_authoring.py     12 sites   the authoring plan, i.e. the screen
server/ledger/setup_bundle.py         validates it (_validate_packs)
server/ledger/source_profile.py       never
```

So the file's `packs` is what the screen writes, what the setup validator judges, and what the
owner has been authoring all night. Calling it "something else" would mean the screen has spent
this round authoring a section no profile validator ever consults — which is the situation, and
is the thing being reported as a bug rather than a design.

## Branch A costs two test files. Nothing else.

**A was: `validate()` builds the registry from the file's own `packs`.**

Every configuration on disk already declares the packs it uses:

```
config/ontology/ledger_config.json            packs: dt-job@1, lot-lineage@1     refs 8/8 declared
config/sample/ledger_config.json.sample       same shape                          refs 8/8 declared
config/sample/ontology/transfer_explorer/…    packs: dt-assembly@1                refs 5/5 declared
```

🔴 **And that third one does not use `transfer@1` at all** — the built-in pack that looked like
a live dependency is referenced by no configuration anywhere.

What relies on the built-in registry is exactly two test files, which name a pack in a profile's
`packs` list and declare no `packs` section:

```
server/tests/test_ledger_frame_chain_mapper.py:227   "packs": ["transfer@1"]   no packs section
server/tests/test_ledger_l1_pg.py:308                "packs": ["transfer@1"]   no packs section
```

Both already call the validator, so either they declare a minimal pack, or they pass the
`registries` argument that has existed unused all along.

## The shape maps directly — no information is missing

```
PackDescriptor  (pack_id, version, claims)      <- the file's key splits into id@version
ClaimDescriptor (claim_id, roles)               <- file claim holds roles (and emit, unused here)
RoleDescriptor  (role_id, kind, required, allowed_binding_kinds, allow_null,
                 symbolic_constants, allowed_constant_types)
                                                <- file role holds kind, required
                                                   (+ allowed_binding_kinds, allowed_values
                                                    where declared; the rest default)
```

## What is still open, and it is the owner's

The measurement says B is untenable and A is cheap. It does **not** say what a pack IS — whether
a profile may only use packs the same file declares, or whether some registry of shared packs is
meant to exist across configs. A answers the first; nobody has asked the second out loud.

**Not built. Two test files is a small number, and a wrong contract is not.**
