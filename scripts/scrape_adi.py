#!/usr/bin/env python3
"""Scrape EPA's Applicability Determination Index (cfpub.epa.gov/adi).

Public-domain EPA data. Pulls all determinations (metadata + Q/A abstracts)
plus a subpart -> control-number map built by querying each subpart filter.
Polite: sequential requests with a delay, no parallelism.

Usage: python3 scripts/scrape_adi.py --out /tmp/adi_scrape
Outputs: rows.json, details.json, subpart_map.json, subpart_labels.json
"""
import argparse, json, os, re, sys, time
import html as H
import urllib.parse, urllib.request, http.cookiejar

BASE = 'https://cfpub.epa.gov/adi/'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
DELAY = 0.25


class Session:
    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.op.addheaders = [('User-Agent', UA)]

    def get(self, url, data=None, tries=3):
        if data is not None:
            data = urllib.parse.urlencode(data, doseq=True).encode()
        for attempt in range(tries):
            try:
                time.sleep(DELAY)
                with self.op.open(url if url.startswith('http') else BASE + url, data, timeout=300) as r:
                    return r.read().decode('utf8', 'replace')
            except Exception as e:
                if attempt == tries - 1:
                    raise
                print(f'  retry {attempt+1} after {e}', flush=True)
                time.sleep(3 * (attempt + 1))


def parse_form(src):
    """Return (action, hidden-field dict) of the main CF POST form."""
    m = re.search(r'<FORM[^>]*ACTION="(index\.cfm[^"]*)"[^>]*>(.*?)</FORM>', src, re.S | re.I)
    if not m:
        raise RuntimeError('no CF form in page')
    action, body = m.group(1), m.group(2)
    fields = {}
    for chunk in re.split(r'<input', body, flags=re.I)[1:]:
        name = re.search(r'NAME="([^"]*)"', chunk, re.I)
        typ = re.search(r'TYPE="([^"]*)"', chunk, re.I)
        val = re.search(r'VALUE="([^"]*)"', chunk, re.I)
        if name and typ and typ.group(1).lower() == 'hidden':
            fields[name.group(1)] = H.unescape(val.group(1) if val else '')
    return H.unescape(action), fields


def run_query(sess, criteria):
    """criteria -> results page HTML + the results form (for detail POSTs)."""
    main = sess.get('index.cfm?fuseaction=home.dsp_query')
    act = H.unescape(re.search(r'<FORM[^>]*ACTION="(index\.cfm[^"]*)"', main, re.I).group(1))
    crit = {'fuseaction': 'home.dsp_review_critieria'}
    crit.update(criteria)
    review = sess.get(act, crit)
    act2, fields = parse_form(review)
    if fields.get('fuseaction') != 'home.dsp_show_results_table':
        raise RuntimeError('criteria not accepted: ' + str(criteria))
    res = sess.get(act2, fields)
    return res


def parse_rows(res):
    recs = []
    for m in re.finditer(r'<input name="control_number" type="checkbox" value="([^"]+)">(.*?)</tr>', res, re.S):
        ctrl, body = m.group(1), m.group(2)
        tds = re.findall(r'<td[^>]*>(.*?)</td>', body, re.S)
        clean = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', H.unescape(td))).strip() for td in tds]
        # tds: [ctrl, title, date, categories, office, author]
        recs.append({'control_number': ctrl, 'title': clean[1], 'date': clean[2],
                     'categories': clean[3], 'office': clean[4], 'author': clean[5]})
    return recs


def parse_details(det):
    """Parse dsp_show_results detail blocks -> {ctrl: {author, categories, office, abstract}}."""
    out = {}
    blocks = re.split(r'<input name="control_number" type="checkbox" value="', det)[1:]
    for b in blocks:
        ctrl = b[:b.index('"')]
        divs = re.findall(r'<div class="no-sort"[^>]*>(.*?)</div>', b, re.S)
        meta, abstract = {}, ''
        for d in divs:
            text = H.unescape(re.sub(r'<br\s*/?>', '\n', d))
            text = re.sub(r'<[^>]+>', ' ', text)
            if '<strong>Author</strong>' in d or 'Author</strong>' in d:
                for key in ('Author', 'Categories', 'Office'):
                    km = re.search(key + r'\s*:\s*([^:]*?)(?=(?:Author|Categories|Office)\s*:|$)',
                                   re.sub(r'\s+', ' ', text))
                    if km:
                        meta[key.lower()] = km.group(1).replace('\xa0', ' ').strip()
            elif d.strip().startswith('Q:') or '\nQ:' in text or text.strip().startswith('Q:'):
                abstract = re.sub(r'\n{2,}', '\n', text).strip()
        out[ctrl] = {**meta, 'abstract': abstract}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/tmp/adi_scrape')
    ap.add_argument('--chunk', type=int, default=50)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    # ---- Phase A: all rows -------------------------------------------------
    rows_path = os.path.join(args.out, 'rows.json')
    sess = Session()
    res = run_query(sess, {'begindate': '01/01/1960', 'enddate': '12/31/2030'})
    act3, fields3 = parse_form(res)
    rows = parse_rows(res)
    json.dump(rows, open(rows_path, 'w'))
    print(f'A: {len(rows)} rows', flush=True)

    # ---- Phase B: Q/A abstracts in chunks ---------------------------------
    det_path = os.path.join(args.out, 'details.json')
    details = json.load(open(det_path)) if os.path.exists(det_path) else {}
    ctrls = [r['control_number'] for r in rows if r['control_number'] not in details]
    for i in range(0, len(ctrls), args.chunk):
        chunk = ctrls[i:i + args.chunk]
        f = dict(fields3)
        f['fuseaction'] = 'home.dsp_show_results'
        f['control_number'] = chunk
        try:
            det = sess.get(act3, f)
            got = parse_details(det)
        except Exception as e:
            print(f'B: chunk {i} failed ({e}); new session', flush=True)
            sess = Session()
            res = run_query(sess, {'begindate': '01/01/1960', 'enddate': '12/31/2030'})
            act3, fields3 = parse_form(res)
            f = dict(fields3); f['fuseaction'] = 'home.dsp_show_results'; f['control_number'] = chunk
            got = parse_details(sess.get(act3, f))
        details.update(got)
        json.dump(details, open(det_path, 'w'))
        print(f'B: {len(details)}/{len(rows)} abstracts', flush=True)

    # ---- Phase C: subpart -> control numbers -------------------------------
    qsrc = sess.get('index.cfm?fuseaction=home.dsp_query')
    sel = re.search(r'<select name="subpartvalue".*?</select>', qsrc, re.S | re.I).group(0)
    opts = [(v, re.sub(r'\s+', ' ', H.unescape(l)).strip())
            for v, l in re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)', sel) if v != 'ALL']
    json.dump(dict(opts), open(os.path.join(args.out, 'subpart_labels.json'), 'w'))
    map_path = os.path.join(args.out, 'subpart_map.json')
    smap = json.load(open(map_path)) if os.path.exists(map_path) else {}
    todo = [(v, l) for v, l in opts if v not in smap]
    for n, (v, l) in enumerate(todo):
        if n % 30 == 0:
            sess = Session()
        try:
            res = run_query(sess, {'subpartvalue': v})
            smap[v] = re.findall(r'name="control_number" type="checkbox" value="([^"]+)"', res)
        except Exception as e:
            print(f'C: {v} failed ({e}); new session, retrying once', flush=True)
            sess = Session()
            try:
                res = run_query(sess, {'subpartvalue': v})
                smap[v] = re.findall(r'name="control_number" type="checkbox" value="([^"]+)"', res)
            except Exception as e2:
                print(f'C: {v} FAILED twice ({e2}); marking empty', flush=True)
                smap[v] = []
        json.dump(smap, open(map_path, 'w'))
        if n % 10 == 0:
            print(f'C: {len(smap)}/{len(opts)} subparts', flush=True)

    # ---- Phase D: records the date-range query missed (undated letters) ----
    # Subpart queries can surface control numbers the date-range query missed
    # (e.g. pre-range letters); fetch their blocks via the detail view.
    have = {r['control_number'] for r in rows}
    missing = sorted({c for v in smap.values() for c in v} - have - set(details))
    extra_path = os.path.join(args.out, 'extra.json')
    extra = json.load(open(extra_path)) if os.path.exists(extra_path) else {}
    missing = [c for c in missing if c not in extra]
    if missing:
        sess = Session()
        res = run_query(sess, {'begindate': '01/01/1960', 'enddate': '12/31/2030'})
        act3, fields3 = parse_form(res)
        for i in range(0, len(missing), args.chunk):
            chunk = missing[i:i + args.chunk]
            f = dict(fields3)
            f['fuseaction'] = 'home.dsp_show_results'
            f['control_number'] = chunk
            det = sess.get(act3, f)
            for b in re.split(r'<input name="control_number" type="checkbox" value="', det)[1:]:
                ctrl = b[:b.index('"')]
                tm = re.search(r'target="_blank">(.*?)</A>&nbsp;\(' + re.escape(ctrl) + r'\)&nbsp;([0-9/]*)', b, re.S)
                rec = parse_details('<input name="control_number" type="checkbox" value="' + b).get(ctrl, {})
                rec['title'] = re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', '', tm.group(1)))).strip() if tm else ctrl
                rec['date'] = (tm.group(2).strip() if tm else '') or ''
                extra[ctrl] = rec
            json.dump(extra, open(extra_path, 'w'))
            print(f'D: {len(extra)} undated/missed records', flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
