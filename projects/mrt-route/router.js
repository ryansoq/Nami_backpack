// Taipei MRT router over (service, station) nodes. Shared by the page and the node tests.
//
// A node is one service at one station ("BL|BL12"). Riding moves along a service;
// changing service at a station is a transfer and costs walk + WAIT minutes.
// The 迴龍 and 蘆洲 services share the O01-O12 trunk, so switching between them
// there is a same-platform change (no walk), and 古亭 -> 蘆洲 is a single ride.

function buildRouter(D, opts = {}) {
  const WAIT = opts.wait ?? 2;          // expected wait per transfer, calibrated on the training pairs
  const BOARD = opts.board ?? 1;        // the planner's total runs ~1 min over the sum of its legs
  // Extra cost per transfer used only to CHOOSE the fastest route, not in the reported
  // minutes: with no penalty, a 1-minute gain buys a third transfer nobody wants.
  const PENALTY = opts.penalty ?? 3;
  const nameOf = c => D.stations[c].name;
  const group = c => D.alias[nameOf(c)] || nameOf(c);
  const SAME_PLATFORM = new Set(['O-HL|O-LZ', 'O-LZ|O-HL']);

  const nodes = new Map();              // key -> { sid, code, edges: [] }
  const node = (sid, code) => {
    const k = sid + '|' + code;
    if (!nodes.has(k)) nodes.set(k, { k, sid, code, edges: [] });
    return nodes.get(k);
  };
  const byGroup = new Map();
  for (const s of D.services) {
    s.codes.forEach((c, i) => {
      const n = node(s.id, c);
      if (!byGroup.has(group(c))) byGroup.set(group(c), []);
      byGroup.get(group(c)).push(n);
      if (i > 0) {
        const p = node(s.id, s.codes[i - 1]), m = s.minutes[i - 1];
        p.edges.push({ to: n, min: m, kind: 'ride' });
        n.edges.push({ to: p, min: m, kind: 'ride' });
      }
    });
  }
  for (const [g, ns] of byGroup) {
    for (const a of ns) for (const b of ns) {
      if (a === b || a.sid === b.sid) continue;
      const walk = SAME_PLATFORM.has(a.sid + '|' + b.sid) && a.code === b.code ? 0 : (D.walks[g] ?? D.walks[nameOf(a.code)] ?? 3);
      a.edges.push({ to: b, min: walk + WAIT, walk, kind: 'transfer' });
    }
  }

  // Dijkstra; cost = [transfers, minutes] compared lexicographically when fewest, else minutes only.
  function route(fromGroup, toGroup, mode) {
    const key = (t, m) => mode === 'fewest' ? t * 1e4 + m : m + t * (PENALTY + 1e-3);
    const best = new Map(), prev = new Map(), heap = [];
    const push = (n, t, m, p, e) => {
      const k = key(t, m);
      if (best.has(n.k) && best.get(n.k).k <= k) return;
      best.set(n.k, { k, t, m }); prev.set(n.k, { p, e });
      heap.push({ n, k, t, m });
    };
    for (const n of byGroup.get(fromGroup) || []) push(n, 0, 0, null, null);
    let end = null;
    while (heap.length) {
      let bi = 0; for (let i = 1; i < heap.length; i++) if (heap[i].k < heap[bi].k) bi = i;
      const cur = heap.splice(bi, 1)[0];
      if (best.get(cur.n.k).k < cur.k) continue;
      if (group(cur.n.code) === toGroup) { end = cur; break; }
      for (const e of cur.n.edges) {
        // never transfer at the origin or into the destination: you'd just walk instead
        if (e.kind === 'transfer' && (group(cur.n.code) === fromGroup || group(cur.n.code) === toGroup)) continue;
        push(e.to, cur.t + (e.kind === 'transfer' ? 1 : 0), cur.m + e.min, cur.n, e);
      }
    }
    if (!end) return null;
    const steps = [];
    for (let k = end.n.k; prev.get(k).p; k = prev.get(k).p.k) steps.unshift({ from: prev.get(k).p, to: nodes.get(k), e: prev.get(k).e });
    // consecutive rides form one leg; a transfer closes it
    const legs = [], transfers = [];
    let cur = null;
    for (const s of steps) {
      if (s.e.kind === 'transfer') { transfers.push({ at: nameOf(s.from.code), walk: s.e.walk }); cur = null; continue; }
      if (!cur) { cur = { sid: s.from.sid, from: s.from.code, path: [s.from.code], minutes: 0 }; legs.push(cur); }
      cur.to = s.to.code; cur.path.push(s.to.code); cur.minutes += s.e.min;
    }
    const svc = Object.fromEntries(D.services.map(s => [s.id, s]));
    for (const l of legs) {
      const cs = svc[l.sid].codes;
      l.line = svc[l.sid].line;
      l.stops = l.path.length - 1;
      l.toward = nameOf(cs.indexOf(l.to) > cs.indexOf(l.from) ? cs[cs.length - 1] : cs[0]);
      l.minutes = Math.round(l.minutes * 10) / 10;
    }
    const ride = legs.reduce((a, l) => a + l.minutes, 0);
    const xfer = transfers.reduce((a, t) => a + t.walk + WAIT, 0);
    return { legs, transfers, minutes: Math.round(ride + xfer + BOARD), stops: legs.reduce((a, l) => a + l.stops, 0) };
  }

  function fare(a, b) {
    const i = D.names.indexOf(a), j = D.names.indexOf(b), n = D.names.length;
    if (i < 0 || j < 0) return null;
    const full = 20 + 5 * (D.fare.charCodeAt(i * n + j) - 48);
    const senior = +(D._senior ||= D.senior.split(','))[i * n + j];
    return { full, senior };
  }

  return { route, fare, group, nameOf, groups: [...byGroup.keys()] };
}

if (typeof module !== 'undefined') module.exports = { buildRouter };
if (typeof window !== 'undefined') window.buildRouter = buildRouter;
