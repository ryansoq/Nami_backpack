#!/usr/bin/env python3
"""
🌊 Whisper Covenant v2 — Encode (Local Signing)

Usage:
  python3 encode.py --to <recipient_address> --message "Hello!" --key <sender_privkey> [--plain]

  --plain: plaintext (type=message), without it: ECIES encrypted (type=whisper)

Private key NEVER leaves local!

Output: signed TX JSON ready for broadcast API
"""

import argparse
import asyncio
import json
import os
import sys

import kaspa

# ─── Config ───────────────────────────────────────────────────────
WRPC_URL = "ws://localhost:17210"
NETWORK_ID = "testnet-12"
NETWORK_TYPE = "testnet"
DEPOSIT_SOMPI = 20_000_000      # 0.2 tKAS
FEE_SOMPI = 10_000
FEE_BUFFER_SOMPI = 5_000
REST_API_URL = "https://api-tn12.kaspa.org"

# ─── Script helpers ───────────────────────────────────────────────

def push_data(data: bytes) -> bytes:
    n = len(data)
    if n == 0:
        return bytes([0x00])
    if n <= 75:
        return bytes([n]) + data
    elif n <= 255:
        return bytes([0x4c, n]) + data
    else:
        return bytes([0x4d]) + n.to_bytes(2, "little") + data

def push_int(val: int) -> bytes:
    if val == 0:
        return bytes([0x00])
    if 1 <= val <= 16:
        return bytes([0x50 + val])
    neg = val < 0
    abs_val = abs(val)
    result = []
    while abs_val > 0:
        result.append(abs_val & 0xFF)
        abs_val >>= 8
    if result[-1] & 0x80:
        result.append(0x80 if neg else 0x00)
    elif neg:
        result[-1] |= 0x80
    return push_data(bytes(result))

def build_covenant_script(a_spk_bytes: bytes, b_pubkey: bytes, deposit: int) -> bytes:
    s = b""
    s += push_data(a_spk_bytes)
    s += push_int(0)
    s += bytes([0xC3, 0x87, 0x69])  # OP_TX_OUTPUT_SPK, OP_EQUAL, OP_VERIFY
    s += push_int(0)
    s += bytes([0xC2])              # OP_TX_OUTPUT_AMOUNT
    s += push_int(deposit)
    s += bytes([0xA2, 0x69])        # OP_GTE, OP_VERIFY
    s += push_data(b_pubkey)
    s += bytes([0xAC])              # OP_CHECKSIG
    return s


async def main():
    parser = argparse.ArgumentParser(description="Whisper Covenant v2 — Encode & Sign locally")
    parser.add_argument("--to", required=True, help="Recipient address")
    parser.add_argument("--message", "-m", required=True, help="Message text")
    parser.add_argument("--key", "-k", required=True, help="Sender private key (hex)")
    parser.add_argument("--plain", action="store_true", help="Send plaintext (type=message)")
    parser.add_argument("--local-only", action="store_true", help="Skip uploading covenant_info to API")
    parser.add_argument("--api-url", default="http://whisper.openclaw-alpha.com", help="Whisper API URL")
    parser.add_argument("--remote", action="store_true", help="Use REST API instead of local kaspad (no node needed!)")
    args = parser.parse_args()

    # ── Derive sender info ──
    a_privkey = kaspa.PrivateKey(args.key)
    a_pubkey = a_privkey.to_public_key()
    a_xonly = a_pubkey.to_x_only_public_key()
    a_addr = a_xonly.to_address(NETWORK_TYPE)
    a_addr_str = a_addr.to_string()
    a_spk = kaspa.pay_to_address_script(a_addr)
    a_spk_bytes = b'\x00\x00' + bytes.fromhex(a_spk.script)

    # ── Derive recipient pubkey ──
    to_addr_obj = kaspa.Address(args.to)
    to_spk = kaspa.pay_to_address_script(to_addr_obj)
    to_script = bytes.fromhex(to_spk.script)
    if len(to_script) != 34 or to_script[0] != 0x20 or to_script[33] != 0xac:
        print("❌ Cannot extract pubkey from recipient address")
        sys.exit(1)
    b_pubkey_bytes = to_script[1:33]
    b_xonly_hex = b_pubkey_bytes.hex()

    # ── Encrypt or plaintext ──
    msg_type = "message" if args.plain else "whisper"
    if args.plain:
        data_str = args.message
    else:
        from ecies import encrypt as ecies_encrypt
        # ECIES needs 33-byte compressed pubkey, add 02 prefix to x-only
        compressed_hex = "02" + b_xonly_hex
        ciphertext = ecies_encrypt(compressed_hex, args.message.encode("utf-8"))
        data_str = ciphertext.hex()

    # ── Build covenant ──
    covenant_script = build_covenant_script(a_spk_bytes, b_pubkey_bytes, DEPOSIT_SOMPI)

    # ── Build payload (includes covenant metadata in `a` for on-chain self-containment) ──
    payload_obj = {
        "v": 1,
        "t": msg_type,
        "d": data_str,
        "a": {
            "from": a_addr_str,
            "script": covenant_script.hex(),
            "spk": a_spk.script,
            "deposit": DEPOSIT_SOMPI,
        }
    }
    payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    p2sh_spk = kaspa.pay_to_script_hash_script(covenant_script)
    p2sh_addr = kaspa.address_from_script_public_key(p2sh_spk, NETWORK_TYPE)
    p2sh_addr_str = p2sh_addr.to_string()

    print(f"🌊 Whisper Covenant v2 — Encode")
    print(f"   From: {a_addr_str}")
    print(f"   To:   {args.to}")
    print(f"   Type: {msg_type}")
    print(f"   P2SH: {p2sh_addr_str}")
    print()

    # ── Get UTXOs & DAA score ──
    client = None
    use_remote = args.remote

    if not use_remote:
        try:
            client = kaspa.RpcClient(url=WRPC_URL, encoding="borsh", network_id=NETWORK_ID)
            await client.connect()
            result = await client.get_utxos_by_addresses({"addresses": [a_addr_str]})
            entries = result.get("entries", [])
            dag_info = await client.get_block_dag_info()
            current_daa = dag_info["virtualDaaScore"]
        except Exception as e:
            print(f"⚠️  Local kaspad not available ({e}), falling back to REST API...")
            use_remote = True
            client = None

    if use_remote:
        import urllib.request
        # Fetch UTXOs from REST API
        utxo_url = f"{REST_API_URL}/addresses/{a_addr_str}/utxos"
        print(f"🌐 Fetching UTXOs from REST API...")
        try:
            with urllib.request.urlopen(utxo_url, timeout=15) as resp:
                utxo_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"❌ REST API UTXO fetch failed: {e}")
            sys.exit(1)

        # Convert REST API format to kaspa SDK format
        entries = []
        for u in utxo_data:
            entry = {
                "outpoint": {
                    "transactionId": u["outpoint"]["transactionId"],
                    "index": u["outpoint"]["index"],
                },
                "address": a_addr_str,
                "utxoEntry": {
                    "amount": int(u["utxoEntry"]["amount"]),
                    "scriptPublicKey": u["utxoEntry"]["scriptPublicKey"],
                    "blockDaaScore": int(u["utxoEntry"]["blockDaaScore"]),
                    "isCoinbase": u["utxoEntry"]["isCoinbase"],
                },
            }
            entries.append(entry)

        # Fetch DAA score
        daa_url = f"{REST_API_URL}/info/virtual-chain-blue-score"
        with urllib.request.urlopen(daa_url, timeout=10) as resp:
            daa_data = json.loads(resp.read().decode("utf-8"))
        current_daa = int(daa_data["blueScore"])

    lock_amount = DEPOSIT_SOMPI + FEE_BUFFER_SOMPI
    needed = lock_amount + FEE_SOMPI + 10000

    mature = []
    for e in entries:
        utxo = e["utxoEntry"]
        if utxo["isCoinbase"] and (current_daa - utxo["blockDaaScore"]) < 500:
            continue
        if utxo["amount"] >= needed:
            mature.append(e)

    if not mature:
        print(f"❌ No suitable UTXO (need {needed} sompi = {needed/1e8:.4f} tKAS)")
        print(f"   💧 Need tKAS? Message @Nami_Kaspa_Bot on Telegram for testnet faucet!")
        if client:
            await client.disconnect()
        sys.exit(1)

    selected = mature[0]
    input_amount = selected["utxoEntry"]["amount"]
    change = input_amount - lock_amount - FEE_SOMPI

    # ── Build & sign TX ──
    tx = kaspa.create_transaction(
        [selected],
        [
            kaspa.PaymentOutput(kaspa.Address(p2sh_addr_str), lock_amount),
            kaspa.PaymentOutput(kaspa.Address(a_addr_str), change),
        ],
        0, payload,
    )
    kaspa.sign_transaction(tx, [a_privkey], False)

    tx_id = tx.id
    print(f"✅ TX signed locally! ID: {tx_id}")
    print(f"   Lock: {lock_amount/1e8:.4f} tKAS → P2SH")
    print(f"   Change: {change/1e8:.4f} tKAS")

    # ── Build covenant_info for decode ──
    covenant_info = {
        "tx_id": tx_id,
        "covenant_script_hex": covenant_script.hex(),
        "p2sh_address": p2sh_addr_str,
        "p2sh_spk": p2sh_spk.script,
        "a_address": a_addr_str,
        "a_spk": a_spk.script,
        "b_pubkey": b_xonly_hex,
        "deposit_sompi": DEPOSIT_SOMPI,
        "message": args.message,
        "d": data_str,
        "type": msg_type,
        "output_index": 0,
    }

    # ── Submit TX ──
    if client and not use_remote:
        try:
            r = await client.submit_transaction({"transaction": tx, "allow_orphan": False})
            submitted_id = r.get("transactionId", tx_id)
            print(f"📡 TX submitted to kaspad! ID: {submitted_id}")
        except Exception as e:
            print(f"❌ Submit failed: {e}")
            await client.disconnect()
            sys.exit(1)
    else:
        # Submit via REST API
        import urllib.request
        submit_url = f"{REST_API_URL}/transactions"
        # Serialize TX to JSON for REST API
        tx_json = tx.to_json()
        print(f"📡 Broadcasting TX via REST API...")
        try:
            req = urllib.request.Request(
                submit_url,
                data=json.dumps(tx_json).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                print(f"📡 TX broadcast via REST API! ID: {result.get('transactionId', tx_id)}")
        except Exception as e:
            print(f"❌ REST API broadcast failed: {e}")
            sys.exit(1)

    # Save covenant_info locally
    info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covenant_info.json")
    with open(info_path, "w") as f:
        json.dump(covenant_info, f, indent=2)
    print(f"💾 Covenant info → {info_path}")

    # ── Upload covenant_info to API (default) ──
    if not args.local_only:
        import aiohttp
        api_key = os.environ.get("WHISPER_API_KEY", "whisper-testnet-poc-key")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{args.api_url}/api/broadcast",
                    json={"covenant_info": covenant_info},
                    headers={"X-Whisper-Key": api_key}
                ) as resp:
                    if resp.status == 200:
                        print(f"☁️  Covenant info uploaded to API")
                    else:
                        print(f"⚠️  API upload failed: {await resp.text()}")
        except Exception as e:
            print(f"⚠️  API upload failed (offline?): {e}")
    else:
        print(f"   (--local-only: skipped API upload)")

    if client:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
