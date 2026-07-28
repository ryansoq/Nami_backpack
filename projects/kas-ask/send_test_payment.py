#!/usr/bin/env python3
"""One-off: send a testnet payment so kas-ask's detection path can be exercised.

Not part of the service — the service is receive-only by design and never
signs anything. This script exists purely to close the last untested gap:
"a stranger pays, the watcher notices, credit appears".

Usage:
    /usr/bin/python3 send_test_payment.py <from_key_hex> <to_address> <kas>
"""

from __future__ import annotations

import asyncio
import sys

from kaspa import (
    Address,
    PaymentOutput,
    PrivateKey,
    Resolver,
    RpcClient,
    create_transaction,
    sign_transaction,
)

NETWORK_ID = "testnet-10"
# Kaspa requires fee >= 100 sompi per gram of compute mass; a 2-output tx runs
# ~2000 mass, so 10_000 gets rejected as non-standard. 500_000 leaves headroom.
FEE = 500_000  # sompi
SOMPI = 100_000_000


async def send(from_key_hex: str, to_address: str, kas: float) -> str:
    amount = int(round(kas * SOMPI))
    pk = PrivateKey(from_key_hex)
    from_address = pk.to_address("testnet").to_string()

    # Resolver picks a public node, so no local kaspad is needed.
    client = RpcClient(resolver=Resolver(), network_id=NETWORK_ID)
    await client.connect()
    try:
        resp = await client.get_utxos_by_addresses({"addresses": [from_address]})
        entries = resp.get("entries", [])
        if not entries:
            raise SystemExit(f"no UTXOs on {from_address}")

        total = sum(e["utxoEntry"]["amount"] for e in entries)
        if total < amount + FEE:
            raise SystemExit(
                f"insufficient: have {total/SOMPI:.8f}, need {(amount+FEE)/SOMPI:.8f}"
            )

        outputs = [PaymentOutput(Address(to_address), amount)]
        change = total - amount - FEE
        if change > 0:
            outputs.append(PaymentOutput(Address(from_address), change))

        tx = create_transaction(
            utxo_entry_source=entries, outputs=outputs, priority_fee=FEE
        )
        signed = sign_transaction(tx, [pk], False)
        tx_id = await client.submit_transaction(
            {"transaction": signed, "allow_orphan": False}
        )

        print(f"from   {from_address}")
        print(f"to     {to_address}")
        print(f"amount {amount/SOMPI:.8f} TKAS  (change {change/SOMPI:.8f}, fee {FEE/SOMPI:.8f})")
        print(f"txid   {tx_id}")
        return tx_id
    finally:
        await client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    asyncio.run(send(sys.argv[1], sys.argv[2], float(sys.argv[3])))
