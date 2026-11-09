#!/usr/bin/env python3
"""Build a vertical (9:16) "ΠΑΣΑ στα ΝΕΑ" news reel with Greek voiceover.

Usage: python3 build.py [script.json] [output.mp4]

Voice ("engine" in script.json):
  azure    - official Azure AI Speech REST API (free F0 tier). The key is injected by the
             session proxy for <region>.tts.speech.microsoft.com; locally set AZURE_SPEECH_KEY.
             Each sentence is synthesised separately with natural pauses; word timings for the
             captions are estimated from the audio (pauses + syllables).
  edge     - edge-tts (unofficial Edge read-aloud endpoint), exact word timings.
  fallback - offline espeak-ng + MBROLA (mb-gr2), robotic.
Questions get a rising end (pyworld) whatever the engine.
Needs: ffmpeg, Pillow, numpy, pyworld (+ edge-tts for the edge engine).
"""
import asyncio, json, math, os, random, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_BOTTOM = 150          # px between the kouponaki logo and the bottom edge
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

# ---- Azure (official) -------------------------------------------------------
def _xml(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _azure_request(ssml, out, region):
    import ssl, urllib.request
    key = os.environ.get("AZURE_SPEECH_KEY", "proxy-injected")   # the session proxy replaces the placeholder
    req = urllib.request.Request(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                                 data=ssml.encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/ssml+xml", "User-Agent": "news-reel",
                                          "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                                          "Ocp-Apim-Subscription-Key": key})
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        open(out, "wb").write(r.read())

def _read_wav(p):
    import numpy as np, wave as wv
    with wv.open(p) as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float64) / 32768, f.getframerate()

def _syllables(w):
    return max(1, len(re.findall(r"[αεηιουωάέήίόύώϊϋΐΰ]+", w.lower())) or len(w) // 3)

def _estimate_word_times(x, fs, toks, text):
    """Word timings for one sentence: speech span from energy, comma pauses from silences,
    and the rest shared out by syllable count."""
    import numpy as np
    hop = int(0.01 * fs)
    rms = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)]) if len(x) > hop else np.zeros(1)
    thr = max(rms.max() * 0.025, 1e-4)
    on = np.where(rms > thr)[0]
    if len(on) == 0:
        return [(0.0, len(x) / fs, t) for t in toks]
    start, end = on[0] * 0.01, (on[-1] + 1) * 0.01
    # silent gaps (>=120 ms) inside the speech = comma pauses
    gaps, run = [], None
    for i in range(on[0], on[-1] + 1):
        if rms[i] <= thr:
            run = i if run is None else run
        elif run is not None:
            if i - run >= 12: gaps.append((run * 0.01, i * 0.01))
            run = None
    # group words by the commas in the text
    groups, cur, pos = [], [], 0
    for t in toks:
        cur.append(t)
        k = text.find(t, pos)
        if k >= 0:
            pos = k + len(t)
            if re.match(r"\s*[,:–—]", text[pos:]): groups.append(cur); cur = []
    if cur: groups.append(cur)
    cuts = sorted(sorted(gaps, key=lambda g: g[0] - g[1])[:len(groups) - 1]) if len(gaps) >= len(groups) - 1 else None
    if cuts is None:
        groups = [[t for g in groups for t in g]]; spans = [(start, end)]
    else:
        edges = [start] + [c for g in cuts for c in g] + [end]
        spans = [(edges[2 * i], edges[2 * i + 1]) for i in range(len(groups))]
    out = []
    for g, (a, b) in zip(groups, spans):
        wts = [_syllables(t) + 0.6 for t in g]; tot = sum(wts); tcur = a
        for t, wgt in zip(g, wts):
            d = (b - a) * wgt / tot
            out.append((tcur, tcur + d, t)); tcur += d
    return out

def _cap_pauses(x, fs, cap):
    """Shorten silences inside a sentence (comma pauses) that run longer than `cap` seconds."""
    import numpy as np
    hop = int(0.01 * fs)
    if len(x) < hop * 10: return x
    rms = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
    thr = rms.max() * 0.025
    on = np.where(rms > thr)[0]
    if len(on) < 2: return x
    keep, run, last = [], None, 0
    for i in range(on[0], on[-1] + 1):
        if rms[i] <= thr:
            run = i if run is None else run
        else:
            if run is not None and (i - run) * 0.01 > cap:
                cut_a = (run + int(cap * 50)) * hop          # keep half the cap at each side
                cut_b = (i - int(cap * 50)) * hop
                keep.append(x[last:cut_a]); last = cut_b
            run = None
    keep.append(x[last:])
    return np.concatenate(keep)

def tts_azure(text, cfg, wav, tmp):
    import numpy as np, wave as wv
    region = cfg.get("region", "northeurope")
    voice = cfg.get("voice", "el-GR-NestorasNeural")
    rate = cfg.get("rate", "+0%")
    # target silence between sentences (seconds of real silence a listener hears)
    want = {"!": 0.27, ".": 0.32, "…": 0.40, ";": 0.45, "?": 0.45, "\u037e": 0.45}
    TAIL, LEAD, QPAUSE = 0.10, 0.03, 0.28      # QPAUSE is added later by question_intonation
    sentences = [m.strip() for m in re.findall(r"[^.!;?\u037e…]+[.!;?\u037e…]*", text) if m.strip()]
    pieces, words, t0, fs = [], [], 0.0, 24000
    for n, snt in enumerate(sentences):
        body = f'<prosody rate="{rate}">{_xml(snt)}</prosody>'
        if "Multilingual" in voice: body = f'<lang xml:lang="el-GR">{body}</lang>'
        ssml = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
                f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="el-GR"><voice name="{voice}">{body}</voice></speak>')
        p = os.path.join(tmp, f"az{n}.wav")
        _azure_request(ssml, p, region)
        x, fs = _read_wav(p)
        x = _cap_pauses(x, fs, cfg.get("max_comma_pause", 0.26))
        toks = re.findall(r"[\w’'·-]+", snt)
        wt = _estimate_word_times(x, fs, toks, snt)
        # trim leading/trailing silence, keep a little air
        a = max(0, int((wt[0][0] - LEAD) * fs)) if wt else 0
        b = min(len(x), int((wt[-1][1] + TAIL) * fs)) if wt else len(x)
        x = x[a:b]
        words += [(t0 + s0 - a / fs, t0 + s1 - a / fs, w) for s0, s1, w in wt]
        end_mark = snt[-1] if snt[-1] in want else "."
        silence = want[end_mark] - (QPAUSE if end_mark in Q_MARKS else 0.0)
        pause = max(0.0, silence - TAIL - LEAD) if n < len(sentences) - 1 else 0.05
        pieces += [x, np.zeros(int(pause * fs))]
        t0 += len(x) / fs + pause
    y = np.clip(np.concatenate(pieces) if pieces else np.zeros(fs // 10), -1, 1)
    raw = os.path.join(tmp, "az_all.wav")
    with wv.open(raw, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(fs); f.writeframes((y * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-ar", "44100", "-ac", "1", wav], check=True)
    return words

def tts(text, cfg, wav, tmp):
    if cfg.get("engine", "edge") == "azure":
        try:
            return tts_azure(text, cfg, wav, tmp), f"azure ({cfg.get('voice')})"
        except Exception as e:
            print("azure failed, trying edge-tts:", e)
            cfg = dict(cfg, voice="el-GR-NestorasNeural", rate=cfg.get("edge_rate", "+22%"))
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

Q_MARKS = (";", "?", "\u037e")

def question_words(words, text):
    """Indexes of words that end a question (followed by ; ? or the Greek question mark)."""
    out, pos = [], 0
    for k, (_, _, w) in enumerate(words):
        i = text.find(w, pos)
        if i < 0: continue
        pos = i + len(w)
        m = re.match(r"[^\w\s]*", text[pos:])
        if m and any(q in m.group(0) for q in Q_MARKS): out.append(k)
    return out

def question_intonation(wav, words, text, rise=1.35, pause=0.28):
    """Give questions a rising end (WORLD vocoder) and a short pause after them.
    Returns the word timings shifted for the inserted pauses."""
    qs = question_words(words, text)
    if not qs: return words
    try:
        import numpy as np, pyworld as pw, wave as wv
    except ImportError:
        print("pyworld not installed: questions keep the default intonation"); return words
    with wv.open(wav) as f:
        fs = f.getframerate(); x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    f0, t = pw.harvest(x, fs, f0_floor=60, f0_ceil=320, frame_period=5.0)
    sp = pw.cheaptrick(x, f0, t, fs); ap = pw.d4c(x, f0, t, fs)
    f0n = f0.copy(); first_a = None
    for k in qs:
        a, b = words[k][0], words[k][1]
        voiced = f0 > 0
        # robust speaking pitch of the sentence before the question word (ignore octave errors)
        ref = f0[voiced & (t < a) & (t > max(0, a - 2.5))]
        ref = ref[(ref > 70) & (ref < 180)]
        body = float(np.median(ref)) if len(ref) else 110.0
        idx = np.where(voiced & (t >= a) & (t <= b + 0.12))[0]
        if len(idx) < 3: continue
        # impose the contour: level on the stressed start, then a clear glide up to +35%
        for j, i in enumerate(idx):
            p = j / (len(idx) - 1)
            r = 0.0 if p < 0.2 else ((p - 0.2) / 0.8) ** 1.2
            f0n[i] = body * (1.0 + (rise - 1.0) * r)
        first_a = a if first_a is None else min(first_a, a)
    if first_a is None: return words
    y = pw.synthesize(f0n, sp, ap, fs, 5.0)[:len(x)]
    if len(y) < len(x): y = np.pad(y, (0, len(x) - len(y)))
    s0 = int(max(0, first_a - 0.04) * fs); cf = int(0.03 * fs)
    out = x.copy(); w = np.linspace(0, 1, cf)
    out[s0:s0 + cf] = x[s0:s0 + cf] * (1 - w) + y[s0:s0 + cf] * w
    out[s0 + cf:] = y[s0 + cf:]
    # short pause after each question that is not the end of the clip
    shift, pieces, last, words2 = 0.0, [], 0, []
    cut = {k: int((words[k][1] + 0.06) * fs) for k in qs if k < len(words) - 1}
    for k, (a, b, wd) in enumerate(words):
        words2.append((a + shift, b + shift, wd))
        if k in cut:
            pieces += [out[last:cut[k]], np.zeros(int(pause * fs))]; last = cut[k]; shift += pause
    pieces.append(out[last:])
    out = np.clip(np.concatenate(pieces), -1, 1)
    with wv.open(wav, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(fs)
        f.writeframes((out * 32767).astype(np.int16).tobytes())
    return words2

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
        if len(cur) >= maxw or re.search(r"[.,!?;:·…]$", w) or len(" ".join(c[2] for c in cur)) >= 20:
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

def photo_frame(path, rnd, size=(W, 690)):
    """Clean, full-width photo (no paper border), cover-cropped and slightly oversized for the
    slow zoom, with a soft dark fade at the bottom where the headline panel overlaps."""
    im = Image.open(path).convert("RGB")
    tw, th = size
    k = max(tw / im.width, th / im.height) * 1.1
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    l, t = (im.width - int(tw * 1.1)) // 2, (im.height - int(th * 1.1)) // 2
    im = im.crop((l, t, l + int(tw * 1.1), t + int(th * 1.1))).convert("RGBA")
    frame = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    fade = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fade)
    for y in range(th):
        a = 0
        if y > th - 220: a = int(170 * ((y - (th - 220)) / 220) ** 1.6)   # bottom fade into the panel
        if y < 40: a = max(a, int(90 * (1 - y / 40)))                      # tiny top fade under the title
        fd.line([(0, y), (tw, y)], fill=BG2 + (a,))
    return {"photo": im, "frame": frame, "size": size, "inset": (0, 0), "fade": fade}

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

# ---------------------------------------------------------------- follow pop-up (end card)
SR = 44100
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

def ease_out_back(t, s=1.70158):
    t = max(0.0, min(1.0, t)); return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2

def place(dst, im, cx, cy, s=1.0, a=1.0, rot=0.0):
    """Composite `im` centred at (cx, cy) with scale, opacity and rotation; clips at the frame edges."""
    if s <= 0.01 or a <= 0.01: return
    w, h = max(1, int(im.width * s)), max(1, int(im.height * s))
    t = im.resize((w, h), Image.BILINEAR) if (w, h) != im.size else im
    if rot: t = t.rotate(rot, expand=True, resample=Image.BICUBIC)
    if a < 0.999:
        t = t.copy(); t.putalpha(t.getchannel("A").point(lambda v: int(v * a)))
    x, y = int(cx - t.width / 2), int(cy - t.height / 2)
    l, u = max(0, -x), max(0, -y)
    r, b = min(t.width, dst.width - x), min(t.height, dst.height - y)
    if r > l and b > u:
        dst.alpha_composite(t.crop((l, u, r, b)), (x + l, y + u))

_emo = {}
def emoji_img(ch, size):
    if (ch, size) not in _emo:
        f = ImageFont.truetype(EMOJI_FONT, 109)
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
        im = im.crop(im.getbbox()); k = size / max(im.size)
        _emo[(ch, size)] = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return _emo[(ch, size)]

def _pill(w, h, fill, outline=None, top=None):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=fill + (255,),
                                         outline=outline and outline + (255,), width=5 if outline else 0)
    if top:
        hi = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(hi).rounded_rectangle((8, 6, w - 9, h // 2), h // 4, fill=top)
        im.alpha_composite(hi.filter(ImageFilter.GaussianBlur(4)))
    return im

def _icon(kind, size, color, width=10):
    im = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    d, s4, w = ImageDraw.Draw(im), size * 4, width * 4
    if kind == "plus":
        d.line((s4 / 2, w / 2, s4 / 2, s4 - w / 2), fill=color + (255,), width=w)
        d.line((w / 2, s4 / 2, s4 - w / 2, s4 / 2), fill=color + (255,), width=w)
    else:
        d.line([(w / 2, s4 * 0.55), (s4 * 0.38, s4 - w), (s4 - w / 2, w)], fill=color + (255,), width=w, joint="curve")
    return im.resize((size, size), Image.LANCZOS)

def follow_card(cfg):
    """Static parts of the follow pop-up: kouponaki profile card, avatar, both button states."""
    fc = cfg.get("follow", {})
    CW, CH, R, pad = 760, 300, 46, 50
    card = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, CW - 1, CH - 1), R, fill=(250, 250, 252, 255))
    D = 140
    av = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    ImageDraw.Draw(av).ellipse((0, 0, D - 1, D - 1), fill=GREEN + (255,))
    ImageDraw.Draw(av).ellipse((8, 8, D - 9, D - 9), fill=(16, 22, 26, 255))
    logo = Image.open(os.path.join(HERE, cfg.get("logo", "assets/logo.png"))).convert("RGBA")
    a = logo.getchannel("A"); cols = [a.crop((x, 0, x + 1, logo.height)).getbbox() is not None for x in range(logo.width)]
    cut = next((x for x in range(40, logo.width) if not cols[x]), logo.width // 4)      # the ticket+ball icon
    icon = logo.crop((0, 0, cut, logo.height)); icon = icon.crop(icon.getbbox())
    k = 104 / max(icon.size); icon = icon.resize((int(icon.width * k), int(icon.height * k)), Image.LANCZOS)
    av.alpha_composite(icon, ((D - icon.width) // 2, (D - icon.height) // 2))
    card.alpha_composite(av, (30, 30))
    d = ImageDraw.Draw(card)
    d.text((196, 40), fc.get("name", "kouponaki.com"), font=font(F_BLACK_I, 58), fill=INK)
    sub, size = fc.get("sub", "Για περισσότερα «ΠΑΣΑ στα ΝΕΑ»"), 34
    while size > 20 and d.textlength(sub, font=font(F_SEMI, size)) > CW - 196 - 24: size -= 1
    d.text((198, 112), sub, font=font(F_SEMI, size), fill=(112, 118, 128))
    bw, bh = CW - 60, 100
    tf = font(F_BLACK_I, 60)
    def button(label, fill, txt, icon_kind, outline=None, top=None):
        b = _pill(bw, bh, fill, outline=outline, top=top)
        ic = _icon(icon_kind, 40, txt)
        bd = ImageDraw.Draw(b); tw = bd.textlength(label, font=tf)
        x = (bw - (ic.width + 18 + tw)) // 2
        b.alpha_composite(ic, (int(x), (bh - ic.height) // 2))
        bd.text((x + ic.width + 18, bh // 2 + 2), label, font=tf, fill=txt, anchor="lm")
        return b
    follow = button(fc.get("button", "ΚΑΝΕ FOLLOW"), GREEN, INK, "plus", top=(255, 255, 255, 90))
    done = button(fc.get("following", "FOLLOWING"), (22, 26, 32), GREEN, "check", outline=GREEN)
    shadow = Image.new("L", (CW + 2 * pad, CH + 2 * pad), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 18, pad + CW, pad + CH + 18), R, fill=140)
    plus, ok = Image.new("RGBA", (52, 52), (0, 0, 0, 0)), Image.new("RGBA", (52, 52), (0, 0, 0, 0))
    ImageDraw.Draw(plus).ellipse((0, 0, 51, 51), fill=(255, 59, 92, 255), outline=(250, 250, 252, 255), width=5)
    plus.alpha_composite(_icon("plus", 24, WHITE, 6), (14, 14))
    ImageDraw.Draw(ok).ellipse((0, 0, 51, 51), fill=GREEN + (255,), outline=(250, 250, 252, 255), width=5)
    ok.alpha_composite(_icon("check", 26, INK, 6), (13, 14))
    gl = Image.new("RGBA", (CW + 120, CH + 120), (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle((60, 60, 60 + CW, 60 + CH), R, fill=GREEN + (255,))
    gl = gl.filter(ImageFilter.GaussianBlur(26))
    return dict(card=card, shadow=shadow.filter(ImageFilter.GaussianBlur(22)), pad=pad, CW=CW, CH=CH,
                follow=follow, done=done, btn=(30, 180, bw, bh), plus=plus, ok=ok, av_badge=(30 + D - 40, 30 + D - 44),
                glow=gl, pointer=emoji_img("👆", 132), bell=emoji_img("🔔", 78),
                floaters=[(emoji_img(e, 64), dx) for e, dx in zip("💚⚽🔥💛⭐", random.Random(11).sample(range(-300, 300, 30), 5))],
                sparks=[dict(a=r.uniform(0, 2 * math.pi), v=r.uniform(520, 1150), r=r.uniform(5, 12),
                             col=r.choice([GREEN, GREEN, YELLOW, WHITE]), star=r.random() < 0.35)
                        for r in [random.Random(5)] for _ in range(34)])

def follow_times(words, default=1.2):
    """When the pop-up appears (as «φόλοου» is said), the tap, and the switch to FOLLOWING."""
    tw = next((a for a, b, w in words if re.sub(r"[^\w]", "", w).lower() in ("φόλοου", "follow")), default)
    tF = max(0.5, tw - 0.3)
    return dict(tF=tF, tP=tF + 0.55, tTap=tF + 1.05, tOn=tF + 1.11)

def draw_follow(fr, t, k, T, CX=W // 2, CY=880):
    tF, tP, tTap, tOn = T["tF"], T["tP"], T["tTap"], T["tOn"]
    v = t - tF
    if v <= 0: return
    dim = Image.new("RGBA", fr.size, (4, 10, 14, int(150 * min(1, v / 0.3))))     # focus on the card
    fr.alpha_composite(dim)
    bx, by, bw, bh = k["btn"]
    bc = (CX - k["CW"] / 2 + bx + bw / 2, CY - k["CH"] / 2 + by + bh / 2)
    target = (bc[0] + 150, bc[1] + 8)
    card = k["card"].copy()
    on = t >= tOn
    press = 1 - 0.07 * math.sin(math.pi * min(1, max(0, (t - tTap) / 0.16)))
    btn = k["done"] if on else k["follow"]
    if press < 0.999: btn = btn.resize((int(bw * press), int(bh * press)), Image.BILINEAR)
    card.alpha_composite(btn, (int(bx + (bw - btn.width) / 2), int(by + (bh - btn.height) / 2)))
    if on:
        q = ease_out_back((t - tOn) / 0.35, 2.2)
        b = k["ok"].resize((max(1, int(52 * q)), max(1, int(52 * q))), Image.BILINEAR)
        card.alpha_composite(b, (int(k["av_badge"][0] + 26 - b.width / 2), int(k["av_badge"][1] + 26 - b.height / 2)))
    else:
        card.alpha_composite(k["plus"], k["av_badge"])
    comp = Image.new("RGBA", k["shadow"].size, (0, 0, 0, 0))
    comp.paste((0, 0, 0, 255), (0, 0), k["shadow"])
    comp.alpha_composite(card, (k["pad"], k["pad"]))
    s = ease_out_back(v / 0.45, 1.9)
    if on: s *= 1 + 0.045 * math.sin(math.pi * min(1, (t - tOn) / 0.3))
    bob = 5 * math.sin(2 * math.pi * 0.7 * max(0, v - 0.45))
    rot = -7 * (1 - ease(v / 0.45))
    if on:
        place(fr, k["glow"], CX, CY + bob, s, 0.9 * math.sin(math.pi * min(1, (t - tOn) / 0.9)))
    place(fr, comp, CX, CY + bob, s, min(1, v / 0.12), rot)
    if v > 0.25:
        ring = 22 * math.sin(2 * math.pi * 5 * (t - tOn)) * math.exp(-3 * (t - tOn)) if on else 0
        place(fr, k["bell"], CX + k["CW"] / 2 - 40, CY - k["CH"] / 2 + 2 + bob, ease_out_back((v - 0.25) / 0.4, 2.2), 1, ring)
    if tP <= t < tOn + 0.75:
        e = ease(min(1, (t - tP) / 0.4))
        x = target[0] + 230 * (1 - e)
        y = target[1] + 330 * (1 - e) + k["pointer"].height * 0.42
        sc = 1 - 0.14 * math.sin(math.pi * min(1, max(0, (t - tTap) / 0.16)))
        fade = 1 - min(1, max(0, (t - tOn - 0.35) / 0.4))
        place(fr, k["pointer"], x, y + 40 * (1 - fade), sc, fade, 8)
    if on and t - tOn < 1.1:
        w = t - tOn; d = ImageDraw.Draw(fr)
        for sp in k["sparks"]:
            dist = sp["v"] * (1 - math.exp(-3.2 * w)) / 3.2
            x = bc[0] + math.cos(sp["a"]) * dist * 1.25
            y = bc[1] + math.sin(sp["a"]) * dist + 380 * w * w
            r = sp["r"] * (1 - w / 1.1); a = int(255 * max(0, 1 - w / 1.1))
            if sp["star"]:
                d.polygon([(x + math.cos(i * math.pi / 4) * (r * 1.8 if i % 2 == 0 else r * 0.6),
                            y + math.sin(i * math.pi / 4) * (r * 1.8 if i % 2 == 0 else r * 0.6)) for i in range(8)],
                          fill=sp["col"] + (a,))
            else:
                d.ellipse((x - r, y - r, x + r, y + r), fill=sp["col"] + (a,))
    if on:
        for i, (em, dx) in enumerate(k["floaters"]):
            w = t - tOn - 0.08 * i
            if 0 < w < 1.6:
                place(fr, em, bc[0] + dx * 0.9 + 26 * math.sin(w * 5 + i), bc[1] - 40 - 330 * ease(min(1, w / 1.6)),
                      ease_out_back(min(1, w / 0.3), 2.5) * 0.9, 1 - max(0, (w - 1.1) / 0.5))

# --- sound effects (synthesised) ---
def _env(dur): import numpy as np; return np.arange(int(dur * SR)) / SR
def _band(dur, lo, hi, seed=0):
    import numpy as np
    n = int(dur * SR); x = np.random.default_rng(seed).standard_normal(n)
    X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1 / SR); X[(f < lo) | (f > hi)] = 0
    y = np.fft.irfft(X, n); return y / (np.abs(y).max() + 1e-9)
def sfx_whoosh(dur=0.5):
    import numpy as np
    t = _env(dur); return _band(dur, 300, 4000, 3) * np.sin(np.pi * t / dur) ** 2 * 0.6
def sfx_pop(dur=0.14):
    import numpy as np
    t = _env(dur); f = 900 - 600 * t / dur
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30)
def sfx_click(dur=0.09):
    import numpy as np
    t = _env(dur); return _band(dur, 1800, 9000, 4) * np.exp(-t * 170) * 0.8 + np.sin(2 * np.pi * 900 * t) * np.exp(-t * 80) * 0.5
def sfx_notify(dur=1.0):
    import numpy as np
    t = _env(dur)
    def note(f, t0):
        tt = np.clip(t - t0, 0, None)
        tone = sum(g * np.sin(2 * np.pi * f * k * tt) for k, g in ((1, 1.0), (2, 0.35), (3, 0.12)))
        return (t >= t0) * tone * np.exp(-tt * 6.5) * np.clip(tt / 0.004, 0, 1)
    return note(1318.5, 0.0) * 0.55 + note(1975.5, 0.11) * 0.6
def sfx_confetti(dur=1.4):
    import numpy as np
    rng = np.random.default_rng(7); y = np.zeros(int(dur * SR))
    for _ in range(70):
        t0 = int(abs(rng.normal(0.25, 0.3)) * SR)
        if t0 >= len(y) - 400: continue
        c = sfx_click(0.02) * rng.uniform(0.15, 0.6)
        y[t0:t0 + len(c)] += c[: len(y) - t0]
    return y * np.exp(-np.arange(len(y)) / SR * 1.8)

def mix_sfx(path, events):
    """Add sound effects [(time, name, gain)] into a mono 16-bit wav in place."""
    import numpy as np, wave as wv
    lib = {"whoosh": sfx_whoosh, "pop": sfx_pop, "click": sfx_click, "notify": sfx_notify, "confetti": sfx_confetti}
    with wv.open(path) as f:
        fs = f.getframerate(); y = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    for t0, name, g in events:
        s = lib[name](); i = int(t0 * fs)
        if 0 <= i < len(y): y[i:i + len(s)] += s[: len(y) - i] * g
    with wv.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(fs)
        f.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())

def loudnorm(src, dst, target=-13.0, tp=-1.0):
    """Voice-over style compression + peak limiting, then two-pass EBU R128 loudness normalisation
    of the whole soundtrack (social apps play around -14 LUFS)."""
    pre = dst + ".pre.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af",
                    "acompressor=threshold=-20dB:ratio=3:attack=5:release=90:makeup=3dB,"
                    "alimiter=limit=0.7:attack=3:release=40:level=false", "-ar", "44100", "-ac", "1", pre], check=True)
    src = pre
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af",
                        f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    try:
        m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
        af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except Exception:
        af = f"loudnorm=I={target}:TP={tp}:LRA=11"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af, "-ar", "44100", "-ac", "1", dst], check=True)
    return dst

# ---------------------------------------------------------------- script check (flow & pauses)
KNOWN_WORDS = {"ΑΠΟΕΛ", "ΑΕΚ", "ΑΕΛ", "ΕΝΥ", "ΚΟΠ", "ΟΦΗ", "ΠΑΟΚ", "ΑΕΚ"}

def lint_voice(cfg, pron):
    """Warn about things in the voice text that cause odd pauses, choppy flow or bad pronunciation."""
    parts = ([("hook", cfg["hook"])] if cfg.get("hook") else []) + [("intro", cfg["intro"])] + \
            [(f"story {i + 1}", s) for i, s in enumerate(cfg["stories"])] + [("outro", cfg["outro"])]
    out = []
    for name, p in parts:
        v = p.get("voice", "")
        def warn(msg): out.append(f"[{name}] {msg}")
        if re.search(r"[;?;]", v): warn("έχει ερώτηση: γράψ' την ως δήλωση/θαυμαστικό")
        if re.search(r"\d", v): warn("έχει ψηφία: γράψε τους αριθμούς/ώρες ολογράφως")
        if re.search(r"[«»()\[\]:/–—\"]", v): warn("έχει «» ( ) : – / ή εισαγωγικά, που φέρνουν περίεργες παύσεις")
        if re.search(r"[A-Za-z]{2,}", v): warn("έχει λατινικούς χαρακτήρες: γράψ' τους όπως προφέρονται στα ελληνικά")
        for ab in set(re.findall(r"\b[Α-ΩΆ-Ώ]{2,5}\b", v)):
            if ab not in pron and ab not in KNOWN_WORDS: warn(f"συντομογραφία «{ab}»: πρόσθεσέ τη στο pronunciations.json")
        for snt in re.findall(r"[^.!;?…]+[.!;?…]*", v):
            words = snt.split()
            if len(words) > 18: warn(f"μεγάλη πρόταση ({len(words)} λέξεις): «{snt.strip()[:40]}…»")
            if snt.count(",") >= 3: warn(f"πολλά κόμματα σε μία πρόταση: «{snt.strip()[:40]}…»")
            if 0 < len(words) <= 2 and not snt.strip().endswith("!"): warn(f"πολύ κοφτή πρόταση: «{snt.strip()}»")
    hook = cfg.get("hook", {}).get("voice", "")
    if hook and len(hook.split()) > 14: out.append("[hook] πάνω από 14 λέξεις: το hook πρέπει να «χτυπάει» στα 2-3 δευτερόλεπτα")
    return out

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
    y = 1440 - (len(lines) - 1) * 44
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
    for w in lint_voice(cfg, pron):
        print("⚠️  κείμενο:", w)
    intro = cfg["intro"]
    intro_video = os.path.join(HERE, intro["video"]) if intro.get("video") else None
    hook = cfg.get("hook")
    intro_start = float(intro.get("start", 0))
    outro = dict(cfg["outro"])
    FOLLOW = cfg.get("follow", {}).get("enabled", True)
    if FOLLOW and not re.search(r"φόλοου|follow", outro["voice"], re.I):
        outro["voice"] = outro["voice"].rstrip() + " Κάνε φόλοου για να μη χάνεις τίποτα!"
    segments = ([("hook", hook)] if hook else []) + [("intro", intro)] + \
               [("story", s) for s in cfg["stories"]] + [("recap", outro)]
    FT = None
    audio = []
    for i, (kind, s) in enumerate(segments):
        wav = os.path.join(tmp, f"v{i}.wav")
        spoken = to_spoken(s["voice"], pron)
        words, engine = tts(spoken, cfg, wav, tmp)
        words = question_intonation(wav, words, spoken)
        words = restore_words(words, pron)
        if kind == "intro" and intro_video:
            lead = float(intro.get("voice_at", 1.5))
            dur = max(float(intro.get("min_length", 3.5)), duration(wav) + lead + 0.3)
            dur = min(dur, duration(intro_video) - intro_start)
        elif kind == "hook":
            lead = 0.05
            dur = duration(wav) + lead + float(s.get("hold", 0.15))
        else:
            lead = 0.15
            dur = duration(wav) + lead + (1.2 if i == len(segments) - 1 else 0.12)
        if kind == "recap" and FOLLOW:
            FT = follow_times([(a + lead, b + lead, w) for a, b, w in words])
            dur = max(dur, FT["tOn"] + 1.9)
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
    # story slides: slightly smaller logotype so the photos can be bigger
    TS = float(cfg.get("title_scale", 0.8))
    title = title.resize((int(title.width * TS), int(title.height * TS)), Image.LANCZOS)
    TITLE_Y = 150
    TOP = TITLE_Y + title.height + 12          # where the story area starts

    logo_path = os.path.join(HERE, cfg.get("logo", "assets/logo.png"))
    logo = Image.open(logo_path).convert("RGBA") if os.path.exists(logo_path) else None
    if logo: logo = logo.resize((700, int(logo.height * 780 / logo.width)), Image.LANCZOS)
    base = base.convert("RGBA")
    if logo: base.alpha_composite(logo, ((W - logo.width) // 2, H - logo.height - LOGO_BOTTOM))

    layers = []
    for kind, s in segments:
        if kind == "recap":
            rows = [story_layer(st, rnd, compact=True, body=len(cfg["stories"]) <= 4) for st in cfg["stories"]]
            avail = 1560 - TOP - 6 * len(rows)
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
                layers.append([story_layer(s, rnd, body=False, size=100), photo_frame(img_path, rnd)])
            else:
                layers.append([story_layer(s, rnd), None])

    FCARD = follow_card(cfg) if FOLLOW else None
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
                if logo: img.alpha_composite(logo, ((W - logo.width) // 2, H - logo.height - LOGO_BOTTOM))
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
                img.alpha_composite(tl, ((W - tl.width) // 2, TITLE_Y + (title.height - tl.height) // 2))
            else:
                img.alpha_composite(title, ((W - title.width) // 2, TITLE_Y))
            area_top = TOP - 20
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
                if fr.get("fade") is not None: frame.alpha_composite(fr["fade"])
                img.alpha_composite(frame, ((W - frame.width) // 2 + int(W * (1 - pp)), TOP - 20))
                p = ease((t - 0.18) / 0.4)
                img.alpha_composite(layer, (int(-W * (1 - p)), TOP - 20 + frame.height - 110))
            else:
                y = TOP
                for k, r in enumerate(rows):
                    p = ease((t - k * 0.18) / 0.35)
                    if p > 0: img.alpha_composite(r, ((W - r.width) // 2 + int(-W * (1 - p)), y))
                    y += r.height + 6
                if FOLLOW and FT:
                    draw_follow(img, t, FCARD, FT, CY=int(cfg.get("follow", {}).get("y", 900)))
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
                if segments[i][0] == "recap" and FOLLOW and FT:
                    mix_sfx(p, [(FT["tF"], "whoosh", 0.35), (FT["tF"] + 0.06, "pop", 0.5), (FT["tP"], "whoosh", 0.25),
                                (FT["tTap"], "click", 0.45), (FT["tOn"], "notify", 0.55), (FT["tOn"] + 0.02, "confetti", 0.4)])
            fh.write(f"file '{p}'\n")
    voice = os.path.join(tmp, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, voice], check=True)
    voice = loudnorm(voice, os.path.join(tmp, "voice_loud.wav"), float(cfg.get("loudness", -13)))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", voice, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(tmp)
    print(f"done: {out} ({sum(a[2] for a in audio):.1f}s)")

if __name__ == "__main__":
    main()
