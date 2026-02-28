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

def push_data(data: bytes) -> bytes:
    n = len(data)
    if n <= 75:
        return bytes([n]) + data
    elif n <= 255:
        return bytes([0x4c, n]) + data
    else:
        return bytes([0x4d]) + n.to_bytes(2, "little") + data


async def main():
    parser = argparse.ArgumentParser(description="Whisper Covenant v2 — Decode & Refund locally")
    parser.add_argument("--tx", required=True, help="Whisper TX ID")
    parser.add_argument("--key", "-k", required=True, help="Recipient private key (hex)")
    parser.add_argument("--info", default=None, help="Path to covenant_info.json (default: auto-detect)")
    parser.add_argument("--no-refund", action="store_true", help="Only decrypt, don't spend covenant")
    args = parser.parse_args()

    # ── Load covenant info ──
    info = None
    if args.info:
        with open(args.info) as f:
            info = json.load(f)
    else:
        # Try local file
        info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covenant_info.json")
        if os.path.exists(info_path):
            with open(info_path) as f:
                info = json.load(f)

    if not info or info.get("tx_id") != args.tx:
        print(f"❌ No covenant info found for TX {args.tx}")
        print(f"   Provide --info path or ensure covenant_info.json matches")
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
    client = kaspa.RpcClient(url=WRPC_URL, encoding="borsh", network_id=NETWORK_ID)
    await client.connect()

    p2sh_addr = info["p2sh_address"]
    result = await client.get_utxos_by_addresses({"addresses": [p2sh_addr]})
    entries = result.get("entries", [])

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

    try:
        r = await client.submit_transaction({"transaction": tx, "allow_orphan": False})
        refund_tx_id = r.get("transactionId", tx.id)
        print(f"\n✅ Refund TX submitted! ID: {refund_tx_id}")
        print(f"   Sender {a_addr_str} gets {refund_amount/1e8:.4f} tKAS back")
    except Exception as e:
        print(f"\n❌ Refund failed: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
