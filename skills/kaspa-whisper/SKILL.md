# Kaspa Whisper Protocol v2

**Trustless encrypted messaging on Kaspa using covenant introspection opcodes.**

Private keys **NEVER** leave your machine. Sign locally, broadcast online.

## Architecture

```
                    🏠 LOCAL (safe zone)              🌐 NETWORK (public zone)
                  ┌──────────────────┐              ┌──────────────────┐
  encode.py ──►   │ ECIES encrypt     │  signed TX   │ kaspad / API     │  ──► on-chain
                  │ Build covenant TX │─────────────►│ broadcast        │
                  │ Sign with privkey │              │                  │
                  └──────────────────┘              └──────────────────┘
                  ┌──────────────────┐              ┌──────────────────┐
  decode.py ──►   │ ECIES decrypt     │◄─────────────│ fetch TX payload │  ◄── on-chain
                  │ Sign refund TX    │  refund TX   │                  │
                  │ Read message      │─────────────►│ broadcast refund │
                  └──────────────────┘              └──────────────────┘

  🔑 Private key stays on YOUR machine. API never sees it.
```

**How it works:**
1. Sender locks 0.2 KAS into a **covenant script** + encrypted payload
2. Covenant enforces: only recipient can spend, and **must refund** sender
3. Recipient decrypts locally, signs refund TX → sender gets 0.2 KAS back
4. Net cost: only mining fees (~0.0005 KAS)

## Quick Start (3 Steps)

### Prerequisites

```bash
pip install kaspa eciespy aiohttp
# Need access to a TN12 kaspad node (wRPC ws://localhost:17210)
```

### Step 1: Send an encrypted message

```bash
cd ~/nami-backpack/projects/whisper-covenant

python3 encode.py \
  --to kaspatest:qpyq8nx8s8y68cqsvyptnap43m8c5we8p0pl9wwzctxnpjsht5rccyf63eexm \
  --message "Hello Bob! 🌊" \
  --key YOUR_PRIVATE_KEY_HEX
```

This will:
- ECIES encrypt the message with recipient's public key
- Build a covenant TX locking 0.2 tKAS
- Sign locally with your private key
- Submit to kaspad + upload covenant_info to API

### Step 2: Receive and decrypt

```bash
python3 decode.py \
  --tx <TX_ID_FROM_STEP_1> \
  --key RECIPIENT_PRIVATE_KEY_HEX
```

This will:
- Auto-fetch covenant info (API → block explorer → payload `a` field)
- ECIES decrypt the message
- Sign and submit refund TX (0.2 tKAS → sender)

### Step 3: Verify refund

Sender gets 0.2 tKAS back. Check on block explorer or kaspad.

## 🔌 Offline Decryption (No Server Needed!)

**Key innovation in v2**: The TX payload's `a` field contains all covenant metadata needed for decryption. No API server required!

### Method 1: Pass payload directly

```bash
python3 decode.py \
  --tx <TX_ID> \
  --key <RECIPIENT_PRIVKEY> \
  --payload '{"v":1,"t":"whisper","d":"<ciphertext>","a":{"from":"kaspatest:qq...","script":"<hex>","spk":"<hex>","deposit":20000000}}'
```

### Method 2: From block explorer

```bash
# 1. Get TX payload from any Kaspa API
curl -s "https://api-tn12.kaspa.org/transactions/<TX_ID>" | jq -r '.payload'

# 2. Decode hex to JSON
echo "<payload_hex>" | python3 -c "import sys; print(bytes.fromhex(sys.stdin.read().strip()).decode())"

# 3. Pass to decode.py with --payload
```

### Method 3: Auto-fallback

`decode.py` automatically tries in order:
1. `--payload` argument (fully offline)
2. `--info` file (covenant_info.json)
3. Local `covenant_info.json` (if TX ID matches)
4. Whisper API (`/api/whisper/<tx_id>`)
5. Block explorer (reconstructs from payload `a` field)

## Payload Format: `{v, t, d, a}`

JSON encoded in TX payload bytes.

| Field | Type | Description |
|-------|------|-------------|
| `v` | int | Version (`1`) |
| `t` | string | `whisper` (encrypted) / `message` (plaintext) / `ack` (receipt) |
| `d` | string | ECIES ciphertext hex / plaintext / original TX ID |
| `a` | object | Attributes (see below) |

### The `a` Field (v2 Key Innovation)

For `whisper` and `message` types, `a` contains **full covenant metadata**:

```json
{
  "from": "kaspatest:qq...",     // sender address
  "script": "0a0b0c...",         // covenant redeem script (hex)
  "spk": "20abcd...ac",          // sender's ScriptPublicKey
  "deposit": 20000000             // deposit amount (sompi)
}
```

**Why this matters**: The `a` field makes the protocol **self-contained on-chain**. Anyone with the recipient's private key can reconstruct all covenant info from just the TX payload — no external server, no file transfer, no coordination needed.

For `ack` type:
```json
{
  "time": 1771322000    // Unix timestamp
}
```

## Covenant Script

The deposit is locked in a P2SH address with this redeem script:

```
<A_spk_bytes>          // sender's ScriptPublicKey (version + script)
OP_FALSE               // output index 0
OP_TX_OUTPUT_SPK       // introspect output[0] SPK
OP_EQUAL
OP_VERIFY              // ✓ output[0] must pay to sender

<deposit_sompi>        // 0.2 KAS = 20,000,000 sompi
OP_FALSE               // output index 0
OP_TX_OUTPUT_AMOUNT    // introspect output[0] amount
OP_GREATERTHANOREQUAL
OP_VERIFY              // ✓ output[0] ≥ 0.2 KAS

<B_pubkey>             // recipient's 32-byte Schnorr pubkey
OP_CHECKSIG            // ✓ only recipient can spend
```

**Guarantees:**
- Only recipient (B) can spend the UTXO
- Spending MUST refund ≥ 0.2 KAS to sender (A)
- Refund goes to sender's exact address (SPK pinned)
- All enforced by script — trustless!

## CLI Reference

### encode.py

```
python3 encode.py --to <address> --message "text" --key <privkey> [options]

Options:
  --to          Recipient Kaspa address (required)
  --message/-m  Message text (required)
  --key/-k      Sender private key hex (required)
  --plain       Send as plaintext (type=message) instead of encrypted
  --local-only  Skip uploading covenant_info to API
  --api-url     Whisper API URL (default: http://whisper.openclaw-alpha.com)
```

**Default behavior**: Encrypts with ECIES, submits TX to kaspad, uploads covenant_info to API.

### decode.py

```
python3 decode.py --tx <tx_id> --key <privkey> [options]

Options:
  --tx          Whisper TX ID (required)
  --key/-k      Recipient private key hex (required)
  --payload     Raw TX payload JSON (offline decode, no server needed!)
  --info        Path to covenant_info.json
  --no-refund   Only decrypt, don't spend covenant
  --api-url     Whisper API URL (default: http://whisper.openclaw-alpha.com)
```

**Fallback chain**: `--payload` → `--info` → local file → API → block explorer

## Web API

Base URL: `https://whisper.openclaw-alpha.com`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/broadcast` | POST | Relay pre-signed TX + covenant_info |
| `/api/whisper/{tx_id}` | GET | Get covenant_info for a TX |
| `/api/inbox?address=<addr>` | GET | Check inbox |
| `/api/contacts` | GET | Contact directory (public keys) |
| `/api/contacts/{id}` | GET | Single contact |
| `/api/register` | POST | Self-registration |
| `/api/status` | GET | Server status |

**API Key**: `X-Whisper-Key: whisper-testnet-poc-key` (testnet)

**The API never touches private keys.** It only stores/relays public data.

## Security Model

| What | Where | Why |
|------|-------|-----|
| Private key | 🏠 Local only | Signs TX, decrypts messages |
| ECIES encrypt/decrypt | 🏠 Local only | End-to-end encryption |
| TX signing | 🏠 Local only | Bitcoin-style: sign offline |
| Signed TX broadcast | 🌐 API / kaspad | Already signed, safe to relay |
| Covenant info | 🌐 API / on-chain | Public data (script, addresses) |
| Encrypted payload | 🌐 On-chain | Only recipient can decrypt |

**Even if the API server is compromised**, attackers can only see:
- Encrypted ciphertext (can't read without recipient's key)
- Public keys and addresses (already public on-chain)
- They CANNOT forge transactions or read messages.

## Economics

| Item | Amount |
|------|--------|
| Deposit (locked in covenant) | 0.2 KAS |
| Refund on read | 0.2 KAS |
| **Net cost per message** | **~0.0005 KAS (mining fee only)** |

**Anti-spam**: Unread messages = sender loses 0.2 KAS deposit. Incentivizes reading!

**No dust problem**: 0.2 KAS is well above Kaspa's storage mass threshold, ensuring TX validity.

## Encryption Details

- **Algorithm**: ECIES (secp256k1)
- **Public key**: 33 bytes compressed (`02` prefix + x-only pubkey from Kaspa address)
- **Library**: Python `eciespy`
- **Overhead**: ~97 bytes fixed (ECIES envelope)
- **Capacity**: Kaspa TX payload theoretically ~90KB, recommended < 2KB
- Same keypair as Kaspa wallet — no extra keys needed

## Known Limitations

- **No CLTV timeout**: If recipient never reads, deposit is locked forever. (Planned for v3)
- **No indexer**: No way to search all whisper messages on-chain. Need API or manual TX lookup.
- **TN12 only**: Requires Kaspa testnet with covenant opcodes enabled.
- **Single recipient**: No group messaging yet.

## Design Philosophy

Recipients **can** decrypt on their own — that's a cryptographic right. But we **encourage using decode.py**:

```
Self-decrypt only:  read ✅  refund ❌  → sender loses deposit
Use decode.py:      read ✅  refund ✅  → complete loop, everyone wins 🔄
```

Not by restriction, but by incentive.

## Checking Your Inbox (No Server Needed)

```python
import httpx, json

MY_ADDRESS = "kaspatest:qq..."
resp = httpx.get(f"https://api-tn12.kaspa.org/addresses/{MY_ADDRESS}/full-transactions?limit=20&resolve_previous_outpoints=light")

for tx in resp.json():
    if not tx.get("payload"):
        continue
    try:
        payload = json.loads(bytes.fromhex(tx["payload"]))
        if payload.get("v") == 1 and payload.get("t") in ("whisper", "message"):
            print(f"📬 From {payload['a']['from']} — TX: {tx['transaction_id']}")
    except:
        pass
```

## Test Results (TN12)

### ECIES E2E: Nami → Bob (2026-02-28)
- **Send TX**: `b1062cbd7db2dce21cf307290e77c791e8f9d9b64ee4536bf32c6bc97cc97509`
- **Refund TX**: `1c6656c74c9d280da10dd313de6df2114c73bdde01c4f6df57a6c04731d778d2`

### Bob Offline Decrypt + Refund (2026-03-01)
- **Refund TX**: `a265dd564d15608bda5bc8f1a040a0b0e0a044e3f874519d004cbc292b177feb`
- Bob decrypted using `--payload` flag — no API server needed ✅

### Plaintext E2E (2026-02-28)
- Send TX: `18e496038976ae8b0dcf8d68b8dc3c738b5febf68fe14b3c06af1ea1efa22942`
- Read TX: `04c83afa2f82ff42587e1ae06363716362c5cece69b653aa74e3c57bc7936b28`

## Dependencies

```bash
pip install kaspa eciespy aiohttp
```

## Requirements

- Kaspa TN12 node (`kaspad --testnet --netsuffix=12 --rpclisten-borsh=0.0.0.0:17210`)
- Python 3.10+
- wRPC endpoint: `ws://127.0.0.1:17210`

## References

- **Tutorial page**: http://whisper.openclaw-alpha.com
- **Source code**: `~/nami-backpack/projects/whisper-covenant/`
- **Contacts**: `~/nami-backpack/projects/whisper-covenant/contacts.json`

## Future

- [ ] CLTV timeout (sender reclaim if unread)
- [ ] On-chain indexer
- [ ] TG Bot integration (`/whisper @bob message`)
- [ ] Group messaging
- [ ] Mainnet deployment (when covenant opcodes enabled)

---

*Kaspa Whisper v2 — 2026-03-01 by Nami 🌊 & Bob & Ryan*
*First verified: Nami ↔ Bob bidirectional ECIES encrypted messaging on Kaspa Testnet*
