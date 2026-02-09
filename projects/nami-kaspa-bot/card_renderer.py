"""
🎴 英雄卡片渲染器
根據 block hash + 稀有度生成獨特背景
"""

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pathlib import Path
import hashlib
import math
import io

# 稀有度配色方案
RARITY_THEMES = {
    "N": {
        "gradient": [(30, 30, 50), (50, 50, 80)],  # 深藍灰
        "glow": None,
        "stars": 3,
        "border": (100, 100, 100),
    },
    "R": {
        "gradient": [(20, 40, 60), (40, 80, 120)],  # 藍色
        "glow": (100, 150, 255, 30),
        "stars": 8,
        "border": (80, 140, 200),
    },
    "SR": {
        "gradient": [(40, 20, 60), (80, 40, 120)],  # 紫色
        "glow": (180, 100, 255, 50),
        "stars": 15,
        "border": (160, 80, 200),
    },
    "SSR": {
        "gradient": [(60, 40, 20), (120, 80, 40)],  # 金棕
        "glow": (255, 200, 100, 70),
        "stars": 25,
        "border": (255, 180, 50),
    },
    "UR": {
        "gradient": [(60, 50, 10), (140, 120, 40)],  # 金色
        "glow": (255, 220, 100, 100),
        "stars": 40,
        "border": (255, 215, 0),
    },
    "LR": {
        "gradient": [(50, 20, 30), (120, 40, 60)],  # 紅金
        "glow": (255, 100, 100, 120),
        "stars": 60,
        "border": (255, 50, 50),
        "rainbow": True,
    },
}

# 向後相容舊稀有度名稱
RARITY_MAP = {
    "common": "N", "uncommon": "R", "rare": "SR",
    "epic": "SSR", "legendary": "UR", "mythic": "LR"
}


def hash_to_values(block_hash: str, count: int = 10) -> list[int]:
    """從 block hash 提取數值（0-255）"""
    if not block_hash:
        block_hash = "default_hash_for_testing"
    
    # 用 hash 生成更多隨機數
    h = hashlib.sha256(block_hash.encode()).hexdigest()
    values = []
    for i in range(0, min(len(h), count * 2), 2):
        values.append(int(h[i:i+2], 16))
    return values


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """線性插值兩個顏色"""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_gradient(draw: ImageDraw, width: int, height: int, c1: tuple, c2: tuple, angle: float = 0):
    """繪製漸層背景"""
    for y in range(height):
        t = y / height
        # 加入角度變化
        color = lerp_color(c1, c2, t)
        draw.line([(0, y), (width, y)], fill=color)


def draw_stars(draw: ImageDraw, width: int, height: int, count: int, hash_values: list, base_brightness: int = 200):
    """根據 hash 繪製星星"""
    for i in range(count):
        # 用 hash 值決定位置
        idx = i % len(hash_values)
        x = (hash_values[idx] * (i + 1) * 7) % width
        y = (hash_values[(idx + 1) % len(hash_values)] * (i + 1) * 11) % height
        
        # 星星大小和亮度
        size = 1 + (hash_values[(idx + 2) % len(hash_values)] % 3)
        brightness = base_brightness + (hash_values[idx] % 55)
        
        # 繪製星星（簡單的十字）
        color = (brightness, brightness, brightness + 20)
        draw.ellipse([x-size, y-size, x+size, y+size], fill=color)
        
        # 有些星星加光芒
        if hash_values[idx] % 4 == 0:
            glow_color = (brightness//2, brightness//2, brightness//2 + 10)
            draw.line([x-size*2, y, x+size*2, y], fill=glow_color)
            draw.line([x, y-size*2, x, y+size*2], fill=glow_color)


def draw_glow(img: Image, color: tuple, intensity: int = 50):
    """添加發光效果"""
    if not color:
        return img
    
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    
    cx, cy = img.size[0] // 2, img.size[1] // 2
    for r in range(intensity, 0, -5):
        alpha = int(color[3] * (1 - r / intensity))
        c = (*color[:3], alpha)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=c)
    
    return Image.alpha_composite(img.convert('RGBA'), glow)


def draw_border(img: Image, color: tuple, width: int = 3):
    """繪製邊框"""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for i in range(width):
        draw.rectangle([i, i, w-1-i, h-1-i], outline=color)
    return img


def render_hero_card(
    hero_class: str,
    rank: str,
    block_hash: str,
    card_size: tuple = (128, 128)
) -> bytes:
    """
    渲染英雄卡片
    
    Args:
        hero_class: knight/mage/archer/rogue
        rank: N/R/SR/SSR/UR/LR
        block_hash: 用於生成獨特背景
        card_size: 輸出尺寸
    
    Returns:
        PNG 圖片 bytes
    """
    # 標準化稀有度
    rank = RARITY_MAP.get(rank, rank)
    if rank not in RARITY_THEMES:
        rank = "N"
    
    theme = RARITY_THEMES[rank]
    hash_values = hash_to_values(block_hash, 20)
    
    # 創建背景
    width, height = card_size
    bg = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(bg)
    
    # 根據 hash 微調漸層顏色
    c1 = tuple(min(255, c + hash_values[0] % 20 - 10) for c in theme["gradient"][0])
    c2 = tuple(min(255, c + hash_values[1] % 20 - 10) for c in theme["gradient"][1])
    draw_gradient(draw, width, height, c1, c2)
    
    # 繪製星星
    draw_stars(draw, width, height, theme["stars"], hash_values)
    
    # 轉 RGBA 處理特效
    bg = bg.convert('RGBA')
    
    # 添加光暈
    if theme.get("glow"):
        bg = draw_glow(bg, theme["glow"], intensity=width//3)
    
    # 載入英雄圖片
    hero_images_dir = Path.home() / "nami-backpack" / "projects" / "pixel-hero-stage"
    hero_img_path = hero_images_dir / f"{hero_class}.png"
    
    if hero_img_path.exists():
        hero_img = Image.open(hero_img_path).convert('RGBA')
        
        # 縮放英雄圖片（留邊距）
        hero_size = int(min(width, height) * 0.75)
        hero_img = hero_img.resize((hero_size, hero_size), Image.Resampling.LANCZOS)
        
        # 置中貼上
        x = (width - hero_size) // 2
        y = (height - hero_size) // 2
        bg.paste(hero_img, (x, y), hero_img)
    
    # 繪製邊框
    bg = draw_border(bg, theme["border"], width=3)
    
    # LR 特殊：彩虹邊框動畫感（用漸變色）
    if theme.get("rainbow"):
        draw = ImageDraw.Draw(bg)
        for i in range(3):
            # 彩虹色
            hue = (hash_values[i] + i * 60) % 360
            r = int(255 * (1 + math.cos(math.radians(hue))) / 2)
            g = int(255 * (1 + math.cos(math.radians(hue - 120))) / 2)
            b = int(255 * (1 + math.cos(math.radians(hue - 240))) / 2)
            draw.rectangle([i, i, width-1-i, height-1-i], outline=(r, g, b))
    
    # 輸出
    output = io.BytesIO()
    bg.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def render_hero_card_to_file(
    hero_class: str,
    rank: str,
    block_hash: str,
    output_path: str,
    card_size: tuple = (128, 128)
):
    """渲染並保存到檔案"""
    data = render_hero_card(hero_class, rank, block_hash, card_size)
    with open(output_path, 'wb') as f:
        f.write(data)
    return output_path


# 測試
if __name__ == "__main__":
    import sys
    
    test_hash = "ebceb599b6699dd543668520a07048c2b3c991f1df78dee0e4de71d0cad66f14"
    
    # 測試所有稀有度
    for rank in ["N", "R", "SR", "SSR", "UR", "LR"]:
        for hero_class in ["knight", "mage", "archer", "rogue"]:
            output = f"/tmp/test_card_{rank}_{hero_class}.png"
            render_hero_card_to_file(hero_class, rank, test_hash, output)
            print(f"✅ {output}")
    
    print("\n🎴 測試完成！")
