#!/usr/bin/env python3
"""
🎯 Kaspa 事件訂閱模組
簡潔版 - 事件驅動架構

by Nami 🌊

用法：
    from kaspa_events import KaspaEvents
    
    events = KaspaEvents()
    await events.connect()
    
    # 訂閱 DAA 變化
    async for daa in events.daa_stream():
        print(f"DAA: {daa}")
        if should_trigger_reward(daa):
            await trigger_reward()
"""

import asyncio
import logging
from typing import Optional, AsyncGenerator, Set
from kaspa import RpcClient, Address

logger = logging.getLogger(__name__)


class KaspaEvents:
    """Kaspa 事件訂閱管理器"""
    
    def __init__(
        self,
        url: str = "ws://127.0.0.1:17210",
        network_id: str = "testnet-10"
    ):
        self.url = url
        self.network_id = network_id
        self._client: Optional[RpcClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connected = False
        
        # 事件佇列
        self._daa_queue: asyncio.Queue = None
        self._utxo_queue: asyncio.Queue = None
        self._block_queue: asyncio.Queue = None
        
        # 監控地址
        self._watched_addresses: Set[str] = set()
    
    async def connect(self) -> bool:
        """連接到 Kaspa 節點"""
        try:
            self._loop = asyncio.get_event_loop()
            self._daa_queue = asyncio.Queue()
            self._utxo_queue = asyncio.Queue()
            self._block_queue = asyncio.Queue()
            
            self._client = RpcClient(
                url=self.url,
                network_id=self.network_id
            )
            
            await asyncio.wait_for(
                self._client.connect(),
                timeout=15
            )
            
            self._connected = True
            logger.info(f"✅ Connected to {self.url}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """斷開連接"""
        if self._client:
            try:
                await self._client.disconnect()
            except:
                pass
        self._connected = False
        logger.info("🔌 Disconnected")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DAA 訂閱
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def subscribe_daa(self):
        """訂閱 DAA 變化"""
        if not self._client:
            raise RuntimeError("Not connected")
        
        def callback(event):
            try:
                if self._loop and self._daa_queue and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(
                        self._daa_queue.put_nowait, event
                    )
            except Exception:
                pass  # 忽略關閉時的錯誤
        
        self._client.add_event_listener('virtual-daa-score-changed', callback)
        await self._client.subscribe_virtual_daa_score_changed()
        logger.info("📡 Subscribed to DAA changes")
    
    async def daa_stream(self) -> AsyncGenerator[int, None]:
        """
        DAA 事件串流
        
        async for daa in events.daa_stream():
            print(f"DAA: {daa}")
        """
        if not self._daa_queue:
            await self.subscribe_daa()
        
        while self._connected:
            try:
                event = await asyncio.wait_for(
                    self._daa_queue.get(),
                    timeout=5.0
                )
                data = event.get("data", {})
                daa = data.get("virtualDaaScore", 0)
                yield daa
            except asyncio.TimeoutError:
                # 定期 yield None 讓呼叫者有機會檢查
                continue
            except Exception as e:
                logger.error(f"DAA stream error: {e}")
                await asyncio.sleep(1)
    
    async def get_current_daa(self) -> int:
        """取得當前 DAA（非訂閱方式）"""
        if not self._client:
            raise RuntimeError("Not connected")
        
        result = await self._client.get_block_dag_info()
        return result.get("virtualDaaScore", 0)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UTXO 訂閱（付款偵測）
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def subscribe_utxo(self, addresses: list[str]):
        """訂閱 UTXO 變化（監控特定地址）"""
        if not self._client:
            raise RuntimeError("Not connected")
        
        self._watched_addresses.update(addresses)
        
        def callback(event):
            try:
                if self._loop and self._utxo_queue and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(
                        self._utxo_queue.put_nowait, event
                    )
            except Exception:
                pass
        
        self._client.add_event_listener('utxos-changed', callback)
        # 轉換字串地址為 Address 物件
        address_objects = [Address(addr) for addr in self._watched_addresses]
        await self._client.subscribe_utxos_changed(address_objects)
        logger.info(f"📡 Subscribed to UTXO changes for {len(self._watched_addresses)} addresses")
    
    async def utxo_stream(self) -> AsyncGenerator[dict, None]:
        """
        UTXO 事件串流（付款偵測）
        
        async for event in events.utxo_stream():
            # event 包含 added/removed UTXOs
            print(f"UTXO changed: {event}")
        """
        while self._connected:
            try:
                event = await asyncio.wait_for(
                    self._utxo_queue.get(),
                    timeout=5.0
                )
                yield event
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"UTXO stream error: {e}")
                await asyncio.sleep(1)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 區塊訂閱
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def subscribe_blocks(self):
        """訂閱新區塊"""
        if not self._client:
            raise RuntimeError("Not connected")
        
        def callback(event):
            if self._loop and self._block_queue:
                self._loop.call_soon_threadsafe(
                    self._block_queue.put_nowait, event
                )
        
        self._client.add_event_listener('block-added', callback)
        await self._client.subscribe_block_added()
        logger.info("📡 Subscribed to new blocks")
    
    async def block_stream(self) -> AsyncGenerator[dict, None]:
        """新區塊事件串流"""
        if not self._block_queue:
            await self.subscribe_blocks()
        
        while self._connected:
            try:
                event = await asyncio.wait_for(
                    self._block_queue.get(),
                    timeout=5.0
                )
                yield event
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Block stream error: {e}")
                await asyncio.sleep(1)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 便捷方法
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def wait_for_daa(self, target_daa: int, callback=None) -> int:
        """
        等待特定 DAA
        
        daa = await events.wait_for_daa(385066666)
        # 或帶回呼
        await events.wait_for_daa(385066666, callback=on_reached)
        """
        async for daa in self.daa_stream():
            if daa >= target_daa:
                if callback:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(daa)
                    else:
                        callback(daa)
                return daa
    
    async def watch_payments(
        self,
        address: str,
        callback,
        min_amount: int = 0
    ):
        """
        監控付款
        
        await events.watch_payments(
            "kaspa:...",
            callback=on_payment,
            min_amount=10_00000000  # 10 KAS
        )
        """
        if address not in self._watched_addresses:
            await self.subscribe_utxo([address])
        
        async for event in self.utxo_stream():
            data = event.get("data", {})
            added = data.get("added", [])
            
            for utxo in added:
                utxo_address = utxo.get("address", {}).get("prefix", "") + ":" + \
                               utxo.get("address", {}).get("payload", "")
                
                if utxo_address == address:
                    amount = utxo.get("utxoEntry", {}).get("amount", 0)
                    if amount >= min_amount:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(utxo)
                        else:
                            callback(utxo)


# ═══════════════════════════════════════════════════════════════════════════════
# 測試
# ═══════════════════════════════════════════════════════════════════════════════

async def _test():
    """測試事件訂閱"""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    events = KaspaEvents()
    
    if not await events.connect():
        return
    
    await events.subscribe_daa()
    
    print("\n🎯 Monitoring DAA (press Ctrl+C to stop)...\n")
    
    count = 0
    async for daa in events.daa_stream():
        count += 1
        if count <= 5:
            print(f"   DAA: {daa}")
        if count >= 10:
            break
    
    print(f"\n📊 Received {count} DAA events")
    await events.disconnect()


if __name__ == "__main__":
    asyncio.run(_test())
