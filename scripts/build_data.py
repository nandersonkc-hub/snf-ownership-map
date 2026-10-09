#!/usr/bin/env python3
"""Join the three CMS files into data.json for the map.

Usage: python scripts/build_data.py --raw data/raw --out data.json

Finds the three CSVs in --raw by their column headers, so file names do not matter.
"""
import argparse, csv, glob, json, os, random, re, sys
from collections import defaultdict, Counter
from datetime import date
import zipcodes

csv.field_size_limit(10**8)

def header(path):
    with open(path, 'rb') as fh:
        line = fh.readline()
    try:
        text = line.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = line.decode('cp1252', errors='replace')
    return [c.strip().strip('"') for c in text.strip().split(',')]

def find(raw, *required):
    """Pick the CSV in `raw` whose header row has every required column.
    A tuple means any one of those names will do (CMS renamed some columns between releases)."""
    files = sorted(glob.glob(os.path.join(raw, '*.csv')))
    for f in files:
        cols = header(f)
        if all((any(x in cols for x in r) if isinstance(r, tuple) else r in cols) for r in required):
            return f
    seen = ['%s: %s' % (os.path.basename(f), ', '.join(header(f)[:6])) for f in files]
    raise RuntimeError('No CSV with columns %s. Files seen: %s' % (list(required), seen or 'none'))

def pick(row, *phrases):
    """First value whose column name equals (or else contains) one of the phrases, ignoring case."""
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for ph in phrases:
        if ph.lower() in low:
            return low[ph.lower()]
    for ph in phrases:
        for k, v in low.items():
            if ph.lower() in k:
                return v
    return None

def read(path):
    raw = open(path, 'rb').read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252', errors='replace')
    return list(csv.DictReader(text.splitlines()))

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def clean(s):
    return re.sub(r'\s+', ' ', (s or '').strip())

OWN_ROLES = {'34', '35', '85', '86'}          # 5%+ direct/indirect and other ownership interests
MGR_ROLES = {'43', '25', '42', '63'}          # managing / operational control roles
FLAGS = {'PRIVATE EQUITY COMPANY - OWNER': 'PE', 'REIT - OWNER': 'REIT',
         'MANAGEMENT SERVICES COMPANY - OWNER': 'MGMT', 'HOLDING COMPANY - OWNER': 'HOLD',
         'CHAIN HOME OFFICE - OWNER': 'HOME', 'NON PROFIT - OWNER': 'NP', 'INVESTMENT FIRM - OWNER': 'INV'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='data/raw')
    ap.add_argument('--out', default='data.json')
    a = ap.parse_args()
    ef = find(a.raw, 'NURSING HOME PROVIDER NAME', 'AFFILIATION ENTITY ID')
    of = find(a.raw, 'ASSOCIATE ID - OWNER', 'ROLE CODE - OWNER')
    cf = find(a.raw, ('Chain ID', 'Affiliated entity ID'), 'Number of facilities')
    print('enrollments:', os.path.basename(ef)); print('owners:', os.path.basename(of)); print('chains:', os.path.basename(cf))
    enr, own, chn = read(ef), read(of), read(cf)

    chains, national = {}, {}
    for c in chn:
        cid = (pick(c, 'Chain ID', 'Affiliated entity ID') or '').strip()
        rec = dict(n=(pick(c, 'Chain', 'Affiliated entity') or '').strip(),
                   fac=num(pick(c, 'Number of facilities')), st=num(pick(c, 'Number of states')),
                   sff=num(pick(c, 'Number of Special Focus Facilities')), ab=num(pick(c, 'Percentage of facilities with an abuse icon')),
                   fp=num(pick(c, 'Percent of facilities classified as for-profit')), ov=num(pick(c, 'Average overall 5-star rating', 'overall 5-star')),
                   hi=num(pick(c, 'Average health inspection rating')), sf=num(pick(c, 'Average staffing rating')),
                   q=num(pick(c, 'Average quality rating')), fines=num(pick(c, 'Total amount of fines in dollars')),
                   to=num(pick(c, 'Average total nursing staff turnover percentage')))
        if cid:
            chains[cid] = rec
        else:
            national = {k: rec[k] for k in ('ov', 'hi', 'sf', 'q', 'ab', 'to')}
    rated = sum(1 for c in chains.values() if c['ov'] is not None)
    print('chains', len(chains), 'with overall rating', rated)

    fac, eid2i, nocoord = [], {}, 0
    for r in enr:
        z = clean(r['ZIP CODE'])[:5].zfill(5) if r['ZIP CODE'] else ''
        m = zipcodes.matching(z) if z else []
        if m:
            rnd = random.Random(r['CCN'])          # stable nudge: same building lands in the same spot every month
            lat = round(float(m[0]['lat']) + rnd.uniform(-.012, .012), 4)
            lng = round(float(m[0]['long']) + rnd.uniform(-.014, .014), 4)
        else:
            lat = lng = None; nocoord += 1
        name = clean(r['NURSING HOME PROVIDER NAME']) or clean(r['DOING BUSINESS AS NAME']) or clean(r['ORGANIZATION NAME'])
        fac.append(dict(nm=name, op=clean(r['ORGANIZATION NAME']), ad=clean(r['ADDRESS LINE 1']), ci=clean(r['CITY']).title(),
                        s=clean(r['STATE']), z=z, pt=r['PROPRIETARY_NONPROFIT'], ch=r['AFFILIATION ENTITY ID'] or '',
                        ccn=r['CCN'], lat=lat, lng=lng))
        eid2i[r['ENROLLMENT ID']] = len(fac) - 1
    print('facilities', len(fac), 'without coordinates', nocoord)

    lens_chain = defaultdict(list)
    for i, x in enumerate(fac):
        if x['ch']:
            lens_chain[x['ch']].append(i)

    own_f, mgr_f, meta, names = defaultdict(set), defaultdict(set), {}, defaultdict(Counter)
    for r in own:
        i = eid2i.get(r['ENROLLMENT ID'])
        k = r['ASSOCIATE ID - OWNER']
        if i is None or not k:
            continue
        isorg = r['TYPE - OWNER'] == 'O'
        n = clean(r['ORGANIZATION NAME - OWNER']) if isorg else clean(' '.join(filter(None, [r['FIRST NAME - OWNER'], r['MIDDLE NAME - OWNER'], r['LAST NAME - OWNER']])))
        if not n:
            continue
        names[k][n] += 1
        t = meta.setdefault(k, set()); t.add('ORG' if isorg else 'IND')
        if isorg:
            for col, tag in FLAGS.items():
                if r.get(col) == 'Y':
                    t.add(tag)
        role = r['ROLE CODE - OWNER']
        if role in OWN_ROLES:
            own_f[k].add(i)
        if isorg and r.get('MANAGEMENT SERVICES COMPANY - OWNER') == 'Y' and role in MGR_ROLES:
            mgr_f[k].add(i)

    def mk(src):
        out = [dict(k=k, n=names[k].most_common(1)[0][0], t=sorted(meta[k]), f=sorted(s)) for k, s in src.items() if len(s) >= 2]
        return sorted(out, key=lambda o: -len(o['f']))
    owners, mgrs = mk(own_f), mk(mgr_f)
    chain_list = sorted([dict(k=cid, n=chains.get(cid, {'n': 'Chain ' + cid})['n'], f=idx) for cid, idx in lens_chain.items()], key=lambda o: -len(o['f']))

    # sanity checks so a bad download never replaces good data
    problems = []
    if len(fac) < 10000: problems.append('only %d facilities' % len(fac))
    if len(chain_list) < 300: problems.append('only %d chains' % len(chain_list))
    if rated < 300: problems.append('only %d chains have an overall rating (column names may have changed: %s)' % (rated, list(chn[0].keys())[:14]))
    if len(owners) < 2000: problems.append('only %d multi-building owners' % len(owners))
    if nocoord > len(fac) * .02: problems.append('%d buildings without coordinates' % nocoord)
    if problems:
        print('::error::Refusing to write data.json: ' + '; '.join(problems)); sys.exit(1)

    keys = ['nm', 'op', 'ad', 'ci', 's', 'z', 'pt', 'ch', 'ccn', 'lat', 'lng']
    data = dict(keys=keys, F=[[x[k] for k in keys] for x in fac], chains=chains, national=national,
                meta=dict(built=date.today().strftime('%b %-d, %Y'), sources='; '.join(re.sub(r'^\w+?__', '', os.path.basename(f)) for f in (ef, of, cf))),
                lens=dict(chain=chain_list, owner=[dict(k=o['k'], n=o['n'], t=o['t'], f=o['f']) for o in owners],
                          mgr=[dict(k=o['k'], n=o['n'], t=o['t'], f=o['f']) for o in mgrs]))
    with open(a.out, 'w') as fh:
        fh.write(json.dumps(data, separators=(',', ':')))
    print('wrote', a.out, os.path.getsize(a.out) // 1024, 'KB;', len(chain_list), 'chains,', len(owners), 'owners,', len(mgrs), 'managers')

if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print('::error::%s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:800]))
        raise
