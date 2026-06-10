#!/usr/bin/env python3
"""Build SQL batches + repo data artifact from scrape_adi.py output.

Usage: python3 scripts/build_adi_sql.py --scrape /tmp/adi_scrape --sqlout /tmp/adi_sql
Writes: /tmp/adi_sql/batch_NN.sql (adi_determinations upserts),
        /tmp/adi_sql/subparts.sql  (adi_subparts upserts),
        data/adi.json.gz           (full normalized dataset, for reproducibility/refresh)
"""
import argparse, gzip, json, os, re, time

def esc(s):
    return (s or '').replace("'", "''").replace('\x00', '')

def arr(items):
    if not items:
        return "'{}'::text[]"
    return 'array[' + ','.join("'" + esc(i) + "'" for i in items) + ']'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scrape', default='/tmp/adi_scrape')
    ap.add_argument('--sqlout', default='/tmp/adi_sql')
    ap.add_argument('--batch', type=int, default=200)
    args = ap.parse_args()
    os.makedirs(args.sqlout, exist_ok=True)

    rows = json.load(open(os.path.join(args.scrape, 'rows.json')))
    details = json.load(open(os.path.join(args.scrape, 'details.json')))
    smap = json.load(open(os.path.join(args.scrape, 'subpart_map.json')))
    labels = json.load(open(os.path.join(args.scrape, 'subpart_labels.json')))

    # option value "Part 60$A" -> code "60-A"
    def code_of(optval):
        part, sub = optval.split('$', 1)
        return part.replace('Part ', '').strip() + '-' + sub.strip()

    ctrl_subs = {}
    for optval, ctrls in smap.items():
        c = code_of(optval)
        for ctrl in ctrls:
            ctrl_subs.setdefault(ctrl, []).append(c)

    extra_path = os.path.join(args.scrape, 'extra.json')
    extra = json.load(open(extra_path)) if os.path.exists(extra_path) else {}

    def iso_date(us):
        m = re.match(r'(\d{2})/(\d{2})/(\d{4})$', us or '')
        if not m or m.group(3) < '1950':   # EPA stores undated letters as 12/30/1899
            return None
        return f'{m.group(3)}-{m.group(1)}-{m.group(2)}'

    recs = []
    seen = set()
    for r in rows:
        ctrl = r['control_number']
        d = details.get(ctrl, {})
        cats = [c.strip() for c in (r['categories'] or '').split(',') if c.strip()]
        seen.add(ctrl)
        recs.append({
            'control_number': ctrl,
            'title': r['title'],
            'letter_date': iso_date(r['date']),
            'categories': cats,
            'office': r['office'] or None,
            'author': r['author'] or None,
            'abstract': d.get('abstract') or None,
            'subparts': sorted(set(ctrl_subs.get(ctrl, []))),
        })
    # records only reachable via subpart queries (mostly undated letters)
    for ctrl, d in extra.items():
        if ctrl in seen:
            continue
        cats = [c.strip() for c in (d.get('categories') or '').split(',') if c.strip()]
        recs.append({
            'control_number': ctrl,
            'title': d.get('title') or ctrl,
            'letter_date': iso_date(d.get('date')),
            'categories': cats,
            'office': d.get('office') or None,
            'author': d.get('author') or None,
            'abstract': d.get('abstract') or None,
            'subparts': sorted(set(ctrl_subs.get(ctrl, []))),
        })

    # deterministic order so refresh runs only commit on real content changes
    recs.sort(key=lambda r: r['control_number'])

    # data artifact for the public repo (public EPA data) — includes the subpart
    # lookup so the adi-load edge function can rebuild both tables from this file
    label_map = {}
    for optval, label in labels.items():
        c = code_of(optval)
        m = re.match(r'Part\s+(\d+),\s*(\S+)\s*-?\s*(.*)$', label)
        part, sub, desc = (m.group(1), m.group(2), m.group(3).strip()) if m else (c.split('-')[0], c.split('-', 1)[1], '')
        label_map[c] = {'part': part, 'subpart': sub, 'description': desc,
                        'n_dets': len(smap.get(optval, []))}
    artifact = {'source': 'https://cfpub.epa.gov/adi/', 'scraped': time.strftime('%Y-%m-%d'),
                'labels': label_map, 'determinations': recs}
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(repo_root, 'data'), exist_ok=True)
    with gzip.open(os.path.join(repo_root, 'data', 'adi.json.gz'), 'wt') as f:
        json.dump(artifact, f)

    # determination batches
    nb = 0
    for i in range(0, len(recs), args.batch):
        chunk = recs[i:i + args.batch]
        vals = []
        for r in chunk:
            vals.append('(' + ','.join([
                "'" + esc(r['control_number']) + "'",
                "'" + esc(r['title']) + "'",
                ("'" + r['letter_date'] + "'") if r['letter_date'] else 'null',
                arr(r['categories']),
                ("'" + esc(r['office']) + "'") if r['office'] else 'null',
                ("'" + esc(r['author']) + "'") if r['author'] else 'null',
                ("'" + esc(r['abstract']) + "'") if r['abstract'] else 'null',
                arr(r['subparts']),
            ]) + ')')
        sql = ('insert into public.adi_determinations '
               '(control_number,title,letter_date,categories,office,author,abstract,subparts) values\n'
               + ',\n'.join(vals)
               + '\non conflict (control_number) do update set title=excluded.title,'
                 'letter_date=excluded.letter_date,categories=excluded.categories,'
                 'office=excluded.office,author=excluded.author,abstract=excluded.abstract,'
                 'subparts=excluded.subparts;')
        nb += 1
        open(os.path.join(args.sqlout, f'batch_{nb:02d}.sql'), 'w').write(sql)

    # subpart lookup
    svals = []
    for optval, label in labels.items():
        c = code_of(optval)
        m = re.match(r'Part\s+(\d+),\s*(\S+)\s*-?\s*(.*)$', label)
        part, sub, desc = (m.group(1), m.group(2), m.group(3).strip()) if m else (c.split('-')[0], c.split('-', 1)[1], '')
        n = len(smap.get(optval, []))
        svals.append(f"('{esc(c)}','{esc(part)}','{esc(sub)}','{esc(desc)}',{n})")
    sql = ('insert into public.adi_subparts (code,part,subpart,description,n_dets) values\n'
           + ',\n'.join(svals)
           + '\non conflict (code) do update set part=excluded.part,subpart=excluded.subpart,'
             'description=excluded.description,n_dets=excluded.n_dets;')
    open(os.path.join(args.sqlout, 'subparts.sql'), 'w').write(sql)

    tagged = sum(1 for r in recs if r['subparts'])
    withabs = sum(1 for r in recs if r['abstract'])
    print(f'{len(recs)} determinations -> {nb} batches; {len(svals)} subparts; '
          f'{tagged} subpart-tagged; {withabs} with abstracts')

if __name__ == '__main__':
    main()
