#!/usr/bin/env python3
"""
💧 tKAS Faucet Server
Whisper Covenant 測試幣水龍頭

用法：
  python3 faucet_server.py --port 18805

API:
  POST /faucet         — 領取 tKAS（JSON: {"address": "kaspatest:qq..."}）
  GET  /faucet/status  — 查看發放統計

by Nami 🌊
"""

import argparse
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread

logger = logging.getLogger(__name__)

# === 設定 ===
WALLET_FILE = Path("/home/ymchang/clawd/.secrets/testnet-wallet.json")
LOG_FILE = Path(__file__).parent / "faucet_log.json"
RPC_URL = "ws://127.0.0.1:17210"
NETWORK_ID = "testnet-12"

DAILY_LIMIT_SOMPI = 50_0000_0000  # 50 tKAS per address per day
DEFAULT_AMOUNT_SOMPI = 5_0000_0000  # 5 tKAS per request
MIN_FEE = 5000

ALLOWED_ORIGINS = [
    "https://ryansoq.github.io",
    "https://whisper.openclaw-alpha.com",
    "http://localhost",
    "http://127.0.0.1",
]

# === 日誌管理 ===

def load_log() -> dict:
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            return json.load(f)
    return {"records": [], "daily": {}}

def save_log(log_data: dict):
    with open(LOG_FILE, "w") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_daily_total(log_data: dict, address: str) -> int:
    """取得某地址今天已領取的 sompi"""
    key = today_key()
    daily = log_data.get("daily", {}).get(key, {})
    return daily.get(address, 0)

def record_dispense(log_data: dict, address: str, amount: int, tx_id: str):
    key = today_key()
    if "daily" not in log_data:
        log_data["daily"] = {}
    if key not in log_data["daily"]:
        log_data["daily"][key] = {}
    log_data["daily"][key][address] = log_data["daily"][key].get(address, 0) + amount

    log_data["records"].append({
        "time": datetime.now(timezone.utc).isoformat(),
        "address": address,
        "amount_sompi": amount,
        "amount_tkas": amount / 1e8,
        "tx_id": tx_id,
    })
    save_log(log_data)

# === Kaspa 轉帳 ===

async def send_tkas(address: str, amount_sompi: int) -> str:
    """發送 tKAS 到指定地址"""
    from kaspa import (
        RpcClient, PrivateKey, Address, PaymentOutput,
        create_transaction, sign_transaction
    )

    wallet = json.loads(WALLET_FILE.read_text())
    pk = PrivateKey(wallet["private_key"])
    sender_addr = Address(wallet["address"])
    recipient_addr = Address(address)

    client = RpcClient(url=RPC_URL, network_id=NETWORK_ID)
    await client.connect()

    try:
        utxo_response = await client.get_utxos_by_addresses(
            {"addresses": [wallet["address"]]}
        )
        entries = utxo_response.get("entries", [])
        if not entries:
            raise Exception("Faucet 錢包沒有 UTXO")

        # 找合適的 UTXO
        suitable = [
            e for e in entries
            if e["utxoEntry"]["amount"] > amount_sompi + MIN_FEE * 2
            and not e["utxoEntry"].get("isCoinbase", False)
        ]
        if not suitable:
            suitable = [
                e for e in entries
                if e["utxoEntry"]["amount"] > amount_sompi + MIN_FEE * 2
            ]
        if not suitable:
            raise Exception("Faucet 錢包餘額不足")

        entry = min(suitable, key=lambda e: e["utxoEntry"]["amount"])
        utxo_amount = entry["utxoEntry"]["amount"]

        change = utxo_amount - amount_sompi - MIN_FEE
        outputs = [PaymentOutput(recipient_addr, amount_sompi)]
        if change > 0:
            outputs.append(PaymentOutput(sender_addr, change))

        tx = create_transaction(
            utxo_entry_source=[entry],
            outputs=outputs,
            priority_fee=0,
            payload=json.dumps({"faucet": True, "to": address}).encode("utf-8"),
        )
        signed_tx = sign_transaction(tx, [pk], False)
        result = await client.submit_transaction(
            {"transaction": signed_tx, "allow_orphan": False}
        )
        return result.get("transactionId", str(result))
    finally:
        await client.disconnect()

# === HTTP Handler ===

class FaucetHandler(BaseHTTPRequestHandler):

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if any(origin.startswith(o) for o in ALLOWED_ORIGINS):
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0])
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/faucet/status":
            self._handle_status()
        elif self.path == "/faucet" or self.path == "/faucet/":
            self._serve_faucet_page()
        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/faucet" or self.path == "/faucet/":
            self._handle_faucet()
        else:
            self._json_response(404, {"error": "Not found"})

    def _serve_faucet_page(self):
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>💧 tKAS Faucet</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a2e;color:#e0e0e0;font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#16213e;border:1px solid #30363d;border-radius:16px;padding:40px;max-width:500px;width:90%}
h1{color:#00ced1;margin-bottom:8px;font-size:1.8rem}
p{color:#a0a0a0;margin-bottom:24px}
input{width:100%;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e0e0e0;font-size:1rem;margin-bottom:16px;font-family:monospace}
input:focus{outline:none;border-color:#00ced1}
button{width:100%;padding:12px;background:#00ced1;color:#1a1a2e;border:none;border-radius:8px;font-size:1.1rem;font-weight:700;cursor:pointer}
button:hover{background:#00b4d8}
button:disabled{background:#555;cursor:not-allowed}
#result{margin-top:16px;padding:12px;border-radius:8px;display:none}
.ok{background:rgba(0,230,118,.1);border:1px solid #00e676;color:#00e676}
.err{background:rgba(255,107,107,.1);border:1px solid #ff6b6b;color:#ff6b6b}
a{color:#00ced1}
</style></head><body>
<div class="card">
<h1>💧 tKAS Faucet</h1>
<p>輸入你的 Kaspa Testnet 地址，免費領取 5 tKAS！<br>每個地址每天最多 50 tKAS。</p>
<input id="addr" placeholder="kaspatest:qq..." autocomplete="off">
<button id="btn" onclick="claim()">領取 tKAS</button>
<div id="result"></div>
<p style="margin-top:24px;font-size:.85rem">
  📖 <a href="https://ryansoq.github.io/Nami_backpack/projects/whisper-covenant/docs/wallet-guide">開錢包教學</a> ·
  🌊 <a href="https://ryansoq.github.io/Nami_backpack/projects/whisper-covenant/docs/">Whisper Covenant</a>
</p>
</div>
<script>
async function claim(){
  const addr=document.getElementById('addr').value.trim();
  const btn=document.getElementById('btn');
  const res=document.getElementById('result');
  if(!addr){res.className='err';res.style.display='block';res.textContent='請輸入地址';return}
  btn.disabled=true;btn.textContent='發送中...';
  try{
    const r=await fetch('/faucet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:addr})});
    const d=await r.json();
    if(d.success){res.className='ok';res.textContent='✅ '+d.message+' TX: '+d.tx_id}
    else{res.className='err';res.textContent='❌ '+d.error}
    res.style.display='block';
  }catch(e){res.className='err';res.style.display='block';res.textContent='❌ 網路錯誤：'+e.message}
  btn.disabled=false;btn.textContent='領取 tKAS';
}
document.getElementById('addr').addEventListener('keydown',e=>{if(e.key==='Enter')claim()});
</script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _handle_faucet(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            return self._json_response(400, {"error": "Invalid JSON"})

        address = body.get("address", "").strip()

        # 驗證地址格式
        if not address.startswith("kaspatest:"):
            return self._json_response(400, {
                "error": "地址必須是 kaspatest: 開頭（Testnet 地址）"
            })

        if len(address) < 30:
            return self._json_response(400, {"error": "地址格式不正確"})

        # 檢查每日限額
        log_data = load_log()
        daily_total = get_daily_total(log_data, address)
        if daily_total >= DAILY_LIMIT_SOMPI:
            return self._json_response(429, {
                "error": f"今日額度已用完（已領 {daily_total/1e8:.1f} tKAS，上限 {DAILY_LIMIT_SOMPI/1e8:.0f} tKAS）",
                "daily_used": daily_total / 1e8,
                "daily_limit": DAILY_LIMIT_SOMPI / 1e8,
            })

        # 計算本次可領金額
        remaining = DAILY_LIMIT_SOMPI - daily_total
        amount = min(DEFAULT_AMOUNT_SOMPI, remaining)

        # 發送
        try:
            tx_id = asyncio.get_event_loop().run_until_complete(
                send_tkas(address, amount)
            )
        except Exception as e:
            logger.exception("Faucet send failed")
            return self._json_response(500, {"error": f"發送失敗：{e}"})

        # 記錄
        record_dispense(log_data, address, amount, tx_id)
        logger.info(f"💧 Dispensed {amount/1e8:.1f} tKAS → {address} TX: {tx_id}")

        self._json_response(200, {
            "success": True,
            "tx_id": tx_id,
            "amount": f"{amount/1e8:.1f} tKAS",
            "message": f"已發送 {amount/1e8:.1f} tKAS 到你的地址！",
            "daily_used": (daily_total + amount) / 1e8,
            "daily_limit": DAILY_LIMIT_SOMPI / 1e8,
        })

    def _handle_status(self):
        log_data = load_log()
        records = log_data.get("records", [])
        today = today_key()
        today_records = [r for r in records if r["time"].startswith(today)]

        total_dispensed = sum(r["amount_sompi"] for r in records)
        today_dispensed = sum(r["amount_sompi"] for r in today_records)
        unique_addresses = len(set(r["address"] for r in records))

        self._json_response(200, {
            "status": "running",
            "total_dispensed_tkas": total_dispensed / 1e8,
            "total_requests": len(records),
            "unique_addresses": unique_addresses,
            "today": {
                "date": today,
                "dispensed_tkas": today_dispensed / 1e8,
                "requests": len(today_records),
            },
            "daily_limit_per_address_tkas": DAILY_LIMIT_SOMPI / 1e8,
            "default_amount_tkas": DEFAULT_AMOUNT_SOMPI / 1e8,
        })

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description="💧 tKAS Faucet Server")
    parser.add_argument("--port", type=int, default=18805, help="Port (default: 18805)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not WALLET_FILE.exists():
        logger.error(f"❌ 錢包檔案不存在: {WALLET_FILE}")
        return

    server = HTTPServer((args.host, args.port), FaucetHandler)
    logger.info(f"💧 tKAS Faucet 啟動！ http://{args.host}:{args.port}/faucet")
    logger.info(f"   每日限額: {DAILY_LIMIT_SOMPI/1e8:.0f} tKAS/地址")
    logger.info(f"   每次發放: {DEFAULT_AMOUNT_SOMPI/1e8:.1f} tKAS")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Faucet 停止")
        server.server_close()


if __name__ == "__main__":
    main()
