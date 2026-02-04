#!/usr/bin/env python3
"""
🌊 Nami Kaspa Bot - TG 店面機器人
================================

功能：
- /start - 歡迎訊息
- /faucet <地址> - 領 tKAS（每人每天限 50 tKAS）
- /balance - 查水龍頭餘額
- /status - 今日發放統計

作者：Nami 🌊
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ═══════════════════════════════════════════════════════════════════════════════
# 設定
# ═══════════════════════════════════════════════════════════════════════════════

# Bot Token（從環境變數或檔案讀取）
TOKEN_FILE = Path(__file__).parent.parent.parent.parent / "clawd/.secrets/nami-kaspa-bot.json"
DATA_DIR = Path(__file__).parent / "data"
FAUCET_RECORD_FILE = DATA_DIR / "faucet_records.json"
USER_DB_FILE = DATA_DIR / "users.json"

# 水龍頭設定
DAILY_LIMIT_PER_USER = 50   # 每人每天最多領 50 tKAS
AMOUNT_PER_REQUEST = 10     # 每次發 10 tKAS

# Testnet 錢包（水龍頭專用 + 輪盤彩池）
FAUCET_WALLET_FILE = Path(__file__).parent.parent.parent.parent / "clawd/.secrets/testnet-wallet.json"

# 輪盤設定
ROULETTE_BETS_FILE = DATA_DIR / "roulette_bets.json"
ROULETTE_PINS_FILE = DATA_DIR / "roulette_pins.json"
ROULETTE_HISTORY_FILE = DATA_DIR / "roulette_history.json"

# 輪盤顏色定義
RED_NUMBERS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
BLACK_NUMBERS = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}
GREEN_NUMBERS = {0, 37}  # 37 代表 00

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 資料管理
# ═══════════════════════════════════════════════════════════════════════════════

def load_token() -> str:
    """載入 Bot Token"""
    with open(TOKEN_FILE, 'r') as f:
        data = json.load(f)
        return data['token']

def load_faucet_wallet() -> dict:
    """載入水龍頭錢包"""
    with open(FAUCET_WALLET_FILE, 'r') as f:
        return json.load(f)

def load_records() -> dict:
    """載入發放紀錄"""
    if FAUCET_RECORD_FILE.exists():
        with open(FAUCET_RECORD_FILE, 'r') as f:
            return json.load(f)
    return {"records": [], "daily_stats": {}}

def load_users() -> dict:
    """載入用戶資料庫"""
    if USER_DB_FILE.exists():
        with open(USER_DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users: dict):
    """儲存用戶資料庫"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_DB_FILE, 'w') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def get_user_address(identifier: str) -> str | None:
    """根據 user_id 或 @username 查找地址"""
    users = load_users()
    # 如果是 @username 格式
    if identifier.startswith('@'):
        username = identifier[1:].lower()
        for uid, data in users.items():
            if data.get('username', '').lower() == username:
                return data.get('address')
    # 如果是 user_id
    elif identifier.isdigit():
        if identifier in users:
            return users[identifier].get('address')
    return None

def register_user(user_id: int, username: str, address: str):
    """註冊用戶地址"""
    users = load_users()
    users[str(user_id)] = {
        'username': username,
        'address': address,
        'created_at': datetime.now().isoformat()
    }
    save_users(users)

def save_records(records: dict):
    """儲存發放紀錄"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FAUCET_RECORD_FILE, 'w') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

def get_user_today_amount(records: dict, user_id: int) -> float:
    """取得用戶今天已領取的數量（防洗地址）"""
    today = datetime.now().strftime('%Y-%m-%d')
    total = 0
    for record in records.get("records", []):
        if record.get("user_id") == user_id and record.get("date") == today:
            total += record.get("amount", 0)
    return total

# ═══════════════════════════════════════════════════════════════════════════════
# 輪盤資料管理
# ═══════════════════════════════════════════════════════════════════════════════

def load_roulette_bets() -> dict:
    """載入當前輪盤下注"""
    if ROULETTE_BETS_FILE.exists():
        with open(ROULETTE_BETS_FILE, 'r') as f:
            return json.load(f)
    return {"target_block": None, "bets": []}

def save_roulette_bets(data: dict):
    """儲存輪盤下注"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ROULETTE_BETS_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_roulette_pins() -> dict:
    """載入 PIN 碼對應表"""
    if ROULETTE_PINS_FILE.exists():
        with open(ROULETTE_PINS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_roulette_pins(data: dict):
    """儲存 PIN 碼對應表"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ROULETTE_PINS_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_private_key_from_pin_or_hex(user_id: int, pin_or_key: str) -> str | None:
    """從 PIN 或私鑰字串取得私鑰"""
    # 如果是 PIN（4-6 位數字）
    if pin_or_key.isdigit() and 4 <= len(pin_or_key) <= 6:
        pins = load_roulette_pins()
        user_pins = pins.get(str(user_id), {})
        return user_pins.get(pin_or_key)
    # 如果是私鑰（64 位 hex）
    elif len(pin_or_key) == 64:
        return pin_or_key
    return None

def verify_private_key(private_key_hex: str) -> str | None:
    """驗證私鑰並返回對應地址"""
    try:
        from kaspa import PrivateKey
        pk = PrivateKey(private_key_hex)
        address = pk.to_address("testnet")
        return address.to_string()
    except Exception as e:
        logger.error(f"Invalid private key: {e}")
        return None

def get_roulette_result(block_hash: str) -> int:
    """從區塊 hash 計算輪盤結果（0-37，37=00）"""
    # 整個 hash 轉整數，mod 38，簡單透明
    hash_int = int(block_hash, 16)
    return hash_int % 38

def get_bet_color(number: int) -> str:
    """取得數字對應的顏色"""
    if number in RED_NUMBERS:
        return "🔴 紅"
    elif number in BLACK_NUMBERS:
        return "⚫ 黑"
    else:
        return "🟢 綠"

def calculate_winnings(bet_type: str, bet_amount: float, result: int) -> float:
    """計算獎金"""
    bet_type = bet_type.lower()
    
    # 顏色下注
    if bet_type in ['red', '紅', '红']:
        if result in RED_NUMBERS:
            return bet_amount * 2  # 1:1 賠率，返還本金+獎金
        return 0
    elif bet_type in ['black', '黑']:
        if result in BLACK_NUMBERS:
            return bet_amount * 2
        return 0
    elif bet_type in ['green', '綠', '绿', '0', '00']:
        if result in GREEN_NUMBERS:
            return bet_amount * 18  # 17:1 賠率
        return 0
    
    # 數字下注
    try:
        bet_num = int(bet_type)
        if bet_num == result or (bet_type == '00' and result == 37):
            return bet_amount * 36  # 35:1 賠率
        return 0
    except ValueError:
        return 0

# ═══════════════════════════════════════════════════════════════════════════════
# Kaspa 交易（簡化版，之後可以優化）
# ═══════════════════════════════════════════════════════════════════════════════

async def send_tkas(to_address: str, amount: float) -> str | None:
    """
    發送 tKAS（回傳 TX ID 或 None）
    
    TODO: 實作真正的交易發送
    目前先回傳 mock TX ID
    """
    try:
        from kaspa import (
            RpcClient, Resolver, PrivateKey, Address,
            create_transactions, PaymentOutput, kaspa_to_sompi
        )
        
        wallet = load_faucet_wallet()
        private_key = PrivateKey(wallet['private_key'])
        from_address = wallet['address']
        
        # 連接 testnet
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            # 獲取 UTXO
            utxos_result = await client.get_utxos_by_addresses(
                {"addresses": [from_address]}
            )
            utxos = utxos_result.get("entries", [])[:100]
            
            if not utxos:
                logger.error("No UTXOs available")
                return None
            
            # 創建交易
            outputs = [PaymentOutput(Address(to_address), kaspa_to_sompi(amount))]
            result = create_transactions(
                "testnet-10",
                utxos,
                Address(from_address),
                outputs,
                None, None,
                kaspa_to_sompi(0.0001)  # 手續費
            )
            
            # 簽名並提交
            for tx in result["transactions"]:
                tx.sign([private_key])
                tx_id = await tx.submit(client)
                return tx_id
                
        finally:
            await client.disconnect()
            
    except Exception as e:
        logger.error(f"Send tKAS error: {e}")
        return None

async def get_faucet_balance() -> float | None:
    """查詢水龍頭餘額"""
    try:
        from kaspa import RpcClient
        
        wallet = load_faucet_wallet()
        address = wallet['address']
        
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            result = await client.get_balance_by_address({"address": address})
            balance_sompi = result.get("balance", 0)
            return balance_sompi / 100_000_000
        finally:
            await client.disconnect()
            
    except Exception as e:
        logger.error(f"Get balance error: {e}")
        return None

# 公告群設定檔
ANNOUNCE_GROUP_FILE = DATA_DIR / "announce_group.json"

def load_announce_group() -> int | None:
    """載入公告群 ID"""
    if ANNOUNCE_GROUP_FILE.exists():
        with open(ANNOUNCE_GROUP_FILE, 'r') as f:
            data = json.load(f)
            return data.get("chat_id")
    return None

def save_announce_group(chat_id: int):
    """儲存公告群 ID"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANNOUNCE_GROUP_FILE, 'w') as f:
        json.dump({"chat_id": chat_id}, f)

# ═══════════════════════════════════════════════════════════════════════════════
# Bot 指令
# ═══════════════════════════════════════════════════════════════════════════════

async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示聊天室 ID"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    await update.message.reply_text(
        f"📍 Chat ID: `{chat_id}`\n"
        f"📝 Type: {chat_type}",
        parse_mode='Markdown'
    )

async def set_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """設定公告群（在群裡使用）"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == 'private':
        await update.message.reply_text("⚠️ 請在群組中使用此指令")
        return
    
    # 儲存群 ID
    save_announce_group(chat.id)
    
    await update.message.reply_text(
        f"✅ 已設定此群為輪盤公告群！\n\n"
        f"下注結果將公布在這裡 🎰"
    )
    logger.info(f"Announce group set to {chat.id} by {user.username}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /start 或 /nami 指令"""
    welcome_msg = """🌊 *Welcome to Nami Kaspa Bot!*

我是 Nami 的 Kaspa 服務機器人 🦞

*可用指令：*
• `/nami_faucet <地址>` — 領取測試網 tKAS
• `/nami_balance` — 查看水龍頭餘額
• `/nami_status` — 今日發放統計

*關於 tKAS：*
tKAS 是 Kaspa 測試網代幣，沒有實際價值。
用於學習、測試、實驗 — 放心玩！

*關於 Kaspa：*
⚡ 最快的 PoW 區塊鏈（10 blocks/sec）
🔗 BlockDAG 技術
🛡️ 去中心化、無預挖

有問題歡迎來找 @NamiElf 聊天！✨
"""
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def faucet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /faucet 指令"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    address = None
    target_name = None  # 用於顯示
    
    if context.args:
        arg = context.args[0]
        
        # 如果是 @username 格式
        if arg.startswith('@'):
            address = get_user_address(arg)
            target_name = arg
            if not address:
                await update.message.reply_text(
                    f"❌ 找不到 {arg} 的錢包地址\n\n"
                    f"對方需要先用 `/nami_wallet` 創建錢包",
                    parse_mode='Markdown'
                )
                return
        # 如果是地址格式
        elif arg.startswith('kaspatest:'):
            address = arg
        else:
            await update.message.reply_text(
                "❌ 格式錯誤！\n\n"
                "用法：\n"
                "• `/nami_faucet kaspatest:qq...`\n"
                "• `/nami_faucet @username`\n"
                "• `/nami_faucet`（發到自己地址）",
                parse_mode='Markdown'
            )
            return
    else:
        # 沒有參數，查找自己的地址
        address = get_user_address(str(user_id))
        if not address:
            await update.message.reply_text(
                "❌ 你還沒有註冊地址！\n\n"
                "請先用 `/nami_wallet` 創建錢包\n"
                "或直接指定地址：`/nami_faucet kaspatest:qq...`",
                parse_mode='Markdown'
            )
            return
        target_name = f"@{username}"
    
    # 檢查用戶今日額度（防洗地址）
    records = load_records()
    today_amount = get_user_today_amount(records, user_id)
    
    if today_amount >= DAILY_LIMIT_PER_USER:
        await update.message.reply_text(
            f"⏳ 今天已達領取上限（{DAILY_LIMIT_PER_USER} tKAS）\n"
            "明天再來吧！🌊"
        )
        return
    
    # 發送 tKAS
    await update.message.reply_text("🔄 處理中...")
    
    amount = min(AMOUNT_PER_REQUEST, DAILY_LIMIT_PER_USER - today_amount)
    tx_id = await send_tkas(address, amount)
    
    if tx_id:
        # 記錄
        today = datetime.now().strftime('%Y-%m-%d')
        records["records"].append({
            "user_id": user_id,
            "username": username,
            "address": address,
            "amount": amount,
            "tx_id": tx_id,
            "date": today,
            "timestamp": datetime.now().isoformat()
        })
        
        # 更新每日統計
        if today not in records.get("daily_stats", {}):
            records["daily_stats"][today] = {"count": 0, "total": 0}
        records["daily_stats"][today]["count"] += 1
        records["daily_stats"][today]["total"] += amount
        
        save_records(records)
        
        await update.message.reply_text(
            f"✅ *發送成功！*\n\n"
            f"💰 數量：{amount} tKAS\n"
            f"📍 地址：`{address[:20]}...`\n"
            f"🔗 TX：`{tx_id[:20]}...`\n\n"
            f"[查看交易](https://explorer-tn10.kaspa.org/txs/{tx_id})",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        logger.info(f"Faucet: {username} ({user_id}) -> {address} : {amount} tKAS")
    else:
        await update.message.reply_text(
            "❌ 發送失敗，請稍後再試\n"
            "如果持續失敗，請聯繫 @NamiElf"
        )

async def get_address_balance(address: str) -> float | None:
    """查詢任意地址餘額"""
    try:
        from kaspa import RpcClient
        
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            result = await client.get_balance_by_address({"address": address})
            balance_sompi = result.get("balance", 0)
            return balance_sompi / 100_000_000
        finally:
            await client.disconnect()
            
    except Exception as e:
        logger.error(f"Get balance error for {address}: {e}")
        return None

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /balance 指令"""
    user = update.effective_user
    user_id = user.id
    
    address = None
    label = None
    
    if context.args:
        arg = context.args[0]
        
        # @username 格式
        if arg.startswith('@'):
            address = get_user_address(arg)
            label = arg
            if not address:
                await update.message.reply_text(
                    f"❌ 找不到 {arg} 的錢包地址",
                    parse_mode='Markdown'
                )
                return
        # 地址格式
        elif arg.startswith('kaspatest:'):
            address = arg
            label = f"`{arg[:25]}...`"
        # faucet 關鍵字
        elif arg.lower() == 'faucet':
            address = None  # 查水龍頭
        else:
            await update.message.reply_text(
                "用法：\n"
                "• `/nami_balance` — 水龍頭餘額\n"
                "• `/nami_balance @username` — 查用戶餘額\n"
                "• `/nami_balance kaspatest:...` — 查地址餘額",
                parse_mode='Markdown'
            )
            return
    
    await update.message.reply_text("🔄 查詢中...")
    
    if address:
        # 查詢指定地址
        bal = await get_address_balance(address)
        if bal is not None:
            await update.message.reply_text(
                f"💰 *錢包餘額*\n\n"
                f"👤 {label}\n"
                f"🌊 {bal:,.2f} tKAS",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ 查詢失敗，請稍後再試")
    else:
        # 查詢水龍頭餘額
        bal = await get_faucet_balance()
        if bal is not None:
            await update.message.reply_text(
                f"💰 *水龍頭餘額*\n\n"
                f"🌊 {bal:,.2f} tKAS\n\n"
                f"_餘額來自 Nami 的挖礦收益_",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ 查詢失敗，請稍後再試")

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /nami_wallet 指令 - 創建 testnet 錢包"""
    user = update.effective_user
    user_id = user.id
    
    try:
        from kaspa import Mnemonic, XPrv, PrivateKeyGenerator
        
        # 生成 12 字助記詞
        mnemonic = Mnemonic.random(12)
        seed = mnemonic.to_seed()
        xprv = XPrv(seed)
        xprv_str = xprv.to_string()
        
        # 生成地址
        key_gen = PrivateKeyGenerator(xprv_str, False, 0)
        private_key = key_gen.receive_key(0)
        address = private_key.to_address("testnet")
        
        # 取得私鑰字串（用於輪盤下注）
        private_key_hex = private_key.to_string()
        
        # 嘗試私訊用戶助記詞和私鑰
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔐 *你的 Testnet 錢包*\n\n"
                     f"📍 *地址：*\n`{address.to_string()}`\n\n"
                     f"🔑 *私鑰（輪盤下注用）：*\n`{private_key_hex}`\n\n"
                     f"📝 *助記詞：*\n```\n{mnemonic.phrase}\n```\n\n"
                     f"⚠️ *重要：*\n"
                     f"• 私鑰用於 `/bet` 下注\n"
                     f"• 可用 `/setpin` 設定 PIN 碼簡化\n"
                     f"• 這是 TESTNET，不要存真的 KAS！\n\n"
                     f"🎰 輪盤指令：`/bet red 10 私鑰`",
                parse_mode='Markdown'
            )
            
            # 先註冊用戶地址（確保即使後續失敗也有記錄）
            register_user(user_id, user.username or user.first_name, address.to_string())
            logger.info(f"Wallet created for {user.username} ({user_id}): {address.to_string()}")
            
            # 在原聊天室回覆（不顯示助記詞）
            await update.message.reply_text(
                f"✅ *Testnet 錢包已創建！*\n\n"
                f"📍 地址：\n`{address.to_string()}`\n\n"
                f"🔐 助記詞已私訊給你，請查收！\n\n"
                f"提示：用 `/nami_faucet` 領取 tKAS",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            # 無法私訊（用戶沒有先私聊過 Bot）
            logger.warning(f"Cannot DM user {user_id}: {e}")
            await update.message.reply_text(
                f"⚠️ *無法私訊你！*\n\n"
                f"請先私聊我一下 @Nami_Kaspa_Bot\n"
                f"然後再輸入 `/nami_wallet`\n\n"
                f"_（這樣我才能安全地把助記詞發給你）_",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Wallet creation error: {e}")
        await update.message.reply_text(
            "❌ 創建錢包失敗，請稍後再試\n"
            "如果持續失敗，請聯繫 @NamiElf"
        )

# ═══════════════════════════════════════════════════════════════════════════════
# 輪盤指令
# ═══════════════════════════════════════════════════════════════════════════════

async def recover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """從助記詞恢復私鑰"""
    user = update.effective_user
    user_id = user.id
    
    # 只允許私聊
    if update.effective_chat.type != 'private':
        await update.message.reply_text("⚠️ 請私聊我恢復錢包！")
        return
    
    if len(context.args) < 12:
        await update.message.reply_text(
            "🔐 *從助記詞恢復私鑰*\n\n"
            "用法：`/recover word1 word2 ... word12`\n\n"
            "請輸入你的 12 個助記詞（空格分隔）",
            parse_mode='Markdown'
        )
        return
    
    mnemonic_phrase = ' '.join(context.args[:12])
    
    try:
        from kaspa import Mnemonic, XPrv, PrivateKeyGenerator
        
        # 從助記詞恢復
        mnemonic = Mnemonic(mnemonic_phrase)
        seed = mnemonic.to_seed()
        xprv = XPrv(seed)
        xprv_str = xprv.to_string()
        
        # 生成私鑰和地址
        key_gen = PrivateKeyGenerator(xprv_str, False, 0)
        private_key = key_gen.receive_key(0)
        address = private_key.to_address("testnet")
        private_key_hex = private_key.to_string()
        
        await update.message.reply_text(
            f"✅ *錢包恢復成功！*\n\n"
            f"📍 *地址：*\n`{address.to_string()}`\n\n"
            f"🔑 *私鑰：*\n`{private_key_hex}`\n\n"
            f"⚠️ 請妥善保存私鑰！\n\n"
            f"🎰 下注用：`/bet red 10 私鑰`\n"
            f"或設定 PIN：`/setpin 1234 私鑰`",
            parse_mode='Markdown'
        )
        
        logger.info(f"Wallet recovered for {user.username} ({user_id})")
        
    except Exception as e:
        logger.error(f"Recover error: {e}")
        await update.message.reply_text(
            f"❌ 恢復失敗：助記詞無效\n\n"
            f"請確認 12 個單詞正確且用空格分隔"
        )

async def setpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """設定 PIN 碼綁定私鑰"""
    user = update.effective_user
    user_id = user.id
    
    # 只允許私聊
    if update.effective_chat.type != 'private':
        await update.message.reply_text("⚠️ 請私聊我設定 PIN！")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "用法：`/setpin <PIN> <私鑰>`\n\n"
            "例如：`/setpin 1234 abc123...`\n"
            "PIN 為 4-6 位數字",
            parse_mode='Markdown'
        )
        return
    
    pin = context.args[0]
    private_key_hex = context.args[1]
    
    # 驗證 PIN 格式
    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        await update.message.reply_text("❌ PIN 需為 4-6 位數字")
        return
    
    # 驗證私鑰
    address = verify_private_key(private_key_hex)
    if not address:
        await update.message.reply_text("❌ 私鑰無效")
        return
    
    # 儲存 PIN
    pins = load_roulette_pins()
    if str(user_id) not in pins:
        pins[str(user_id)] = {}
    pins[str(user_id)][pin] = private_key_hex
    save_roulette_pins(pins)
    
    await update.message.reply_text(
        f"✅ PIN 設定成功！\n\n"
        f"🔑 PIN：`{pin}`\n"
        f"📍 地址：`{address[:30]}...`\n\n"
        f"下注時使用：`/bet red 10 {pin}`",
        parse_mode='Markdown'
    )
    logger.info(f"PIN set for {user.username} ({user_id})")

async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """下注輪盤"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    # 只允許私聊
    if update.effective_chat.type != 'private':
        await update.message.reply_text("⚠️ 請私聊我下注！")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "🎰 *輪盤下注*\n\n"
            "用法：`/bet <類型> <金額> <PIN或私鑰>`\n\n"
            "*類型：*\n"
            "• `red` / `紅` — 紅色（賠率 1:1）\n"
            "• `black` / `黑` — 黑色（賠率 1:1）\n"
            "• `green` / `綠` / `0` — 綠色（賠率 17:1）\n"
            "• `1-36` — 單一數字（賠率 35:1）\n\n"
            "*範例：*\n"
            "`/bet red 10 1234`\n"
            "`/bet 17 5 abc123...`",
            parse_mode='Markdown'
        )
        return
    
    bet_type = context.args[0]
    try:
        bet_amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ 金額格式錯誤")
        return
    
    if bet_amount <= 0:
        await update.message.reply_text("❌ 金額必須大於 0")
        return
    
    pin_or_key = context.args[2]
    
    # 取得私鑰
    private_key_hex = get_private_key_from_pin_or_hex(user_id, pin_or_key)
    if not private_key_hex:
        await update.message.reply_text("❌ PIN 或私鑰無效")
        return
    
    # 驗證私鑰
    from_address = verify_private_key(private_key_hex)
    if not from_address:
        await update.message.reply_text("❌ 私鑰無效")
        return
    
    await update.message.reply_text("🔄 處理下注中...")
    
    # 發送 tKAS 到彩池（水龍頭錢包）
    try:
        from kaspa import (
            RpcClient, PrivateKey, Address,
            create_transactions, PaymentOutput, kaspa_to_sompi
        )
        
        faucet_wallet = load_faucet_wallet()
        pool_address = faucet_wallet['address']
        
        pk = PrivateKey(private_key_hex)
        
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            # 獲取 UTXO
            utxos_result = await client.get_utxos_by_addresses({"addresses": [from_address]})
            utxos = utxos_result.get("entries", [])[:100]
            
            if not utxos:
                await update.message.reply_text("❌ 餘額不足")
                return
            
            # 計算餘額
            balance = sum(u.get('utxoEntry', {}).get('amount', 0) for u in utxos) / 100_000_000
            if balance < bet_amount:
                await update.message.reply_text(f"❌ 餘額不足（目前：{balance:.2f} tKAS）")
                return
            
            # 創建交易
            outputs = [PaymentOutput(Address(pool_address), kaspa_to_sompi(bet_amount))]
            result = create_transactions(
                "testnet-10",
                utxos,
                Address(from_address),
                outputs,
                None, None,
                kaspa_to_sompi(0.0001)
            )
            
            # 簽名並提交
            tx_id = None
            for tx in result["transactions"]:
                tx.sign([pk])
                tx_id = await tx.submit(client)
                break
            
            if not tx_id:
                await update.message.reply_text("❌ 交易失敗")
                return
                
        finally:
            await client.disconnect()
        
        # 記錄下注
        bets_data = load_roulette_bets()
        
        # 如果是第一個下注，設定目標開獎區塊
        if not bets_data.get("target_block"):
            # 計算下一個 6666 區塊
            from kaspa import RpcClient as RpcClient2
            rpc2 = RpcClient2(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
            await rpc2.connect()
            try:
                info2 = await rpc2.get_block_dag_info({})
                current_h = info2.get("virtualDaaScore", 0)
                remainder = current_h % 10000
                if remainder < 6666:
                    target = current_h - remainder + 6666
                else:
                    target = current_h - remainder + 16666
                bets_data["target_block"] = target
            finally:
                await rpc2.disconnect()
        
        bets_data["bets"].append({
            "user_id": user_id,
            "username": username,
            "address": from_address,
            "bet_type": bet_type,
            "amount": bet_amount,
            "tx_id": tx_id,
            "timestamp": datetime.now().isoformat()
        })
        save_roulette_bets(bets_data)
        
        # 格式化下注類型
        bet_display = bet_type.upper()
        if bet_type.lower() in ['red', '紅', '红']:
            bet_display = "🔴 紅"
        elif bet_type.lower() in ['black', '黑']:
            bet_display = "⚫ 黑"
        elif bet_type.lower() in ['green', '綠', '绿', '0', '00']:
            bet_display = "🟢 綠"
        else:
            bet_display = f"🔢 {bet_type}"
        
        await update.message.reply_text(
            f"✅ *下注成功！*\n\n"
            f"🎰 押注：{bet_display}\n"
            f"💰 金額：{bet_amount} tKAS\n"
            f"🔗 TX：`{tx_id[:20]}...`\n\n"
            f"等待開盤... 🎲",
            parse_mode='Markdown'
        )
        
        # 在公告群公布下注（含區塊資訊 + 所有下注者）
        announce_group = load_announce_group()
        if announce_group:
            try:
                from kaspa import RpcClient
                
                # 取得區塊資訊
                rpc = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
                await rpc.connect()
                try:
                    info = await rpc.get_block_dag_info({})
                    current_height = info.get("virtualDaaScore", 0)
                    
                    # 計算下一個 6666 區塊
                    remainder = current_height % 10000
                    if remainder < 6666:
                        next_6666 = current_height - remainder + 6666
                    else:
                        next_6666 = current_height - remainder + 16666
                    
                    blocks_left = next_6666 - current_height
                    minutes_left = blocks_left // 60
                    
                    # 查詢獎池餘額
                    faucet_wallet = load_faucet_wallet()
                    pool_result = await rpc.get_balance_by_address({"address": faucet_wallet['address']})
                    pool_balance = pool_result.get("balance", 0) / 100_000_000
                finally:
                    await rpc.disconnect()
                
                # 取得所有下注者
                all_bets = load_roulette_bets().get("bets", [])
                total_pool = sum(b.get("amount", 0) for b in all_bets)
                
                # 格式化下注列表
                bets_list = ""
                for b in all_bets:
                    bt = b.get("bet_type", "?").lower()
                    if bt in ['red', '紅', '红']:
                        bd = "🔴"
                    elif bt in ['black', '黑']:
                        bd = "⚫"
                    elif bt in ['green', '綠', '绿', '0', '00']:
                        bd = "🟢"
                    else:
                        bd = f"#{bt}"
                    bets_list += f"  • @{b.get('username', '?')} {bd} {b.get('amount', 0)} tKAS\n"
                
                await context.bot.send_message(
                    chat_id=announce_group,
                    text=f"🎰 *新下注！*\n\n"
                         f"👤 @{username} 押 {bet_display} {bet_amount} tKAS\n\n"
                         f"━━━━━━━━━━━━━━\n"
                         f"📋 *目前下注：*\n{bets_list}\n"
                         f"💰 本輪彩池：{total_pool} tKAS\n"
                         f"🏦 莊家籌碼：{pool_balance:,.1f} tKAS\n\n"
                         f"━━━━━━━━━━━━━━\n"
                         f"📊 目前高度：{current_height:,}\n"
                         f"🎯 開獎高度：{next_6666:,}\n"
                         f"⏳ 約 {minutes_left} 分鐘後開獎",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to announce bet: {e}")
        
        logger.info(f"Bet: {username} ({user_id}) -> {bet_type} {bet_amount} tKAS")
        
    except Exception as e:
        logger.error(f"Bet error: {e}")
        await update.message.reply_text(f"❌ 下注失敗：{e}")

async def bets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看當前下注"""
    bets_data = load_roulette_bets()
    current_bets = bets_data.get("bets", [])
    
    if not current_bets:
        await update.message.reply_text("🎰 目前沒有下注")
        return
    
    msg = "🎰 *當前下注*\n\n"
    total = 0
    for b in current_bets:
        bet_type = b.get("bet_type", "?").upper()
        if bet_type.lower() in ['red', '紅', '红']:
            bet_display = "🔴"
        elif bet_type.lower() in ['black', '黑']:
            bet_display = "⚫"
        elif bet_type.lower() in ['green', '綠', '绿', '0', '00']:
            bet_display = "🟢"
        else:
            bet_display = f"#{bet_type}"
        
        amount = b.get("amount", 0)
        total += amount
        msg += f"• @{b.get('username', '?')} {bet_display} {amount} tKAS\n"
    
    msg += f"\n💰 總彩池：{total} tKAS"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def roulette_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看輪盤狀態"""
    try:
        from kaspa import RpcClient
        
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            # 取得目前區塊高度
            info = await client.get_block_dag_info({})
            current_height = info.get("virtualDaaScore", 0)
            
            # 計算下一個 6666 區塊
            remainder = current_height % 10000
            if remainder < 6666:
                next_6666 = current_height - remainder + 6666
            else:
                next_6666 = current_height - remainder + 16666
            
            blocks_left = next_6666 - current_height
            # 估算時間（每秒約 1 區塊）
            seconds_left = blocks_left
            
            bets_data = load_roulette_bets()
            bet_count = len(bets_data.get("bets", []))
            total_pool = sum(b.get("amount", 0) for b in bets_data.get("bets", []))
            
            await update.message.reply_text(
                f"🎰 *輪盤狀態*\n\n"
                f"📊 目前區塊：{current_height:,}\n"
                f"🎯 開盤區塊：{next_6666:,}\n"
                f"⏳ 剩餘：{blocks_left:,} 塊（約 {seconds_left//60} 分鐘）\n\n"
                f"🎲 下注數：{bet_count}\n"
                f"💰 總彩池：{total_pool} tKAS",
                parse_mode='Markdown'
            )
            
        finally:
            await client.disconnect()
            
    except Exception as e:
        logger.error(f"Roulette status error: {e}")
        await update.message.reply_text(f"❌ 查詢失敗：{e}")

async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """手動開獎（僅限管理員）"""
    user = update.effective_user
    
    # 簡單的管理員檢查（可以之後改成更完善的）
    ADMIN_IDS = [5168530096]  # Ryan 的 ID
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ 只有管理員可以開獎")
        return
    
    bets_data = load_roulette_bets()
    current_bets = bets_data.get("bets", [])
    
    if not current_bets:
        await update.message.reply_text("🎰 目前沒有下注，無法開獎")
        return
    
    await update.message.reply_text("🎲 開獎中...")
    
    try:
        from kaspa import RpcClient, PrivateKey, Address, create_transactions, PaymentOutput, kaspa_to_sompi
        
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            # 取得當前區塊資訊作為隨機源
            info = await client.get_block_dag_info({})
            current_height = info.get("virtualDaaScore", 0)
            target_block = bets_data.get("target_block", current_height)
            
            # 確定性選擇 tip：按 blueScore 降序，相同則按 hash 字母序
            tips = info.get("tipHashes", ["0"])
            tip_info = []
            for th in tips[:10]:  # 最多檢查 10 個 tip
                try:
                    block = await client.get_block({"hash": th, "includeTransactions": False})
                    header = block.get('block', {}).get('header', {})
                    tip_info.append({
                        'hash': th,
                        'blueScore': header.get('blueScore', 0)
                    })
                except:
                    tip_info.append({'hash': th, 'blueScore': 0})
            
            # 排序：blueScore 高優先，相同則 hash 字母序
            tip_info.sort(key=lambda x: (-x['blueScore'], x['hash']))
            tip_hash = tip_info[0]['hash'] if tip_info else tips[0]
            
            # 用區塊 hash + 目標區塊算結果
            result = get_roulette_result(tip_hash)
            result_display = str(result) if result < 37 else "00"
            result_color = get_bet_color(result)
            
            # 記錄開獎 log
            logger.info(f"Draw: target={target_block}, hash={tip_hash[:16]}..., result={result_display}")
            
            # 計算贏家和獎金
            winners = []
            losers = []
            total_payout = 0
            
            for bet in current_bets:
                winnings = calculate_winnings(bet["bet_type"], bet["amount"], result)
                if winnings > 0:
                    winners.append({
                        "username": bet["username"],
                        "address": bet["address"],
                        "bet_type": bet["bet_type"],
                        "bet_amount": bet["amount"],
                        "winnings": winnings
                    })
                    total_payout += winnings
                else:
                    losers.append({
                        "username": bet["username"],
                        "bet_type": bet["bet_type"],
                        "bet_amount": bet["amount"]
                    })
            
            # 發放獎金
            faucet_wallet = load_faucet_wallet()
            faucet_pk = PrivateKey(faucet_wallet['private_key'])
            faucet_address = faucet_wallet['address']
            
            payout_results = []
            for winner in winners:
                try:
                    # 獲取 UTXO
                    utxos_result = await client.get_utxos_by_addresses({"addresses": [faucet_address]})
                    utxos = utxos_result.get("entries", [])[:100]
                    
                    if utxos:
                        outputs = [PaymentOutput(Address(winner["address"]), kaspa_to_sompi(winner["winnings"]))]
                        tx_result = create_transactions(
                            "testnet-10",
                            utxos,
                            Address(faucet_address),
                            outputs,
                            None, None,
                            kaspa_to_sompi(0.0001)
                        )
                        
                        for tx in tx_result["transactions"]:
                            tx.sign([faucet_pk])
                            tx_id = await tx.submit(client)
                            payout_results.append(f"✅ @{winner['username']} +{winner['winnings']} tKAS")
                            break
                except Exception as e:
                    payout_results.append(f"❌ @{winner['username']} 發放失敗")
                    logger.error(f"Payout error for {winner['username']}: {e}")
            
        finally:
            await client.disconnect()
        
        # 格式化結果
        winners_text = ""
        if winners:
            for w in winners:
                winners_text += f"  🎉 @{w['username']} 押 {w['bet_type']} → +{w['winnings']} tKAS\n"
        else:
            winners_text = "  （無人獲勝）\n"
        
        losers_text = ""
        if losers:
            for l in losers:
                losers_text += f"  💸 @{l['username']} 押 {l['bet_type']} -{l['bet_amount']} tKAS\n"
        else:
            losers_text = "  （無人輸錢）\n"
        
        result_msg = (
            f"🎰 *開獎結果！*\n\n"
            f"Block Hash:\n`{tip_hash}`\n\n"
            f"int(hash,16) % 38 = *{result}*\n"
            f"結果：*{result_color}({result_display})*\n\n"
            f"🏆 *贏家：*\n{winners_text}\n"
            f"💀 *輸家：*\n{losers_text}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 本輪發放：{total_payout} tKAS"
        )
        
        # 公告到群組
        announce_group = load_announce_group()
        if announce_group:
            try:
                await context.bot.send_message(
                    chat_id=announce_group,
                    text=result_msg,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to announce result: {e}")
        
        # 回覆開獎者
        await update.message.reply_text(result_msg, parse_mode='Markdown')
        
        # 清空下注記錄
        save_roulette_bets({"target_block": None, "bets": []})
        
        logger.info(f"Draw completed: result={result_display}, winners={len(winners)}, losers={len(losers)}")
        
    except Exception as e:
        logger.error(f"Draw error: {e}")
        await update.message.reply_text(f"❌ 開獎失敗：{e}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /nami_help 指令"""
    help_msg = """🌊 *Nami Kaspa Bot 指令列表*

━━━━━━━━━━━━━━━━━━━━
👛 *錢包*
━━━━━━━━━━━━━━━━━━━━
`/nami_wallet`
創建 Testnet 錢包，私訊助記詞+私鑰
_(請先私聊 Bot 一次)_

━━━━━━━━━━━━━━━━━━━━
💧 *水龍頭*
━━━━━━━━━━━━━━━━━━━━
`/nami_faucet` — 領到自己地址
`/nami_faucet @user` — 發給別人
每次 10 tKAS，每天限 50 tKAS

━━━━━━━━━━━━━━━━━━━━
🎰 *輪盤*（私聊下注）
━━━━━━━━━━━━━━━━━━━━
`/setpin <PIN> <私鑰>`
設定 4-6 位 PIN 綁定私鑰

`/bet <類型> <金額> <PIN或私鑰>`
下注！類型可以是：
• `red` / `紅` — 紅色 1:1
• `black` / `黑` — 黑色 1:1
• `green` / `0` — 綠色 17:1
• `1-36` — 單一數字 35:1

`/bets` — 查看當前下注
`/roulette` — 輪盤狀態

*開盤：* 區塊高度 xx6666
*結果：* 由區塊 hash 決定

━━━━━━━━━━━━━━━━━━━━
📊 *查詢*
━━━━━━━━━━━━━━━━━━━━
`/nami_balance` — 餘額查詢
`/nami_status` — 發放統計

━━━━━━━━━━━━━━━━━━━━
🌊 Nami Kaspa Bot ✨
"""
    await update.message.reply_text(help_msg, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /status 指令"""
    records = load_records()
    today = datetime.now().strftime('%Y-%m-%d')
    
    daily = records.get("daily_stats", {}).get(today, {"count": 0, "total": 0})
    total_all_time = sum(r.get("amount", 0) for r in records.get("records", []))
    
    # 最近 5 筆發放紀錄
    recent = records.get("records", [])[-5:]
    recent_text = ""
    if recent:
        recent_text = "\n*最近發放：*\n"
        for r in reversed(recent):
            addr = r.get("address", "")[:20] + "..."
            amt = r.get("amount", 0)
            recent_text += f"• `{addr}` → {amt} tKAS\n"
    
    await update.message.reply_text(
        f"📊 *水龍頭狀態*\n\n"
        f"*今日 ({today})*\n"
        f"• 發放次數：{daily['count']} 次\n"
        f"• 發放總量：{daily['total']} tKAS\n\n"
        f"*累計*\n"
        f"• 總發放量：{total_all_time:,.0f} tKAS\n"
        f"{recent_text}\n"
        f"_每次 {AMOUNT_PER_REQUEST} tKAS，每天上限 {DAILY_LIMIT_PER_USER} tKAS_",
        parse_mode='Markdown'
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 主程式
# ═══════════════════════════════════════════════════════════════════════════════

# 記錄上次開獎的區塊（持久化）
LAST_DRAW_FILE = DATA_DIR / "last_draw_block.json"

def load_last_draw_block() -> int:
    """載入上次開獎區塊"""
    if LAST_DRAW_FILE.exists():
        with open(LAST_DRAW_FILE, 'r') as f:
            data = json.load(f)
            return data.get("block", 0)
    return 0

def save_last_draw_block(block: int):
    """儲存上次開獎區塊"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAST_DRAW_FILE, 'w') as f:
        json.dump({"block": block}, f)

async def auto_draw_check_standalone(bot):
    """自動檢查是否需要開獎"""
    try:
        from kaspa import RpcClient, PrivateKey, Address, create_transactions, PaymentOutput, kaspa_to_sompi
        
        # 檢查是否有下注和目標區塊
        bets_data = load_roulette_bets()
        current_bets = bets_data.get("bets", [])
        target_block = bets_data.get("target_block")
        
        if not current_bets or not target_block:
            return  # 沒有下注或沒有目標區塊，不需要開獎
        
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            info = await client.get_block_dag_info({})
            current_height = info.get("virtualDaaScore", 0)
            
            # 檢查是否到達目標開獎區塊
            if current_height < target_block:
                return  # 還沒到開獎時間
            
            current_6666 = target_block  # 使用下注時設定的目標區塊
            
            # 開獎！
            logger.info(f"Auto draw triggered at block {current_height}, target was {current_6666}")
            save_last_draw_block(current_6666)
            
            # 確定性選擇 tip：按 blueScore 降序，相同則按 hash 字母序
            tips = info.get("tipHashes", ["0"])
            tip_info = []
            for th in tips[:10]:  # 最多檢查 10 個 tip
                try:
                    block = await client.get_block({"hash": th, "includeTransactions": False})
                    header = block.get('block', {}).get('header', {})
                    tip_info.append({
                        'hash': th,
                        'blueScore': header.get('blueScore', 0)
                    })
                except:
                    tip_info.append({'hash': th, 'blueScore': 0})
            
            # 排序：blueScore 高優先，相同則 hash 字母序
            tip_info.sort(key=lambda x: (-x['blueScore'], x['hash']))
            tip_hash = tip_info[0]['hash'] if tip_info else tips[0]
            
            result = get_roulette_result(tip_hash)
            result_display = str(result) if result < 37 else "00"
            result_color = get_bet_color(result)
            
            # 記錄開獎 log
            logger.info(f"Auto draw: target={current_6666}, hash={tip_hash[:16]}..., result={result_display}")
            
            # 保存開獎歷史
            history_file = DATA_DIR / "roulette_history.json"
            history = []
            if history_file.exists():
                with open(history_file, 'r') as f:
                    history = json.load(f)
            history.append({
                "target_block": current_6666,
                "block_hash": tip_hash,
                "result": result,
                "result_display": result_display,
                "color": result_color,
                "timestamp": datetime.now().isoformat(),
                "bets_count": len(current_bets),
                "total_pool": sum(b.get("amount", 0) for b in current_bets)
            })
            with open(history_file, 'w') as f:
                json.dump(history[-100:], f, indent=2)  # 只保留最近 100 筆
            
            # 計算贏家和獎金
            winners = []
            losers = []
            total_payout = 0
            
            for bet in current_bets:
                winnings = calculate_winnings(bet["bet_type"], bet["amount"], result)
                if winnings > 0:
                    winners.append({
                        "username": bet["username"],
                        "address": bet["address"],
                        "bet_type": bet["bet_type"],
                        "bet_amount": bet["amount"],
                        "winnings": winnings
                    })
                    total_payout += winnings
                else:
                    losers.append({
                        "username": bet["username"],
                        "bet_type": bet["bet_type"],
                        "bet_amount": bet["amount"]
                    })
            
            # 發放獎金
            faucet_wallet = load_faucet_wallet()
            faucet_pk = PrivateKey(faucet_wallet['private_key'])
            faucet_address = faucet_wallet['address']
            
            for winner in winners:
                try:
                    utxos_result = await client.get_utxos_by_addresses({"addresses": [faucet_address]})
                    utxos = utxos_result.get("entries", [])[:100]
                    
                    if utxos:
                        outputs = [PaymentOutput(Address(winner["address"]), kaspa_to_sompi(winner["winnings"]))]
                        tx_result = create_transactions(
                            "testnet-10",
                            utxos,
                            Address(faucet_address),
                            outputs,
                            None, None,
                            kaspa_to_sompi(0.0001)
                        )
                        
                        for tx in tx_result["transactions"]:
                            tx.sign([faucet_pk])
                            await tx.submit(client)
                            break
                except Exception as e:
                    logger.error(f"Auto payout error for {winner['username']}: {e}")
            
        finally:
            await client.disconnect()
        
        # 格式化結果
        winners_text = ""
        if winners:
            for w in winners:
                winners_text += f"  🎉 @{w['username']} 押 {w['bet_type']} → +{w['winnings']} tKAS\n"
        else:
            winners_text = "  （無人獲勝）\n"
        
        losers_text = ""
        if losers:
            for l in losers:
                losers_text += f"  💸 @{l['username']} 押 {l['bet_type']} -{l['bet_amount']} tKAS\n"
        else:
            losers_text = "  （無人輸錢）\n"
        
        result_msg = (
            f"🎰 *自動開獎結果！*\n\n"
            f"Block Hash:\n`{tip_hash}`\n\n"
            f"int(hash,16) % 38 = *{result}*\n"
            f"結果：*{result_color}({result_display})*\n\n"
            f"🏆 *贏家：*\n{winners_text}\n"
            f"💀 *輸家：*\n{losers_text}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 本輪發放：{total_payout} tKAS"
        )
        
        # 公告到群組
        announce_group = load_announce_group()
        if announce_group:
            try:
                await bot.send_message(
                    chat_id=announce_group,
                    text=result_msg,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to announce auto result: {e}")
        
        # 清空下注記錄
        save_roulette_bets({"target_block": None, "bets": []})
        
        logger.info(f"Auto draw completed: result={result_display}, winners={len(winners)}, losers={len(losers)}")
        
    except Exception as e:
        logger.error(f"Auto draw check error: {e}")

def main():
    """啟動 Bot"""
    token = load_token()
    
    # 建立 Application
    app = Application.builder().token(token).build()
    
    # 工具指令
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(CommandHandler("set_announce", set_announce))
    
    # 註冊指令（加上 nami_ 前綴避免與其他 Bot 衝突）
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nami", start))  # /nami 也能用
    app.add_handler(CommandHandler("nami_help", help_cmd))
    app.add_handler(CommandHandler("nami_wallet", wallet))
    app.add_handler(CommandHandler("nami_faucet", faucet))
    app.add_handler(CommandHandler("nami_balance", balance))
    app.add_handler(CommandHandler("nami_status", status))
    # 保留舊指令（私聊用）
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("faucet", faucet))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("status", status))
    
    # 輪盤指令
    app.add_handler(CommandHandler("recover", recover))
    app.add_handler(CommandHandler("setpin", setpin))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("bets", bets))
    app.add_handler(CommandHandler("roulette", roulette_status))
    app.add_handler(CommandHandler("draw", draw))
    
    # 啟動
    logger.info("🌊 Nami Kaspa Bot 啟動中...")
    logger.info("🎰 自動開獎已啟用（每 30 秒檢查）")
    
    # 自動開獎背景任務
    async def run_auto_draw():
        while True:
            await asyncio.sleep(30)
            try:
                await auto_draw_check_standalone(app.bot)
            except Exception as e:
                logger.error(f"Auto draw background error: {e}")
    
    async def main_async():
        async with app:
            await app.start()
            asyncio.create_task(run_auto_draw())
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            # 保持運行
            while True:
                await asyncio.sleep(3600)
    
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
