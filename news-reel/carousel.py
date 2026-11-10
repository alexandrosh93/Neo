#!/usr/bin/env python3
"""Instagram carousel (1080x1350, 4:5) from the same script.json as the reel.

Usage: python3 carousel.py [script.json] [out_dir]

Slides: 1 cover (hook photo + headline + swipe hint) -> one slide per story
(photo, headline, body text) -> CTA slide (follow card + comment prompt).
Re-uses the look of build.py (fonts, colours, torn paper, logo, date badge).
"""
import json, os, random, sys
from PIL import Image, ImageDraw

import build as B

CW, CH = 1080, 1350


def _bg():
    h0 = B.H
    B.H = CH
    try:
        return B.background().convert("RGBA")
    finally:
        B.H = h0


def _logo(cfg, width=470):
    p = os.path.join(B.HERE, cfg.get("logo", "assets/logo.png"))
    if not os.path.exists(p): return None
    lg = Image.open(p).convert("RGBA")
    return lg.resize((width, int(lg.height * width / lg.width)), Image.LANCZOS)


def _title(rnd, width):
    t = B.title_layer(rnd)
    return t.resize((width, int(t.height * width / t.width)), Image.LANCZOS)


def _header(img, rnd, cfg, badge, width=600, y=34):
    t = _title(rnd, width)
    img.alpha_composite(t, ((CW - t.width) // 2, y))
    if badge: img.alpha_composite(badge, (CW - badge.width - 4, y + (t.height - badge.height) // 2))
    return y + t.height


def _footer(img, cfg):
    lg = _logo(cfg)
    if lg: img.alpha_composite(lg, ((CW - lg.width) // 2, CH - lg.height - 34))


def _cover_photo(path, h):
    im = Image.open(path).convert("RGB")
    k = max(CW / im.width, h / im.height)
    im = im.resize((int(im.width * k) + 1, int(im.height * k) + 1), Image.LANCZOS)
    l, t = (im.width - CW) // 2, (im.height - h) // 2
    return im.crop((l, t, l + CW, t + h)).convert("RGBA")


def _fade(h, top=0, bottom=200, alpha=200):
    f = Image.new("RGBA", (CW, h), (0, 0, 0, 0)); d = ImageDraw.Draw(f)
    for y in range(h):
        a = 0
        if y > h - bottom: a = int(alpha * ((y - (h - bottom)) / bottom) ** 1.5)
        if y < top: a = max(a, int(alpha * (1 - y / top)))
        d.line([(0, y), (CW, y)], fill=B.BG2 + (a,))
    return f


def _swipe(img, y, text="ΣΥΡΕ ΓΙΑ ΤΑ ΝΕΑ"):
    f = B.font(B.F_XB_I, 40)
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=f)
    w, h = int(tw + 130), 74
    x = (CW - w) // 2
    d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=B.GREEN + (255,))
    d.text((x + 40, y + h / 2 + 1), text, font=f, fill=B.INK, anchor="lm")
    ax = x + 40 + tw + 24; ay = y + h / 2
    d.polygon([(ax, ay - 15), (ax + 36, ay), (ax, ay + 15)], fill=B.INK)
    d.rectangle((ax - 20, ay - 5, ax + 4, ay + 5), fill=B.INK)


def cover(cfg, rnd, badge):
    hk = cfg["hook"]
    img = _bg()
    if hk.get("image"):
        img.alpha_composite(_cover_photo(os.path.join(B.HERE, hk["image"]), CH))
        img.alpha_composite(_fade(CH, top=330, bottom=700, alpha=235))
    _header(img, rnd, cfg, badge, width=560)
    layer = B.story_layer(hk, rnd, body=False, size=int(hk.get("size", 160)))
    img.alpha_composite(layer, (45, 610))
    _swipe(img, 610 + layer.height + 40)
    _footer(img, cfg)
    return img


def story_slide(s, cfg, rnd, badge):
    img = _bg()
    top = _header(img, rnd, cfg, badge) + 18
    lg = _logo(cfg)
    floor = CH - (lg.height if lg else 0) - 34 - 14          # the paper must end above the logo
    layer = B.story_layer(s, rnd, body=False, size=96)
    # fit the body: smaller photo first, then a smaller font if it is still too long
    lines, bf, lh, ph_h = [], None, 56, 470
    for size in (44, 40, 36, 33):
        bf = B.font(B.F_SEMI, size); lh = int(size * 1.27)
        lines = [ln for p in s.get("body", "").split("\n") for ln in B.wrap(p, bf, 900)] if s.get("body") else []
        paper_h = lh * len(lines) + 56 + 20 if lines else 0
        ph_h = min(470, floor - paper_h - 6 - layer.height + 105 - top)
        if ph_h >= 330: break
    ph_h = max(300, ph_h)
    if s.get("image") and os.path.exists(os.path.join(B.HERE, s["image"])):
        ph = _cover_photo(os.path.join(B.HERE, s["image"]), ph_h)
        ph.alpha_composite(_fade(ph_h, top=30, bottom=180, alpha=170))
        img.alpha_composite(ph, (0, top))
    ly = top + ph_h - 105
    img.alpha_composite(layer, (0, ly))
    if lines:
        paper = B.paper((960, lh * len(lines) + 56), rnd)
        pd = ImageDraw.Draw(paper)
        for i, ln in enumerate(lines):
            pd.text((50, 20 + 28 + i * lh), ln, font=bf, fill=B.INK)
        paper = paper.rotate(rnd.uniform(-1, 1), expand=True, resample=Image.BICUBIC)
        img.alpha_composite(paper, ((CW - paper.width) // 2, ly + layer.height + 6))
    _footer(img, cfg)
    return img


def cta(cfg, rnd, badge):
    img = _bg()
    _header(img, rnd, cfg, badge, width=760, y=70)
    k = B.follow_card(cfg)
    card = k["card"].copy()
    bx, by, bw, bh = k["btn"]
    card.alpha_composite(k["follow"], (bx, by))
    card.alpha_composite(k["plus"], k["av_badge"])
    comp = Image.new("RGBA", k["shadow"].size, (0, 0, 0, 0))
    comp.paste((0, 0, 0, 255), (0, 0), k["shadow"])
    comp.alpha_composite(card, (k["pad"], k["pad"]))
    B.place(img, k["glow"], CW / 2, 560, 1.0, 0.55)
    B.place(img, comp, CW / 2, 560, 1.12)
    B.place(img, k["pointer"], CW / 2 + 330, 560 + 175, 1.0, 1.0, 8)
    B.place(img, k["bell"], CW / 2 + 400, 560 - 150, 1.0, 1.0, -12)
    d = ImageDraw.Draw(img)
    q = cfg.get("carousel_question", "Ποιο θέμα σε εντυπωσίασε περισσότερο;")
    d.text((CW / 2, 830), "ΓΡΑΨΕ ΣΤΑ ΣΧΟΛΙΑ", font=B.font(B.F_BLACK_I, 64), fill=B.YELLOW, anchor="mm")
    f = B.font(B.F_SEMI, 52)
    for i, ln in enumerate(B.wrap(q, f, 900)):
        d.text((CW / 2, 915 + i * 66), ln, font=f, fill=B.WHITE, anchor="mm")
    em = B.emoji_img("👇", 90)
    B.place(img, em, CW / 2, 915 + 66 * len(B.wrap(q, f, 900)) + 50)
    _footer(img, cfg)
    return img


def make_carousel(src, out_dir):
    cfg = json.load(open(src, encoding="utf-8"))
    rnd = random.Random(7)
    badge = B.date_badge(B.reel_date(cfg)) if cfg.get("show_date", True) else None
    os.makedirs(out_dir, exist_ok=True)
    slides = [cover(cfg, rnd, badge)] + [story_slide(s, cfg, rnd, badge) for s in cfg["stories"]
                                         if s.get("type") != "table"] + [cta(cfg, rnd, badge)]
    paths = []
    for i, im in enumerate(slides, 1):
        p = os.path.join(out_dir, f"{i:02d}.jpg")
        im.convert("RGB").save(p, quality=94)
        paths.append(p)
    return paths


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(B.HERE, "script.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(B.HERE, "carousel")
    for p in make_carousel(src, out): print(p)
