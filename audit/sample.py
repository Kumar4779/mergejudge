import json, glob, os, re, random, string
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
SEED = 20261123
rng = random.Random(SEED)
fresh = {t['instance_id'] for t in json.load(open('tasks/fresh/index.json'))['tasks']}
pool = defaultdict(list); rec = {}
for f in sorted(glob.glob('results/*.json')):
    r = json.load(open(f))
    if r.get('agent') in ('gold', 'none', 'ci') or r.get('probe_prompt') or r.get('scaffold', 'direct') != 'direct':
        continue
    if not re.fullmatch(r'claude-(e2e|sonnet)(-r\d+)?', r['agent']):
        continue
    run = os.path.basename(f)[:-5]
    if not Path(f'results/{run}.patch').read_text().strip():
        continue
    repo = 'fresh' if r['task'] in fresh else r['task'].split('__')[0]
    arm = 'sonnet' if 'sonnet' in r['agent'] else 'default'
    rec[run] = dict(r, repo=repo, arm=arm)
    pool[(repo, arm, r['verdict'])].append(run)

chosen = []
def pick(stratum, n, forced=()):
    got = list(forced)
    cands = [x for x in pool[stratum] if x not in got]
    rng.shuffle(cands)
    for strict in (True, False):  # prefer tasks not yet sampled; fall back
        for c in cands:
            if len(got) >= n: break
            if c in got: continue
            if strict and rec[c]['task'] in {rec[g]['task'] for g in got + chosen}: continue
            got.append(c)
    assert len(got) == n, stratum
    chosen.extend(got)

R, U = 'resolved', 'not_resolved'
reg12171 = [x for x in pool[('sympy', 'sonnet', U)] if x.startswith('sympy-12171-')
            and rec[x]['pass_to_pass_named']['passed'] < rec[x]['pass_to_pass_named']['total']]
pick(('django', 'default', R), 3, forced=['django-10914-claude-e2e'])
pick(('django', 'sonnet', R), 3)
for repo in ('sympy', 'fresh'):
    pick((repo, 'default', R), 2); pick((repo, 'sonnet', R), 2)
for repo in ('matplotlib', 'scikit-learn', 'astropy'):
    pick((repo, 'default', R), 1); pick((repo, 'sonnet', R), 1)
pick(('sympy', 'sonnet', U), 1, forced=[rng.choice(reg12171)])
pick(('django', 'sonnet', U), 1)
pick(('fresh', 'default', U), 1)
pick(('sympy', 'default', U), 1)
assert len(chosen) == 24 == len(set(chosen))

def code():
    return ''.join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))
codes = set()
while len(codes) < 24: codes.add(code())
codes = sorted(codes)
order = chosen[:]; rng.shuffle(order)
key = {}
for c, run in zip(codes, order):
    r = rec[run]
    task_short = re.sub(r'^[^_]+__', '', r['task'])  # e.g. sympy-12171, scikit-learn-10297
    issue = (ROOT / ('tasks/fresh' if r['repo'] == 'fresh' else 'tasks') / f'{task_short}-issue.txt').read_text().strip()
    patch = Path(f'results/{run}.patch').read_text().rstrip('\n')
    Path(f'audit/packets/{c}.md').write_text(
        f"# Packet {c}\n\n## Problem statement\n\n{issue}\n\n## Patch\n\n```diff\n{patch}\n```\n")
    key[c] = {'run': run, 'task': r['task'], 'stratum': r['repo'], 'arm': r['arm'], 'verdict': r['verdict']}

# calibration set: 10 codes, stratified
want = [('django', 'default', R, 'django-10914-claude-e2e'), ('django', 'sonnet', R, None),
        ('sympy', 'default', R, None), ('fresh', 'sonnet', R, None), ('matplotlib', 'default', R, None),
        ('scikit-learn', 'sonnet', R, None), ('astropy', 'default', R, None),
        ('sympy', 'sonnet', U, None), ('fresh', 'default', U, None), ('django', 'sonnet', U, None)]
calib = []
for repo, arm, v, run in want:
    opts = [c for c, k in key.items() if k['stratum'] == repo and k['arm'] == arm and k['verdict'] == v
            and (run is None or k['run'] == run) and c not in calib]
    calib.append(rng.choice(opts))
rng.shuffle(calib)
json.dump({'seed': SEED, 'note': 'Local until the audit is complete; then published for reproducibility.',
           'packets': key, 'calibration_set': calib}, open('audit/key.json', 'w'), indent=2)
print(json.dumps(calib))
