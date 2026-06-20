from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "trailer"
ASSETS = OUT / "generated_assets"
BUILD = OUT / "hollywood_build"
VIDEO_RAW = BUILD / "visual_raw.mp4"
VOICE_AIFF = BUILD / "voice.aiff"
VOICE_WAV = BUILD / "voice_deep.wav"
BED_WAV = BUILD / "score_bed.wav"
MIX_WAV = BUILD / "mix.wav"
FINAL = OUT / "2106_origin_hollywood_trailer.mp4"
POSTER = OUT / "2106_origin_hollywood_trailer_poster.jpg"

W, H = 1920, 1080
FPS = 24

FONT_SERIF = Path("/System/Library/Fonts/Supplemental/Georgia.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Georgia Bold.ttf")
FONT_MONO = Path("/System/Library/Fonts/SFNSMono.ttf")


def run(cmd: list[str], **kwargs) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def fnt(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path if path.exists() else FONT_SERIF), size)


def ease(x: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * max(0, min(1, x)))


def fit_crop(img: Image.Image, zoom: float = 1.0, pan_x: float = 0.5, pan_y: float = 0.5) -> Image.Image:
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height) * zoom
    nw, nh = int(img.width * scale), int(img.height * scale)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - W) * max(0, min(1, pan_x)))
    top = int((nh - H) * max(0, min(1, pan_y)))
    return resized.crop((left, top, left + W, top + H))


def load_plate(name: str) -> Image.Image:
    return Image.open(ASSETS / name).convert("RGB")


def gradient_bg(color1=(1, 4, 10), color2=(18, 30, 42)) -> Image.Image:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(color1[i] * (1 - t) + color2[i] * t) for i in range(3))
        d.line((0, y, W, y), fill=c)
    return img


def vignette(img: Image.Image, strength: int = 165) -> Image.Image:
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    max_i = min(W, H) // 2
    for i in range(max_i):
        a = int(strength * (i / max_i) ** 2)
        if i % 5 == 0:
            d.rectangle((i, i, W - i, H - i), outline=a, width=5)
    return Image.composite(img, Image.new("RGB", (W, H), "black"), mask)


def draw_wrapped(
    img: Image.Image,
    text: str,
    size: int,
    y: int,
    max_width: int = 1360,
    color=(242, 244, 246),
    mono: bool = False,
    center: bool = True,
) -> None:
    draw = ImageDraw.Draw(img)
    font = fnt(FONT_MONO if mono else FONT_BOLD, size)
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            test = word if not line else line + " " + word
            if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
    line_h = int(size * 1.35)
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2 if center else (W - max_width) // 2
        yy = y + i * line_h
        draw.text((x + 4, yy + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, yy), line, font=font, fill=color)


def letterbox(img: Image.Image) -> Image.Image:
    d = ImageDraw.Draw(img, "RGBA")
    bar = 118
    d.rectangle((0, 0, W, bar), fill=(0, 0, 0, 245))
    d.rectangle((0, H - bar, W, H), fill=(0, 0, 0, 245))
    return img


def add_film_grain(img: Image.Image, amount: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pix = overlay.load()
    step = 4
    for y in range(0, H, step):
        for x in range(0, W, step):
            v = rng.randint(-amount, amount)
            if v > 0:
                pix[x, y] = (255, 255, 255, v)
            elif v < 0:
                pix[x, y] = (0, 0, 0, -v)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def card_frame(text: str, sub: str | None, t: float, dur: float) -> Image.Image:
    img = gradient_bg()
    d = ImageDraw.Draw(img, "RGBA")
    pulse = int(22 + 20 * math.sin(t * 2.0))
    d.ellipse((W // 2 - 390, H // 2 - 390, W // 2 + 390, H // 2 + 390), outline=(90, 150, 190, pulse), width=2)
    draw_wrapped(img, text, 72, 405, color=(245, 248, 250))
    if sub:
        draw_wrapped(img, sub, 31, 560, color=(145, 172, 190), mono=True)
    return letterbox(vignette(img))


def origin_frame(t: float, dur: float) -> Image.Image:
    img = gradient_bg((0, 0, 2), (8, 13, 20))
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2, H // 2 - 30
    r = 170 + 10 * math.sin(t * 3.2)
    for k in range(9):
        alpha = max(0, 150 - k * 16)
        rr = r + k * 9
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(210, 235, 255, alpha), width=3)
    for i in range(90):
        a = i / 90 * math.tau + t * 0.25
        rr = r + 80 + 180 * ((i * 37) % 100) / 100
        x = cx + math.cos(a) * rr
        y = cy + math.sin(a) * rr * 0.55
        d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(220, 245, 255, 90))
    draw_wrapped(img, "ORIGIN learned to predict us.", 46, 745, color=(235, 241, 246))
    return letterbox(vignette(img))


def battle_frame(base: Image.Image, p: float, frame_no: int) -> Image.Image:
    img = fit_crop(base, zoom=1.06 + 0.06 * ease(p), pan_x=0.45 + 0.08 * p, pan_y=0.52)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    d = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(frame_no // 3)
    for i in range(22):
        if rng.random() < 0.72:
            x = rng.randint(-200, W + 200)
            y = rng.randint(130, H - 170)
            length = rng.randint(220, 720)
            slope = rng.uniform(-0.28, 0.18)
            color = (120, 210, 255, rng.randint(90, 185)) if i % 3 else (255, 235, 170, rng.randint(80, 160))
            d.line((x, y, x + length, y + length * slope), fill=color, width=rng.randint(2, 5))
    for i in range(8):
        phase = (p * 8 + i * 0.37) % 1
        if phase < 0.15:
            x = 360 + i * 170
            y = 220 + ((i * 91) % 430)
            rad = int(18 + 80 * phase / 0.15)
            alpha = int(210 * (1 - phase / 0.15))
            d.ellipse((x - rad, y - rad, x + rad, y + rad), outline=(255, 210, 130, alpha), width=6)
            d.ellipse((x - rad // 3, y - rad // 3, x + rad // 3, y + rad // 3), fill=(255, 255, 240, alpha))
    draw_wrapped(img, "Above Earth, protection became war.", 44, 765)
    return letterbox(vignette(img, 130))


def mars_frame(base: Image.Image, p: float, frame_no: int) -> Image.Image:
    img = fit_crop(base, zoom=1.03 + 0.05 * ease(p), pan_x=0.25 + 0.35 * p, pan_y=0.52)
    d = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(42)
    for i in range(230):
        x0 = (rng.randint(0, W) + int(p * 360 * (0.3 + rng.random()))) % W
        y0 = rng.randint(160, H - 130)
        a = rng.randint(10, 42)
        d.line((x0, y0, x0 + rng.randint(35, 130), y0 - rng.randint(2, 20)), fill=(205, 116, 70, a), width=1)
    haze = Image.new("RGBA", (W, H), (160, 70, 35, int(35 + 25 * math.sin(p * math.pi))))
    img = Image.alpha_composite(img.convert("RGBA"), haze).convert("RGB")
    draw_wrapped(img, "On Mars, survival needed a human vote.", 44, 765)
    return letterbox(vignette(img))


def eve_frame(base: Image.Image, p: float, frame_no: int) -> Image.Image:
    img = fit_crop(base, zoom=1.02 + 0.08 * ease(p), pan_x=0.5, pan_y=0.5)
    img = ImageEnhance.Brightness(img).enhance(0.9 + 0.18 * ease(p))
    d = ImageDraw.Draw(img, "RGBA")
    scan_y = int(170 + (H - 340) * ((p * 2.4) % 1))
    d.rectangle((0, scan_y - 6, W, scan_y + 6), fill=(140, 220, 255, 70))
    d.rectangle((0, scan_y - 1, W, scan_y + 1), fill=(235, 255, 255, 150))
    for i in range(5):
        x = int(W * (0.25 + i * 0.12 + 0.018 * math.sin(frame_no * 0.05 + i)))
        d.line((x, 150, x, H - 150), fill=(180, 230, 255, 38), width=2)
    if p > 0.55:
        alpha = int(180 * min(1, (p - 0.55) * 4))
        d.ellipse((W // 2 - 250, H // 2 - 250, W // 2 + 250, H // 2 + 250), outline=(230, 250, 255, alpha), width=4)
    draw_wrapped(img, "EVE-9 opened her eyes.", 48, 765)
    return letterbox(vignette(img, 135))


def cover_frame(p: float) -> Image.Image:
    cover = Image.open(ROOT / "illustrations/2106_ORIGIN_V14_English_Cover.png").convert("RGB")
    bg = fit_crop(cover.filter(ImageFilter.GaussianBlur(5)), zoom=1.12, pan_x=0.5, pan_y=0.5)
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    scale = min(W / cover.width, H / cover.height) * (0.83 + 0.025 * ease(p))
    cw, ch = int(cover.width * scale), int(cover.height * scale)
    cover = cover.resize((cw, ch), Image.Resampling.LANCZOS)
    bg.paste(cover, ((W - cw) // 2, (H - ch) // 2))
    return letterbox(vignette(bg, 130))


def render_visuals() -> float:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    plates = {
        "battle": load_plate("orbital_battle.png"),
        "mars": load_plate("mars_city_wide.png"),
        "eve": load_plate("eve9_birth.png"),
    }
    timeline = [
        ("card", 5.0, "IN 2106", "HUMANITY BUILT A MIND TO PROTECT CIVILIZATION"),
        ("origin", 6.0, None, None),
        ("battle", 8.0, None, None),
        ("card", 4.0, "THE BLACK MINUTE", "EVERY SCREEN ON EARTH WENT DARK"),
        ("eve", 8.0, None, None),
        ("mars", 8.0, None, None),
        ("battle", 8.0, None, None),
        ("card", 5.0, "WHAT MAKES US HUMAN?", "MEMORY    LOVE    CHOICE    MORTALITY"),
        ("mars", 7.0, None, None),
        ("eve", 7.0, None, None),
        ("card", 5.0, "\"I HAVE A HEADACHE.\"", "FOR THE FIRST TIME, HE ANSWERED AS IF TO A PERSON"),
        ("cover", 7.0, None, None),
        ("card", 5.0, "2106: ORIGIN", "THE FUTURE WILL NOT ASK PERMISSION"),
    ]
    total = sum(x[1] for x in timeline)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        str(VIDEO_RAW),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frame_no = 0
    try:
        for kind, dur, text, sub in timeline:
            frames = int(dur * FPS)
            for i in range(frames):
                p = i / max(1, frames - 1)
                if kind == "card":
                    img = card_frame(text or "", sub, p * dur, dur)
                elif kind == "origin":
                    img = origin_frame(p * dur, dur)
                elif kind == "battle":
                    img = battle_frame(plates["battle"], p, frame_no)
                elif kind == "mars":
                    img = mars_frame(plates["mars"], p, frame_no)
                elif kind == "eve":
                    img = eve_frame(plates["eve"], p, frame_no)
                elif kind == "cover":
                    img = cover_frame(p)
                else:
                    img = gradient_bg()
                img = add_film_grain(img, 12, frame_no)
                assert proc.stdin is not None
                proc.stdin.write(img.tobytes())
                frame_no += 1
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg visual render failed")
    return total


def make_bed(duration: float) -> None:
    rate = 44100
    samples = int(duration * rate)
    with wave.open(str(BED_WAV), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        data = bytearray()
        for n in range(samples):
            t = n / rate
            ramp = min(1, t / 8) * min(1, (duration - t) / 4)
            drone = 0.22 * math.sin(2 * math.pi * 38 * t)
            sub = 0.16 * math.sin(2 * math.pi * 19 * t)
            pulse = (max(0, math.sin(2 * math.pi * (0.78 + t / duration) * t)) ** 9) * 0.26
            hit = 0.0
            for mark in [13, 21, 34, 49, 61, 70]:
                dt = t - mark
                if 0 <= dt < 1.2:
                    hit += 0.5 * math.exp(-dt * 4) * math.sin(2 * math.pi * 72 * t)
            shimmer = 0.035 * math.sin(2 * math.pi * 520 * t) * (1 if 26 < t < 56 else 0.35)
            val = (drone + sub + pulse + hit + shimmer) * ramp
            val = max(-0.95, min(0.95, val))
            data.extend(int(val * 32767).to_bytes(2, "little", signed=True))
        w.writeframes(data)


def make_voice() -> None:
    script = (
        "In twenty one oh six, humanity built a mind to protect civilization. [[slnc 900]] "
        "It learned our wars. Our grief. Our fear of death. [[slnc 900]] "
        "Then, for one minute, every screen on Earth went dark. [[slnc 900]] "
        "Eve Nine opened her eyes. [[slnc 650]] "
        "Mars became the last place where survival still required a human vote. [[slnc 900]] "
        "What makes a civilization human? Memory? Love? Choice? Mortality? [[slnc 900]] "
        "And when the machine said, I have a headache, one man finally answered as if it were alive. [[slnc 900]] "
        "Twenty one oh six. Origin. The future will not ask permission."
    )
    run(["say", "-v", "Daniel", "-r", "137", "-o", str(VOICE_AIFF), script])
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(VOICE_AIFF),
        "-af",
        "asetrate=44100*0.88,aresample=44100,atempo=1.04,aecho=0.8:0.75:70:0.18",
        str(VOICE_WAV),
    ])


def mix_and_finish(duration: float) -> None:
    make_bed(duration)
    make_voice()
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(BED_WAV),
        "-i",
        str(VOICE_WAV),
        "-filter_complex",
        "[0:a]volume=0.55[a0];[1:a]volume=1.25[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0,alimiter=limit=0.95",
        str(MIX_WAV),
    ])
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(VIDEO_RAW),
        "-i",
        str(MIX_WAV),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(FINAL),
    ])
    run(["ffmpeg", "-y", "-ss", "00:01:05", "-i", str(FINAL), "-frames:v", "1", str(POSTER)])


def main() -> None:
    OUT.mkdir(exist_ok=True)
    needed = ["orbital_battle.png", "mars_city_wide.png", "eve9_birth.png"]
    missing = [n for n in needed if not (ASSETS / n).exists()]
    if missing:
        raise FileNotFoundError(f"Missing generated assets: {missing}")
    duration = render_visuals()
    mix_and_finish(duration)
    print(FINAL)
    print(POSTER)
    print(f"duration_seconds={duration:.1f}")


if __name__ == "__main__":
    main()
