"""Parse the official planner's result text into routes: total minutes, legs, transfers."""
import json, re, sys

HDR = re.compile(r"(\d+)分鐘｜於 (\d\d:\d\d) 從 (.+?) 發車經過 (\d+) 站")
LEG = re.compile(r"經過 (\d+) 站 \( (\d+) 分鐘\)")
WALK = re.compile(r"步行\(約 (\d+) 分鐘\)")


def parse_section(txt):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    r = {"total": None, "legs": [], "walks": []}
    last_station = None
    for i, l in enumerate(lines):
        m = HDR.search(l)
        if m and r["total"] is None:
            r["total"] = int(m.group(1)); r["origin"] = m.group(3); continue
        if l.startswith("往"):
            r["legs"].append({"dir": l[1:], "from": last_station}); continue
        m = LEG.search(l)
        if m and r["legs"]:
            r["legs"][-1].update(stops=int(m.group(1)), minutes=int(m.group(2))); continue
        m = WALK.search(l)
        if m:
            r["walks"].append({"at": last_station, "minutes": int(m.group(1))}); continue
        # station lines look like "名稱" or "名稱\tHH:MM"
        name = l.split("\t")[0].strip()
        if name and not re.search(r"[｜>＞]|^\d+$|分鐘|支線", name):
            if r["legs"] and "to" not in r["legs"][-1] and "minutes" in r["legs"][-1]:
                r["legs"][-1]["to"] = name
            last_station = name
    return r


def parse(txt):
    a, _, b = txt.partition("最少轉乘次數")
    return {"fastest": parse_section(a), "fewest": parse_section(b)}


if __name__ == "__main__":
    d = json.load(open(sys.argv[1]))
    for k, v in d.items():
        p = parse(v)
        f, w = p["fastest"], p["fewest"]
        fmt = lambda r: f"{r['total']}m " + " + ".join(f"{g.get('from')}→{g.get('to')}[{g.get('stops')}站{g.get('minutes')}m]" for g in r["legs"]) + ("" if not r["walks"] else " walks=" + ",".join(f"{x['at']}:{x['minutes']}" for x in r["walks"]))
        print(k, "| FAST", fmt(f), "| FEW", fmt(w))
