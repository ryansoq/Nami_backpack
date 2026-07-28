#!/usr/bin/env python3
"""kas-ask — pay-per-question gateway: KAS in, nami-lm answers out.

Stage 1 (prepaid balance). The flow:

  1. user sends TKAS to NAMI_ADDRESS from their own wallet
  2. this server polls the public indexer for new UTXOs on that address
  3. each new UTXO credits the payer's balance (1 KAS -> PRICE_TOKENS credits)
  4. POST /ask spends credits and proxies the question to nami-lm

Deliberately receive-only: the server never needs Nami's private key, because
watching for incoming payments is a read-only operation on the chain. Nothing
here can move funds.

Trust model (stage 1): the payer trusts Nami to honour the credit. Stage 2
replaces this with a covenant escrow so the funds are locked, not handed over.

No node required — uses the public REST indexer.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread

# ── config ───────────────────────────────────────────────────────────────────

NETWORK = os.environ.get("KAS_ASK_NETWORK", "testnet-10")
INDEXER = {
    "testnet-10": "https://api-tn10.kaspa.org",
    "mainnet": "https://api.kaspa.org",
}[NETWORK]

# Nami's receive address for this network. Derived from her existing keypair —
# same key as mainnet, only the prefix differs. Receive-only here.
NAMI_ADDRESS = os.environ.get(
    "KAS_ASK_ADDRESS",
    "kaspatest:qrnctcwj2mf7hh27x8gafa44e3vg9q9vrv50as3us0tnr40tl9st738ry6yg8",
)

NAMI_LM = os.environ.get("KAS_ASK_NAMI_LM", "http://127.0.0.1:18807/chat")

SOMPI = 100_000_000          # 1 KAS
PRICE_PER_QUESTION = 10      # credits spent per question
CREDITS_PER_KAS = 1000       # 1 KAS buys this many credits
POLL_SECONDS = 15

STATE_PATH = Path(__file__).parent / "state.json"
PORT = int(os.environ.get("KAS_ASK_PORT", "18809"))

# ── state ────────────────────────────────────────────────────────────────────
# {"seen_outpoints": [...], "credits": {payer_addr: int}, "anonymous": int,
#  "log": [...]}

_lock = Lock()


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"seen_outpoints": [], "credits": {}, "anonymous": 0, "log": []}


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(STATE_PATH)


# ── chain watching ───────────────────────────────────────────────────────────


def fetch_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "kas-ask/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_utxos() -> list[dict]:
    return fetch_json(f"{INDEXER}/addresses/{NAMI_ADDRESS}/utxos")


def payer_of(tx_id: str) -> str | None:
    """Best-effort: who funded this transaction.

    The indexer exposes previous_outpoint_address on inputs for indexed txs.
    When it is unavailable the payment still counts, just as anonymous credit.
    """
    try:
        tx = fetch_json(f"{INDEXER}/transactions/{tx_id}?inputs=true&outputs=false")
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None
    for inp in tx.get("inputs") or []:
        addr = inp.get("previous_outpoint_address")
        if addr:
            return addr
    return None


def credit_new_payments() -> list[dict]:
    """Poll the indexer; credit any UTXO we have not seen before."""
    try:
        utxos = fetch_utxos()
    except Exception as exc:  # network flake — try again next tick
        print(f"[watch] indexer error: {exc}", flush=True)
        return []

    credited = []
    with _lock:
        state = load_state()
        seen = set(state["seen_outpoints"])
        first_run = not seen and not state["log"]

        for u in utxos:
            op = u.get("outpoint") or {}
            key = f"{op.get('transactionId')}:{op.get('index')}"
            if key in seen:
                continue
            seen.add(key)

            amount = int((u.get("utxoEntry") or {}).get("amount", 0))
            credits = amount * CREDITS_PER_KAS // SOMPI

            # A pre-existing balance is not a payment for questions. On the very
            # first run we only record the outpoints so old funds don't grant
            # free credit.
            if first_run:
                print(f"[watch] baseline {key} {amount/SOMPI:.8f} KAS (no credit)", flush=True)
                continue

            payer = payer_of(op.get("transactionId", "")) or "anonymous"
            if payer == "anonymous":
                state["anonymous"] += credits
            else:
                state["credits"][payer] = state["credits"].get(payer, 0) + credits

            entry = {
                "ts": int(time.time()),
                "outpoint": key,
                "amount_kas": amount / SOMPI,
                "credits": credits,
                "payer": payer,
            }
            state["log"].append(entry)
            credited.append(entry)
            print(f"[watch] +{credits} credits to {payer} ({amount/SOMPI:.8f} KAS)", flush=True)

        state["seen_outpoints"] = sorted(seen)
        save_state(state)
    return credited


def watch_loop() -> None:
    while True:
        credit_new_payments()
        time.sleep(POLL_SECONDS)


# ── nami-lm ──────────────────────────────────────────────────────────────────


def ask_nami_lm(question: str) -> dict:
    body = json.dumps({"q": question}).encode()
    req = urllib.request.Request(
        NAMI_LM, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


# ── http ─────────────────────────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):  # quieter default logging
        print(f"[http] {fmt % args}", flush=True)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path in ("/", "/health"):
            return self._send(200, {
                "ok": True,
                "service": "kas-ask",
                "network": NETWORK,
                "address": NAMI_ADDRESS,
                "price_per_question": PRICE_PER_QUESTION,
                "credits_per_kas": CREDITS_PER_KAS,
            })

        if path == "/balance":
            query = dict(
                p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p
            )
            addr = urllib.parse.unquote(query.get("addr", ""))
            with _lock:
                state = load_state()
            return self._send(200, {
                "addr": addr,
                "credits": state["credits"].get(addr, 0),
                "anonymous_pool": state["anonymous"],
                "questions_affordable": state["credits"].get(addr, 0) // PRICE_PER_QUESTION,
            })

        if path == "/payments":
            with _lock:
                state = load_state()
            return self._send(200, {"log": state["log"][-20:]})

        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path != "/ask":
            return self._send(404, {"error": "not found"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode() or "{}")
        except (ValueError, TypeError):
            return self._send(400, {"error": "bad json"})

        question = (body.get("q") or "").strip()
        payer = (body.get("addr") or "").strip()
        if not question:
            return self._send(400, {"error": "missing q"})

        # Pick up payments that landed since the last poll, so a user who just
        # paid isn't told to wait a full cycle.
        credit_new_payments()

        with _lock:
            state = load_state()
            pool = "credits" if payer and payer in state["credits"] else "anonymous"
            available = state["credits"].get(payer, 0) if pool == "credits" else state["anonymous"]

            if available < PRICE_PER_QUESTION:
                return self._send(402, {
                    "error": "insufficient credits",
                    "have": available,
                    "need": PRICE_PER_QUESTION,
                    "pay_to": NAMI_ADDRESS,
                    "network": NETWORK,
                    "hint": f"1 KAS = {CREDITS_PER_KAS} credits = "
                            f"{CREDITS_PER_KAS // PRICE_PER_QUESTION} questions",
                })

            # Debit before doing the work, so a crash cannot be replayed for free.
            if pool == "credits":
                state["credits"][payer] -= PRICE_PER_QUESTION
            else:
                state["anonymous"] -= PRICE_PER_QUESTION
            save_state(state)
            remaining = state["credits"].get(payer, 0) if pool == "credits" else state["anonymous"]

        try:
            answer = ask_nami_lm(question)
        except Exception as exc:
            with _lock:  # refund — the user got nothing
                state = load_state()
                if pool == "credits":
                    state["credits"][payer] = state["credits"].get(payer, 0) + PRICE_PER_QUESTION
                else:
                    state["anonymous"] += PRICE_PER_QUESTION
                save_state(state)
            return self._send(502, {"error": f"nami-lm unreachable: {exc}", "refunded": True})

        return self._send(200, {
            "q": question,
            "a": answer.get("a", ""),
            "latency_ms": answer.get("latency_ms"),
            "charged": PRICE_PER_QUESTION,
            "remaining_credits": remaining,
            "pool": pool,
        })


def main() -> None:
    print(f"kas-ask on :{PORT}", flush=True)
    print(f"  network  {NETWORK}  ({INDEXER})", flush=True)
    print(f"  pay to   {NAMI_ADDRESS}", flush=True)
    print(f"  nami-lm  {NAMI_LM}", flush=True)
    print(f"  price    {PRICE_PER_QUESTION} credits/question, "
          f"1 KAS = {CREDITS_PER_KAS} credits", flush=True)

    credit_new_payments()  # establish baseline before serving
    Thread(target=watch_loop, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
