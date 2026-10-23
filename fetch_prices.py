#!/usr/bin/env python3
"""
Price cache for the Vavetra Yard app (runs on GitHub Actions).

Downloads ALL of India's mandi prices from data.gov.in (Agmarknet) in a few big calls,
splits them per state and writes   <out>/prices/GJ.json, MH.json, ...   + meta.json.
The app downloads its state's file instead of calling data.gov.in itself, so
one key (a GitHub Secret, never inside the app) serves every phone.

  cur   today's live list           (CURRENT resource, fetched every run)
  hist  last ~4 days, newest first  (HISTORY resource, changes once a night: fetched every 6 hours)

Row format (short, to keep the files small):
  [day "dd/MM/yyyy", district, market, commodity, variety, grade, min, max, modal]

Safety: if the live list cannot be downloaded the run fails and the previous files stay as they are.
Usage: DATA_GOV_IN_KEY=... python fetch_prices.py <out_dir>
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta

BASE = "https://api.data.gov.in/resource/"
CURRENT = "9ef84268-d588-465a-a308-a864a43d0070"
HISTORY = "35985678-0d79-46b4-9ed6-6f13308a1d24"
LIMIT = 4000
HIST_EVERY = 6 * 3600          # seconds
HIST_DAYS = 4

# Government spelling -> app state key (same table as States.kt in the app)
STATES = {
    "GJ": ["Gujarat"], "MH": ["Maharashtra"], "RJ": ["Rajasthan"], "MP": ["Madhya Pradesh"],
    "UP": ["Uttar Pradesh"], "PB": ["Punjab"], "HR": ["Haryana"], "KA": ["Karnataka"],
    "TN": ["Tamil Nadu"], "TG": ["Telangana"], "AP": ["Andhra Pradesh"], "KL": ["Keralam", "Kerala"],
    "WB": ["West Bengal"], "OD": ["Odisha", "Orissa"], "BR": ["Bihar"], "CG": ["Chattisgarh", "Chhattisgarh"],
    "JH": ["Jharkhand"], "HP": ["Himachal Pradesh"], "UK": ["Uttrakhand", "Uttarakhand"],
    "JK": ["Jammu and Kashmir", "Jammu & Kashmir"], "GA": ["Goa"], "AS": ["Assam"], "TR": ["Tripura"],
    "ML": ["Meghalaya"], "MN": ["Manipur"], "NL": ["Nagaland"], "MZ": ["Mizoram"],
    "AR": ["Arunachal Pradesh"], "SK": ["Sikkim"], "DL": ["NCT of Delhi", "Delhi"], "CH": ["Chandigarh"],
    "PY": ["Pondicherry", "Puducherry"], "AN": ["Andaman and Nicobar"], "LA": ["Ladakh"],
    "DD": ["Dadra and Nagar Haveli and Daman and Diu", "Dadra and Nagar Haveli", "Daman and Diu",
           "Dadra & Nagar Haveli, Daman & Diu"],
}
KEY_OF = {n.lower(): k for k, names in STATES.items() for n in names}


def api(resource, params, offset):
    key = os.environ.get("DATA_GOV_IN_KEY", "").strip()
    if not key:
        sys.exit("DATA_GOV_IN_KEY secret is missing.")
    q = [("api-key", key), ("format", "json"), ("limit", str(LIMIT)), ("offset", str(offset))] + params
    url = BASE + resource + "?" + urllib.parse.urlencode(q, safe="[]")
    last = None
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "vavetra-prices/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                j = json.loads(r.read().decode("utf-8"))
            if j.get("error"):
                raise RuntimeError(j["error"])
            return j
        except Exception as e:  # never print the URL: it holds the key
            last = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"data.gov.in did not answer ({resource[:8]}…, offset {offset}): {last}")


def g(o, *names):
    for n in names:
        v = o.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def row(o):
    """(state key, short row) or None."""
    st = KEY_OF.get(g(o, "state", "State").lower())
    date = g(o, "arrival_date", "Arrival_Date")
    if not st or not date:
        return None
    def num(*n):
        try:
            return float(g(o, *n).replace(",", "") or 0)
        except ValueError:
            return 0.0
    modal = num("modal_price", "Modal_Price")
    if modal <= 0 or not g(o, "commodity", "Commodity") or not g(o, "market", "Market"):
        return None
    r = [date, g(o, "district", "District"), g(o, "market", "Market"), g(o, "commodity", "Commodity"),
         g(o, "variety", "Variety"), g(o, "grade", "Grade"),
         num("min_price", "Min_Price"), num("max_price", "Max_Price"), modal]
    r[6:9] = [int(x) if x == int(x) else x for x in r[6:9]]
    return st, r


def fetch_current():
    out, offset = {}, 0
    for _ in range(40):
        j = api(CURRENT, [], offset)
        recs = j.get("records") or []
        for o in recs:
            x = row(o)
            if x:
                out.setdefault(x[0], []).append(x[1])
        offset += len(recs)
        total = int(j.get("total") or 0)
        print(f"current: {offset}/{total}")
        if not recs or offset >= total:
            break
        time.sleep(1)
    return out


def fetch_history():
    out, offset, newest = {}, 0, None
    for _ in range(60):
        j = api(HISTORY, [("sort[Arrival_Date]", "desc")], offset)
        recs = j.get("records") or []
        oldest = None
        for o in recs:
            x = row(o)
            if not x:
                continue
            d = datetime.strptime(x[1][0], "%d/%m/%Y")
            newest = newest or d
            oldest = d if oldest is None or d < oldest else oldest
            if d >= newest - timedelta(days=HIST_DAYS - 1):
                out.setdefault(x[0], []).append(x[1])
        offset += len(recs)
        total = int(j.get("total") or 0)
        print(f"history: {offset} rows read, oldest {oldest:%d/%m/%Y}" if oldest else f"history: {offset}")
        if not recs or offset >= total or (oldest and newest and oldest < newest - timedelta(days=HIST_DAYS - 1)):
            break
        time.sleep(1)
    return out


def main():
    out_dir = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "out", "prices")
    os.makedirs(out_dir, exist_ok=True)
    now = int(time.time())

    old = {}
    for k in STATES:
        p = os.path.join(out_dir, f"{k}.json")
        if os.path.exists(p):
            try:
                old[k] = json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
    meta_p = os.path.join(out_dir, "meta.json")
    meta = json.load(open(meta_p, encoding="utf-8")) if os.path.exists(meta_p) else {}

    cur = fetch_current()
    cur_ok = now if any(cur.values()) else meta.get("cur_ok", 0)
    if not any(cur.values()) and now - cur_ok < 12 * 3600:
        # An empty live list early in the morning is normal; keep yesterday's for a while.
        cur = {k: v.get("cur", []) for k, v in old.items()}

    hist_at = meta.get("hist_at", 0)
    hist = None
    if now - hist_at >= HIST_EVERY:
        try:
            hist = fetch_history() or None
            if hist:
                hist_at = now
        except Exception as e:
            print("history failed, keeping the old one:", e)
    if hist is None:
        hist = {k: v.get("hist", []) for k, v in old.items()}

    n = 0
    for k in STATES:
        c, h = cur.get(k, []), hist.get(k, [])
        if not c and not h:
            continue
        with open(os.path.join(out_dir, f"{k}.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "updated": now, "hist_at": hist_at, "cur": c, "hist": h}, f,
                      ensure_ascii=False, separators=(",", ":"))
        n += len(c) + len(h)
    meta = {"updated": now, "cur_ok": cur_ok, "hist_at": hist_at,
            "states": sorted(k for k in STATES if cur.get(k) or hist.get(k))}
    json.dump(meta, open(meta_p, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"wrote {len(meta['states'])} states, {n} rows")


if __name__ == "__main__":
    main()
