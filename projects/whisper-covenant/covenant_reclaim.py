#!/usr/bin/env python3
"""
🌊 Whisper Covenant — Reclaim (A reclaims deposit after timeout)

Usage: python3 covenant_reclaim.py

Flow:
  1. Load covenant info from covenant_info.json
  2. Check that current DAA score > timeout_daa
  3. Build spend TX with lock_time = timeout_daa
  4. Sign with A's key, use OP_FALSE to select ELSE branch
  5. A gets deposit back
"""

import asyncio
import json
import os

import kaspa

# ─── Config ───────────────────────────────────────────────────────
WRPC_URL = "ws://localhost:17210"
NETWORK_ID = "testnet-12"
NETWORK_TYPE = "testnet"

WALLET_PATH = os.path.expanduser("~/.secrets/testnet-wallet.json")


def push_data(data: bytes) -> bytes:
    n = len(data)
    if n <= 75:
        return bytes([n]) + data
    elif n <= 255:
        return bytes([0x4c, n]) + data
    else:
        return bytes([0x4d]) + n.to_bytes(2, "little") + data


async def main():
    # Load covenant info
    info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covenant_info.json")
    if not os.path.exists(info_path):
        print("❌ covenant_info.json not found. Run covenant_send.py first!")
        return

    with open(info_path) as f:
        info = json.load(f)

    timeout_daa = info.get("timeout_daa")
    if not timeout_daa:
        print("❌ No timeout_daa in covenant_info.json. Was this sent with timeout?")
        return

    print(f"🌊 Whisper Covenant — Reclaim (timeout)")
    print(f"   TX ID: {info['tx_id']}")
    print(f"   Deposit: {info['deposit_sompi'] / 1e8:.2f} tKAS")
    print(f"   Timeout DAA: {timeout_daa}")
    print()

    # Load A's wallet
    with open(WALLET_PATH) as f:
        wallet = json.load(f)

    a_privkey = kaspa.PrivateKey(wallet["private_key"])
    a_pubkey = a_privkey.to_public_key()
    a_xonly = a_pubkey.to_x_only_public_key()
    a_addr = a_xonly.to_address(NETWORK_TYPE)
    a_addr_str = a_addr.to_string()

    # Connect
    client = kaspa.RpcClient(url=WRPC_URL, encoding="borsh", network_id=NETWORK_ID)
    await client.connect()
    print("✅ Connected to kaspad")

    # Check current DAA
    dag_info = await client.get_block_dag_info()
    current_daa = int(dag_info["virtualDaaScore"])
    print(f"   Current DAA: {current_daa}")
    print(f"   Timeout DAA: {timeout_daa}")

    if current_daa < timeout_daa:
        remaining = timeout_daa - current_daa
        print(f"   ⏳ Not yet! Need to wait ~{remaining} more DAA scores (~{remaining // 10}s)")
        await client.disconnect()
        return

    print(f"   ✅ Timeout reached! (current {current_daa} >= timeout {timeout_daa})")
    print()

    # Find the covenant UTXO
    p2sh_addr = info["p2sh_address"]
    result = await client.get_utxos_by_addresses({"addresses": [p2sh_addr]})
    entries = result.get("entries", [])

    if not entries:
        print("❌ No covenant UTXO found! Already spent?")
        await client.disconnect()
        return

    # Find exact UTXO
    covenant_entry = None
    for e in entries:
        if e["outpoint"]["transactionId"] == info["tx_id"]:
            covenant_entry = e
            break

    if not covenant_entry:
        covenant_entry = entries[0]
        print(f"   ⚠️ Exact UTXO not found, using first available")

    utxo_amount = covenant_entry["utxoEntry"]["amount"]
    print(f"   Found UTXO: {covenant_entry['outpoint']['transactionId']}:{covenant_entry['outpoint']['index']}")
    print(f"   Amount: {utxo_amount / 1e8:.4f} tKAS")

    # Build reclaim TX
    fee = 3000
    reclaim_amount = utxo_amount - fee

    tx = kaspa.create_transaction(
        [covenant_entry],
        [kaspa.PaymentOutput(kaspa.Address(a_addr_str), reclaim_amount)],
        0,
        b"",
    )

    # Set lock_time to timeout_daa (required for CLTV)
    tx.lock_time = timeout_daa

    print(f"📝 Reclaim TX")
    print(f"   Reclaim to A: {reclaim_amount / 1e8:.4f} tKAS")
    print(f"   Fee: {fee / 1e8:.5f} tKAS")
    print(f"   Lock time: {tx.lock_time}")

    # Sign with A's key
    sig = kaspa.create_input_signature(tx, 0, a_privkey, kaspa.SighashType.All)
    sig_bytes = bytes.fromhex(sig) if isinstance(sig, str) else sig
    print(f"   Signature: {sig_bytes.hex()[:40]}... ({len(sig_bytes)} bytes)")

    # Build P2SH sig script: <sig_serialized> <OP_FALSE> <push redeem_script>
    # OP_FALSE (0x00) selects the ELSE branch (A reclaims)
    covenant_script = bytes.fromhex(info["covenant_script_hex"])
    sig_script = sig_bytes + bytes([0x00]) + push_data(covenant_script)
    print(f"   Sig script: {len(sig_script)} bytes")

    tx.inputs[0].signature_script = sig_script
    tx.inputs[0].sig_op_count = 1

    print(f"   TX ID: {tx.id}")

    # Submit
    try:
        r = await client.submit_transaction({"transaction": tx, "allow_orphan": False})
        print(f"\n✅ Reclaim TX submitted! Deposit returned to A.")
        print(f"   Result: {r}")
    except Exception as e:
        print(f"\n❌ Submit failed: {e}")
        print(f"\n   Debug info:")
        print(f"   TX version: {tx.version}")
        print(f"   TX lock_time: {tx.lock_time}")
        print(f"   TX ID: {tx.id}")
        d = tx.serialize_to_dict()
        print(f"   TX dict inputs[0] sig_script: {d['inputs'][0].get('signatureScript', 'N/A')[:80]}...")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
