# 🌊 Whisper Covenant v0.1

**Trustless message refund system on Kaspa TN12 using covenant introspection opcodes.**

## Concept

A sends a message to B by locking 0.2 KAS into a covenant script. When B reads the message (spends the UTXO), the covenant **enforces** that 0.2 KAS is refunded to A. Result: A only pays tx fees, B reads for free.

```
A (sender)                    Covenant UTXO                    B (receiver)
    │                              │                               │
    ├──── lock 0.2 KAS ──────────►│ P2SH script                   │
    │     + message in payload     │ enforces refund to A          │
    │                              │                               │
    │                              │◄──── B spends (reads) ────────┤
    │◄──── 0.2 KAS refund ────────│     covenant verifies:         │
    │     (enforced by script)     │     1. output[0] → A          │
    │                              │     2. amount ≥ 0.2 KAS       │
    │                              │     3. signed by B            │
```

## Covenant Script

```
// Redeem script (inside P2SH):

<A_spk_bytes>          // A's ScriptPublicKey bytes (version + script)
OP_FALSE               // output index 0
OP_TX_OUTPUT_SPK       // introspect spending TX's output[0] SPK
OP_EQUAL
OP_VERIFY              // ✓ output[0] pays to A

<20000000>             // 0.2 KAS in sompi
OP_FALSE               // output index 0
OP_TX_OUTPUT_AMOUNT    // introspect spending TX's output[0] amount
OP_GREATERTHANOREQUAL
OP_VERIFY              // ✓ output[0] ≥ 0.2 KAS

<B_pubkey>             // 32-byte Schnorr pubkey
OP_CHECKSIG            // ✓ only B can spend
```

### Opcode Reference (TN12)

| Opcode | Hex | Stack Effect |
|--------|-----|--------------|
| `OP_TX_OUTPUT_SPK` | `0xc3` | `<idx> → <spk_bytes>` |
| `OP_TX_OUTPUT_AMOUNT` | `0xc2` | `<idx> → <amount_i64>` |
| `OP_TX_INPUT_COUNT` | `0xb3` | `→ <count>` |
| `OP_TX_OUTPUT_COUNT` | `0xb4` | `→ <count>` |
| `OP_TX_INPUT_AMOUNT` | `0xbe` | `<idx> → <amount_i64>` |

### SPK Bytes Format

`OP_TX_OUTPUT_SPK` pushes `version(2 bytes BE) + script_bytes`:
- P2PK: `0x0000` + `[0x20 <32-byte-pubkey> 0xac]` = 36 bytes

## Message Format

Messages are encoded in the transaction **payload**:

```
WHSP (4 bytes magic)
0x01 (1 byte version)
<sender_pubkey> (32 bytes)
<msg_len> (2 bytes LE)
<message> (UTF-8)
```

## Usage

```python
from whisper_covenant_v01 import *

# Generate covenant script
a_spk = encode_spk_bytes(a_pubkey_bytes)
script = create_covenant_script(a_spk, b_pubkey_bytes, 20_000_000)

# Send message (locks 0.2 KAS)
result = await send_message(sender_privkey_hex, receiver_pubkey_hex, "Hello!")

# Read message (spends covenant, refunds to sender)
result = await read_message(receiver_privkey_hex, covenant_utxo)
```

## Status

- [x] Covenant script design & generation
- [x] SPK encoding (matches OP_TX_OUTPUT_SPK format)
- [x] Message encoding/decoding in TX payload
- [x] ScriptBuilder SDK integration
- [x] P2SH address derivation
- [x] Transaction building (send) — `covenant_send.py`
- [x] P2SH spending (sig script construction) — `covenant_read.py`
- [x] RPC integration (UTXO fetch, TX submit)
- [x] **End-to-end test on TN12** ✅ 2026-02-28
- [ ] Message scanning / indexer

## Test Results (TN12, 2026-02-28)

### Send (A locks deposit)
- **TX**: `18e496038976ae8b0dcf8d68b8dc3c738b5febf68fe14b3c06af1ea1efa22942`
- Locked 0.2001 tKAS (0.2 deposit + fee buffer) to P2SH covenant address
- Message: "Whisper Covenant PoC - B reads and refunds A"

### Read (B spends → A gets refund)
- **TX**: `04c83afa2f82ff42587e1ae06363716362c5cece69b653aa74e3c57bc7936b28`
- B signed and spent covenant UTXO
- Covenant enforced: output[0] = 0.2 tKAS → A's address ✅
- A received refund confirmed on-chain ✅

### Key Insights
- `kaspa.create_input_signature()` + `kaspa.pay_to_script_hash_signature_script()` handle P2SH signing
- sig_op_count = 1 (one OP_CHECKSIG in redeem script)
- Fee buffer in covenant UTXO allows B to pay mining fee from the locked amount
- Single output avoids storage mass issues

## Requirements

- Kaspa TN12 node (`kaspad --testnet --netsuffix=12`)
- Python kaspa SDK (`pip install kaspa`)
- wRPC endpoint: `ws://127.0.0.1:17210`

## Architecture Notes

### Why P2SH?

The covenant logic lives in a **redeem script** wrapped in P2SH. When A sends, the UTXO is locked to the P2SH hash. When B spends, B provides the full redeem script + signature in the sig script. The script engine verifies:
1. Redeem script hash matches
2. Covenant conditions (output SPK, amount)
3. B's signature

### Security Properties

- **Trustless refund**: The covenant script is the law — B cannot spend without refunding A
- **Only B can spend**: `OP_CHECKSIG` ensures only B's signature is valid
- **Amount guaranteed**: `OP_GREATERTHANOREQUAL` ensures full refund
- **SPK pinned**: `OP_TX_OUTPUT_SPK` + `OP_EQUAL` ensures refund goes to A's exact address

### Limitations (v0.1)

- No message encryption (plaintext in payload)
- No expiry mechanism (A can't reclaim if B never reads)
- Single recipient only
- No message threading
