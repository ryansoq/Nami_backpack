#!/usr/bin/env python3
"""
🌲 事件驅動獎勵系統
==================

用訂閱取代輪詢，DAA 變化即時觸發！

by Nami 🌊
"""

import asyncio
import logging
from typing import Callable, Optional
from kaspa_events import KaspaEvents
from reward_system import (
    should_trigger_reward,
    check_and_distribute,
    REWARD_TRIGGER_SUFFIX
)
from hero_game import load_heroes_db, TREE_ADDRESS

logger = logging.getLogger(__name__)


class RewardEventHandler:
    """
    事件驅動的獎勵處理器
    
    用法：
        handler = RewardEventHandler()
        handler.on_reward_distributed = my_callback  # 設定回呼
        await handler.start()
    """
    
    def __init__(self):
        self._events: Optional[KaspaEvents] = None
        self._running = False
        self._last_checked_daa = 0
        self._last_triggered_daa = 0
        
        # 回呼函數（供 bot 使用）
        self.on_reward_distributed: Optional[Callable] = None
        self.on_goblin_spawned: Optional[Callable] = None
        self.on_payment_received: Optional[Callable] = None
    
    async def start(self):
        """啟動事件處理"""
        if self._running:
            return
        
        self._running = True
        self._events = KaspaEvents()
        
        if not await self._events.connect():
            logger.error("❌ 無法連接 Kaspa 節點")
            return
        
        # 訂閱 DAA 變化
        await self._events.subscribe_daa()
        
        # 訂閱大地之樹的 UTXO（付款偵測）
        await self._events.subscribe_utxo([TREE_ADDRESS])
        
        logger.info("🌲 事件驅動獎勵系統啟動")
        
        # 啟動處理任務
        asyncio.create_task(self._process_daa_events())
        asyncio.create_task(self._process_utxo_events())
    
    async def stop(self):
        """停止事件處理"""
        self._running = False
        if self._events:
            await self._events.disconnect()
        logger.info("🛑 獎勵系統停止")
    
    async def _process_daa_events(self):
        """處理 DAA 事件"""
        logger.info("📡 開始監聽 DAA 變化...")
        
        async for daa in self._events.daa_stream():
            if not self._running:
                break
            
            # 跳過已處理的 DAA
            if daa <= self._last_checked_daa:
                continue
            
            self._last_checked_daa = daa
            
            # 檢查是否觸發獎勵
            if should_trigger_reward(daa):
                # 避免重複觸發
                if daa == self._last_triggered_daa:
                    continue
                
                self._last_triggered_daa = daa
                logger.info(f"🎯 觸發點 DAA: {daa}")
                
                # 執行獎勵發放
                await self._trigger_reward(daa)
    
    async def _process_utxo_events(self):
        """處理 UTXO 事件（付款偵測）"""
        logger.info(f"📡 監聽大地之樹付款: {TREE_ADDRESS[:30]}...")
        
        async for event in self._events.utxo_stream():
            if not self._running:
                break
            
            try:
                data = event.get("data", {})
                added = data.get("added", [])
                
                for utxo in added:
                    amount = utxo.get("utxoEntry", {}).get("amount", 0)
                    if amount > 0:
                        amount_kas = amount / 1e8
                        logger.info(f"💰 收到付款: {amount_kas:.2f} tKAS")
                        
                        if self.on_payment_received:
                            await self._safe_callback(
                                self.on_payment_received,
                                amount=amount,
                                utxo=utxo
                            )
            except Exception as e:
                logger.error(f"UTXO 處理錯誤: {e}")
    
    async def _trigger_reward(self, daa: int):
        """觸發獎勵發放"""
        try:
            logger.info(f"🌲 開始發放獎勵 (DAA: {daa})...")
            
            # 取得大地之樹餘額
            import unified_wallet
            tree_balance = await unified_wallet.get_tree_balance()
            
            # 執行發放
            result = await check_and_distribute(daa, tree_balance)
            
            if result:
                logger.info(f"✅ 獎勵發放完成: {result}")
                
                # 呼叫回呼（讓 bot 可以發送通知）
                if self.on_reward_distributed:
                    await self._safe_callback(
                        self.on_reward_distributed,
                        daa=daa,
                        result=result
                    )
                    
                # 哥布林入侵
                if result.get("goblins_spawned"):
                    if self.on_goblin_spawned:
                        await self._safe_callback(
                            self.on_goblin_spawned,
                            goblins=result.get("goblins_spawned")
                        )
            else:
                logger.info("⏭️ 無需發放獎勵（條件不符或已發放）")
                
        except Exception as e:
            logger.error(f"❌ 獎勵發放錯誤: {e}")
            import traceback
            traceback.print_exc()
    
    async def _safe_callback(self, callback: Callable, **kwargs):
        """安全執行回呼"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(**kwargs)
            else:
                callback(**kwargs)
        except Exception as e:
            logger.error(f"回呼執行錯誤: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 全域實例
# ═══════════════════════════════════════════════════════════════════════════════

_handler: Optional[RewardEventHandler] = None


def get_reward_handler() -> RewardEventHandler:
    """取得獎勵處理器實例"""
    global _handler
    if _handler is None:
        _handler = RewardEventHandler()
    return _handler


async def start_reward_events():
    """啟動事件驅動獎勵系統"""
    handler = get_reward_handler()
    await handler.start()


async def stop_reward_events():
    """停止事件驅動獎勵系統"""
    handler = get_reward_handler()
    await handler.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 測試
# ═══════════════════════════════════════════════════════════════════════════════

async def _test():
    """測試事件驅動獎勵系統"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    handler = get_reward_handler()
    
    # 設定回呼
    async def on_reward(daa, result):
        print(f"🎉 獎勵發放通知！DAA: {daa}")
        print(f"   結果: {result}")
    
    async def on_payment(amount, utxo):
        print(f"💰 收到付款: {amount / 1e8:.4f} tKAS")
    
    handler.on_reward_distributed = on_reward
    handler.on_payment_received = on_payment
    
    await handler.start()
    
    print("\n🌲 事件驅動獎勵系統測試中...")
    print(f"   下次觸發: DAA 結尾 {REWARD_TRIGGER_SUFFIX}")
    print("   按 Ctrl+C 停止\n")
    
    try:
        while True:
            await asyncio.sleep(10)
            # 顯示狀態
            print(f"📊 最後 DAA: {handler._last_checked_daa}")
    except KeyboardInterrupt:
        await handler.stop()


if __name__ == "__main__":
    asyncio.run(_test())
