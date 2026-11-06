#!/usr/bin/env python3
"""Build a vertical (9:16) news reel with Greek voiceover from script.json.

Usage: python3 build.py [script.json] [output.mp4]

Voice: tries Microsoft Neural TTS (edge-tts, el-GR-NestorasNeural); if it is
unreachable, falls back to offline espeak-ng + MBROLA (mb-gr2, male).
Needs: ffmpeg, Pillow, and edge-tts or espeak-ng (+ mbrola-gr2).
"""
import json, os, subprocess, sys, tempfile, shutil, math
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BG_TOP, BG_BOT = (10, 25, 60), (2, 8, 22)
ACCENT, ACCENT2, WHITE, GREY = (255, 196, 0), (0, 170, 110), (255, 255, 255), (170, 185, 210)

def font(path, size): return ImageFont.truetype(path, size)

# ---------- voice ----------
def tts(text, out_wav, tmp):
    mp3 = os.path.join(tmp, "e.mp3")
    if shutil.which("edge-tts"):
        r = subprocess.run(["edge-tts", "--voice", "el-GR-NestorasNeural", "--rate", "+8%",
                            "--text", text, "--write-media", mp3],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.getsize(mp3) > 1000:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "1", out_wav], check=True)
            return "edge-tts (Nestoras)"
    raw = os.path.join(tmp, "raw.wav")
    subprocess.run(["espeak-ng", "-v", "mb-gr2", "-s", "160", "-p", "45", "-w", raw, text], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
                    "-af", "highpass=f=70,acompressor=threshold=-18dB:ratio=3,loudnorm=I=-16",
                    "-ar", "44100", "-ac", "1", out_wav], check=True)
    return "espeak-ng/MBROLA (mb-gr2)"

def duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", path]).strip())

# ---------- drawing ----------
def background():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    # pitch lines motif
    for i, r in enumerate((260, 420)):
        d.ellipse([W // 2 - r, 1350 - r, W // 2 + r, 1350 + r], outline=(25, 50, 95), width=4)
    d.line([(0, 1350), (W, 1350)], fill=(25, 50, 95), width=4)
    return img

BG = None

def ease(t): t = max(0, min(1, t)); return 1 - (1 - t) ** 3

def wrap(d, text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= maxw: cur = test
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def ctext(d, y, text, f, fill):
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

def header(d, meta, n, total):
    d.rectangle([0, 0, W, 210], fill=(5, 14, 36))
    d.rectangle([0, 210, W, 218], fill=ACCENT)
    ctext(d, 50, meta["title"], font(FONT_B, 64), WHITE)
    ctext(d, 135, meta["subtitle"], font(FONT_R, 38), GREY)
    # story dots
    seg = (W - 120) / total
    for i in range(total):
        x0 = 60 + i * seg + 6
        d.rounded_rectangle([x0, 250, x0 + seg - 12, 260], radius=5, fill=ACCENT if i <= n else (40, 60, 100))

def caption(d, text, t_frac):
    f = font(FONT_B, 46)
    lines = wrap(d, text, f, W - 160)
    # show a moving window of 3 lines, synced roughly to audio progress
    total = len(lines); win = 3
    start = min(max(0, int(t_frac * total) - 1), max(0, total - win))
    shown = lines[start:start + win]
    top = 1560
    d.rounded_rectangle([50, top - 30, W - 50, top + 3 * 66 + 20], radius=28, fill=(0, 0, 0))
    for i, ln in enumerate(shown):
        ctext(d, top + i * 66, ln, f, WHITE)

def card(img, slide, p):
    d = ImageDraw.Draw(img)
    off = int((1 - ease(p)) * 400)
    if slide["type"] == "match":
        y = 470 + off
        d.rounded_rectangle([60, y, W - 60, y + 760], radius=40, fill=(18, 36, 78), outline=ACCENT, width=5)
        fT = font(FONT_B, 58)
        for k, team in enumerate((slide["home"], slide["away"])):
            ty = y + 70 + k * 470
            ctext(d, ty, team, fT, WHITE)
        sf = font(FONT_B, 190)
        ctext(d, y + 200, slide["score"], sf, ACCENT)
        d.rounded_rectangle([140, y + 640, W - 140, y + 720], radius=40, fill=ACCENT2)
        ctext(d, y + 652, slide["note"], font(FONT_B, 42), WHITE)
        ctext(d, y + 420, "ΤΕΛΙΚΟ", font(FONT_R, 36), GREY)
    elif slide["type"] == "table":
        y = 430 + off
        ctext(d, y, slide["headline"], font(FONT_B, 72), ACCENT)
        for i, (pos, team, pts) in enumerate(slide["rows"]):
            ry = y + 150 + i * 220
            d.rounded_rectangle([60, ry, W - 60, ry + 180], radius=30,
                                fill=(18, 36, 78) if i else (60, 48, 0), outline=ACCENT if i == 0 else (50, 80, 140), width=4)
            d.text((110, ry + 50), pos, font=font(FONT_B, 76), fill=ACCENT)
            d.text((220, ry + 55), team, font=font(FONT_B, 64), fill=WHITE)
            pf = font(FONT_B, 76)
            d.text((W - 110 - d.textlength(pts, font=pf), ry + 50), pts, font=pf, fill=WHITE)
    else:  # intro / outro
        y = 650 + off
        ball = 150
        d.ellipse([W / 2 - ball, y - 40, W / 2 + ball, y - 40 + 2 * ball], fill=WHITE, outline=ACCENT, width=8)
        ctext(d, y + 50, "⚽" if False else "", font(FONT_B, 10), WHITE)
        # pentagon pattern
        cx, cy = W / 2, y - 40 + ball
        pts = [(cx + 60 * math.cos(math.radians(-90 + 72 * k)), cy + 60 * math.sin(math.radians(-90 + 72 * k))) for k in range(5)]
        d.polygon(pts, fill=(10, 25, 60))
        fH = font(FONT_B, 80)
        for i, ln in enumerate(wrap(d, slide["headline"], fH, W - 140)):
            ctext(d, y + 330 + i * 100, ln, fH, ACCENT if slide["type"] == "intro" else WHITE)

def render_slide(proc, meta, slide, n, total, dur):
    frames = int(round(dur * FPS))
    for f in range(frames):
        img = BG.copy()
        d = ImageDraw.Draw(img)
        header(d, meta, n, total)
        card(img, slide, f / (0.45 * FPS))
        caption(d, slide["voice"], f / max(1, frames))
        proc.stdin.write(img.tobytes())

def main():
    global BG
    here = os.path.dirname(os.path.abspath(__file__))
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "script.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "reel.mp4")
    meta = json.load(open(src, encoding="utf-8"))
    BG = background()
    tmp = tempfile.mkdtemp()
    slides = meta["slides"]
    wavs, durs, engine = [], [], None
    for i, s in enumerate(slides):
        w = os.path.join(tmp, f"v{i}.wav")
        engine = tts(s["voice"], w, tmp)
        durs.append(duration(w) + 0.5)
        wavs.append(w)
    print("voice engine:", engine)
    # audio: each clip padded to its slide length
    concat = os.path.join(tmp, "list.txt")
    with open(concat, "w") as fh:
        for i, w in enumerate(wavs):
            p = os.path.join(tmp, f"p{i}.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", w, "-af", f"adelay=150,apad",
                            "-t", f"{durs[i]:.3f}", p], check=True)
            fh.write(f"file '{p}'\n")
    audio = os.path.join(tmp, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat, audio], check=True)
    video = os.path.join(tmp, "video.mp4")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                             "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", video], stdin=subprocess.PIPE)
    for i, s in enumerate(slides):
        render_slide(proc, meta, s, i, len(slides), durs[i])
    proc.stdin.close(); proc.wait()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(tmp)
    print(f"done: {out} ({sum(durs):.1f}s)")

if __name__ == "__main__":
    main()
