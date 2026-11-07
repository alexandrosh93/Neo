#!/usr/bin/env python3
"""Build a vertical (9:16) "ΠΑΣΑ στα ΝΕΑ" news reel with Greek voiceover.

Usage: python3 build.py [script.json] [output.mp4]

Voice: Microsoft Neural TTS via edge-tts (default el-GR-NestorasNeural, male),
with word-synced captions. If the service is unreachable it falls back to
offline espeak-ng + MBROLA (mb-gr2), which sounds robotic.
Needs: ffmpeg, Pillow, edge-tts (pip). Network: speech.platform.bing.com.
"""
import asyncio, json, math, os, random, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
FD = os.path.join(HERE, "assets", "fonts")
F_BLACK_I = os.path.join(FD, "FiraSansExtraCondensed-900i.ttf")
F_XB_I = os.path.join(FD, "FiraSansExtraCondensed-800i.ttf")
F_BOLD = os.path.join(FD, "FiraSansExtraCondensed-700.ttf")
F_SEMI = os.path.join(FD, "FiraSansExtraCondensed-600.ttf")

BG1, BG2 = (14, 38, 46), (5, 16, 20)
GREEN, GREEN_D = (24, 226, 120), (10, 150, 80)
YELLOW, WHITE, INK = (255, 222, 0), (255, 255, 255), (12, 18, 20)
PANEL = (10, 26, 32)
PAPER = (240, 240, 236)

_fc = {}
def font(path, size):
    k = (path, size)
    if k not in _fc: _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]

def ease(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3

# ---------------------------------------------------------------- voice
async def _edge(text, voice, rate, mp3):
    import edge_tts
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    com = edge_tts.Communicate(text, voice, rate=rate, proxy=proxy, boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as fh:
        async for ch in com.stream():
            if ch["type"] == "audio": fh.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    return words

def tts(text, cfg, wav, tmp):
    mp3 = os.path.join(tmp, "e.mp3")
    try:
        words = asyncio.run(_edge(text, cfg.get("voice", "el-GR-NestorasNeural"), cfg.get("rate", "+0%"), mp3))
        if os.path.getsize(mp3) > 1000:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "1", wav], check=True)
            return words, "edge-tts"
    except Exception as e:
        print("edge-tts failed, using offline voice:", e)
    raw = os.path.join(tmp, "raw.wav")
    subprocess.run(["espeak-ng", "-v", "mb-gr2", "-s", "160", "-w", raw, text], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", "loudnorm=I=-16",
                    "-ar", "44100", "-ac", "1", wav], check=True)
    d, toks = duration(wav), text.split()
    per = d / max(1, len(toks))
    return [(i * per, (i + 1) * per, w) for i, w in enumerate(toks)], "espeak-ng (offline)"

def duration(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).strip())

def load_pronunciations(cfg):
    """pronunciations.json (+ optional "pronunciations" in script.json): written form -> spoken form."""
    p = {}
    f = os.path.join(HERE, "pronunciations.json")
    if os.path.exists(f):
        p.update({k: v for k, v in json.load(open(f, encoding="utf-8")).items() if not k.startswith("_")})
    p.update(cfg.get("pronunciations", {}))
    return p

def _pat(k):
    return re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)")

def to_spoken(text, pron):
    for k, v in sorted(pron.items(), key=lambda kv: -len(kv[0])):
        text = _pat(k).sub(v, text)
    return text

def restore_words(words, pron):
    """Merge the spoken tokens of a replacement back into its written form, for the captions."""
    norm = lambda w: re.sub(r"[^\w]", "", w).lower()
    reps = [(k, [norm(t) for t in v.split()]) for k, v in pron.items()]
    out, i = [], 0
    while i < len(words):
        for k, toks in reps:
            seg = words[i:i + len(toks)]
            if len(seg) == len(toks) and [norm(w[2]) for w in seg] == toks:
                out.append((seg[0][0], seg[-1][1], k)); i += len(toks); break
        else:
            out.append(words[i]); i += 1
    return out

def chunks(words, text, maxw=4):
    """Group word timings into caption chunks, breaking at punctuation in the source text."""
    out, cur, pos = [], [], 0
    for a, b, w in words:
        i = text.find(w, pos)
        if i >= 0:
            pos = i + len(w)
            m = re.match(r"[.,!?;:·…]+", text[pos:])
            if m: w += m.group(0); pos += len(m.group(0))
        cur.append((a, b, w))
        if len(cur) >= maxw or re.search(r"[.,!?;:·…]$", w):
            out.append(cur); cur = []
    if cur: out.append(cur)
    return out

# ---------------------------------------------------------------- shapes
def torn_rect(d, box, fill, rnd, jag=7, step=14):
    x0, y0, x1, y1 = box
    pts = []
    for x in range(int(x0), int(x1) + 1, step): pts.append((x, y0 + rnd.uniform(-jag, jag)))
    for y in range(int(y0), int(y1) + 1, step): pts.append((x1 + rnd.uniform(-jag / 2, jag / 2), y))
    for x in range(int(x1), int(x0) - 1, -step): pts.append((x, y1 + rnd.uniform(-jag, jag)))
    for y in range(int(y1), int(y0) - 1, -step): pts.append((x0 + rnd.uniform(-jag / 2, jag / 2), y))
    d.polygon(pts, fill=fill)

def paper(size, rnd, fill=PAPER):
    w, h = size
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    torn_rect(ImageDraw.Draw(sh), (24, 26, w + 24, h + 26), (0, 0, 0, 150), random.Random(rnd.random()))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    torn_rect(ImageDraw.Draw(im), (20, 20, w + 20, h + 20), fill + (255,), rnd)
    # paper grain
    g = Image.effect_noise((w + 40, h + 40), 22).convert("L")
    grain = Image.new("RGBA", im.size, (0, 0, 0, 0))
    grain.putalpha(g.point(lambda v: max(0, v - 120) // 4))
    a = im.getchannel("A")
    im.alpha_composite(grain)
    im.putalpha(a)
    return im

def para(d, xy, w, h, skew, fill):
    x, y = xy
    d.polygon([(x + skew, y), (x + w + skew, y), (x + w, y + h), (x, y + h)], fill=fill)

def wrap(text, f, maxw):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def rich(d, xy, line, f, base, hi):
    """Draw a line where [bracketed] parts are highlighted."""
    x, y = xy
    for part in re.split(r"(\[[^\]]*\])", line):
        if not part: continue
        col = hi if part.startswith("[") else base
        txt = part.strip("[]")
        d.text((x, y), txt, font=f, fill=col)
        x += d.textlength(txt, font=f)
    return x

def rich_len(d, line, f):
    return d.textlength(line.replace("[", "").replace("]", ""), font=f)

# ---------------------------------------------------------------- layers
def background():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = abs(y / H - 0.45) * 1.6
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * min(1, t)) for a, b in zip(BG1, BG2)))
    # grunge noise
    n = Image.effect_noise((W, H), 40).convert("L").point(lambda v: v // 10)
    img = Image.composite(Image.new("RGB", (W, H), (40, 70, 75)), img, n)
    d = ImageDraw.Draw(img, "RGBA")
    # halftone corners
    for cx, cy in ((W, 0), (0, H), (W, H * 0.55)):
        for gx in range(0, 420, 18):
            for gy in range(0, 420, 18):
                px, py = cx + (gx if cx == 0 else -gx), cy + (gy if cy == 0 else -gy)
                r = max(0, 6 - math.hypot(gx, gy) / 70)
                if r > 0.6: d.ellipse([px - r, py - r, px + r, py + r], fill=GREEN + (70,))
    # diagonal stripes
    def stripes(x, y, n, length, width, gap, alpha, flip=1):
        for i in range(n):
            ox = x + i * gap * flip
            d.polygon([(ox, y), (ox + width * flip, y), (ox + (width - length) * flip, y + length),
                       (ox - length * flip, y + length)], fill=GREEN + (alpha,))
    stripes(-40, -60, 4, 260, 28, 46, 200)
    stripes(W - 30, 300, 4, 180, 22, 40, 170, -1)
    stripes(-60, H - 480, 5, 260, 24, 44, 190)
    stripes(W + 40, H - 380, 5, 300, 26, 46, 210, -1)
    return img

def title_layer(rnd, maxw=1010):
    """The torn-paper 'ΠΑΣΑ στα ΝΕΑ' logotype, laid out from measured text and fitted to maxw."""
    fbig, fsm = font(F_BLACK_I, 240), font(F_BLACK_I, 104)
    m = ImageDraw.Draw(Image.new("L", (1, 1)))
    w1, w3 = m.textlength("ΠΑΣΑ", font=fbig), m.textlength("ΝΕΑ", font=fbig)
    pw, gw = int(w1 + 90), int(w3 + 90)
    yw, overlap = 200, 70
    gx = pw + yw - 2 * overlap
    L = Image.new("RGBA", (gx + gw + 40, 360), (0, 0, 0, 0))
    p = paper((pw, 250), rnd).rotate(2.5, expand=True, resample=Image.BICUBIC)
    L.alpha_composite(p, (0, 30))
    g = Image.new("RGBA", (gw, 260), (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    torn_rect(gd, (0, 10, gw, 250), GREEN_D + (255,), rnd)
    torn_rect(gd, (24, 0, gw - 20, 230), GREEN + (255,), rnd)
    torn_rect(gd, (gw // 2, 40, gw, 240), (16, 110, 60, 255), rnd)
    L.alpha_composite(g.rotate(-2, expand=True, resample=Image.BICUBIC), (gx, 20))
    d = ImageDraw.Draw(L)
    d.text((60, 32), "ΠΑΣΑ", font=fbig, fill=INK)
    d.text((gx + 45, 22), "ΝΕΑ", font=fbig, fill=WHITE, stroke_width=3, stroke_fill=INK)
    y = Image.new("RGBA", (yw, 120), (0, 0, 0, 0))
    yd = ImageDraw.Draw(y)
    yd.rectangle([0, 0, yw, 120], fill=YELLOW)
    yd.text((yw // 2, 58), "στα", font=fsm, fill=INK, anchor="mm")
    L.alpha_composite(y.rotate(-4, expand=True, resample=Image.BICUBIC), (pw - overlap, 140))
    d.line([(gx + 20, 312), (gx + gw - 10, 298)], fill=YELLOW, width=12)
    if L.width > maxw:
        L = L.resize((maxw, int(L.height * maxw / L.width)), Image.LANCZOS)
    return L

def story_layer(s, rnd, compact=False, body=True, size=128):
    """Tag + dark headline panel (+ torn paper body). Returns RGBA, anchor = top-left."""
    hf = font(F_BLACK_I, 76 if compact else size)
    tf = font(F_XB_I, 30 if compact else 46)
    pw = (600 if body else 900) if compact else 960
    # shrink the headline until the longest line fits inside the panel
    _m = ImageDraw.Draw(Image.new("L", (1, 1)))
    while hf.size > 40 and max(rich_len(_m, ln, hf) for ln in s["headline"]) > pw - (100 if compact else 130):
        hf = font(F_BLACK_I, hf.size - 4)
    lh = int(hf.size * 0.98)
    ph = lh * len(s["headline"]) + (60 if compact else 90)
    tag_h = 48 if compact else 72
    L = Image.new("RGBA", (W, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    top = tag_h - 14
    # panel
    para(d, (20, top), pw, ph, 0, PANEL + (255,))
    d.rectangle([20, top + 14, 34 if not compact else 30, top + ph - 14], fill=GREEN)
    d.polygon([(pw + 10, top), (pw + 40, top), (pw + 10, top + ph), (pw - 20, top + ph)], fill=YELLOW)
    # tag
    tw = d.textlength(s["tag"], font=tf) + (40 if compact else 60)
    para(d, (40, 0), tw, tag_h, 14, YELLOW)
    d.text((40 + 14 + (tw - d.textlength(s["tag"], font=tf)) / 2 - 6, tag_h / 2), s["tag"], font=tf, fill=INK, anchor="lm")
    # headline
    x0 = 66 if compact else 80
    y = top + (24 if compact else 36)
    longest = 0
    for ln in s["headline"]:
        rich(d, (x0, y), ln, hf, WHITE, YELLOW)
        longest = max(longest, rich_len(d, ln, hf)); y += lh
    d.rectangle([x0, y + 6, x0 + min(longest + 20, pw - 80), y + (12 if compact else 18)], fill=GREEN)
    bottom = top + ph
    if body and s.get("body"):
        bf = font(F_SEMI, 34 if compact else 56)
        bw = 390 if compact else 840
        lines = [ln for para_ in s["body"].split("\n") for ln in wrap(para_, bf, bw)]
        bl = int(bf.size * 1.22)
        bh = bl * len(lines) + (34 if compact else 70)
        p = paper((bw + (40 if compact else 80), bh), rnd)
        pd = ImageDraw.Draw(p)
        for i, ln in enumerate(lines):
            pd.text((40 if compact else 60, 20 + (17 if compact else 35) + i * bl), ln, font=bf, fill=INK)
        p = p.rotate(rnd.uniform(-1.2, 1.2), expand=True, resample=Image.BICUBIC)
        if compact:
            L.alpha_composite(p, (pw - 10, max(0, top + ph // 2 - p.height // 2)))
            bottom = max(bottom, top + ph // 2 + p.height // 2)
        else:
            L.alpha_composite(p, (60, bottom + 20)); bottom += 20 + p.height
    return L.crop((0, 0, W, int(bottom) + 10))

def photo_frame(path, rnd, size=(940, 430)):
    """Torn white paper frame + cover-cropped photo (a bit larger, for the slow zoom)."""
    im = Image.open(path).convert("RGB")
    tw, th = size
    k = max(tw / im.width, th / im.height) * 1.1
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    l, t = (im.width - int(tw * 1.1)) // 2, (im.height - int(th * 1.1)) // 2
    im = im.crop((l, t, l + int(tw * 1.1), t + int(th * 1.1))).convert("RGBA")
    frame = paper((tw + 36, th + 36), rnd)
    return {"photo": im, "frame": frame, "size": size, "inset": (38, 38)}

def hook_background(path):
    """Full-bleed photo (cover crop, oversized for zoom) for the opening hook."""
    if not path or not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGB")
    k = max(W / im.width, H / im.height) * 1.15
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    return im

_grad = None
def hook_frame(bg, t, dur):
    global _grad
    if _grad is None:
        _grad = Image.new("RGBA", (W, H))
        gd = ImageDraw.Draw(_grad)
        for y in range(H):
            a = int(85 + 150 * abs(y / H - 0.42) * 2)
            gd.line([(0, y), (W, y)], fill=(4, 14, 18, min(235, a)))
    if bg is None:
        img = Image.new("RGBA", (W, H), BG2 + (255,))
    else:
        z = 1.0 + 0.10 * (t / max(dur, 0.1))  # fast push-in
        k0 = min(bg.width / W, bg.height / H)
        cw, ch = int(W * k0 / z), int(H * k0 / z)
        cx, cy = (bg.width - cw) // 2, (bg.height - ch) // 2
        img = bg.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.BILINEAR).convert("RGBA")
    img.alpha_composite(_grad)
    return img

def draw_caption(img, chunk, t):
    if not chunk: return
    d = ImageDraw.Draw(img)
    f = font(F_BLACK_I, 76)
    words = [w[2] for w in chunk]
    lines, cur = [], []
    for i, w in enumerate(words):
        test = " ".join(words[j] for j in cur + [i])
        if cur and d.textlength(test, font=f) > W - 140: lines.append(cur); cur = [i]
        else: cur.append(i)
    lines.append(cur)
    y = 1395 - (len(lines) - 1) * 44
    for ln in lines:
        text = " ".join(words[i] for i in ln)
        x = (W - d.textlength(text, font=f)) / 2
        for i in ln:
            active = chunk[i][0] <= t < chunk[i][1] + 0.08
            d.text((x, y), words[i], font=f, fill=YELLOW if active else WHITE, stroke_width=7, stroke_fill=INK)
            x += d.textlength(words[i] + " ", font=f)
        y += 88

# ---------------------------------------------------------------- main
def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "script.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "reel.mp4")
    cfg = json.load(open(src, encoding="utf-8"))
    rnd = random.Random(7)
    tmp = tempfile.mkdtemp()

    pron = load_pronunciations(cfg)
    intro = cfg["intro"]
    intro_video = os.path.join(HERE, intro["video"]) if intro.get("video") else None
    hook = cfg.get("hook")
    intro_start = float(intro.get("start", 0))
    segments = ([("hook", hook)] if hook else []) + [("intro", intro)] + \
               [("story", s) for s in cfg["stories"]] + [("recap", cfg["outro"])]
    audio = []
    for i, (kind, s) in enumerate(segments):
        wav = os.path.join(tmp, f"v{i}.wav")
        words, engine = tts(to_spoken(s["voice"], pron), cfg, wav, tmp)
        words = restore_words(words, pron)
        if kind == "intro" and intro_video:
            lead = float(intro.get("voice_at", 1.5))
            dur = max(float(intro.get("min_length", 3.5)), duration(wav) + lead + 0.3)
            dur = min(dur, duration(intro_video) - intro_start)
        elif kind == "hook":
            lead = 0.05
            dur = duration(wav) + lead + float(s.get("hold", 0.15))
        else:
            lead = 0.2
            dur = duration(wav) + lead + (1.2 if i == len(segments) - 1 else 0.25)
        audio.append((wav, [(a + lead, b + lead, w) for a, b, w in words], dur, lead))
    print("voice engine:", engine)

    # --- static layers
    base = background()
    bd = ImageDraw.Draw(base)
    kf = font(F_BOLD, 54)
    kick = cfg.get("kicker", "ΚΥΠΡΙΑΚΟ ΠΟΔΟΣΦΑΙΡΟ")
    # letter-spaced kicker
    sp = 10
    total = sum(bd.textlength(c, font=kf) for c in kick) + sp * (len(kick) - 1)
    x = (W - total) / 2
    for c in kick:
        bd.text((x, 80), c, font=kf, fill=WHITE); x += bd.textlength(c, font=kf) + sp
    title = title_layer(rnd)
    logo_path = os.path.join(HERE, cfg.get("logo", "assets/logo.png"))
    logo = Image.open(logo_path).convert("RGBA") if os.path.exists(logo_path) else None
    if logo: logo = logo.resize((700, int(logo.height * 780 / logo.width)), Image.LANCZOS)
    base = base.convert("RGBA")
    if logo: base.alpha_composite(logo, ((W - logo.width) // 2, H - logo.height - 250))

    layers = []
    for kind, s in segments:
        if kind == "recap":
            rows = [story_layer(st, rnd, compact=True, body=len(cfg["stories"]) <= 4) for st in cfg["stories"]]
            avail = 1500 - 545 - 6 * len(rows)
            tot = sum(r.height for r in rows)
            if tot > avail:  # keep the recap clear of the logo
                k = avail / tot
                rows = [r.resize((int(W * k), int(r.height * k)), Image.LANCZOS) for r in rows]
            L = Image.new("RGBA", (W, 1200), (0, 0, 0, 0)); y = 0
            for r in rows: L.alpha_composite(r, (0, y)); y += r.height + 6
            layers.append([L.crop((0, 0, W, y)), rows])
        elif kind == "intro" and intro_video:
            layers.append([None, None])
        elif kind == "hook":
            layers.append([story_layer(s, rnd, body=False, size=int(s.get("size", 150))),
                           hook_background(os.path.join(HERE, s["image"]) if s.get("image") else None)])
        else:
            img_path = os.path.join(HERE, s["image"]) if s.get("image") else None
            if img_path and os.path.exists(img_path):
                layers.append([story_layer(s, rnd, body=False, size=112), photo_frame(img_path, rnd)])
            else:
                layers.append([story_layer(s, rnd), None])

    video = os.path.join(tmp, "video.mp4")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "19", "-pix_fmt", "yuv420p", video], stdin=subprocess.PIPE)
    for si, ((kind, s), (wav, words, dur, lead), (layer, rows)) in enumerate(zip(segments, audio, layers)):
        caps = chunks(words, s["voice"])
        n = int(round(dur * FPS))
        if kind == "hook":
            bgimg = rows
            for f in range(n):
                t = f / FPS
                img = hook_frame(bgimg, t, dur)
                if logo: img.alpha_composite(logo, ((W - logo.width) // 2, H - logo.height - 250))
                # punch-in: starts big (already readable on frame 0), settles fast
                sc = 1.0 + 0.07 * (1 - ease(t / 0.25))
                shake = int(10 * math.sin(t * 60) * max(0, 1 - t / 0.35))
                L = layer if sc == 1.0 else layer.resize((int(layer.width * sc), int(layer.height * sc)), Image.BILINEAR)
                img.alpha_composite(L, ((W - L.width) // 2 + 45 + shake, 760 - (L.height - layer.height) // 2))
                cur = next((c for c in caps if c[0][0] - 0.05 <= t <= c[-1][1] + 0.25), None)
                draw_caption(img, cur, t)
                proc.stdin.write(img.convert("RGBA").tobytes())
            continue
        if kind == "intro" and intro_video:
            dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{intro_start:.3f}", "-i", intro_video, "-t", f"{dur:.3f}",
                                    "-vf", f"scale={W}:{H},fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                   stdout=subprocess.PIPE)
            last = None
            for f in range(n):
                buf = dec.stdout.read(W * H * 4)
                if len(buf) == W * H * 4: last = Image.frombytes("RGBA", (W, H), buf)
                img = last.copy()
                t = f / FPS
                cur = next((c for c in caps if c[0][0] - 0.05 <= t <= c[-1][1] + 0.25), None)
                draw_caption(img, cur, t)
                proc.stdin.write(img.tobytes())
            dec.stdout.close(); dec.wait()
            continue
        for f in range(n):
            t = f / FPS
            img = base.copy()
            # title: pops in on the very first segment
            if si == next(i for i, sg in enumerate(segments) if sg[0] == "story"):
                sc = 0.6 + 0.4 * ease(t / 0.45)
                tl = title.resize((int(title.width * sc), int(title.height * sc)), Image.BILINEAR)
                img.alpha_composite(tl, ((W - tl.width) // 2, 175 + (title.height - tl.height) // 2))
            else:
                img.alpha_composite(title, ((W - title.width) // 2, 175))
            area_top = 560
            if rows is None:
                p = ease(t / 0.4)
                img.alpha_composite(layer, (int(-W * (1 - p)), area_top + 20))
            elif isinstance(rows, dict):  # story with photo: framed photo + headline panel
                fr = rows
                pp = ease((t - 0.08) / 0.4)
                z = 1.0 + 0.08 * (t / max(dur, 0.1))
                src = fr["photo"]
                cw, ch = int(src.width / z), int(src.height / z)
                cx, cy = (src.width - cw) // 2, (src.height - ch) // 2
                ph_img = src.crop((cx, cy, cx + cw, cy + ch)).resize(fr["size"], Image.BILINEAR)
                frame = fr["frame"].copy()
                frame.paste(ph_img, fr["inset"])
                img.alpha_composite(frame, ((W - frame.width) // 2 + int(W * (1 - pp)), 520))
                p = ease((t - 0.18) / 0.4)
                img.alpha_composite(layer, (int(-W * (1 - p)), 520 + frame.height - 70))
            else:
                y = 545
                for k, r in enumerate(rows):
                    p = ease((t - k * 0.18) / 0.35)
                    if p > 0: img.alpha_composite(r, ((W - r.width) // 2 + int(-W * (1 - p)), y))
                    y += r.height + 6
            if not isinstance(rows, list):
                cur = next((c for c in caps if c[0][0] - 0.05 <= t <= c[-1][1] + 0.25), None)
                draw_caption(img, cur, t)
            proc.stdin.write(img.tobytes())
    proc.stdin.close(); proc.wait()

    # --- audio track
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        for i, (wav, _, dur, lead) in enumerate(audio):
            p = os.path.join(tmp, f"p{i}.wav")
            if segments[i][0] == "hook":
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-f", "lavfi", "-i",
                                "aevalsrc='0.55*sin(2*PI*55*t)*exp(-5*t)+0.25*(random(0)*2-1)*exp(-14*t)':d=1.2:s=44100",
                                "-filter_complex", f"[0:a]adelay={int(lead * 1000)},apad[v];[1:a]volume=0.8[b];"
                                "[v][b]amix=inputs=2:duration=first:normalize=0",
                                "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "1", p], check=True)
            elif segments[i][0] == "intro" and intro_video:
                vol = float(intro.get("music_volume", 0.35))
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro_video, "-i", wav, "-filter_complex",
                                f"[0:a]atrim={intro_start:.3f}:{intro_start + dur:.3f},asetpts=PTS-STARTPTS,aformat=channel_layouts=mono,volume='if(gte(t,{lead - 0.2:.2f}),{vol},1)':eval=frame,"
                                f"afade=t=out:st={max(0, dur - 0.5):.3f}:d=0.5[m];"
                                f"[1:a]adelay={int(lead * 1000)},apad[v];[m][v]amix=inputs=2:duration=first:normalize=0",
                                "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "1", p], check=True)
            else:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af",
                                f"adelay={int(lead * 1000)},apad", "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "1", p], check=True)
            fh.write(f"file '{p}'\n")
    voice = os.path.join(tmp, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, voice], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", voice, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(tmp)
    print(f"done: {out} ({sum(a[2] for a in audio):.1f}s)")

if __name__ == "__main__":
    main()
