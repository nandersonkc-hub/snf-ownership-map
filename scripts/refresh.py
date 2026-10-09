#!/usr/bin/env python3
"""Download the latest CMS files, then rebuild data.json.

Order of attempts for each of the three files:
  1. An override URL in an environment variable (ENROLLMENTS_URL, OWNERS_URL, CHAIN_URL).
  2. The data.cms.gov catalog (https://data.cms.gov/data.json), matched by dataset title.
  3. The URLs listed in sources.json (the links that were current when this repo was made).

Run locally:  python scripts/refresh.py
Skip the download and rebuild from files already in data/raw:  python scripts/refresh.py --no-download
"""
import argparse, io, json, os, re, subprocess, sys, zipfile
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'data', 'raw')
CATALOG = 'https://data.cms.gov/data.json'
HEADERS = {'User-Agent': 'snf-ownership-map/1.0 (monthly data refresh)'}

SOURCES = {
    'enrollments': dict(env='ENROLLMENTS_URL', title=r'skilled nursing facility enrollments', label='SNF_Enrollments'),
    'owners': dict(env='OWNERS_URL', title=r'skilled nursing facility all owners', label='SNF_All_Owners'),
    'chain': dict(env='CHAIN_URL', title=r'nursing home chain performance', label='Chain_Performance'),
}

def catalog_urls():
    """Map each source key to the newest downloadable CSV/ZIP the catalog lists for it."""
    try:
        cat = requests.get(CATALOG, headers=HEADERS, timeout=120).json()
    except Exception as e:
        print('  catalog unavailable:', e); return {}
    out = {}
    for ds in cat.get('dataset', []):
        title = (ds.get('title') or '').lower()
        for key, src in SOURCES.items():
            if key in out or not re.search(src['title'], title):
                continue
            cands = []
            for d in ds.get('distribution', []):
                u = d.get('downloadURL') or d.get('accessURL') or ''
                if re.search(r'\.(csv|zip)(\?|$)', u, re.I):
                    latest = 'latest' in ((d.get('title') or '') + (d.get('description') or '')).lower()
                    cands.append((latest, d.get('modified') or d.get('issued') or '', u))
            if cands:
                cands.sort(reverse=True)
                out[key] = cands[0][2]
    return out

def fetch(key, url):
    print('  downloading', key, url)
    r = requests.get(url, headers=HEADERS, timeout=600)
    r.raise_for_status()
    name = SOURCES[key]['label']
    saved = []
    if url.lower().split('?')[0].endswith('.zip') or r.content[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for n in z.namelist():
                if n.lower().endswith('.csv'):
                    path = os.path.join(RAW, '%s__%s' % (name, os.path.basename(n)))
                    open(path, 'wb').write(z.read(n)); saved.append(path)
    else:
        path = os.path.join(RAW, '%s__download.csv' % name)
        open(path, 'wb').write(r.content); saved.append(path)
    if not saved:
        raise RuntimeError('no CSV found in download for %s' % key)
    return saved

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-download', action='store_true')
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    if not a.no_download:
        for f in os.listdir(RAW):
            if f.endswith('.csv'): os.remove(os.path.join(RAW, f))
        fallback = json.load(open(os.path.join(ROOT, 'sources.json')))
        found = None
        failed = []
        for key, src in SOURCES.items():
            urls = []
            if os.environ.get(src['env']): urls.append(('override', os.environ[src['env']]))
            if found is None:
                print('Reading the data.cms.gov catalog...'); found = catalog_urls()
            if key in found: urls.append(('catalog', found[key]))
            if fallback.get(key): urls.append(('sources.json', fallback[key]))
            ok = False
            for how, u in urls:
                try:
                    fetch(key, u); ok = True; print('  ok via', how); break
                except Exception as e:
                    print('  failed via %s: %s' % (how, e))
            if not ok: failed.append(key)
        if failed:
            sys.exit('Could not download: %s. Existing data.json left unchanged.' % ', '.join(failed))
    subprocess.check_call([sys.executable, os.path.join(ROOT, 'scripts', 'build_data.py'), '--raw', RAW, '--out', os.path.join(ROOT, 'data.json')])

if __name__ == '__main__':
    main()
