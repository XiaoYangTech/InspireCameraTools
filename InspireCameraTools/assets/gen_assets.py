"""用 Pillow 生成应用图标资源（扁平线性风格，无外网素材依赖）。

运行::

    D:/Software/python314/python.exe assets/gen_assets.py

生成：
- ``assets/icons/<功能>.png``：6 个功能图标（256x256，透明背景）
- ``assets/icons/status_ok.png`` / ``status_off.png``：首页状态小图标
- ``assets/icons/logo.png``：应用 Logo（256x256）
- ``assets/app.ico``：多尺寸 Windows 图标（16/24/32/48/64/128/256）
- ``assets/icons/_preview.png``：图标拼图预览（仅用于人工检查）

风格：圆角线条（描边约 14px），主题色 #0d6efd（蓝）与 #6c757d（灰）。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BASE = 256
SS = 4  # 超采样倍数（抗锯齿）
SIZE = BASE * SS

BLUE = (13, 110, 253, 255)  # #0d6efd
BLUE_LIGHT = (13, 110, 253, 60)
GRAY = (108, 117, 125, 255)  # #6c757d
WHITE = (255, 255, 255, 255)
GREEN = (25, 135, 84, 255)  # #198754
GRAY_LIGHT = (173, 181, 189, 255)  # #adb5bd
STROKE = 15

ASSETS_DIR = Path(__file__).resolve().parent
ICONS_DIR = ASSETS_DIR / "icons"


def s(v: float) -> int:
    return int(round(v * SS))


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def line(draw: ImageDraw.ImageDraw, points, color=BLUE, width=STROKE, joint="curve"):
    draw.line([(s(x), s(y)) for x, y in points], fill=color, width=s(width), joint=joint)


def circle(draw, cx, cy, r, color=BLUE, width=STROKE):
    draw.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], outline=color, width=s(width))


def filled_circle(draw, cx, cy, r, color):
    draw.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], fill=color)


def rounded_rect(draw, x0, y0, x1, y1, radius, color=BLUE, width=STROKE, fill=None):
    draw.rounded_rectangle(
        [s(x0), s(y0), s(x1), s(y1)], radius=s(radius), outline=color, width=s(width), fill=fill
    )


def arc(draw, x0, y0, x1, y1, start, end, color=BLUE, width=STROKE):
    draw.arc([s(x0), s(y0), s(x1), s(y1)], start=start, end=end, fill=color, width=s(width))


def save(img: Image.Image, name: str) -> Path:
    out = ICONS_DIR / name
    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((BASE, BASE), Image.LANCZOS).save(out)
    print(f"生成 {out.relative_to(ASSETS_DIR)}")
    return out


# ---------------------------------------------------------------------------
# 各图标绘制
# ---------------------------------------------------------------------------
def icon_patch() -> Image.Image:
    """一键补丁：盾牌 + 对勾（安全修复）。"""
    img, d = new_canvas()
    shield = [(128, 34), (194, 58), (194, 112), (128, 220), (62, 112), (62, 58), (128, 34)]
    line(d, shield + [shield[0]], BLUE, STROKE)
    line(d, [(101, 124), (121, 146), (157, 100)], BLUE, 17)
    return img


def icon_hid() -> Image.Image:
    """状态调试：灯泡 + 光线。"""
    img, d = new_canvas()
    circle(d, 128, 106, 48, BLUE, STROKE)
    # 灯泡底座
    line(d, [(108, 172), (148, 172)], GRAY, 14)
    line(d, [(112, 190), (144, 190)], GRAY, 14)
    line(d, [(118, 206), (138, 206)], GRAY, 13)
    # 光线
    for angle in (0, 45, 90, 135, 180, 225, 270, 315):
        rad = math.radians(angle)
        x0, y0 = 128 + math.cos(rad) * 66, 106 + math.sin(rad) * 66
        x1, y1 = 128 + math.cos(rad) * 82, 106 + math.sin(rad) * 82
        line(d, [(x0, y0), (x1, y1)], GRAY, 12)
    return img


def icon_download() -> Image.Image:
    """历史版本下载：下载箭头 + 托盘。"""
    img, d = new_canvas()
    line(d, [(128, 46), (128, 152)], BLUE, 17)
    line(d, [(94, 120), (128, 156), (162, 120)], BLUE, 17)
    line(d, [(64, 158), (64, 204), (192, 204), (192, 158)], GRAY, 15)
    return img


def icon_autoupdate() -> Image.Image:
    """破坏自动更新：刷新循环 + 禁止斜杠。"""
    img, d = new_canvas()
    arc(d, 58, 58, 198, 198, 35, 300, BLUE, 15)
    # 箭头
    d.polygon(
        [(s(168), s(42)), (s(206), s(66)), (s(160), s(84))],
        fill=BLUE,
    )
    line(d, [(72, 190), (186, 72)], GRAY, 16)
    return img


def icon_camera() -> Image.Image:
    """一键相机：相机机身 + 镜头。"""
    img, d = new_canvas()
    rounded_rect(d, 46, 86, 210, 196, 26, BLUE, 15)
    # 顶部取景器凸起
    line(d, [(92, 86), (104, 62), (152, 62), (164, 86)], BLUE, 15)
    circle(d, 128, 144, 36, BLUE, 15)
    filled_circle(d, 180, 112, 7, GRAY)
    return img


def icon_settings() -> Image.Image:
    """设置关于：齿轮。"""
    img, d = new_canvas()
    for i in range(8):
        angle = math.radians(i * 45)
        x0 = 128 + math.cos(angle) * 68
        y0 = 128 + math.sin(angle) * 68
        x1 = 128 + math.cos(angle) * 92
        y1 = 128 + math.sin(angle) * 92
        line(d, [(x0, y0), (x1, y1)], BLUE, 22)
    circle(d, 128, 128, 58, BLUE, 15)
    circle(d, 128, 128, 20, GRAY, 13)
    return img


def icon_status(ok: bool) -> Image.Image:
    """首页连接状态小图标。"""
    img, d = new_canvas()
    filled_circle(d, 128, 128, 96, GREEN if ok else GRAY_LIGHT)
    if ok:
        line(d, [(86, 130), (116, 162), (172, 96)], WHITE, 20)
    else:
        line(d, [(92, 128), (164, 128)], WHITE, 20)
    return img


def icon_logo() -> Image.Image:
    """应用 Logo：蓝色圆角方块 + 白色相机线条。"""
    img, d = new_canvas()
    d.rounded_rectangle([s(18), s(18), s(238), s(238)], radius=s(48), fill=BLUE)
    # 白色相机
    rounded_rect(d, 62, 92, 194, 188, 24, WHITE, 13)
    line(d, [(100, 92), (112, 68), (150, 68), (162, 92)], WHITE, 13)
    circle(d, 128, 142, 32, WHITE, 13)
    filled_circle(d, 173, 116, 7, WHITE)
    return img


def build_ico(logo: Image.Image) -> None:
    """生成 Windwos 多尺寸 ico。"""
    out = ASSETS_DIR / "app.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    logo.resize((256, 256), Image.LANCZOS).save(out, format="ICO", sizes=sizes)
    print(f"生成 {out.relative_to(ASSETS_DIR)}")


def build_preview(images: list[tuple[str, Image.Image]]) -> None:
    """拼图预览（人工检查用）。"""
    cols = 4
    cell, padding = 148, 16
    rows = max(1, math.ceil(len(images) / cols))
    width = cols * (cell + padding) + padding
    height = rows * (cell + padding) + padding
    sheet = Image.new("RGB", (width, height), (248, 249, 250))
    draw = ImageDraw.Draw(sheet)
    for idx, (name, img) in enumerate(images):
        row, col = divmod(idx, cols)
        x = padding + col * (cell + padding)
        y = padding + row * (cell + padding)
        thumb = img.resize((cell, cell), Image.LANCZOS)
        bg = Image.new("RGBA", thumb.size, (255, 255, 255, 255))
        bg.alpha_composite(thumb)
        sheet.paste(bg.convert("RGB"), (x, y))
        draw.text((x + 4, y + cell + 2), name, fill=(73, 80, 87))
    out = ICONS_DIR / "_preview.png"
    sheet.save(out)
    print(f"生成 {out.relative_to(ASSETS_DIR)}")


def main() -> int:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    icons = {
        "patch": icon_patch(),
        "hid": icon_hid(),
        "download": icon_download(),
        "autoupdate": icon_autoupdate(),
        "camera": icon_camera(),
        "settings": icon_settings(),
        "status_on": icon_status(True),
        "status_off": icon_status(False),
    }
    for name, img in icons.items():
        save(img, f"{name}.png")
    logo = icon_logo()
    save(logo, "logo.png")
    build_ico(logo)
    build_preview(list(icons.items()) + [("logo", logo)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
