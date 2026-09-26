"""Schematic (octilinear) layout for the MRT map — Ryan 2026-09-26:
「線拉成直的…直一點加轉角 比較要好操作」.

Transfer stations and terminals are pinned to a grid by hand, following the
official map's topology. Each service is a path of anchors (a station name
with a fixed point) and corner waypoints; stations between two anchors are
spaced evenly by arc length along the path. Every path leg is horizontal,
vertical or 45°, so the drawn lines are straight with corners.

Output: schema.json = { pos: {name: [x, y]}, segs: {sid: [[pts of segment k], ...]} }
where segs[sid][k] runs from codes[k] to codes[k+1] including any corners.
"""
import json, math

D = json.load(open('mrt-data.json'))
NAME = {c: v['name'] for c, v in D['stations'].items()}
SVC = {s['id']: s['codes'] for s in D['services']}

A = lambda name, x, y: ('A', name, (x, y))     # anchored station
W = lambda x, y: ('W', None, (x, y))            # corner waypoint
S = lambda name: ('S', name, None)              # station placed by interpolation

PATHS = {
    "BR": [A("動物園", 6, 9), S("木柵"), S("萬芳社區"), S("萬芳醫院"), S("辛亥"), S("麟光"), W(6, 6), S("六張犁"), W(4, 4), S("科技大樓"),
           A("大安", 4, 2), A("忠孝復興", 4, 0), A("南京復興", 4, -2), S("中山國中"), S("松山機場"), S("大直"), W(4, -6), W(5, -7),
           S("劍南路"), S("西湖"), S("港墘"), S("文德"), S("內湖"), S("大湖公園"), S("葫洲"), W(11, -7), W(12, -6), S("東湖"), S("南港軟體園區"),
           A("南港展覽館", 12, 0)],
    "R": [A("廣慈/奉天宮", 8, 2), S("象山"), S("台北101/世貿"), S("信義安和"), A("大安", 4, 2), S("大安森林公園"), A("東門", 2, 2),
          A("中正紀念堂", 0, 2), S("台大醫院"), A("台北車站", 0, 0), A("中山", 0, -2), S("雙連"), A("民權西路", 0, -4),
          S("圓山"), S("劍潭"), S("士林"), S("芝山"), S("明德"), S("石牌"), W(0, -10), S("唭哩岸"), S("奇岩"), S("北投"), W(-3, -13),
          S("復興崗"), S("忠義"), S("關渡"), S("竹圍"), S("紅樹林"), A("淡水", -9, -13)],
    "G": [A("新店", 2, 11), S("新店區公所"), S("七張"), A("大坪林", 2, 8), S("景美"), S("萬隆"), S("公館"), S("台電大樓"), W(2, 4),
          A("古亭", 1, 3), A("中正紀念堂", 0, 2), A("小南門", -1, 1), A("西門", -2, 0), A("北門", -1, -1), A("中山", 0, -2),
          A("松江南京", 2, -2), A("南京復興", 4, -2), S("台北小巨蛋"), S("南京三民"), A("松山", 7, -2)],
    "O-HL": [A("南勢角", -3, 7), A("景安", -2, 6), S("永安市場"), S("頂溪"), A("古亭", 1, 3), A("東門", 2, 2), A("忠孝新生", 2, 0),
             A("松江南京", 2, -2), S("行天宮"), A("中山國小", 2, -4), A("民權西路", 0, -4), A("大橋頭", -1.5, -4),
             S("台北橋"), S("菜寮"), S("三重"), S("先嗇宮"), A("頭前庄", -6, -4), S("新莊"), S("輔大"), S("丹鳳"), A("迴龍", -10, -4)],
    "O-LZ": [A("南勢角", -3, 7), A("景安", -2, 6), S("永安市場"), S("頂溪"), A("古亭", 1, 3), A("東門", 2, 2), A("忠孝新生", 2, 0),
             A("松江南京", 2, -2), S("行天宮"), A("中山國小", 2, -4), A("民權西路", 0, -4), A("大橋頭", -1.5, -4),
             S("三重國小"), S("三和國中"), S("徐匯中學"), S("三民高中"), A("蘆洲", -6.5, -9)],
    "BL": [A("頂埔", -12, 6), S("永寧"), S("土城"), S("海山"), S("亞東醫院"), S("府中"), A("板橋", -6, 0), A("新埔", -5, 0),
           S("江子翠"), S("龍山寺"), A("西門", -2, 0), A("台北車站", 0, 0), S("善導寺"), A("忠孝新生", 2, 0), A("忠孝復興", 4, 0),
           S("忠孝敦化"), S("國父紀念館"), S("市政府"), S("永春"), S("後山埤"), S("昆陽"), S("南港"), A("南港展覽館", 12, 0)],
    "Y": [A("大坪林", 2, 8), S("十四張"), S("秀朗橋"), W(0, 8), S("景平"), A("景安", -2, 6), S("中和"), S("橋和"), S("中原"), W(-6, 2),
          S("板新"), A("板橋", -6, 0), S("新埔民生"), A("頭前庄", -6, -4), S("幸福"), A("新北產業園區", -6, -6)],
}


def layout(path):
    """Place interpolated stations; return [(name, point)] in order and the full point list with station indices."""
    pts, out = [], []
    i = 0
    while i < len(path):
        kind, name, p = path[i]
        assert kind == 'A', f"path must start/continue from an anchor: {path[i]}"
        # collect up to the next anchor
        j = i + 1
        while path[j][0] != 'A':
            j += 1
        seg = [p] + [q for k, _, q in path[i + 1:j] if k == 'W'] + [path[j][2]]
        # arc-length parametrisation of the polyline between the two anchors
        lens = [math.dist(a, b) for a, b in zip(seg, seg[1:])]
        total = sum(lens)
        mids = [e for e in path[i + 1:j] if e[0] == 'S']
        n = len(mids) + 1

        def at(t):
            d = t * total
            for (a, b), L in zip(zip(seg, seg[1:]), lens):
                if d <= L + 1e-9:
                    f = d / L if L else 0
                    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                d -= L
            return seg[-1]
        # emit: anchor, then walk the path emitting corners and stations in arc order
        events = [(0.0, 'A', name, p)]
        # station params
        for k, (_, nm, _) in enumerate(mids, 1):
            events.append((k / n, 'S', nm, at(k / n)))
        acc = 0
        for L, q in zip(lens[:-1], seg[1:-1]):
            acc += L
            events.append((acc / total, 'W', None, q))
        events.sort(key=lambda e: (e[0], 0 if e[1] == 'W' else 1))
        for t, kind2, nm, q in events:
            pts.append((nm, q))
            if nm:
                out.append((nm, q))
        if j == len(path) - 1:
            pts.append((path[j][1], path[j][2])); out.append((path[j][1], path[j][2]))
            break
        i = j
    return out, pts


pos, segs = {}, {}
for sid, path in PATHS.items():
    out, pts = layout(path)
    codes = SVC[sid]
    names = [NAME[c] for c in codes]
    assert [n for n, _ in out] == names, (sid, [n for n, _ in out], names)
    for n, q in out:
        q = (round(q[0], 3), round(q[1], 3))
        if n in pos:
            assert math.dist(pos[n], q) < 1e-6, (sid, n, pos[n], q)   # a shared station must land on one point
        pos[n] = q
    # split the point list into per-segment polylines between consecutive stations
    idx = [k for k, (n, _) in enumerate(pts) if n]
    segs[sid] = [[[round(x, 3), round(y, 3)] for _, (x, y) in pts[a:b + 1]] for a, b in zip(idx, idx[1:])]

# short branches hang off their junction
pos["新北投"] = (round(pos["北投"][0] + 0.7, 3), round(pos["北投"][1] - 0.7, 3))
pos["小碧潭"] = (round(pos["七張"][0] - 1, 3), round(pos["七張"][1] + 0.6, 3))
segs["R-XB"] = [[list(pos["北投"]), list(pos["新北投"])]]
segs["G-XB"] = [[list(pos["七張"]), [pos["七張"][0] - 0.6, pos["七張"][1]], list(pos["小碧潭"])]]
missing = [n for n in D['names'] if n not in pos]
assert not missing, missing
json.dump({"pos": pos, "segs": segs}, open('schema.json', 'w'), ensure_ascii=False)
print("stations placed:", len(pos), "services:", len(segs))
