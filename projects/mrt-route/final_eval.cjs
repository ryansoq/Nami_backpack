const fs = require('fs'); const { buildRouter } = require('./router.js');
const D = JSON.parse(fs.readFileSync('mrt-data.json'));
const run = (file, opts) => {
  const R = buildRouter(D, opts), P = JSON.parse(fs.readFileSync(file));
  let e = [], same = 0, few = 0, n = 0;
  for (const [k, p] of Object.entries(P)) {
    const [a, b] = k.split('>'); const ga = R.group(a), gb = R.group(b); if (ga === gb) continue;
    const f = R.route(ga, gb, 'fastest'), w = R.route(ga, gb, 'fewest'); n++;
    e.push(Math.abs(f.minutes - p.fastest.total));
    if (p.fastest.walks.map(x => D.alias[x.at] || x.at).join('/') === f.transfers.map(x => D.alias[x.at] || x.at).join('/')) same++;
    if (w.transfers.length === p.fewest.walks.length) few++;
  }
  e.sort((x, y) => x - y);
  return { n, mae: +(e.reduce((a, b) => a + b, 0) / n).toFixed(2), p90: e[Math.floor(0.9 * n)], max: e[n - 1], same: `${same}/${n}`, fewest: `${few}/${n}` };
};
for (const pen of [1, 3]) console.log('penalty', pen, 'train', JSON.stringify(run('planner_train_parsed.json', { wait: 0, penalty: pen })), 'VAL', JSON.stringify(run('planner_val_parsed.json', { wait: 0, penalty: pen })));
