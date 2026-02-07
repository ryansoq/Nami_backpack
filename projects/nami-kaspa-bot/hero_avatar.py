#!/usr/bin/env python3
"""
🎨 英雄像素頭像生成器
====================

根據命運塊 + Rank + 職業 生成像素風格頭像
完全程序化，不需要存儲任何圖片資料

by Nami 🌊 2026-02-07
"""

from PIL import Image
import io

# 8x8 迷你模板
# 0=透明, 1=輪廓, 2=皮膚, 3=主色(衣服), 5=武器
TEMPLATES = {
    'warrior': [
        "01111100",
        "01232100",
        "00121000",
        "01333150",
        "00333050",
        "00313000",
        "00303000",
        "00101000",
    ],
    'mage': [
        "00555000",
        "01232100",
        "00121000",
        "01333100",
        "00333000",
        "00333000",
        "00303000",
        "00101000",
    ],
    'archer': [
        "01111000",
        "01232155",
        "00121055",
        "01333155",
        "00333000",
        "00313000",
        "00303000",
        "00101000",
    ],
    'rogue': [
        "01111000",
        "01232100",
        "00121000",
        "01133100",
        "00333000",
        "00315000",
        "00305000",
        "00101000",
    ],
}

# Rank 配色
RANK_PALETTES = {
    'N':   {'main': (120, 100, 80),  'outline': (60, 40, 20)},
    'R':   {'main': (70, 120, 180),  'outline': (20, 50, 100)},
    'SR':  {'main': (140, 80, 200),  'outline': (60, 20, 100)},
    'SSR': {'main': (255, 200, 50),  'outline': (180, 120, 0)},
    'UR':  {'main': (255, 100, 50),  'outline': (150, 30, 10)},
    'LR':  {'main': (240, 240, 255), 'outline': (160, 160, 180)},
}

# 皮膚色
SKIN_COLORS = [
    (255, 220, 180),  # 淺
    (220, 180, 140),  # 中
    (180, 140, 100),  # 深
]

# 髮色
HAIR_COLORS = [
    (40, 30, 20),     # 黑
    (100, 70, 40),    # 棕
    (200, 180, 100),  # 金
    (150, 50, 30),    # 紅
]


def generate_avatar(block_hash: str, rank: str, hero_class: str, size: int = 16) -> bytes:
    """
    生成英雄像素頭像
    
    Args:
        block_hash: 命運區塊 hash（決定外觀細節）
        rank: N/R/SR/SSR/UR/LR（決定顏色主題）
        hero_class: warrior/mage/archer/rogue（決定模板）
        size: 輸出尺寸（預設 16，會從 8x8 放大）
    
    Returns:
        PNG 圖片 bytes
    """
    h = block_hash.lower() if block_hash else "0" * 64
    
    # 取得配色
    palette = RANK_PALETTES.get(rank, RANK_PALETTES['N'])
    
    # 根據 hash 決定皮膚和髮色
    skin_idx = int(h[2:4], 16) % len(SKIN_COLORS) if len(h) >= 4 else 0
    hair_idx = int(h[4:6], 16) % len(HAIR_COLORS) if len(h) >= 6 else 0
    skin = SKIN_COLORS[skin_idx]
    hair = HAIR_COLORS[hair_idx]
    
    # 顏色映射
    color_map = {
        '0': (0, 0, 0, 0),           # 透明
        '1': (*palette['outline'], 255),  # 輪廓/頭髮
        '2': (*skin, 255),            # 皮膚
        '3': (*palette['main'], 255), # 主色（衣服）
        '5': (200, 200, 220, 255),    # 武器
    }
    
    # 取得模板
    template = TEMPLATES.get(hero_class, TEMPLATES['warrior'])
    
    # 創建 8x8 圖片
    img = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    pixels = img.load()
    
    for y, row in enumerate(template):
        for x, c in enumerate(row):
            if c != '0':
                pixels[x, y] = color_map.get(c, (0, 0, 0, 255))
    
    # 放大到目標尺寸
    if size != 8:
        img = img.resize((size, size), Image.NEAREST)
    
    # 轉換為 bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def generate_avatar_with_frame(block_hash: str, rank: str, hero_class: str, size: int = 64) -> bytes:
    """
    生成帶邊框的英雄頭像（用於展示）
    """
    from PIL import ImageDraw
    
    # 先生成基礎頭像
    base_size = size - 8  # 留邊框空間
    avatar = generate_avatar(block_hash, rank, hero_class, base_size)
    avatar_img = Image.open(io.BytesIO(avatar))
    
    # 創建帶邊框的圖片
    palette = RANK_PALETTES.get(rank, RANK_PALETTES['N'])
    frame_color = palette['main']
    
    img = Image.new('RGBA', (size, size), (20, 20, 25, 255))
    img.paste(avatar_img, (4, 4), avatar_img)
    
    # 畫邊框
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size-1, size-1], outline=(*frame_color, 255), width=2)
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


if __name__ == "__main__":
    # 測試
    test_hash = "7a6a9e601ff40dedd1cb55e445876c1af6ec5d3d581496c6f4ea56e74ef0b7db"
    
    for hero_class in ['warrior', 'mage', 'archer', 'rogue']:
        for rank in ['N', 'SSR']:
            img = generate_avatar(test_hash, rank, hero_class, 16)
            print(f"{rank} {hero_class}: {len(img)} bytes")
