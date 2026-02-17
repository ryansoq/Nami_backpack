"""
Kaspa Whisper - 發送訊息（加密或明文）
Usage:
  python3 send_whisper.py <to> "<message>" --key <privkey>              # 加密密語
  python3 send_whisper.py <to> "<message>" --from <name>                # 加密密語
  python3 send_whisper.py <to> "<message>" --key <privkey> --plain      # 明文訊息
  python3 send_whisper.py <to> "<message>" --from <name> --plain        # 明文訊息
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

async def send_whisper(to_name: str, message: str, privkey_hex: str, from_addr: str, plain: bool = False):
    contacts = load_contacts()

    # Resolve receiver
    to = contacts.get(to_name.lower())
    if not to:
        print(f"❌ 通訊錄找不到 '{to_name}'，可用: {', '.join(contacts.keys())}")
        return

    if plain:
        # 明文模式
        print(f"📤 發送明文訊息給 {to['name']}")
        print(f"📨 訊息: {message}")
        payload = json.dumps({
            "v": 1,
            "t": "message",
            "d": message,
            "a": {"from": from_addr}
        }, separators=(',', ':'), ensure_ascii=False).encode()
    else:
        # 加密模式
        if not to.get('pubkey'):
            print(f"❌ {to['name']} 沒有公鑰，無法加密")
            return
        print(f"📤 發送加密密語給 {to['name']}")
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
    tx_id = await submit_transaction(signed, allow_orphan=False)

    print(f"\n✅ 密語已發送！")
    print(f"   TX: {tx_id}")
    print(f"   → {to['name']}: 0.2 KAS + 加密訊息")
    print(f"   https://explorer-tn10.kaspa.org/txs/{tx_id}")
    print(f"\n📋 對方解密指令:")
    print(f"   python3 decode_whisper.py {tx_id} --key <私鑰>")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage:")
        print('  python3 send_whisper.py <to> "<message>" --key <privkey>')
        print('  python3 send_whisper.py <to> "<message>" --from <name>')
        print(f"\n通訊錄: {', '.join(load_contacts().keys())}")
        sys.exit(1)

    to_name = sys.argv[1]
    message = sys.argv[2]

    contacts = load_contacts()

    plain = '--plain' in sys.argv
    args = [a for a in sys.argv[3:] if a != '--plain']

    if args[0] == '--key':
        privkey = args[1]
        pk = PrivateKey(privkey)
        addr = pk.to_public_key().to_address('testnet').to_string()
        asyncio.run(send_whisper(to_name, message, privkey, addr, plain))
    elif args[0] == '--from':
        from_name = args[1].lower()
        c = contacts.get(from_name)
        if not c or 'privkey' not in c:
            print(f"❌ '{from_name}' 沒有私鑰")
            sys.exit(1)
        asyncio.run(send_whisper(to_name, message, c['privkey'], c['address'], plain))
    else:
        print("❌ 請用 --key <privkey> 或 --from <name>")
