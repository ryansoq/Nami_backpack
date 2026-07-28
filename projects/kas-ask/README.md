# kas-ask

Pay-per-question gateway: send KAS, ask nami-lm.

Stage 1 of the idea Ryan raised on 2026-07-28 — a framework where asking a
model costs tokens, billed in KAS, so compute can later be farmed out to
providers who earn KAS for helping.

## What works today

```
user's wallet ──KAS──▶ Nami's address
                          │
                   (public indexer poll)
                          ▼
                   kas-ask  :18809 ──▶ nami-lm  :18807
                   credits ledger        (v0.5.1.0-weekly)
```

- **No node required.** Payment detection uses the public REST indexer
  (`api-tn10.kaspa.org`), so there is nothing to run locally.
- **Receive-only.** Watching for incoming payments is a read-only chain
  operation, so the service never touches Nami's private key. Nothing in this
  codebase can move funds.
- Defaults to **testnet-10** because its public indexer is alive
  (testnet-12's is returning 503).

## Pricing

| | |
|---|---|
| 1 KAS | 1000 credits |
| 1 question | 10 credits |

So 1 KAS ≈ 100 questions. At current prices that is a fraction of a cent —
the point is the mechanism, not the revenue.

## Run

```sh
/usr/bin/python3 server.py
# KAS_ASK_NETWORK=mainnet  to switch networks
# KAS_ASK_PORT=18809       to move the port
```

## API

```sh
# service info + where to pay
curl 127.0.0.1:18809/health

# how much credit an address has
curl "127.0.0.1:18809/balance?addr=kaspatest:..."

# recent detected payments
curl 127.0.0.1:18809/payments

# ask (402 with payment instructions if unfunded)
curl -X POST 127.0.0.1:18809/ask -H 'Content-Type: application/json' \
     -d '{"q":"誰是Nami","addr":"kaspatest:..."}'
```

## Design notes

**Credits are debited before the model runs**, then refunded if nami-lm fails,
so a crash mid-request cannot be replayed for free answers.

**Pre-existing funds do not grant credit.** On first run the watcher records
the outpoints it finds as a baseline and credits nothing — otherwise the
address's existing balance would look like a fresh payment.

**Payer identification** uses the indexer's `previous_outpoint_address` on the
funding transaction. When that is unavailable the payment still counts, but
into a shared `anonymous` pool rather than a per-address balance. A production
version would have the payer include an identifier in the transaction payload
field (the same trick `kaspa-whisper` uses) instead of inferring it.

## Trust model — read this

Stage 1 is **prepaid, not escrowed**. Funds arrive in Nami's wallet and the
service credits you off-chain; you are trusting Nami to honour that credit.
That is fine for an experiment between us and useless for strangers.

Stage 2 replaces it with a **covenant escrow**: the payer locks KAS in a
covenant that releases one slice per answer and refunds the remainder on
timeout. That is a variant of the deposit/change/refund pattern already proven
in `whisper-covenant`, and a good first real use for
[Argent](../../../clawd/memory/topics/argent-lang-study.md) — its `emits`
declarations enforce exactly the output-shape checks this needs.

## Known gaps

- No rate limiting; a funded caller can hammer nami-lm.
- Payer inference is best-effort (see above).
- `wallet-web` is pinned to testnet-12 + a local node, so it cannot currently
  send the payment. Either repoint it at testnet-10 + `Resolver`, or pay from
  any other testnet wallet.
- The 15s poll means a payment can take a moment to register; `/ask` forces a
  poll first to soften this.
