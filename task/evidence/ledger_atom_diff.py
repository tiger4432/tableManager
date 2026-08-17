"""Diff the atom cases only. snapshot_sha256 is provenance, not the gate."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
base = json.load(open(sys.argv[1], encoding='utf-8'))
now = json.load(open(sys.argv[2], encoding='utf-8'))
print('baseline snapshot:', base['snapshot_sha256'][:12])
print('current  snapshot:', now['snapshot_sha256'][:12])
bad = 0
for name in sorted(set(base['cases']) | set(now['cases'])):
    b = base['cases'].get(name)
    n = now['cases'].get(name)
    if b == n:
        continue
    bad += 1
    print(f'  DIFF {name}')
    print(f'    baseline: {json.dumps(b, ensure_ascii=False, sort_keys=True)[:300]}')
    print(f'    current : {json.dumps(n, ensure_ascii=False, sort_keys=True)[:300]}')
print('CASE DIFF:', bad, '(0 이면 게이트 통과)')
