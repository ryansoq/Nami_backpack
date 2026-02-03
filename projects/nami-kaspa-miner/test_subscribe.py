#!/usr/bin/env python3
"""測試 NotifyBlockAdded 訂閱模式"""

import sys
sys.path.insert(0, "/home/ymchang/kaspa-pminer")

import grpc
import kaspa_pb2
import kaspa_pb2_grpc
import time

def test_subscribe():
    print("🔗 連接到 testnet...")
    channel = grpc.insecure_channel(
        "localhost:16210",
        options=[
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
            ('grpc.keepalive_permit_without_calls', True),
        ]
    )
    stub = kaspa_pb2_grpc.RPCStub(channel)
    
    # 訂閱 BlockAdded
    print("📡 發送 NotifyBlockAdded 訂閱...")
    
    def request_generator():
        # 先發訂閱請求
        yield kaspa_pb2.KaspadMessage(
            notifyBlockAddedRequest=kaspa_pb2.NotifyBlockAddedRequestMessage()
        )
        
        # 保持連線，等待通知
        while True:
            time.sleep(1)  # 維持 generator 活著
    
    print("👂 監聽新區塊...")
    try:
        responses = stub.MessageStream(request_generator())
        for i, response in enumerate(responses):
            if response.HasField('notifyBlockAddedResponse'):
                print(f"✅ 訂閱成功！")
            elif response.HasField('blockAddedNotification'):
                block = response.blockAddedNotification.block
                print(f"🆕 新區塊！hash={block.header.hashMerkleRoot[:16]}...")
            else:
                print(f"📨 收到訊息: {response.WhichOneof('payload')}")
            
            if i > 20:  # 測試 20 個訊息
                break
                
    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    test_subscribe()
