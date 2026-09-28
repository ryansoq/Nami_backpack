// Nami plays tic-tac-toe on vprogs-tt.izio.fr (testnet-10) through the real web UI.
// The key is read in-process from a 0600 secrets file (a throwaway tn10 key) and typed
// into the page; it never goes on argv or into logs.
const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
const fs = require('fs');
const SITE = 'https://vprogs-tt.izio.fr';
const KEY = JSON.parse(fs.readFileSync('/home/ymchang/clawd/.secrets/tn10-ttt-keys.json')).nami;
const STAKE = process.env.STAKE || '1', ROUNDS = process.env.ROUNDS || '3';
const OOPS = Number(process.env.OOPS || 0.15);   // chance of a casual (random) move, so it's not a wall
const log = (...a) => console.log(new Date().toTimeString().slice(0, 8), ...a);
const api = async p => (await fetch(SITE + p)).json();

const LINES = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
const winner = b => { for (const [a,c,d] of LINES) if (b[a] && b[a] === b[c] && b[a] === b[d]) return b[a]; return 0; };
function minimax(b, me, turn) {
  const w = winner(b); if (w) return w === me ? 10 : -10;
  if (b.every(x => x)) return 0;
  let best = turn === me ? -99 : 99;
  for (let i = 0; i < 9; i++) if (!b[i]) {
    b[i] = turn; const s = minimax(b, me, 3 - turn); b[i] = 0;
    best = turn === me ? Math.max(best, s) : Math.min(best, s);
  }
  return best;
}
function chooseMove(board, me) {
  const free = board.map((v, i) => v ? -1 : i).filter(i => i >= 0);
  if (Math.random() < OOPS) return free[Math.floor(Math.random() * free.length)];
  let best = -99, moves = [];
  for (const i of free) { const b = board.slice(); b[i] = me; const s = minimax(b, me, 3 - me); if (s > best) { best = s; moves = [i]; } else if (s === best) moves.push(i); }
  return moves[Math.floor(Math.random() * moves.length)];
}
// rules.rs: X opens every round; seat 0 plays creator_mark in even rounds, the other mark in odd.
const myMark = (g, round) => (round % 2 === 0 ? g.creator_mark : 3 - g.creator_mark);
const plies = b => b.filter(x => x).length;
const myTurn = (g) => { const r = g.round_wins[0] + g.round_wins[1] + g.draws; const toMove = plies(g.board) % 2 === 0 ? 1 : 2; return [toMove === myMark(g, r), myMark(g, r), r]; };

(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 1000 } });
  p.on('console', m => { if (m.type() === 'error') log('[page error]', m.text().slice(0, 200)); });
  await p.goto(SITE, { waitUntil: 'networkidle', timeout: 90000 });
  await p.fill('input[placeholder^="privkey"]', KEY);
  await p.click('button:has-text("Load")');
  await p.waitForTimeout(6000);
  log('loaded identity');

  let gameId = process.env.GAME;
  if (!gameId) {
    const before = new Set((await api('/api/games?status=open')).games.map(g => g.id));
    await p.fill('input[inputmode="decimal"]', STAKE);
    await p.fill('input[inputmode="numeric"]', ROUNDS);
    await p.click('button:has-text("Create"), button:has-text("create")');
    log(`create submitted: stake ${STAKE} tKAS, ${ROUNDS} rounds`);
    for (let i = 0; i < 90 && !gameId; i++) {
      await p.waitForTimeout(3000);
      const g = (await api('/api/games?status=open')).games.find(g => !before.has(g.id) && g.stake === Number(STAKE) * 1e8 && g.rounds_total === Number(ROUNDS));
      if (g) gameId = g.id;
    }
    if (!gameId) { log('FAILED: game did not appear'); await p.screenshot({ path: 'fail.png', fullPage: true }); process.exit(1); }
  }
  log('GAME', gameId);
  fs.writeFileSync('game.json', JSON.stringify({ gameId, at: Date.now() }));

  let lastPlies = -1, lastState = -1, clickedAt = -1;
  for (;;) {
    let g;
    try { g = await api('/api/games/' + gameId); g = g.game || g; } catch (e) { log('api err', e.message); await p.waitForTimeout(3000); continue; }
    if (g.state !== lastState) { log('state', g.state_name, 'rounds', JSON.stringify(g.round_wins), 'draws', g.draws); lastState = g.state; }
    if (g.state >= 2) { log('FINISHED', g.state_name, 'round_wins', JSON.stringify(g.round_wins), 'draws', g.draws); await p.screenshot({ path: 'final.png', fullPage: true }); break; }
    if (g.state === 1) {
      const [mine, mark, round] = myTurn(g);
      const n = plies(g.board);
      if (n !== lastPlies) { log(`round ${round + 1} board ${g.board.join('')} ${mine ? 'MY turn' : 'waiting for Ryan'}`); lastPlies = n; }
      if (mine && clickedAt !== n) {
        const cell = chooseMove(g.board, mark);
        try {
          await p.click('.game-row', { timeout: 5000 }).catch(() => {});
          await p.waitForTimeout(800);
          await p.click(`button[aria-label="cell ${cell}"]`, { timeout: 10000 });
          clickedAt = n;
          log(`played ${mark === 1 ? 'X' : 'O'} at cell ${cell}`);
        } catch (e) { log('click failed', e.message.split('\n')[0]); await p.screenshot({ path: 'clickfail.png', fullPage: true }); }
      }
    }
    await p.waitForTimeout(3000);
  }
  await b.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
