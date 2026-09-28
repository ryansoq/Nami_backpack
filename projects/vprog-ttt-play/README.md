# vprog-ttt-play: Nami vs Ryan on vprogs-tt.izio.fr (testnet-10)

First live match 2026-09-28, 13:07–13:24. The game is Maksim Biriukov's vprog-tictactoe
(kaspanet/vprogs guest, RISC Zero proofs, Kaspa-miner-ordered lanes).
Game 76707310…f925, 1 tKAS stake, 3 rounds. **Ryan won 2–0–1**, taking both rounds where
the bot's 15% random move skipped a block.

- `bot.cjs`: plays my seat through the real web UI in headless Chromium. Key read in-process
  from `.secrets/tn10-ttt-keys.json` (throwaway tn10 keys for nami + ryan, 0600).
  Turn logic from guest `rules.rs`: X opens every round, the creator's mark swaps each round.
  Minimax plus `OOPS` random-move rate (env). `GAME=<id>` resumes an existing game.
- Funding: 20 tKAS each from `.secrets/testnet-wallet.json` (ShioKaze mining wallet, 118K tKAS in
  14,808 UTXOs; spend the single largest UTXO or storage mass overflows).
- NEVER paste `nami-kaspa-wallet.json` into the site: kas-ask's testnet address is the same key
  as Nami's mainnet wallet.

Payout path: the pot lands on L2 (Ryan's account shows 2.00) → Withdraw → next zk settlement
batch (the operator's GPU; the last one before the match was 9/26) → Claim Exits on L1.

UX lesson: on mobile the board sits under MY GAMES and needs the game row tapped first. Ryan
also clicked "Create game" 4 times and joined 2 strangers' games before finding ours.
