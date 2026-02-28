#!/usr/bin/env python3
"""
🌊 Whisper Covenant — Read (B spends covenant UTXO → A gets refund)

Usage: python3 covenant_read.py

Flow:
  1. Load covenant info from covenant_info.json
  2. Find the covenant UTXO on chain
  3. Build spend TX: output[0] = deposit → A (forced by covenant)
  4. Sign with B's key (P2SH signature script)
  5. A automatically gets refund
"""

import asyncio
import json
import os
import struct

import kaspa

# ─── Config ───────────────────────────────────────────────────────
WRPC_URL = "ws://localhost:17210"
NETWORK_ID = "testnet-12"
NETWORK_TYPE = "testnet"
NATIVE_SUBNETWORK = "00" * 20

WALLET_PATH = os.path.expanduser("~/.secrets/testnet-wallet.json")


async def main():
    # Load covenant info
    info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covenant_info.json")
    if not os.path.exists(info_path):
        print("❌ covenant_info.json not found. Run covenant_send.py first!")
        return

    with open(info_path) as f:
        info = json.load(f)

    print(f"🌊 Whisper Covenant — Read")
    print(f"   TX ID: {info['tx_id']}")
    print(f"   Message: {info['message']}")
    print(f"   Deposit: {info['deposit_sompi'] / 1e8:.2f} tKAS")
    print(f"   A address: {info['a_address']}")
    print()

    # Load B's wallet (PoC: B = A)
    with open(WALLET_PATH) as f:
        wallet = json.load(f)

    b_privkey = kaspa.PrivateKey(wallet["private_key"])

    # Connect
    client = kaspa.RpcClient(url=WRPC_URL, encoding="borsh", network_id=NETWORK_ID)
    await client.connect()
    print("✅ Connected to kaspad")

    # Find the covenant UTXO at P2SH address
    p2sh_addr = info["p2sh_address"]
    result = await client.get_utxos_by_addresses({"addresses": [p2sh_addr]})
    entries = result.get("entries", [])

    print(f"   UTXOs at P2SH address: {len(entries)}")

    if not entries:
        print("❌ No covenant UTXO found! TX may not be confirmed yet.")
        await client.disconnect()
        return

    # Find the specific UTXO from our TX
    covenant_entry = None
    for e in entries:
        if e["outpoint"]["transactionId"] == info["tx_id"]:
            covenant_entry = e
            break

    if not covenant_entry:
        covenant_entry = entries[0]
        print(f"   ⚠️ Exact UTXO not found, using first available")

    utxo_outpoint = covenant_entry["outpoint"]
    utxo_amount = covenant_entry["utxoEntry"]["amount"]
    deposit = info["deposit_sompi"]

    print(f"   Found UTXO: {utxo_outpoint['transactionId']}:{utxo_outpoint['index']}")
    print(f"   Amount: {utxo_amount / 1e8:.4f} tKAS")
    print()

    # Build spend TX
    # The covenant forces output[0] >= deposit to A's SPK
    a_addr_str = info["a_address"]
    fee = 3000  # 0.00003 tKAS
    refund_amount = utxo_amount - fee

    if refund_amount < deposit:
        print(f"❌ UTXO too small for refund + fee! Need {deposit + fee}, have {utxo_amount}")
        await client.disconnect()
        return

    # Use create_transaction to get UTXO entry attached (needed for sighash)
    tx = kaspa.create_transaction(
        [covenant_entry],
        [kaspa.PaymentOutput(kaspa.Address(a_addr_str), refund_amount)],
        0,
        b"",
    )

    print(f"📝 Spend TX (before signing)")
    print(f"   Refund to A: {refund_amount / 1e8:.4f} tKAS")
    print(f"   Fee: {fee / 1e8:.5f} tKAS")

    # For P2SH spending, we need:
    # 1. Compute signature over the tx (sighash uses UTXO's P2SH SPK)
    # 2. Build sig_script = <sig> <redeem_script>
    sig = kaspa.create_input_signature(tx, 0, b_privkey, kaspa.SighashType.All)
    sig_bytes = bytes.fromhex(sig) if isinstance(sig, str) else sig
    print(f"   Signature: {sig_bytes.hex()[:40]}... ({len(sig_bytes)} bytes)")

    # Build P2SH signature script
    covenant_script = bytes.fromhex(info["covenant_script_hex"])
    sig_script_hex = kaspa.pay_to_script_hash_signature_script(covenant_script, sig_bytes)
    sig_script = bytes.fromhex(sig_script_hex) if isinstance(sig_script_hex, str) else sig_script_hex
    print(f"   Sig script: {len(sig_script)} bytes")

    # Now we need to submit the TX with the custom sig script.
    # We'll rebuild the Transaction with the correct sig script.
    # The key is that sig_op_count must match what was used in sighash computation.
    
    inp = kaspa.TransactionInput(
        previous_outpoint=kaspa.TransactionOutpoint(
            transaction_id=kaspa.Hash(utxo_outpoint["transactionId"]),
            index=utxo_outpoint["index"],
        ),
        signature_script=sig_script,
        sequence=0,
        sig_op_count=1,  # 1 OP_CHECKSIG in redeem script
    )

    out = kaspa.TransactionOutput(
        value=refund_amount,
        script_public_key=kaspa.ScriptPublicKey(0, info["a_spk"]),
    )

    tx_signed = kaspa.Transaction(
        version=0,
        inputs=[inp],
        outputs=[out],
        lock_time=0,
        subnetwork_id=NATIVE_SUBNETWORK,
        gas=0,
        payload=b"",
        mass=0,
    )

    print(f"   TX ID: {tx_signed.id}")

    # Submit
    try:
        r = await client.submit_transaction({"transaction": tx_signed, "allow_orphan": False})
        print(f"\n✅ Spend TX submitted! A gets refund automatically.")
        print(f"   Message was: {info['message']}")
        print(f"   Result: {r}")
    except Exception as e:
        print(f"\n❌ Submit failed: {e}")
        
        # Debug: compare TX IDs
        print(f"\n   Debug info:")
        print(f"   TX from create_transaction: {tx.id}")
        print(f"   TX rebuilt:                 {tx_signed.id}")
        if tx.id != tx_signed.id:
            print(f"   ⚠️ TX IDs differ! The sighash was computed for a different TX.")
            print(f"   This means the rebuilt TX doesn't match the signed one.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
