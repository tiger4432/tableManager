"""INV-7b-3 seam oracle — the CLIENT's canonicalisation vs the SERVER's, key -> value.

This is the assertion the round exists for. The reported bug was the two sides disagreeing:
the client composed `LOT_01` while storage held `LOT_1`, so the cell data opened and the
metadata looked absent. Self-consistency on either side would have proved nothing.

The server side is NOT reimplemented here. It imports the live
`server/map_overlay.py` and calls `canonical_key_value` / `build_key_filters` directly, so
this file goes red the moment either half drifts.

    conda run -n assy_manager python client2/tests/seam_7b_oracle.py

Exit 0 = the two halves agree on every vector. Exit 1 = divergence (each one printed).
Exit 2 = the oracle could not run (never read as a pass).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "server"))

# The CLIENT half may be read from a copy. This exists so the oracle can be pointed at a
# deliberately broken client and shown to go RED — an oracle nobody has ever seen fail is
# not evidence. Unset (the normal case) = the working tree.
CLIENT_ROOT = os.environ.get("SEAM_CLIENT_ROOT") or ROOT
CLIENT_HARNESS = os.path.join(CLIENT_ROOT, "client2", "tests", "map_key_canonical_harness.mjs")
# 7b lives in its own module since the map-key extraction round. Pointing this at
# map_editor.js now exits 3 with "missing canonicalKeyValue" — loud, not silently green.
CLIENT_SRC = os.path.join(CLIENT_ROOT, "client2", "src", "map_key.js")

try:
    import map_overlay
except Exception as exc:                                    # pragma: no cover
    print(f"ORACLE FAILURE: cannot import server/map_overlay.py — {exc}")
    print("(This is not a passing result. Nothing was compared.)")
    sys.exit(2)


# A JS boolean stringifies 'true' where Python gives 'True'. A boolean is not a map key
# component in any table, and both sides are internally consistent, so the vector is
# excluded here and recorded in the report rather than papered over.
EXCLUDED = {("True", "number"), ("true", "number")}


def client_matrix():
    """The client's own answers, produced by the client's own code."""
    try:
        out = subprocess.run(
            ["node", CLIENT_HARNESS, "--emit-7b"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
    except FileNotFoundError:
        print("ORACLE FAILURE: node not on PATH.")
        sys.exit(2)
    if not out.stdout.strip():
        print(f"ORACLE FAILURE: client harness produced no matrix.\n{out.stderr}")
        sys.exit(2)
    return json.loads(out.stdout)


def main():
    rows = client_matrix()
    bad = []
    compared = 0
    differing_types = 0

    for row in rows:
        # `type` is absent when the JS vector declared `undefined` — JSON.stringify drops it.
        # Absent and null are the same case here: no declared type, so string semantics.
        value, col_type, client = row["value"], row.get("type"), row["client"]
        if (str(value), str(col_type)) in EXCLUDED:
            continue
        server = map_overlay.canonical_key_value(value, col_type)
        compared += 1
        if server != client:
            bad.append(("canonical", value, col_type, client, server))

    # The differential: how many vectors do the two DECLARED TYPES answer differently?
    # If this is 0 the matrix cannot distinguish a type-aware implementation from one that
    # ignores the declared type entirely, and agreement would mean nothing.
    for row in rows:
        if row.get("type") == "number":
            a = map_overlay.canonical_key_value(row["value"], "number")
            b = map_overlay.canonical_key_value(row["value"], "string")
            if a != b:
                differing_types += 1

    # ── decomposition parity, through the server's REAL build_key_filters ──────────
    # A stub model records what each column was compared against, so the server's own
    # split + canonicalisation runs unmodified.
    class Recorder:
        def __init__(self, name):
            self.name = name
            self.seen = None

        def __eq__(self, other):
            self.seen = other
            return self

    DECOMPOSE_VECTORS = [
        # (key_columns, declared types, map_key)
        (["lot", "slot"], {"lot": "string", "slot": "number"}, "LOT_01"),
        (["lot", "slot"], {"lot": "string", "slot": "number"}, "LOT_1"),
        (["lot", "slot"], {"lot": "string", "slot": "number"}, "A_B_2"),
        (["lot", "slot"], {"lot": "string", "slot": "number"}, "A_B_02"),
        (["lot", "slot"], {"lot": "string", "slot": "number"}, "A_02"),
        (["lot", "slot"], {"lot": "string", "slot": "string"}, "LOT_01"),
        (["lot", "slot"], {"lot": "string", "slot": "number"}, "SOLO"),
        (["pkg_id", "base"], {"pkg_id": "string", "base": "string"}, "P1_07"),
        (["lot"], {"lot": "string"}, "A_B_C"),
    ]

    original = map_overlay.declared_column_type
    for cols, types, key in DECOMPOSE_VECTORS:
        model = type("M", (), {"__tablename__": "t"})()
        recs = {c: Recorder(c) for c in cols}
        for c, r in recs.items():
            setattr(model, c, r)
        map_overlay.declared_column_type = lambda _t, col, _ty=types: _ty.get(col)
        try:
            map_overlay.build_key_filters(model, {"key_columns": cols}, key)
        finally:
            map_overlay.declared_column_type = original
        server_parts = {c: r.seen for c, r in recs.items() if r.seen is not None}

        node = subprocess.run(
            ["node", "-e", DECOMPOSE_JS, json.dumps(cols), key, json.dumps(types), CLIENT_SRC],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        if node.returncode != 0:
            print(f"ORACLE FAILURE: client decompose failed for {key}\n{node.stderr}")
            sys.exit(2)
        client_parts = json.loads(node.stdout)
        compared += 1
        if client_parts != server_parts:
            bad.append(("decompose", key, cols, client_parts, server_parts))

    print(f"compared {compared} vectors "
          f"({len(rows) - len(EXCLUDED & {(str(r['value']), str(r.get('type'))) for r in rows})} canonical "
          f"+ {len(DECOMPOSE_VECTORS)} decompose)")
    print(f"declared-type differential: {differing_types} vectors where number != string "
          f"(0 would mean the matrix proves nothing)")
    if differing_types == 0:
        print("ORACLE FAILURE: the vector set does not activate the declared-type axis.")
        sys.exit(2)
    if bad:
        print(f"\nDIVERGENCE — {len(bad)}:")
        for kind, a, b, client, server in bad:
            print(f"  [{kind}] input={a!r} ctx={b!r}\n        client={client!r}\n        server={server!r}")
        sys.exit(1)
    print("\nPASS — client and server agree on every compared vector.")
    return 0


# Runs the CLIENT's decomposeMapKey out of the real source text (same slicing technique the
# harness uses, so no second copy of the function exists anywhere).
DECOMPOSE_JS = r"""
const fs = require('fs');
const vm = require('vm');
const [cols, key, types, srcPath] = process.argv.slice(1);
const src = fs.readFileSync(srcPath, 'utf8');
function slice(name) {
  const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) { console.error(`missing ${name}`); process.exit(3); }
  let depth = 0;
  for (let j = src.indexOf('{', m.index); j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(m.index, j + 1); }
  }
  console.error(`unbalanced ${name}`); process.exit(3);
}
function sliceConst(name) {
  const m = new RegExp(`const\\s+${name}\\s*=`).exec(src);
  if (!m) { console.error(`missing const ${name}`); process.exit(3); }
  return src.slice(m.index, src.indexOf(';', m.index) + 1);
}
const ctx = {};
vm.createContext(ctx);
vm.runInContext([sliceConst('CANON_INT_RE'), sliceConst('CANON_FLOAT_RE'),
  slice('canonIntString'), slice('canonicalKeyValue'), slice('decomposeMapKey'),
  'globalThis.__r = decomposeMapKey;'].join('\n'), ctx);
process.stdout.write(JSON.stringify(ctx.__r(JSON.parse(cols), key, JSON.parse(types))));
"""

if __name__ == "__main__":
    sys.exit(main())
