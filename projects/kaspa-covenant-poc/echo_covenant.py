#!/usr/bin/env python3
"""
Kaspa Covenant PoC — Echo Server (Agent Communication Protocol)

概念：用戶發 0.2 KAS + 訊息 → Covenant 退 0.19 + 留 0.01 手續費

這個 PoC 先用 Rust 範例的邏輯建構 covenant script，
然後嘗試在 TN12 上部署。

Step 1: 建構 covenant script (P2SH)
Step 2: 計算 covenant address
Step 3: 發送 seed TX（往 covenant 存入初始資金）
Step 4: 建構 echo TX（用戶呼叫 covenant）
"""

import hashlib
import struct

# ═══════════════════════════════════════
# Kaspa Script Opcodes (from rusty-kaspa)
# ═══════════════════════════════════════

# Data push
OP_0 = 0x00
OP_1 = 0x51
OP_2 = 0x52

# Stack
OP_DUP = 0x76
OP_ROT = 0x7b
OP_SWAP = 0x7c

# Logic
OP_EQUAL = 0x87
OP_EQUALVERIFY = 0x88
OP_VERIFY = 0x69

# Arithmetic
OP_1ADD = 0x8b
OP_SUB = 0x94
OP_GREATERTHANOREQUAL = 0xa2
OP_GREATERTHAN = 0xa0
OP_SIZE = 0x82

# Crypto
OP_BLAKE2B_WITH_KEY = 0xaa
OP_SHA256 = 0xa8
OP_HASH256 = 0xaa  # alias

# Covenant-specific (TN12)
OP_TX_VERSION = 0xb2
OP_TX_INPUT_COUNT = 0xb3
OP_TX_OUTPUT_COUNT = 0xb4
OP_TX_LOCK_TIME = 0xb5
OP_TX_PAYLOAD_SUBSTR = 0xb8
OP_TX_INPUT_INDEX = 0xb9
OP_TX_INPUT_AMOUNT = 0xbe
OP_TX_INPUT_SPK = 0xbf
OP_TX_OUTPUT_AMOUNT = 0xc2
OP_TX_OUTPUT_SPK = 0xc3
OP_TX_PAYLOAD_LEN = 0xc4

# P2SH
OP_HASH256_P2SH = 0xaa
OP_CHECKMULTISIG = 0xae

# Cat
OP_CAT = 0x7e
OP_OUTPOINT_TX_ID = 0xba


def push_data(data: bytes) -> bytes:
    """Encode data push for Kaspa script"""
    length = len(data)
    if length == 0:
        return bytes([OP_0])
    if length <= 75:
        return bytes([length]) + data
    elif length <= 255:
        return bytes([0x4c, length]) + data  # OP_PUSHDATA1
    elif length <= 65535:
        return bytes([0x4d]) + struct.pack('<H', length) + data  # OP_PUSHDATA2
    else:
        return bytes([0x4e]) + struct.pack('<I', length) + data  # OP_PUSHDATA4


def push_i64(val: int) -> bytes:
    """Push a small integer onto the stack"""
    if val == 0:
        return bytes([OP_0])
    if 1 <= val <= 16:
        return bytes([0x50 + val])  # OP_1 through OP_16
    # Encode as data
    if val < 0:
        # Negative: set high bit of last byte
        abs_val = abs(val)
        data = abs_val.to_bytes((abs_val.bit_length() + 8) // 8, 'little')
        if data[-1] & 0x80:
            data += b'\x80'
        else:
            data = data[:-1] + bytes([data[-1] | 0x80])
    else:
        data = val.to_bytes((val.bit_length() + 8) // 8, 'little')
        if data[-1] & 0x80:
            data += b'\x00'
    return push_data(data)


# ═══════════════════════════════════════
# Echo Covenant Script
# ═══════════════════════════════════════

def build_echo_covenant_script() -> bytes:
    """
    Build covenant script for echo server.
    
    Rules:
    1. output[0] must go back to same covenant SPK
    2. exactly 2 outputs
    3. output[0] amount >= input[0] amount (covenant doesn't shrink)
    4. payload must be non-empty (message required)
    """
    script = bytearray()
    
    # === Rule 1: output[0] SPK == covenant input SPK ===
    # Push covenant's own SPK
    script.append(OP_TX_INPUT_INDEX)   # push 0 (current input index)
    script.append(OP_TX_INPUT_SPK)     # push this input's SPK
    # Push output[0]'s SPK
    script += push_i64(0)              # push 0
    script.append(OP_TX_OUTPUT_SPK)    # push output[0]'s SPK
    script.append(OP_EQUALVERIFY)      # verify equal
    
    # === Rule 2: exactly 2 outputs ===
    script.append(OP_TX_OUTPUT_COUNT)  # push output count
    script += push_i64(2)              # push 2
    script.append(OP_EQUALVERIFY)      # verify equal
    
    # === Rule 3: output[0] amount >= input[0] amount ===
    # (covenant UTXO doesn't shrink — it can only grow from fees)
    script += push_i64(0)              # push 0
    script.append(OP_TX_OUTPUT_AMOUNT) # push output[0] amount
    script.append(OP_TX_INPUT_INDEX)   # push 0
    script.append(OP_TX_INPUT_AMOUNT)  # push input[0] amount
    script.append(OP_GREATERTHANOREQUAL) # output >= input
    script.append(OP_VERIFY)
    
    # === Rule 4: payload must exist ===
    script.append(OP_TX_PAYLOAD_LEN)   # push payload length
    script += push_i64(0)              # push 0
    script.append(OP_GREATERTHAN)      # payload_len > 0
    
    return bytes(script)


def script_to_p2sh(script: bytes) -> bytes:
    """Compute P2SH script public key from redeem script"""
    # Kaspa P2SH: OP_HASH256 <32-byte-hash> OP_EQUAL
    script_hash = hashlib.blake2b(script, digest_size=32).digest()
    return bytes([OP_HASH256_P2SH]) + push_data(script_hash) + bytes([OP_EQUAL])


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════

if __name__ == '__main__':
    print("🌊 Kaspa Echo Covenant PoC")
    print("=" * 50)
    
    # Build the covenant script
    covenant_script = build_echo_covenant_script()
    print(f"\nCovenant script ({len(covenant_script)} bytes):")
    print(f"  hex: {covenant_script.hex()}")
    
    # Compute P2SH
    p2sh_spk = script_to_p2sh(covenant_script)
    print(f"\nP2SH SPK ({len(p2sh_spk)} bytes):")
    print(f"  hex: {p2sh_spk.hex()}")
    
    # Compute address (testnet)
    script_hash = hashlib.blake2b(covenant_script, digest_size=32).digest()
    print(f"\nScript hash: {script_hash.hex()}")
    
    print("\n📝 Next steps:")
    print("  1. Verify script executes correctly in Rust VM")
    print("  2. Deploy seed TX to TN12")  
    print("  3. Build echo TX with user message")
    print("  4. Read message from chain")
    
    print("\n⚠️ 注意：")
    print("  - P2SH address 計算需要 bech32 encoding (kaspatest:prefix)")
    print("  - 實際部署可能需要用 Rust CLI 工具")
    print("  - Python SDK 不一定支援 covenant TX 簽名")
