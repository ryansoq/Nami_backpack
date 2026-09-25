"""Build mrt-data.json: stations, services (with per-segment minutes), transfer walks, fares.

Sources (all fetched 2026-09-25):
  plan.html      official planner station list (codes + names)
  planner.json   official planner results: line ride totals + walking time at each transfer
  fares_raw.json data.taipei fare table (full fare, senior/child fare, shortest-path km)
  osm.json       OpenStreetMap subway station nodes (drawing positions only)
"""
import json, re, statistics
from parse import parse

codes = dict(re.findall(r'<option value="([A-Z]+[0-9]+A?)">\S+ ([^<]+)', open('plan.html').read()))
order = list(dict.fromkeys(re.findall(r'<option value="([A-Z]+[0-9]+A?)">', open('plan.html').read())))

def seq(prefix, a, b, extra=()):
    return [f"{prefix}{i:02d}" for i in range(a, b + 1)] + list(extra)

LINES = {  # official colours and names
    "BR": ("文湖線", "#C48C31"), "R": ("淡水信義線", "#E3002C"), "G": ("松山新店線", "#008659"),
    "O": ("中和新蘆線", "#F8B61C"), "BL": ("板南線", "#0070BD"), "Y": ("環狀線", "#FFDB00"),
}
SERVICES = [
    ("BR", "BR", seq("BR", 1, 24)),
    ("R", "R", seq("R", 1, 28)),
    ("R-XB", "R", ["R22", "R22A"]),
    ("G", "G", seq("G", 1, 19)),
    ("G-XB", "G", ["G03", "G03A"]),
    ("O-HL", "O", seq("O", 1, 21)),
    ("O-LZ", "O", seq("O", 1, 12) + seq("O", 50, 54)),
    ("BL", "BL", seq("BL", 1, 23)),
    ("Y", "Y", seq("Y", 7, 20)),
]
for sid, _, cs in SERVICES:
    for c in cs:
        assert c in codes, (sid, c)
assert {c for _, _, cs in SERVICES for c in cs} == set(codes), set(codes) ^ {c for _, _, cs in SERVICES for c in cs}

# ---- fares + distances (by station name) ----
rows = json.load(open('fares_raw.json'))
fare, dist = {}, {}
for r in rows:
    k = (r['起站'], r['訖站'])
    f = int(r['優惠票價[金額]']); s = int(r['敬老卡愛心卡愛心陪伴卡及臺北市與新北市兒童'])
    if f and (k not in fare or fare[k][0] == 0):
        fare[k] = (f, s)
    dist[k] = float(r['距離'])

# ---- official ride minutes per service end-to-end ----
P = {k: parse(v) for k, v in json.load(open('planner_train.json')).items()}
def ride(key):  # minutes of the single-leg "fewest transfers" answer
    legs = P[key]['fewest']['legs']; assert len(legs) == 1, key
    return legs[0]['minutes']
TOTAL = {"BR": ride("BR01>BR24"), "R": ride("R01>R28"), "R-XB": ride("R22>R22A"), "G": ride("G01>G19"),
         "G-XB": ride("G03>G03A"), "O-HL": ride("O01>O21"), "BL": ride("BL01>BL23"), "Y": ride("Y07>Y20")}
LZ_BRANCH = ride("O12>O54")

import os
DWELL = float(os.environ.get("DWELL", "0.6"))   # fixed minutes per segment (stop + accel), rest by distance

def seg_minutes(cs, total):
    d = [max(dist.get((codes[a], codes[b]), 0), 0.3) for a, b in zip(cs, cs[1:])]
    run = max(total - DWELL * len(d), 0.1 * total)
    return [round(DWELL * (run < 0.1 * total + 1e-9 and 0 or 1) + run * x / sum(d), 2) for x in d]

# Piecewise anchors: official single-leg minutes for sub-ranges of each line
# (planner_seg_parsed.json). The pieces add up to less than the end-to-end ride
# (R: 28+19+9 = 56 vs 61), so one total spread by distance over-times long lines.
SEG = json.load(open('planner_seg_parsed.json'))
def anchors_for(cs):
    out = []
    for k, p in SEG.items():
        a, b = k.split('>')
        legs = p['fewest']['legs']
        if len(legs) == 1 and a in cs and b in cs:
            i, j = sorted((cs.index(a), cs.index(b)))
            out.append((i, j, legs[0]['minutes']))
    return sorted(out)

def spread(cs, i, j, minutes):
    d = [max(dist.get((codes[a], codes[b]), 0), 0.3) for a, b in zip(cs[i:j], cs[i + 1:j + 1])]
    run = max(minutes - DWELL * len(d), 0.2 * minutes)
    dw = (minutes - run) / len(d)
    return [round(dw + run * x / sum(d), 2) for x in d]

def line_minutes(sid, cs, total):
    mins = [None] * (len(cs) - 1)
    covered = 0
    for i, j, m in anchors_for(cs):
        if all(v is None for v in mins[i:j]):
            mins[i:j] = spread(cs, i, j, m); covered += m
    gaps = [k for k, v in enumerate(mins) if v is None]
    if gaps:   # the rest of the end-to-end total goes to the unmeasured stretch(es)
        rest = max(total - covered, 1.2 * len(gaps))
        runs, start = [], gaps[0]
        for a, b in zip(gaps, gaps[1:] + [None]):
            if b != a + 1: runs.append((start, a + 1)); start = b
        dsum = [sum(max(dist.get((codes[cs[k]], codes[cs[k + 1]]), 0), 0.3) for k in range(i, j)) for i, j in runs]
        for (i, j), ds in zip(runs, dsum):
            mins[i:j] = spread(cs, i, j, rest * ds / sum(dsum))
    return mins

services = []
for sid, line, cs in SERVICES:
    if sid == "O-LZ":
        hl = next(s for s in services if s["id"] == "O-HL")
        mins = hl["minutes"][:11] + spread(cs, 11, len(cs) - 1, LZ_BRANCH)
    else:
        mins = line_minutes(sid, cs, TOTAL[sid])
    services.append({"id": sid, "line": line, "codes": cs, "minutes": mins})

# ---- transfer walking minutes, observed per station name (mean of observations) ----
obs = {}
for k, p in P.items():
    for part in ("fastest", "fewest"):
        for w in p[part]['walks']:
            obs.setdefault(w['at'], []).append(w['minutes'])
walks = {n: round(statistics.mean(v), 1) for n, v in obs.items()}
walks.setdefault("大橋頭", 0)      # 迴龍 ↔ 蘆洲 branch: same platform
# 新埔 (BL08) and 新埔民生 (Y17) are one transfer with two names
GROUP_ALIAS = {"新埔民生": "新埔"}

# ---- positions ----
osm = json.load(open('osm.json'))['elements']
pos = {}
for e in osm:
    n = e['tags'].get('name', '')
    if n.endswith('站') and n != '台北車站': n = n[:-1]
    pos.setdefault(n, []).append((e['lat'], e['lon']))
names = sorted(set(codes.values()))
coord = {}
for n in names:
    if n in pos:
        coord[n] = (round(statistics.mean(p[0] for p in pos[n]), 5), round(statistics.mean(p[1] for p in pos[n]), 5))
# 廣慈/奉天宮 (R01) is not in OSM yet: place it east of 象山 along the line's heading (drawing only)
a, b = coord["象山"], coord["台北101/世貿"]
coord["廣慈/奉天宮"] = (round(a[0] + (a[0] - b[0]) * 0.9, 5), round(a[1] + (a[1] - b[1]) * 0.9, 5))
missing = [n for n in names if n not in coord]
assert not missing, missing

# fares as two strings over a fixed name order: char k = fare index (20 + 5k); senior stored raw
idx = {n: i for i, n in enumerate(names)}
full = []; senior = []
for a in names:
    for b in names:
        f, s = fare.get((a, b), (20, 8)) if a != b else (20, 8)
        full.append(chr(48 + (f - 20) // 5)); senior.append(str(s))
data = {
    "source": "北捷官方路線規劃 + data.taipei 票價表 + OpenStreetMap, 2026-09-25",
    "lines": {k: {"name": v[0], "color": v[1]} for k, v in LINES.items()},
    "stations": {c: {"name": codes[c]} for c in order},
    "coords": coord,
    "services": services,
    "walks": walks,
    "alias": GROUP_ALIAS,
    "names": names,
    "fare": "".join(full),
    "senior": ",".join(senior),
}
# partial-line check (planner_seg_parsed.json): single-leg minutes vs model
if os.path.exists('planner_seg_parsed.json'):
    seg = json.load(open('planner_seg_parsed.json')); errs = []
    svc = {s["id"]: s for s in services}
    for k, p in seg.items():
        a, b = k.split('>')
        legs = p['fewest']['legs']
        if len(legs) != 1: continue
        for s in services:
            if a in s["codes"] and b in s["codes"]:
                i, j = sorted((s["codes"].index(a), s["codes"].index(b)))
                errs.append(sum(s["minutes"][i:j]) - legs[0]['minutes']); break
    data["segFit"] = {"n": len(errs), "mae": round(sum(map(abs, errs)) / len(errs), 2), "errs": [round(e, 1) for e in errs]}
    print("seg fit (in-sample)", data["segFit"])
json.dump(data, open('mrt-data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print("services", [(s['id'], len(s['codes']), round(sum(s['minutes']), 1)) for s in services])
print("walks", walks)
print("bytes", len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()))
