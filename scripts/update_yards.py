#!/usr/bin/env python3
"""
Monthly update of yards.tsv (yard positions for the Vavetra Yard app).

1. Download the list of all yards (APMC markets) from Agmarknet.
2. Compare with last month's list (agmarknet_list.txt):
   - new yards      -> get a position (OpenStreetMap Nominatim, checked to be inside its district)
   - removed yards  -> taken out
3. Rebuild yards.tsv from yards_src.txt (the one source of truth).

Safety: if Agmarknet does not answer, or sends a list much shorter than last month's,
nothing is changed and the run fails (GitHub then e-mails the repo owner).

Files:
  yards_src.txt       state|district|market|lat|lng|quality   (quality "district" = only the district is known)
  agmarknet_list.txt  state|district|market                   (last month's list, as Agmarknet writes it)
  yards.tsv           what the app downloads: STATE<TAB>key<TAB>lat<TAB>lng<TAB>1|0
"""
import html, json, math, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "yards_src.txt")
LIST = os.path.join(ROOT, "agmarknet_list.txt")
OUT = os.path.join(ROOT, "yards.tsv")
API = "https://api.agmarknet.gov.in/v1/guest-location-filters"
UA = "VavetraYard-yard-update/1.0 (https://github.com/chhatrolasmit/vavetra-data)"

CODE = {'Gujarat': 'GJ', 'Maharashtra': 'MH', 'Rajasthan': 'RJ', 'Madhya Pradesh': 'MP', 'Uttar Pradesh': 'UP',
        'Punjab': 'PB', 'Haryana': 'HR', 'Karnataka': 'KA', 'Tamil Nadu': 'TN', 'Telangana': 'TG',
        'Andhra Pradesh': 'AP', 'Keralam': 'KL', 'Kerala': 'KL', 'West Bengal': 'WB', 'Odisha': 'OD', 'Bihar': 'BR',
        'Chattisgarh': 'CG', 'Chhattisgarh': 'CG', 'Jharkhand': 'JH', 'Himachal Pradesh': 'HP', 'Uttarakhand': 'UK',
        'Uttrakhand': 'UK', 'Jammu and Kashmir': 'JK', 'Goa': 'GA', 'Assam': 'AS', 'Tripura': 'TR',
        'Meghalaya': 'ML', 'Manipur': 'MN', 'Nagaland': 'NL', 'Mizoram': 'MZ', 'Arunachal Pradesh': 'AR',
        'Sikkim': 'SK', 'NCT of Delhi': 'DL', 'Chandigarh': 'CH', 'Pondicherry': 'PY',
        'Andaman and Nicobar': 'AN', 'Ladakh': 'LA'}
# Same names the app writes differently (Places.kt sameYard, Gujarat): alias -> name in the app
GJ_SAME = {'talalagir': 'Talala', 'zalod(zalod)': 'Jhalod', 'zalod': 'Jhalod', 's.mandvi': 'Mandvi',
           'chotial(veg,yard)': 'Chotila(Veg,Yard Chotila)', 'radheja': 'Randheja', 'vyra': 'Vyara',
           'daboi': 'Dabhoi', 'apmckhedbrahma': 'Khedbrahma', 'wankaner': 'Vankaner',
           'junagarh': 'Junagadh', 'nadiyad': 'Nadiad'}
# Same yard name twice in one state: the app adds the district (Places.kt sameNameInState)
SAME_IN_STATE = {'rompicherla', 'sonari', 'parathode vfpck market', 'puthur vfpck market', 'pallikkal vfpck market',
                 'ibrahimpatnam', 'anna nagar(uzhavar sandhai)', 'parathode', 'puthur', 'pallikkal', 'anna nagar'}
# Private yards / company names are not offered by the app
PRIVATE = re.compile(r',|\bPvt\b|Private|Krushi|Krishi Bazar|\bLtd\b|Co-Op', re.I)
STOP = set('pmy smy fv ff grain rythu rm regulated town city cantt sadar union apmc market mandi veg vegetable '
           'vegetables yard subyard sub fruit fruits krishi upaj uzhavar sandhai vfpck new old main cotton dist '
           'district the agricultural produce committee and of hq kisan flower flowers onion potato fish gur '
           'cattle animal sabzi sabji bazar bazaar mkt road station nagar'.split())


def key(s):
    """Must stay the same as YardGeo.key() in the app."""
    s = s.lower().replace('&amp;', '&')
    s = re.sub(r'\(\s*f\s*&\s*v\s*\)', '', s)
    s = re.sub(r'\b(apmc|vfpck|market|pmy|smy|uzhavar sandhai|uzhavar|sandhai|rm)\b', '', s)
    s = re.sub(r'^apmc', '', s)
    return re.sub(r'[^a-z]', '', s)


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(d))


def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


# ---------------------------------------------------------------- 1. Agmarknet list
def fetch_agmarknet():
    rows = []
    for s in get_json(API):
        sid, sname = s['id'], html.unescape(s['state_name']).strip()
        for d in get_json(f"{API}?state_id={sid}"):
            did, dname = d['id'], html.unescape(d['district_name']).strip()
            for m in get_json(f"{API}?state_id={sid}&district_id={did}"):
                name = re.sub(r'\s+', ' ', html.unescape(m['mkt_name'])).strip()
                if name:
                    rows.append((sname, dname, name))
            time.sleep(0.2)
    return rows


def clean_name(m):
    """Agmarknet name -> the name kept in yards_src (no 'APMC' at the ends)."""
    m = re.sub(r'(?i)\s*\bAPMC\s*$', '', m).strip()
    m = re.sub(r'(?i)^APMC\s+', '', m).strip()
    return m


# ---------------------------------------------------------------- 2. position of a new yard
def towns(market):
    base = market.split('(')[0]
    out = [b for b in re.findall(r'\(([^)]*)\)', market)] + [base]
    res = []
    for t in out:
        w = [x for x in re.split(r'[^A-Za-z]+', t) if x and x.lower() not in STOP]
        if w:
            res.append(' '.join(w))
    return res


def nominatim(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {'q': q, 'format': 'json', 'limit': 8, 'countrycodes': 'in'})
    time.sleep(1.2)  # Nominatim rule: at most 1 request per second
    try:
        return [(float(r['lat']), float(r['lon']), r.get('addresstype') or r.get('type') or '') for r in get_json(url)]
    except Exception:
        return []


def medoid(ps):
    return min(ps, key=lambda p: sum(km(p, q) for q in ps)) if ps else None


def locate(state, district, market, src):
    """(lat, lng, quality). Town found near its district -> 'town', else the district's position -> 'district'."""
    same_d = [(float(r[3]), float(r[4])) for r in src if r[0] == state and r[1] == district and r[5] != 'district']
    anchor = medoid(same_d)
    if anchor is None:
        d = nominatim(f"{district} district, {state}, India") or nominatim(f"{district}, {state}, India")
        anchor = (d[0][0], d[0][1]) if d else None
    if anchor is None:
        same_s = [(float(r[3]), float(r[4])) for r in src if r[0] == state]
        anchor = medoid(same_s[:200])
    for t in towns(market):
        for q in (f"{t}, {district}, {state}, India", f"{t}, {state}, India"):
            c = [p for p in nominatim(q) if anchor is None or km(p, anchor) <= 80]
            if c:
                towns_first = sorted(c, key=lambda p: (p[2] not in ('town', 'city', 'village', 'suburb', 'hamlet'),
                                                       km(p, anchor) if anchor else 0))
                return round(towns_first[0][0], 5), round(towns_first[0][1], 5), 'osm'
    if anchor:
        return round(anchor[0], 5), round(anchor[1], 5), 'district'
    return None


# ---------------------------------------------------------------- 3. yards.tsv
def build(src):
    seen, base = {}, {}
    for st, d, m, la, lo, q in src:
        c = CODE.get(st)
        if not c:
            continue
        k = key(m)
        if not k:
            continue
        v = (round(float(la), 4), round(float(lo), 4), '0' if q == 'district' else '1')
        seen.setdefault((c, k), v)
        if m.lower() in SAME_IN_STATE:
            seen[(c, k + key(d.title()))] = v
        b = key(m.split('(')[0])
        if b and '(' in m:
            base.setdefault((c, b), v)
    for kk, v in base.items():
        seen.setdefault(kk, v)
    for a, cn in GJ_SAME.items():
        v = seen.get(('GJ', key(a)))
        if v:
            seen.setdefault(('GJ', key(cn)), v)
    return [f"{c}\t{k}\t{la}\t{lo}\t{p}" for (c, k), (la, lo, p) in sorted(seen.items())]


def read_rows(path, n):
    if not os.path.exists(path):
        return []
    return [tuple(l.rstrip('\n').split('|')) for l in open(path, encoding='utf-8') if l.count('|') == n - 1]


def main():
    src = read_rows(SRC, 6)
    old_list = read_rows(LIST, 3)
    if '--rebuild-only' in sys.argv:
        new_list = old_list
    else:
        new_list = fetch_agmarknet()
        # Agmarknet half-answered → do not touch anything
        if len(new_list) < 3000 or (old_list and len(new_list) < 0.9 * len(old_list)):
            sys.exit(f"Agmarknet list too short ({len(new_list)} yards, last month {len(old_list)}): nothing changed.")

    def ident(st, m):
        return (st, key(clean_name(m)))

    now_ids = {ident(s, m) for s, d, m in new_list}
    src_ids = {(r[0], key(r[2])) for r in src}

    # Removed: in last month's list, not in this month's
    removed = []
    if old_list:
        gone = {ident(s, m) for s, d, m in old_list} - now_ids
        if gone:
            before = len(src)
            src = [r for r in src if (r[0], key(r[2])) not in gone]
            removed = sorted(m for s, d, m in old_list if ident(s, m) in gone)
            print(f"removed {before - len(src)} rows: {removed}")

    # Added: in this month's list, not known yet (private / company yards are not offered by the app)
    added = []
    for s, d, m in new_list:
        name = clean_name(m)
        if PRIVATE.search(name) or ident(s, m) in src_ids:
            continue
        pos = locate(s, d, name, src)
        if not pos:
            print("no position:", s, d, name)
            continue
        src.append((s, d, name, str(pos[0]), str(pos[1]), pos[2]))
        src_ids.add(ident(s, m))
        added.append(f"{name} ({d}, {s}) {pos[2]}")
    if added:
        print(f"added {len(added)}:", *added, sep="\n  ")

    lines = build(src)
    if len(lines) < 3000:
        sys.exit(f"yards.tsv would have only {len(lines)} lines: nothing changed.")
    with open(SRC, 'w', encoding='utf-8') as f:
        f.writelines('|'.join(r) + '\n' for r in src)
    if new_list:
        with open(LIST, 'w', encoding='utf-8') as f:
            f.writelines('|'.join(r) + '\n' for r in new_list)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.writelines(l + '\n' for l in lines)
    # Short summary for the commit message
    with open(os.path.join(ROOT, '.update_summary'), 'w', encoding='utf-8') as f:
        f.write(f"Monthly yard update: {len(added)} added, {len(removed)} removed, {len(lines)} keys\n")
    print(f"yards.tsv: {len(lines)} keys")


if __name__ == '__main__':
    main()
