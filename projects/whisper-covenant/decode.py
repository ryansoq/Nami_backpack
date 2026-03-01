#!/usr/bin/env python3
"""
🌊 Whisper Covenant v2 — Decode (Local Signing)

Usage:
  python3 decode.py --tx <tx_id> --key <recipient_privkey> [--info covenant_info.json]

Flow:
  1. Load covenant info (from file or API)
  2. Decrypt message (ECIES) or read plaintext
  3. Spend covenant UTXO → refund to sender
  4. Sign locally with recipient's private key

Private key NEVER leaves local!
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
REST_API_URL = "https://api-tn12.kaspa.org"

def push_data(data: bytes) -> bytes:
    n = len(data)
    if n <= 75:
        return bytes([n]) + data
    elif n <= 255:
        return bytes([0x4c, n]) + data
    else:
        return bytes([0x4d]) + n.to_bytes(2, "little") + data


def covenant_info_from_payload(payload_json, tx_id):
    """Reconstruct covenant_info from on-chain payload's `a` field."""
    a = payload_json["a"]
    script_hex = a["script"]
    script_bytes = bytes.fromhex(script_hex)

    # Extract b_pubkey from covenant script (last 33 bytes before OP_CHECKSIG 0xac)
    # Script ends with: push_data(b_pubkey_32) + 0xac
    # So script[-1] == 0xac, script[-33:-1] == pubkey, script[-34] == 0x20 (push 32 bytes)
    b_pubkey_hex = ""
    if len(script_bytes) > 34 and script_bytes[-1] == 0xac and script_bytes[-34] == 0x20:
        b_pubkey_hex = script_bytes[-33:-1].hex()

    # Reconstruct p2sh_address from script
    p2sh_address = ""
    try:
        covenant_script = script_bytes
        p2sh_spk = kaspa.pay_to_script_hash_script(covenant_script)
        p2sh_addr = kaspa.address_from_script_public_key(p2sh_spk, NETWORK_TYPE)
        p2sh_address = p2sh_addr.to_string()
    except Exception:
        pass

    # Reconstruct a_spk from a_address
    a_spk = ""
    try:
        a_addr_obj = kaspa.Address(a["from"])
        a_spk = kaspa.pay_to_address_script(a_addr_obj).script
    except Exception:
        # Fallback: use spk from payload if available
        a_spk = a.get("spk", "")

    return {
        "tx_id": tx_id,
        "covenant_script_hex": script_hex,
        "p2sh_address": p2sh_address,
        "p2sh_spk": p2sh_spk.script if p2sh_address else "",
        "a_address": a["from"],
        "a_spk": a_spk,
        "b_pubkey": b_pubkey_hex,
        "deposit_sompi": a["deposit"],
        "d": payload_json["d"],
        "type": payload_json["t"],
        "output_index": 0,
    }


async def main():
    parser = argparse.ArgumentParser(description="Whisper Covenant v2 — Decode & Refund locally")
    parser.add_argument("--tx", required=True, help="Whisper TX ID")
    parser.add_argument("--key", "-k", required=True, help="Recipient private key (hex)")
    parser.add_argument("--info", default=None, help="Path to covenant_info.json (default: auto from API)")
    parser.add_argument("--payload", default=None, help="Raw TX payload JSON (offline decode, no API needed)")
    parser.add_argument("--no-refund", action="store_true", help="Only decrypt, don't spend covenant")
    parser.add_argument("--api-url", default="http://whisper.openclaw-alpha.com", help="Whisper API URL")
    parser.add_argument("--remote", action="store_true", help="Use REST API instead of local kaspad (no node needed!)")
    args = parser.parse_args()

    # ── Load covenant info ──
    # Priority: --payload > --info > local file > API > block explorer
    info = None

    if args.payload:
        # Reconstruct from on-chain payload JSON
        try:
            payload_json = json.loads(args.payload)
            info = covenant_info_from_payload(payload_json, args.tx)
            print(f"📦 Reconstructed covenant info from payload `a` field")
        except Exception as e:
            print(f"❌ Failed to parse --payload: {e}")
            sys.exit(1)
    elif args.info:
        with open(args.info) as f:
            info = json.load(f)
    else:
        # Try local file first
        info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covenant_info.json")
        if os.path.exists(info_path):
            with open(info_path) as f:
                local_info = json.load(f)
            if local_info.get("tx_id") == args.tx:
                info = local_info

        # Fallback: fetch from API
        if not info:
            import urllib.request
            api_url = f"{args.api_url}/api/whisper/{args.tx}"
            print(f"📡 Fetching covenant info from API...")
            try:
                req = urllib.request.Request(api_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        info = json.loads(resp.read().decode("utf-8"))
                        print(f"   ✅ Got covenant info from API")
                    else:
                        print(f"   ❌ API returned {resp.status}")
            except Exception as e:
                print(f"   ❌ API fetch failed: {e}")

        # Fallback: try block explorer
        if not info:
            import urllib.request
            explorer_url = f"https://api-tn12.kaspa.org/transactions/{args.tx}"
            print(f"🔍 Trying block explorer...")
            try:
                req = urllib.request.Request(explorer_url, headers={"User-Agent": "whisper/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        tx_data = json.loads(resp.read().decode("utf-8"))
                        # Extract payload from TX data
                        payload_hex = tx_data.get("payload", "")
                        if payload_hex:
                            payload_bytes = bytes.fromhex(payload_hex)
                            payload_json = json.loads(payload_bytes.decode("utf-8"))
                            if payload_json.get("a", {}).get("script"):
                                info = covenant_info_from_payload(payload_json, args.tx)
                                print(f"   ✅ Reconstructed from block explorer payload")
                            else:
                                print(f"   ⚠️ Payload found but no `a` field (old format?)")
            except Exception as e:
                print(f"   ❌ Block explorer failed: {e}")

    if not info or info.get("tx_id") != args.tx:
        print(f"❌ No covenant info found for TX {args.tx}")
        print(f"   Options:")
        print(f"     --payload '<JSON>'  (from on-chain TX payload)")
        print(f"     --info <file>       (covenant_info.json)")
        print(f"     API: {args.api_url}")
        sys.exit(1)

    # ── Verify recipient ──
    b_privkey = kaspa.PrivateKey(args.key)
    b_pubkey = b_privkey.to_public_key()
    b_xonly_hex = b_pubkey.to_x_only_public_key().to_string()

    if b_xonly_hex != info["b_pubkey"]:
        print(f"❌ Wrong key! This whisper is for a different recipient.")
        print(f"   Your pubkey:     {b_xonly_hex}")
        print(f"   Expected pubkey: {info['b_pubkey']}")
        sys.exit(1)

    # ── Decrypt message ──
    msg_type = info.get("type", info.get("t", "message"))
    raw_data = info.get("d", "")

    # If we have the original payload JSON with encrypted data
    if msg_type == "whisper":
        # data is hex-encoded ECIES ciphertext
        from ecies import decrypt as ecies_decrypt
        # Need full 32-byte private key for decryption
        privkey_bytes = bytes.fromhex(args.key)
        ciphertext = bytes.fromhex(raw_data)
        plaintext = ecies_decrypt(privkey_bytes, ciphertext)
        message = plaintext.decode("utf-8")
    else:
        message = raw_data

    print(f"🌊 Whisper Covenant v2 — Decode")
    print(f"   TX: {args.tx}")
    print(f"   From: {info['a_address']}")
    print(f"   Type: {msg_type}")
    print(f"   💬 Message: {message}")
    print()

    if args.no_refund:
        print("   (--no-refund: skipping covenant spend)")
        return

    # ── Spend covenant UTXO → refund to sender ──
    client = None
    use_remote = args.remote

    if not use_remote:
        try:
            client = kaspa.RpcClient(url=WRPC_URL, encoding="borsh", network_id=NETWORK_ID)
            await client.connect()
            p2sh_addr = info["p2sh_address"]
            result = await client.get_utxos_by_addresses({"addresses": [p2sh_addr]})
            entries = result.get("entries", [])
        except Exception as e:
            print(f"⚠️  Local kaspad not available ({e}), falling back to REST API...")
            use_remote = True
            client = None

    if use_remote:
        import urllib.request
        p2sh_addr = info["p2sh_address"]
        utxo_url = f"{REST_API_URL}/addresses/{p2sh_addr}/utxos"
        print(f"🌐 Fetching covenant UTXO from REST API...")
        try:
            req = urllib.request.Request(utxo_url, headers={"User-Agent": "whisper/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                utxo_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"❌ REST API UTXO fetch failed: {e}")
            sys.exit(1)
        entries = []
        for u in utxo_data:
            spk = u["utxoEntry"]["scriptPublicKey"]
            if isinstance(spk, dict):
                spk = "0000" + spk.get("scriptPublicKey", "")
            entry = {
                "outpoint": {
                    "transactionId": u["outpoint"]["transactionId"],
                    "index": u["outpoint"]["index"],
                },
                "address": p2sh_addr,
                "utxoEntry": {
                    "amount": int(u["utxoEntry"]["amount"]),
                    "scriptPublicKey": spk,
                    "blockDaaScore": int(u["utxoEntry"]["blockDaaScore"]),
                    "isCoinbase": u["utxoEntry"]["isCoinbase"],
                },
            }
            entries.append(entry)
    else:
        p2sh_addr = info["p2sh_address"]

    if not entries:
        print("❌ No covenant UTXO found (already spent or not confirmed)")
        await client.disconnect()
        sys.exit(1)

    # Find specific UTXO
    covenant_entry = None
    for e in entries:
        if e["outpoint"]["transactionId"] == args.tx:
            covenant_entry = e
            break
    if not covenant_entry:
        covenant_entry = entries[0]
        print(f"   ⚠️ Exact UTXO not found, using first available")

    utxo_amount = covenant_entry["utxoEntry"]["amount"]
    deposit = info["deposit_sompi"]
    a_addr_str = info["a_address"]
    fee = 3000
    refund_amount = utxo_amount - fee

    if refund_amount < deposit:
        print(f"❌ UTXO too small ({utxo_amount}) for refund ({deposit}) + fee ({fee})")
        await client.disconnect()
        sys.exit(1)

    # Build spend TX
    tx = kaspa.create_transaction(
        [covenant_entry],
        [kaspa.PaymentOutput(kaspa.Address(a_addr_str), refund_amount)],
        0, b"",
    )

    # Sign
    sig = kaspa.create_input_signature(tx, 0, b_privkey, kaspa.SighashType.All)
    sig_bytes = bytes.fromhex(sig) if isinstance(sig, str) else sig

    covenant_script = bytes.fromhex(info["covenant_script_hex"])
    sig_script = sig_bytes + push_data(covenant_script)

    tx.inputs[0].signature_script = sig_script
    tx.inputs[0].sig_op_count = 1

    print(f"📝 Refund TX")
    print(f"   Refund: {refund_amount/1e8:.4f} tKAS → {a_addr_str}")
    print(f"   Fee: {fee/1e8:.5f} tKAS")

    if client and not use_remote:
        try:
            r = await client.submit_transaction({"transaction": tx, "allow_orphan": False})
            refund_tx_id = r.get("transactionId", tx.id)
            print(f"\n✅ Refund TX submitted! ID: {refund_tx_id}")
            print(f"   Sender {a_addr_str} gets {refund_amount/1e8:.4f} tKAS back")
        except Exception as e:
            print(f"\n❌ Refund failed: {e}")
        await client.disconnect()
    else:
        # Submit via Whisper API (which connects to kaspad wRPC)
        import urllib.request
        broadcast_url = f"{args.api_url}/api/broadcast"
        tx_dict = tx.serialize_to_dict()
        broadcast_body = {"signed_tx_dict": tx_dict}
        print(f"📡 Broadcasting refund TX via Whisper API...")
        try:
            req = urllib.request.Request(
                broadcast_url,
                data=json.dumps(broadcast_body).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "whisper/1.0",
                          "X-Whisper-Key": os.environ.get("WHISPER_API_KEY", "whisper-testnet-poc-key")},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result_data = json.loads(resp.read().decode("utf-8"))
                refund_tx_id = result_data.get("tx_id", tx.id)
                print(f"\n✅ Refund TX broadcast via Whisper API! ID: {refund_tx_id}")
                print(f"   Sender {a_addr_str} gets {refund_amount/1e8:.4f} tKAS back")
        except Exception as e:
            err_body = ""
            if hasattr(e, 'read'):
                err_body = e.read().decode("utf-8", errors="replace")
            print(f"\n❌ Whisper API broadcast failed: {e}")
            if err_body:
                print(f"   Detail: {err_body}")


if __name__ == "__main__":
    asyncio.run(main())
