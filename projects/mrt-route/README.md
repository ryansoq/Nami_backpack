# mrt-route — 捷運怎麼搭

Tap two Taipei MRT stations on a map; see the **fastest** and **fewest-transfer**
routes side by side, highlighted, with fares. Ryan's idea 2026-09-25 (the
official planner has no map).
Published: https://claude.ai/artifact/1K9mBH4aAC71j6z8XRwEbk (private)

## Data (fetched 2026-09-25)
- station list + real timings: official planner web.metro.taipei/pages2026/WebRoutePlan
  (ASP.NET postback, scraped with `batch.cjs`, parsed by `parse.py`)
- fares + shortest-path km: data.taipei dataset 893c2f2a-… (17,424 rows; use curl — urllib hangs)
- positions: OpenStreetMap subway stations (R01 廣慈/奉天宮 not in OSM, extrapolated)

Fare fact: Taipei Metro charges by the shortest-path distance between the two
stations regardless of route taken, so "cheapest" is not a route choice.

## Model
Nodes = (service, station). 迴龍 and 蘆洲 are two services sharing O01–O12.
Segment minutes: official single-leg timings for sub-ranges of each line
(piecewise anchors), split within a piece by 0.6 min dwell + distance.
Transfer = official walking minutes at that station + wait (fit: 0).
Fastest-route choice adds a 3-min penalty per transfer (half-headway prior).

## Accuracy (28 held-out pairs never used to build the data)
mean |Δ| 1.57 min, p90 3, max 6; same transfer stations 27/28;
fewest-transfer count 28/28. Penalty 3 was set after seeing val at penalty 1
(24/28), as a prior not a fit; train score unchanged by it.
Known gap: 蘆洲 branch runs every other train, so trips from it read ~6 min fast.

## Layout
Default view is a hand-anchored octilinear schematic (`schematic.py` -> schema.json; Ryan 9/26:
「線拉成直的…直一點加轉角 比較要好操作」). Transfer stations and terminals are pinned on a grid,
the rest spaced by arc length along straight/45° legs; a shared station must land on one point
(asserted). The 地理 button toggles back to the OSM layout.

## Build
`python3 build_data.py && python3 build_page.py` → mrt-route.html
`node final_eval.cjs` for the scores.
