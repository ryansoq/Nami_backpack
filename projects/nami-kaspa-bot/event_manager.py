#!/usr/bin/env python3
"""
🎯 Kaspa 事件管理器
事件驅動架構 - 訂閱取代輪詢

by Nami 🌊

功能：
- 訂閱 DAA 變化（獎勵觸發）
- 訂閱 UTXO 變化（付款偵測）
- 訂閱新區塊（挖礦通知）
- 自動重連 + 心跳保活
"""

import asyncio
import logging
import time
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field
from kaspa import RpcClient

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

RPC_URL = "ws://127.0.0.1:17210"
NETWORK_ID = "testnet-10"

CONNECT_TIMEOUT = 15
RECONNECT_DELAY = 5
MAX_RECONNECT_ATTEMPTS = 10
HEALTH_CHECK_INTERVAL = 30


# ═══════════════════════════════════════════════════════════════════════════════
# 統計追蹤
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConnectionStats:
    """連線統計"""
    connected_at: float = 0
    total_events: int = 0
    daa_events: int = 0
    utxo_events: int = 0
    block_events: int = 0
    reconnects: int = 0
    last_event_at: float = 0
    errors: int = 0
    
    def to_dict(self) -> dict:
        uptime = time.time() - self.connected_at if self.connected_at else 0
        return {
            "uptime_seconds": int(uptime),
            "total_events": self.total_events,
            "daa_events": self.daa_events,
            "utxo_events": self.utxo_events,
            "block_events": self.block_events,
            "reconnects": self.reconnects,
            "errors": self.errors,
            "events_per_minute": round(self.total_events / max(1, uptime / 60), 2)
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 事件類型
# ═══════════════════════════════════════════════════════════════════════════════

class EventType:
    # 事件監聽器用 kebab-case
    DAA_CHANGED = "virtual-daa-score-changed"
    UTXO_CHANGED = "utxos-changed"
    BLOCK_ADDED = "block-added"
    NEW_BLOCK_TEMPLATE = "new-block-template"


# ═══════════════════════════════════════════════════════════════════════════════
# 事件管理器
# ═══════════════════════════════════════════════════════════════════════════════

class KaspaEventManager:
    """
    Kaspa 事件管理器
    
    用法：
        manager = KaspaEventManager()
        
        # 註冊 DAA 變化處理器
        @manager.on_daa_changed
        async def handle_daa(daa: int):
            print(f"New DAA: {daa}")
        
        # 註冊 UTXO 變化處理器（監控特定地址）
        @manager.on_utxo_changed(addresses=["kaspa:..."])
        async def handle_payment(event):
            print(f"UTXO changed: {event}")
        
        # 啟動
        await manager.start()
    """
    
    _instance: Optional['KaspaEventManager'] = None
    
    def __init__(self):
        self._client: Optional[RpcClient] = None
        self._running = False
        self._connected = False
        self._stats = ConnectionStats()
        
        # 事件處理器
        self._daa_handlers: List[Callable] = []
        self._utxo_handlers: List[tuple] = []  # (addresses, handler)
        self._block_handlers: List[Callable] = []
        
        # 監控的地址集合
        self._watched_addresses: set = set()
        
        # 當前 DAA（用於變化偵測）
        self._current_daa: int = 0
        
        # 事件佇列（用於跨 thread 傳遞）
        self._event_queue: asyncio.Queue = None
        self._loop: asyncio.AbstractEventLoop = None
        
    @classmethod
    def get_instance(cls) -> 'KaspaEventManager':
        """取得單例"""
        if cls._instance is None:
            cls._instance = KaspaEventManager()
        return cls._instance
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 裝飾器 - 註冊處理器
    # ═══════════════════════════════════════════════════════════════════════════
    
    def on_daa_changed(self, handler: Callable):
        """
        裝飾器：註冊 DAA 變化處理器
        
        @manager.on_daa_changed
        async def handle(daa: int):
            if daa % 10000 == 0:
                print(f"DAA milestone: {daa}")
        """
        self._daa_handlers.append(handler)
        return handler
    
    def on_utxo_changed(self, addresses: List[str] = None):
        """
        裝飾器：註冊 UTXO 變化處理器
        
        @manager.on_utxo_changed(addresses=["kaspa:..."])
        async def handle(event):
            print(f"Payment received!")
        """
        def decorator(handler: Callable):
            self._utxo_handlers.append((addresses or [], handler))
            if addresses:
                self._watched_addresses.update(addresses)
            return handler
        return decorator
    
    def on_block_added(self, handler: Callable):
        """
        裝飾器：註冊新區塊處理器
        
        @manager.on_block_added
        async def handle(block):
            print(f"New block: {block}")
        """
        self._block_handlers.append(handler)
        return handler
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 地址監控
    # ═══════════════════════════════════════════════════════════════════════════
    
    def watch_address(self, address: str):
        """新增監控地址"""
        self._watched_addresses.add(address)
        logger.info(f"👁️ Watching address: {address[:20]}...")
        
    def unwatch_address(self, address: str):
        """移除監控地址"""
        self._watched_addresses.discard(address)
        
    # ═══════════════════════════════════════════════════════════════════════════
    # 連線管理
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def _connect(self) -> bool:
        """建立連線並設定訂閱"""
        try:
            logger.info(f"🔌 Connecting to {RPC_URL}...")
            
            self._client = RpcClient(
                url=RPC_URL,
                network_id=NETWORK_ID
            )
            
            await asyncio.wait_for(
                self._client.connect(),
                timeout=CONNECT_TIMEOUT
            )
            
            self._connected = True
            self._stats.connected_at = time.time()
            logger.info("✅ Connected to Kaspa node")
            
            # 設定事件監聽
            await self._setup_subscriptions()
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("❌ Connection timeout")
            self._stats.errors += 1
            return False
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            self._stats.errors += 1
            return False
    
    async def _setup_subscriptions(self):
        """設定所有訂閱"""
        if not self._client:
            return
            
        # 1. 訂閱 DAA 變化
        if self._daa_handlers:
            logger.info("📡 Subscribing to DAA changes...")
            self._client.add_event_listener(
                EventType.DAA_CHANGED,
                self._handle_daa_event
            )
            await self._client.subscribe_virtual_daa_score_changed()
            
        # 2. 訂閱 UTXO 變化
        if self._utxo_handlers and self._watched_addresses:
            logger.info(f"📡 Subscribing to UTXO changes for {len(self._watched_addresses)} addresses...")
            self._client.add_event_listener(
                EventType.UTXO_CHANGED,
                self._handle_utxo_event
            )
            await self._client.subscribe_utxos_changed({
                "addresses": list(self._watched_addresses)
            })
            
        # 3. 訂閱新區塊
        if self._block_handlers:
            logger.info("📡 Subscribing to new blocks...")
            self._client.add_event_listener(
                EventType.BLOCK_ADDED,
                self._handle_block_event
            )
            await self._client.subscribe_block_added()
            
        logger.info("✅ All subscriptions active")
    
    async def _disconnect(self):
        """斷開連線"""
        if self._client:
            try:
                await self._client.disconnect()
            except:
                pass
            self._client = None
        self._connected = False
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 事件處理
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _handle_daa_event(self, event):
        """處理 DAA 變化事件（從 callback thread 呼叫）"""
        if self._loop and self._event_queue:
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait,
                ("daa", event)
            )
    
    def _handle_utxo_event(self, event):
        """處理 UTXO 變化事件（從 callback thread 呼叫）"""
        if self._loop and self._event_queue:
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait,
                ("utxo", event)
            )
    
    def _handle_block_event(self, event):
        """處理新區塊事件（從 callback thread 呼叫）"""
        if self._loop and self._event_queue:
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait,
                ("block", event)
            )
    
    async def _process_daa_event(self, event):
        """處理 DAA 事件（在 async context）"""
        try:
            self._stats.total_events += 1
            self._stats.daa_events += 1
            self._stats.last_event_at = time.time()
            
            # 取得新 DAA (格式: {'type': 'VirtualDaaScoreChanged', 'data': {'virtualDaaScore': N}})
            data = event.get("data", {}) if isinstance(event, dict) else {}
            new_daa = data.get("virtualDaaScore", 0)
            if new_daa <= self._current_daa:
                return
                
            self._current_daa = new_daa
            
            # 呼叫所有處理器
            for handler in self._daa_handlers:
                await self._safe_call(handler, new_daa)
                
        except Exception as e:
            logger.error(f"DAA event error: {e}")
            self._stats.errors += 1
    
    async def _process_utxo_event(self, event):
        """處理 UTXO 事件（在 async context）"""
        try:
            self._stats.total_events += 1
            self._stats.utxo_events += 1
            self._stats.last_event_at = time.time()
            
            for addresses, handler in self._utxo_handlers:
                await self._safe_call(handler, event)
                
        except Exception as e:
            logger.error(f"UTXO event error: {e}")
            self._stats.errors += 1
    
    async def _process_block_event(self, event):
        """處理區塊事件（在 async context）"""
        try:
            self._stats.total_events += 1
            self._stats.block_events += 1
            self._stats.last_event_at = time.time()
            
            for handler in self._block_handlers:
                await self._safe_call(handler, event)
                
        except Exception as e:
            logger.error(f"Block event error: {e}")
            self._stats.errors += 1
    
    async def _safe_call(self, handler: Callable, *args):
        """安全呼叫處理器"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(*args)
            else:
                handler(*args)
        except Exception as e:
            logger.error(f"Handler error: {e}")
            self._stats.errors += 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 主迴圈
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def _event_processor(self):
        """事件處理迴圈"""
        while self._running:
            try:
                event_type, event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                
                if event_type == "daa":
                    await self._process_daa_event(event)
                elif event_type == "utxo":
                    await self._process_utxo_event(event)
                elif event_type == "block":
                    await self._process_block_event(event)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event processor error: {e}")
    
    async def start(self):
        """啟動事件管理器"""
        if self._running:
            return
            
        self._running = True
        self._loop = asyncio.get_event_loop()
        self._event_queue = asyncio.Queue()
        
        logger.info("🚀 Starting Kaspa Event Manager...")
        
        # 啟動事件處理器
        processor_task = asyncio.create_task(self._event_processor())
        
        reconnect_attempts = 0
        
        while self._running:
            # 嘗試連線
            if not self._connected:
                if await self._connect():
                    reconnect_attempts = 0
                else:
                    reconnect_attempts += 1
                    if reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                        logger.error("❌ Max reconnect attempts reached")
                        await asyncio.sleep(60)  # 等久一點再試
                        reconnect_attempts = 0
                    else:
                        delay = min(RECONNECT_DELAY * (2 ** reconnect_attempts), 60)
                        logger.info(f"⏳ Reconnecting in {delay}s...")
                        await asyncio.sleep(delay)
                    continue
            
            # 健康檢查
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                
                # 檢查連線是否還活著
                if self._client:
                    await asyncio.wait_for(
                        self._client.ping(),
                        timeout=10
                    )
                    
            except Exception as e:
                logger.warning(f"⚠️ Health check failed: {e}")
                self._connected = False
                self._stats.reconnects += 1
                await self._disconnect()
        
        # 停止事件處理器
        processor_task.cancel()
    
    async def stop(self):
        """停止事件管理器"""
        self._running = False
        await self._disconnect()
        logger.info("🛑 Event Manager stopped")
    
    def get_stats(self) -> dict:
        """取得統計資訊"""
        return self._stats.to_dict()
    
    @property
    def current_daa(self) -> int:
        """取得當前 DAA"""
        return self._current_daa


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函數
# ═══════════════════════════════════════════════════════════════════════════════

def get_event_manager() -> KaspaEventManager:
    """取得事件管理器實例"""
    return KaspaEventManager.get_instance()


# ═══════════════════════════════════════════════════════════════════════════════
# 測試
# ═══════════════════════════════════════════════════════════════════════════════

async def _test():
    """測試事件管理器"""
    logging.basicConfig(level=logging.INFO)
    
    manager = get_event_manager()
    
    # 註冊 DAA 處理器
    @manager.on_daa_changed
    async def handle_daa(daa: int):
        print(f"🎯 DAA: {daa}")
        
        # 測試獎勵觸發
        if daa % 66666 < 10:
            print(f"🎉 Reward trigger at DAA {daa}!")
    
    # 註冊 UTXO 處理器
    TREE_ADDRESS = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"
    manager.watch_address(TREE_ADDRESS)
    
    @manager.on_utxo_changed(addresses=[TREE_ADDRESS])
    async def handle_utxo(event):
        print(f"💰 UTXO event: {event}")
    
    # 啟動
    try:
        await manager.start()
    except KeyboardInterrupt:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(_test())
