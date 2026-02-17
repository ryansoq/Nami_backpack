"""
Kaspa Whisper - 解密密語 + 自動退還 0.2 tKAS
Usage: 
  python3 decode_whisper.py <tx_id> <name>          # 用通訊錄的身份
  python3 decode_whisper.py <tx_id> --key <privkey>  # 直接給私鑰
"""
import asyncio, json, sys, os

sys.path.insert(0, '/home/ymchang/nami-backpack/projects/nami-kaspa-bot')

from ecies import decrypt
from kaspa import PrivateKey, Address, PaymentOutput, create_transaction, sign_transaction
from rpc_manager import get_utxos, submit_transaction

TX_FEE = 50000
REFUND_AMOUNT = 20000000  # 0.2 tKAS
CONTACTS_FILE = os.path.join(os.path.dirname(__file__), 'contacts.json')

def load_contacts():
    with open(CONTACTS_FILE) as f:
        return json.load(f)

async def decode_and_refund(tx_id: str, privkey_hex: str, my_addr: str = None):
    # 1. 從鏈上取得 TX
    print(f"🔍 讀取 TX: {tx_id}")
    import httpx
    async with httpx.AsyncClient() as http:
        resp = await http.get(f"https://api-tn10.kaspa.org/transactions/{tx_id}")
        tx = resp.json()
    
    payload_hex = tx.get('payload', '')
    if not payload_hex:
        print("❌ 沒有 payload")
        return
    
    payload = json.loads(bytes.fromhex(payload_hex))
    msg_type = payload.get('type') or payload.get('t')
    if msg_type != 'whisper':
        print(f"❌ 不是密語 (type={msg_type})")
        return
    
    # Support both formats: {from, enc} and {a:{from}, d}
    sender = payload.get('from') or payload.get('a', {}).get('from', '')
    
    # 查通訊錄找發送者名字
    contacts = load_contacts()
    sender_name = sender
    for name, info in contacts.items():
        if info['address'] == sender:
            sender_name = info['name']
            break
    
    print(f"📤 來自: {sender_name}")
    
    # 2. 解密
    enc_hex = payload.get('enc') or payload.get('d', '')
    encrypted = bytes.fromhex(enc_hex)
    try:
        message = decrypt(privkey_hex, encrypted).decode('utf-8')
        print(f"\n💌 密語: {message}\n")
    except Exception as e:
        print(f"❌ 解密失敗（不是給你的？）: {e}")
        return
    
    # 3. 退還 0.2 tKAS
    if not sender:
        print("⚠️ 無發送者地址，跳過退款")
        return
    
    if not my_addr:
        pk = PrivateKey(privkey_hex)
        my_addr = pk.to_public_key().to_address('testnet').to_string()
    
    print(f"💸 退還 0.2 tKAS → {sender_name}")
    entries = await get_utxos(my_addr)
    entries.sort(key=lambda e: e["utxoEntry"]["amount"], reverse=True)
    
    selected = []
    total = 0
    for e in entries:
        selected.append(e)
        total += e["utxoEntry"]["amount"]
        if total >= REFUND_AMOUNT + TX_FEE + 1000:
            break
    
    if total < REFUND_AMOUNT + TX_FEE:
        print(f"❌ 餘額不足: {total/1e8:.4f} tKAS")
        return
    
    change = total - REFUND_AMOUNT - TX_FEE
    outputs = [PaymentOutput(Address(sender), REFUND_AMOUNT)]
    if change > 0:
        outputs.append(PaymentOutput(Address(my_addr), change))
    
    import time
    ack_payload = json.dumps({
        "v": 1,
        "t": "signal",
        "d": "已讀",
        "a": {
            "from": my_addr,
            "ref": tx_id,
            "time": int(time.time())
        }
    }, separators=(',',':'), ensure_ascii=False).encode()
    
    pk_obj = PrivateKey(privkey_hex)
    rtx = create_transaction(utxo_entry_source=selected, outputs=outputs, priority_fee=TX_FEE, payload=ack_payload)
    signed = sign_transaction(rtx, [pk_obj], False)
    refund_tx = await submit_transaction(signed, allow_orphan=False)
    
    print(f"✅ 已退還 0.2 tKAS！TX: {refund_tx}")
    print(f"https://explorer-tn10.kaspa.org/txs/{refund_tx}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 decode_whisper.py <tx_id> <name>          # 用通訊錄")
        print("  python3 decode_whisper.py <tx_id> --key <privkey>  # 直接給私鑰")
        sys.exit(1)
    
    tx_id = sys.argv[1]
    
    if sys.argv[2] == '--key':
        privkey = sys.argv[3]
        asyncio.run(decode_and_refund(tx_id, privkey))
    else:
        # 從通訊錄找
        name = sys.argv[2].lower()
        contacts = load_contacts()
        if name not in contacts:
            print(f"❌ 通訊錄找不到 '{name}'，可用: {', '.join(contacts.keys())}")
            sys.exit(1)
        c = contacts[name]
        if 'privkey' not in c:
            print(f"❌ {name} 的通訊錄沒有私鑰")
            sys.exit(1)
        asyncio.run(decode_and_refund(tx_id, c['privkey'], c['address']))
