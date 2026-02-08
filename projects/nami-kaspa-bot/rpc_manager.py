#!/usr/bin/env python3
"""
🔌 Kaspa RPC 連線管理器
統一管理 RPC 連線：自動重連、超時處理、連線池

by Nami 🌊
"""

import asyncio
import logging
import time
from typing import Optional, Any
from contextlib import asynccontextmanager
from kaspa import RpcClient

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 連線配置
# ═══════════════════════════════════════════════════════════════════════════════

RPC_URL = "ws://127.0.0.1:17210"
NETWORK_ID = "testnet-10"

# 超時設定
CONNECT_TIMEOUT = 10      # 連線超時（秒）
REQUEST_TIMEOUT = 30      # 請求超時（秒）
RECONNECT_DELAY = 2       # 重連延遲（秒）
MAX_RECONNECT_ATTEMPTS = 3  # 最大重連次數
KEEPALIVE_INTERVAL = 30   # 心跳間隔（秒）


# ═══════════════════════════════════════════════════════════════════════════════
# 連線管理器
# ═══════════════════════════════════════════════════════════════════════════════

class RpcManager:
    """
    單例 RPC 連線管理器
    
    功能：
    - 自動重連
    - 超時處理
    - 心跳檢測
    - 請求排隊（避免同時太多連線）
    
    用法：
        async with get_rpc_client() as client:
            result = await client.get_block_dag_info({})
    """
    
    _instance: Optional['RpcManager'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self._client: Optional[RpcClient] = None
        self._connected = False
        self._last_activity = 0
        self._connection_lock = asyncio.Lock()
        self._keepalive_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        
    @classmethod
    async def get_instance(cls) -> 'RpcManager':
        """取得單例實例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = RpcManager()
        return cls._instance
    
    async def connect(self) -> RpcClient:
        """
        取得已連線的 RPC client
        如果未連線或斷線，會自動嘗試連線
        """
        async with self._connection_lock:
            # 檢查現有連線
            if self._connected and self._client:
                try:
                    # 簡單 ping 測試連線是否還活著
                    await asyncio.wait_for(
                        self._client.get_block_dag_info({}),
                        timeout=5.0
                    )
                    self._last_activity = time.time()
                    return self._client
                except Exception as e:
                    logger.warning(f"連線測試失敗，嘗試重連: {e}")
                    self._connected = False
            
            # 嘗試連線
            return await self._do_connect()
    
    async def _do_connect(self) -> RpcClient:
        """實際執行連線（含重試）"""
        last_error = None
        
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            try:
                # 關閉舊連線
                if self._client:
                    try:
                        await self._client.disconnect()
                    except:
                        pass
                
                # 建立新連線
                logger.info(f"🔌 連線 Kaspa RPC... (嘗試 {attempt + 1}/{MAX_RECONNECT_ATTEMPTS})")
                
                self._client = RpcClient(
                    resolver=None, 
                    url=RPC_URL, 
                    encoding='borsh'
                )
                
                await asyncio.wait_for(
                    self._client.connect(),
                    timeout=CONNECT_TIMEOUT
                )
                
                # 測試連線
                await asyncio.wait_for(
                    self._client.get_block_dag_info({}),
                    timeout=REQUEST_TIMEOUT
                )
                
                self._connected = True
                self._last_activity = time.time()
                self._reconnect_count = 0
                
                # 啟動心跳
                self._start_keepalive()
                
                logger.info("✅ Kaspa RPC 連線成功")
                return self._client
                
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"連線超時 (嘗試 {attempt + 1})")
                logger.warning(f"⏰ 連線超時，等待重試...")
                
            except Exception as e:
                last_error = e
                logger.warning(f"❌ 連線失敗: {e}")
            
            # 等待後重試
            if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                await asyncio.sleep(RECONNECT_DELAY * (attempt + 1))
        
        self._connected = False
        raise ConnectionError(f"RPC 連線失敗（重試 {MAX_RECONNECT_ATTEMPTS} 次）: {last_error}")
    
    def _start_keepalive(self):
        """啟動心跳任務"""
        if self._keepalive_task:
            self._keepalive_task.cancel()
        
        async def keepalive_loop():
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                
                if not self._connected:
                    break
                
                # 如果最近有活動，跳過心跳
                if time.time() - self._last_activity < KEEPALIVE_INTERVAL:
                    continue
                
                try:
                    await asyncio.wait_for(
                        self._client.get_block_dag_info({}),
                        timeout=10.0
                    )
                    self._last_activity = time.time()
                except Exception as e:
                    logger.warning(f"💔 心跳失敗，標記斷線: {e}")
                    self._connected = False
                    break
        
        self._keepalive_task = asyncio.create_task(keepalive_loop())
    
    async def disconnect(self):
        """關閉連線"""
        async with self._connection_lock:
            if self._keepalive_task:
                self._keepalive_task.cancel()
                self._keepalive_task = None
            
            if self._client:
                try:
                    await self._client.disconnect()
                except:
                    pass
                self._client = None
            
            self._connected = False
            logger.info("🔌 RPC 連線已關閉")
    
    async def execute(self, method: str, params: dict = None, timeout: float = None) -> Any:
        """
        執行 RPC 請求（帶自動重連）
        
        Args:
            method: RPC 方法名（如 'get_block_dag_info'）
            params: 參數
            timeout: 超時時間（秒）
        
        Returns:
            RPC 回應
        """
        if params is None:
            params = {}
        if timeout is None:
            timeout = REQUEST_TIMEOUT
        
        last_error = None
        
        for attempt in range(2):  # 最多嘗試 2 次（1 次重連）
            try:
                client = await self.connect()
                
                # 取得方法並執行
                rpc_method = getattr(client, method)
                result = await asyncio.wait_for(
                    rpc_method(params),
                    timeout=timeout
                )
                
                self._last_activity = time.time()
                return result
                
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"請求超時: {method}")
                logger.warning(f"⏰ 請求超時: {method}")
                
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                
                # 連線類錯誤，嘗試重連
                if any(kw in error_msg for kw in ['connection', 'closed', 'disconnect', 'timeout']):
                    logger.warning(f"🔄 連線異常，重連中: {e}")
                    self._connected = False
                    
                    if attempt < 1:
                        await asyncio.sleep(RECONNECT_DELAY)
                        continue
                
                raise
        
        raise last_error


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函數
# ═══════════════════════════════════════════════════════════════════════════════

async def get_manager() -> RpcManager:
    """取得 RPC 管理器實例"""
    return await RpcManager.get_instance()


@asynccontextmanager
async def get_rpc_client():
    """
    Context manager 取得 RPC client
    
    用法：
        async with get_rpc_client() as client:
            result = await client.get_block_dag_info({})
    """
    manager = await get_manager()
    client = await manager.connect()
    try:
        yield client
    except Exception as e:
        # 連線錯誤時標記斷線，讓下次自動重連
        if any(kw in str(e).lower() for kw in ['connection', 'closed', 'disconnect']):
            manager._connected = False
        raise


async def rpc_call(method: str, params: dict = None, timeout: float = None) -> Any:
    """
    簡單 RPC 呼叫
    
    用法：
        result = await rpc_call('get_block_dag_info', {})
    """
    manager = await get_manager()
    return await manager.execute(method, params, timeout)


# ═══════════════════════════════════════════════════════════════════════════════
# 常用查詢（封裝）
# ═══════════════════════════════════════════════════════════════════════════════

async def get_current_daa() -> int:
    """取得當前 DAA score"""
    result = await rpc_call('get_block_dag_info', {})
    return result.get('virtualDaaScore', 0)


async def get_balance(address: str) -> int:
    """查詢餘額（sompi）"""
    result = await rpc_call('get_balance_by_address', {'address': address})
    return result.get('balance', 0)


async def get_utxos(address: str) -> list:
    """取得 UTXO 列表"""
    result = await rpc_call('get_utxos_by_addresses', {'addresses': [address]})
    return result.get('entries', [])


async def get_block(hash: str, include_transactions: bool = False) -> dict:
    """取得區塊資訊"""
    result = await rpc_call('get_block', {
        'hash': hash,
        'includeTransactions': include_transactions
    })
    return result.get('block', {})


async def submit_transaction(signed_tx, allow_orphan: bool = False) -> str:
    """
    提交交易
    
    Returns:
        交易 ID
    """
    result = await rpc_call('submit_transaction', {
        'transaction': signed_tx,
        'allow_orphan': allow_orphan
    })
    return result.get('transactionId', str(result))


# ═══════════════════════════════════════════════════════════════════════════════
# 測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def test():
        print("🧪 測試 RPC 管理器...\n")
        
        # 方法 1: 使用 context manager
        print("1️⃣ Context manager 方式:")
        async with get_rpc_client() as client:
            info = await client.get_block_dag_info({})
            print(f"   DAA: {info.get('virtualDaaScore')}")
        
        # 方法 2: 使用 rpc_call
        print("\n2️⃣ rpc_call 方式:")
        daa = await get_current_daa()
        print(f"   DAA: {daa}")
        
        # 方法 3: 使用封裝函數
        print("\n3️⃣ 封裝函數:")
        address = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"
        balance = await get_balance(address)
        print(f"   餘額: {balance / 1e8:.4f} tKAS")
        
        # 測試重連
        print("\n4️⃣ 模擬斷線重連:")
        manager = await get_manager()
        manager._connected = False  # 強制標記斷線
        
        daa2 = await get_current_daa()  # 應該會自動重連
        print(f"   重連後 DAA: {daa2}")
        
        # 關閉
        await manager.disconnect()
        print("\n✅ 測試完成！")
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
