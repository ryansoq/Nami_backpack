"""
Kaspa Whisper - encode（打包訊息）

加密或明文打包 + 簽名 TX，產出 signed raw TX hex。
可搭配 Web API broadcast 上鏈，或本地直接提交。

Usage:
  python3 encode_whisper.py <to> "<message>" --key <privkey>              # 密文（預設）
  python3 encode_whisper.py <to> "<message>" --key <privkey> --plain      # 明文
  python3 encode_whisper.py <to> "<message>" --from <name>                # 密文（通訊錄）
  python3 encode_whisper.py <to> "<message>" --from <name> --plain        # 明文（通訊錄）
  
  # 只產出 signed TX hex，不上鏈（搭配 Web API 使用）
  python3 encode_whisper.py <to> "<message>" --key <privkey> --raw
"""
import asyncio, json, sys, os, time

sys.path.insert(0, '/home/ymchang/nami-backpack/projects/nami-kaspa-bot')

from ecies import encrypt
from kaspa import PrivateKey, Address, PaymentOutput, create_transaction, sign_transaction
from rpc_manager import get_utxos, submit_transaction

WHISPER_AMOUNT = 20000000  # 0.2 KAS
TX_FEE = 50000
CONTACTS_FILE = os.path.join(os.path.dirname(__file__), 'contacts.json')

def load_contacts():
    with open(CONTACTS_FILE) as f:
        return json.load(f)

async def encode_whisper(to_name: str, message: str, privkey_hex: str, from_addr: str, 
                         plain: bool = False, raw_only: bool = False):
    contacts = load_contacts()

    # Resolve receiver
    to = contacts.get(to_name.lower())
    if not to:
        print(f"❌ 通訊錄找不到 '{to_name}'，可用: {', '.join(contacts.keys())}")
        return

    if not to.get('pubkey'):
        print(f"❌ {to['name']} 沒有公鑰")
        return

    if plain:
        # 明文模式（仍需對方公鑰參數，但不用於加密）
        print(f"📤 打包明文訊息給 {to['name']}")
        print(f"📨 訊息: {message}")
        payload = json.dumps({
            "v": 1,
            "t": "message",
            "d": message,
            "a": {"from": from_addr}
        }, separators=(',', ':'), ensure_ascii=False).encode()
    else:
        # 密文模式
        print(f"📤 打包加密密語給 {to['name']}")
        print(f"📝 訊息: {message}")
        encrypted = encrypt(to['pubkey'], message.encode('utf-8'))
        print(f"🔐 加密: {len(encrypted)} bytes")
        payload = json.dumps({
            "v": 1,
            "t": "whisper",
            "d": encrypted.hex(),
            "a": {"from": from_addr}
        }, separators=(',', ':'), ensure_ascii=False).encode()

    print(f"📦 Payload: {len(payload)} bytes")

    # Get UTXOs
    pk = PrivateKey(privkey_hex)
    entries = await get_utxos(from_addr)
    if not entries:
        print("❌ 錢包沒有餘額")
        return

    entries.sort(key=lambda e: e["utxoEntry"]["amount"], reverse=True)

    # Select UTXO
    selected = []
    total = 0
    for e in entries:
        selected.append(e)
        total += e["utxoEntry"]["amount"]
        if total >= WHISPER_AMOUNT + TX_FEE + 1000:
            break

    if total < WHISPER_AMOUNT + TX_FEE:
        print(f"❌ 餘額不足: {total/1e8:.4f} KAS")
        return

    change = total - WHISPER_AMOUNT - TX_FEE
    outputs = [PaymentOutput(Address(to['address']), WHISPER_AMOUNT)]
    if change > 0:
        outputs.append(PaymentOutput(Address(from_addr), change))

    tx = create_transaction(
        utxo_entry_source=selected,
        outputs=outputs,
        priority_fee=TX_FEE,
        payload=payload
    )
    signed = sign_transaction(tx, [pk], False)

    if raw_only:
        # 只輸出 signed TX hex，搭配 Web API 使用
        print(f"\n📋 Signed TX (raw hex):")
        print(signed.to_json())
        print(f"\n💡 用 Web API 廣播:")
        print(f"   curl -X POST https://api.openclaw-alpha.com/whisper/broadcast \\")
        print(f"     -H 'Content-Type: application/json' \\")
        print(f"     -d '{{\"signed_tx\": \"...\"}}'")
        return

    # 直接上鏈
    tx_id = await submit_transaction(signed, allow_orphan=False)

    print(f"\n✅ 密語已發送！")
    print(f"   TX: {tx_id}")
    print(f"   → {to['name']}: 0.2 KAS + {'明文' if plain else '加密'}訊息")
    print(f"   https://explorer-tn10.kaspa.org/txs/{tx_id}")
    print(f"\n📋 對方解密指令:")
    print(f"   python3 decode_whisper.py {tx_id} --key <私鑰>")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage:")
        print('  python3 encode_whisper.py <to> "<message>" --key <privkey>')
        print('  python3 encode_whisper.py <to> "<message>" --from <name>')
        print('  加 --plain 為明文，加 --raw 只產出不上鏈')
        print(f"\n通訊錄: {', '.join(load_contacts().keys())}")
        sys.exit(1)

    to_name = sys.argv[1]
    message = sys.argv[2]

    contacts = load_contacts()

    plain = '--plain' in sys.argv
    raw_only = '--raw' in sys.argv
    args = [a for a in sys.argv[3:] if a not in ('--plain', '--raw')]

    if args[0] == '--key':
        privkey = args[1]
        pk = PrivateKey(privkey)
        addr = pk.to_public_key().to_address('testnet').to_string()
        asyncio.run(encode_whisper(to_name, message, privkey, addr, plain, raw_only))
    elif args[0] == '--from':
        from_name = args[1].lower()
        c = contacts.get(from_name)
        if not c or 'privkey' not in c:
            print(f"❌ '{from_name}' 沒有私鑰")
            sys.exit(1)
        asyncio.run(encode_whisper(to_name, message, c['privkey'], c['address'], plain, raw_only))
    else:
        print("❌ 請用 --key <privkey> 或 --from <name>")
