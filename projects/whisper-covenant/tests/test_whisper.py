#!/usr/bin/env python3
"""
Whisper Covenant 單元測試

測試項目：
1. 地址格式驗證
2. payload JSON 格式正確性
3. 訊息長度限制檢查
4. ECIES 加解密 round-trip
"""

import json
import pytest
import re
from ecies import encrypt as ecies_encrypt, decrypt as ecies_decrypt
from ecies.utils import generate_key


class TestWhisperCovenant:
    """Whisper Covenant 測試套件"""

    def test_kaspa_address_format(self):
        """測試 Kaspa 地址格式驗證"""
        
        def is_valid_kaspa_address(address):
            """驗證 Kaspa 地址格式"""
            # Kaspa 主網：kaspa:
            # Kaspa 測試網：kaspatest:
            pattern = r'^kaspa(test)?:[a-z0-9]{58,65}$'
            return bool(re.match(pattern, address))

        # 有效地址
        valid_addresses = [
            "kaspa:qz7ulu4c2r3l57uk2nk3ds3kp5hhvgr8v9ru2p5m28q7cm9j9zrp6cg8p7jqr",
            "kaspatest:qzqt39a2qkxjqwqxqvqtqjqpqqqnkgqpqqqpqkqxqqprqwqvqgqyq8qgq7qhvs",
            "kaspatest:qzqt39a2qkxjqwqxqvqtqjqpqqqnkgqpqqqpqkqxqqprqwqvqgqyq8qgq7",
        ]
        
        for addr in valid_addresses:
            assert is_valid_kaspa_address(addr), f"Valid address rejected: {addr}"

        # 無效地址
        invalid_addresses = [
            "",
            "kaspa:",
            "bitcoin:1234567890",
            "kaspa:short",
            "kaspatest:",
            "invalid:qzqt39a2qkxjqwqxqvqtqjqpqqqnkgqpqqqpqkqxqqprqwqvqgqyq8qgq7qhvs",
            "KASPA:qz7ulu4c2r3l57uk2nk3ds3kp5hhvgr8v9ru2p5m28q7cm9j9zrp6cg8p7jqr",  # 大寫
        ]
        
        for addr in invalid_addresses:
            assert not is_valid_kaspa_address(addr), f"Invalid address accepted: {addr}"

    def test_payload_json_format(self):
        """測試 payload JSON 格式正確性"""
        
        # 有效 payload 結構
        valid_payload = {
            "v": 3,
            "t": "whisper",
            "d": "68656c6c6f",  # hex encoded data
            "a": {
                "from": "kaspatest:qzqt39a2qkxjqwqxqvqtqjqpqqqnkgqpqqqpqkqxqqprqwqvqgqyq8qgq7qhvs",
                "script": "636014abcd...",
                "spk": "2014abcd...",
                "deposit": 20000000,
                "timeout_daa": 1000000,
            }
        }
        
        # 檢查必要欄位存在
        assert "v" in valid_payload
        assert "t" in valid_payload
        assert "d" in valid_payload
        assert "a" in valid_payload
        
        # 檢查版本號
        assert valid_payload["v"] == 3
        
        # 檢查類型
        assert valid_payload["t"] in ["whisper", "message"]
        
        # 檢查 a 欄位的子結構
        a_field = valid_payload["a"]
        required_a_fields = ["from", "script", "spk", "deposit", "timeout_daa"]
        for field in required_a_fields:
            assert field in a_field, f"Missing required field in 'a': {field}"
        
        # 檢查 JSON 序列化/反序列化
        json_str = json.dumps(valid_payload, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed == valid_payload

    def test_message_length_limit(self):
        """測試訊息長度限制檢查"""
        MAX_MESSAGE_SIZE = 2048
        
        def check_message_length(message):
            """檢查訊息長度是否超限"""
            return len(message.encode('utf-8')) <= MAX_MESSAGE_SIZE
        
        # 正常長度訊息
        normal_message = "Hello, this is a normal message!"
        assert check_message_length(normal_message)
        
        # 邊界測試 - 剛好 2048 bytes
        boundary_message = "A" * 2048
        assert check_message_length(boundary_message)
        
        # 超過限制
        oversized_message = "A" * 2049
        assert not check_message_length(oversized_message)
        
        # UTF-8 多位元組字符測試
        utf8_message = "你好世界！" * 300  # 每個中文字約 3-4 bytes
        utf8_bytes = len(utf8_message.encode('utf-8'))
        if utf8_bytes <= MAX_MESSAGE_SIZE:
            assert check_message_length(utf8_message)
        else:
            assert not check_message_length(utf8_message)

    def test_ecies_encryption_roundtrip(self):
        """測試 ECIES 加解密 round-trip"""
        
        # 生成測試金鑰對
        private_key = generate_key()
        public_key = private_key.public_key
        
        # 測試訊息
        test_messages = [
            "Hello, World!",
            "這是中文測試訊息 🌊",
            "",  # 空字串
            "A" * 100,  # 較長訊息
            json.dumps({"test": "json message", "number": 12345}),
        ]
        
        for message in test_messages:
            message_bytes = message.encode('utf-8')
            
            # 加密
            ciphertext = ecies_encrypt(public_key.format(compressed=True).hex(), message_bytes)
            assert isinstance(ciphertext, bytes)
            assert len(ciphertext) > 0
            
            # 解密
            decrypted_bytes = ecies_decrypt(private_key.to_hex(), ciphertext)
            decrypted_message = decrypted_bytes.decode('utf-8')
            
            # 驗證 round-trip
            assert decrypted_message == message, f"Round-trip failed for message: {message[:50]}..."

    def test_ecies_with_x_only_pubkey_simulation(self):
        """
        模擬 x-only pubkey 的 ECIES 處理
        （類似 encode.py 和 decode.py 中的處理方式）
        """
        
        # 模擬 x-only pubkey（32 bytes）
        private_key = generate_key()
        public_key = private_key.public_key
        
        # 取得 x-only 部分（33-byte compressed key 去掉第一個 byte）
        compressed_key = public_key.format(compressed=True)
        x_only_hex = compressed_key[1:].hex()  # 去掉 0x02 或 0x03 前綴
        
        test_message = "Whisper test with x-only pubkey simulation"
        message_bytes = test_message.encode('utf-8')
        
        # 模擬 encode.py：嘗試用 02 前綴
        try_02_hex = "02" + x_only_hex
        ciphertext = ecies_encrypt(try_02_hex, message_bytes)
        
        # 模擬 decode.py：先嘗試原始私鑰，失敗則用 negated 私鑰
        try:
            # 嘗試原始私鑰
            decrypted = ecies_decrypt(private_key.to_hex(), ciphertext)
            result = decrypted.decode('utf-8')
        except Exception:
            # 嘗試 negated 私鑰（模擬 parity mismatch 處理）
            from coincurve import PrivateKey as CPrivateKey
            privkey_bytes = bytes.fromhex(private_key.to_hex())
            _sk = CPrivateKey(privkey_bytes)
            _n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
            _neg = (_n - int.from_bytes(privkey_bytes, 'big')).to_bytes(32, 'big')
            decrypted = ecies_decrypt(_neg.hex(), ciphertext)
            result = decrypted.decode('utf-8')
        
        assert result == test_message

    def test_covenant_script_structure_validation(self):
        """測試 covenant script 結構驗證"""
        
        # 模擬有效的 covenant script 開頭（IF-ELSE 結構）
        OP_IF = 0x63
        OP_ELSE = 0x67
        OP_ENDIF = 0x68
        
        valid_script_start = bytes([OP_IF])
        assert valid_script_start[0] == OP_IF
        
        # 檢查 script 必須包含 IF-ELSE-ENDIF 結構
        def has_covenant_structure(script_bytes):
            """檢查是否包含基本的 covenant 結構"""
            if not isinstance(script_bytes, bytes):
                return False
            
            has_if = OP_IF in script_bytes
            has_else = OP_ELSE in script_bytes
            has_endif = OP_ENDIF in script_bytes
            
            return has_if and has_else and has_endif
        
        # 有效結構
        valid_script = bytes([OP_IF, 0x14, *([0xab] * 20), OP_ELSE, 0x21, *([0xcd] * 33), OP_ENDIF])
        assert has_covenant_structure(valid_script)
        
        # 無效結構
        invalid_scripts = [
            b"",
            bytes([OP_IF, OP_ENDIF]),  # 缺少 ELSE
            bytes([OP_ELSE, OP_ENDIF]),  # 缺少 IF
            bytes([OP_IF, OP_ELSE]),    # 缺少 ENDIF
        ]
        
        for script in invalid_scripts:
            assert not has_covenant_structure(script)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])