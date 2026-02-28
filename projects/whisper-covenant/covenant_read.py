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
import sys

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
    # Remaining goes to fee

    # Use create_transaction to get UTXO entry attached
    # Output must go to A's address
    a_addr_str = info["a_address"]
    refund_amount = deposit
    fee = utxo_amount - refund_amount  # rest is fee

    tx = kaspa.create_transaction(
        [covenant_entry],
        [kaspa.PaymentOutput(kaspa.Address(a_addr_str), refund_amount)],
        0,
        b"",
    )

    # For P2SH spending, we need:
    # 1. Compute signature over the tx
    # 2. Build sig_script = <sig> <redeem_script> (P2SH format)
    
    # create_input_signature with the covenant's UTXO
    sig = kaspa.create_input_signature(tx, 0, b_privkey, kaspa.SighashType.All)
    sig_bytes = bytes.fromhex(sig) if isinstance(sig, str) else sig

    # Build P2SH signature script
    covenant_script = bytes.fromhex(info["covenant_script_hex"])
    sig_script = kaspa.pay_to_script_hash_signature_script(covenant_script, sig_bytes)
    sig_script_bytes = bytes.fromhex(sig_script) if isinstance(sig_script, str) else sig_script

    # We need to set the signature script on the input
    # Since sign_transaction won't work for P2SH (it expects P2PK),
    # we need to rebuild the TX with the custom sig_script
    # But rebuilding loses UTXO entries...
    
    # Workaround: modify the serialized dict and submit directly
    td = tx.serialize_to_dict()
    td["inputs"][0]["signatureScript"] = sig_script_bytes.hex() if isinstance(sig_script_bytes, bytes) else sig_script_bytes

    print(f"📝 Spend TX")
    print(f"   Refund to A: {refund_amount / 1e8:.4f} tKAS")
    print(f"   Fee: {fee / 1e8:.4f} tKAS")
    print(f"   Sig script len: {len(sig_script_bytes)} bytes")

    # Rebuild TX object from dict for submission
    # We need a Transaction object. Let's reconstruct:
    inp_signed = kaspa.TransactionInput(
        previous_outpoint=kaspa.TransactionOutpoint(
            transaction_id=kaspa.Hash(utxo_outpoint["transactionId"]),
            index=utxo_outpoint["index"],
        ),
        signature_script=sig_script_bytes,
        sequence=0,
        sig_op_count=len(covenant_script),  # sig_op_count for P2SH
    )

    out_refund = kaspa.TransactionOutput(
        value=refund_amount,
        script_public_key=kaspa.ScriptPublicKey(0, info["a_spk"]),
    )

    tx_signed = kaspa.Transaction(
        version=0,
        inputs=[inp_signed],
        outputs=[out_refund],
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
        print(f"   Result: {r}")
    except Exception as e:
        print(f"\n❌ Submit failed: {e}")
        print(f"   This likely means the covenant opcodes aren't enabled on TN12,")
        print(f"   or the sighash computation is wrong for P2SH scripts.")
        print(f"\n   TX dict:")
        print(json.dumps(tx_signed.serialize_to_dict(), indent=2))

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
