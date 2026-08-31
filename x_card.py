"""X 推文/文章本地渲染卡片截图。

不再用浏览器打开 x.com（headless 被 403、有头逐屏截图对不齐），
而是把 FxTwitter API 拿到的数据渲染成本地 HTML 卡片，
headless 整页截图一次 + PIL 精确切分——回到"一次渲染、一刀切"，
零重复、零遮挡、顺序必对，且不依赖 X 页面和 cookie。
"""
import html
import os
import time

from PIL import Image
from playwright.sync_api import sync_playwright

VIEWPORT_HEIGHT = 1600
DPR = 2
CARD_WIDTH = 700

_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #ffffff;
    font-family: -apple-system, "PingFang SC", "Helvetica Neue",
                 "Microsoft YaHei", sans-serif;
    color: #0f1419;
}
.card { padding: 28px 32px; }
.header { display: flex; align-items: center; margin-bottom: 16px; }
.avatar {
    width: 48px; height: 48px; border-radius: 50%;
    margin-right: 12px; background: #cfd9de;
}
.name { font-size: 16px; font-weight: 700; }
.handle { font-size: 14px; color: #536471; }
.title { font-size: 23px; font-weight: 800; line-height: 1.35; margin-bottom: 14px; }
.text {
    font-size: 17px; line-height: 1.65;
    white-space: pre-wrap; word-break: break-word;
    overflow-wrap: break-word;
}
.media { margin-top: 14px; }
.media img {
    display: block; width: 100%;
    border: 1px solid #e1e8ed; border-radius: 14px;
    margin-bottom: 10px;
}
.quote {
    margin-top: 14px; padding: 14px 16px;
    border: 1px solid #e1e8ed; border-radius: 14px;
}
.quote .q-user { font-size: 14px; color: #536471; margin-bottom: 6px; }
.quote .q-user b { color: #0f1419; }
.quote .text { font-size: 15px; }
.footer {
    margin-top: 18px; padding-top: 12px;
    border-top: 1px solid #eff3f4;
    font-size: 14px; color: #536471;
}
"""


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _build_html(info: dict) -> str:
    author = info.get("author") or {}
    name = _esc(author.get("name"))
    handle = _esc(author.get("screen_name"))
    avatar = author.get("avatar") or ""

    parts = ['<div class="card">']

    parts.append('<div class="header">')
    if avatar:
        parts.append(
            f'<img class="avatar" src="{html.escape(avatar)}" onerror="this.style.visibility=\'hidden\'">'
        )
    parts.append('<div>')
    if name:
        parts.append(f'<div class="name">{name}</div>')
    if handle:
        parts.append(f'<div class="handle">@{handle}</div>')
    parts.append('</div></div>')

    if info.get("title"):
        parts.append(f'<div class="title">{_esc(info["title"])}</div>')
    if info.get("text"):
        parts.append(f'<div class="text">{_esc(info["text"])}</div>')

    quote = info.get("quote")
    if quote and quote.get("text"):
        q_name = _esc(quote.get("name"))
        q_user = _esc(quote.get("user"))
        who = f"<b>{q_name}</b> @{q_user}" if q_name else f"@{q_user}"
        parts.append('<div class="quote">')
        parts.append(f'<div class="q-user">引用 {who}</div>')
        parts.append(f'<div class="text">{_esc(quote["text"])}</div>')
        parts.append('</div>')

    imgs = [p for p in (info.get("images") or []) if os.path.exists(p)]
    if imgs:
        parts.append('<div class="media">')
        for p in imgs:
            parts.append(f'<img src="file://{html.escape(os.path.abspath(p))}">')
        parts.append('</div>')

    footer = "X (Twitter)"
    ts = info.get("created_timestamp")
    if ts:
        try:
            footer = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts))) + " · X (Twitter)"
        except Exception:
            pass
    parts.append(f'<div class="footer">{footer}</div>')
    parts.append('</div>')

    body = "\n".join(parts)
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_CSS}</style></head><body>{body}</body></html>'


def _slice_full_image(full_path: str, save_path_prefix: str, max_segments: int) -> list:
    """整页大图按视口高切分（与 bot.webpage_screenshot 非 X 路径同一套逻辑）。"""
    paths = []
    seg_pixel_h = VIEWPORT_HEIGHT * DPR
    full_img = Image.open(full_path)
    fw, fh = full_img.size
    if fh <= seg_pixel_h:
        seg_path = f"{save_path_prefix}_1.png"
        full_img.save(seg_path)
        paths.append(seg_path)
    else:
        idx = 0
        for top in range(0, fh, seg_pixel_h):
            bottom = min(fh, top + seg_pixel_h)
            # 最后一片太薄（< 15% 视口），合并到上一片
            if idx > 0 and (bottom - top) < seg_pixel_h * 0.15:
                break
            crop = full_img.crop((0, top, fw, bottom))
            seg_path = f"{save_path_prefix}_{idx + 1}.png"
            crop.save(seg_path)
            paths.append(seg_path)
            idx += 1
            if idx >= max_segments:
                break
    full_img.close()
    return paths


def render_card(info: dict, save_path_prefix: str, max_segments: int = 8) -> list:
    """把 fetch_x_content 的结果渲染成卡片截图，返回分段图片路径列表。失败返回 []。"""
    html_path = f"{save_path_prefix}_card.html"
    full_path = f"{save_path_prefix}_card_full.png"
    paths = []
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(_build_html(info))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": CARD_WIDTH, "height": VIEWPORT_HEIGHT},
                device_scale_factor=DPR,
            )
            page = context.new_page()
            page.goto(f"file://{os.path.abspath(html_path)}")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(300)
            page.screenshot(path=full_path, full_page=True)
            browser.close()

        paths = _slice_full_image(full_path, save_path_prefix, max_segments)
    except Exception as e:
        print(f"[卡片渲染失败] {e}")
        paths = []
    finally:
        for p in (html_path, full_path):
            try:
                os.remove(p)
            except Exception:
                pass
    return paths
