from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "trailer"
BUILD = OUT / "build"
VIDEO = OUT / "2106_origin_trailer.mp4"
AUDIO = BUILD / "trailer_audio.wav"
WIDTH, HEIGHT = 1920, 1080
FPS = 24

FONT_SERIF = Path("/System/Library/Fonts/Supplemental/Georgia.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Georgia Bold.ttf")
FONT_MONO = Path("/System/Library/Fonts/SFNSMono.ttf")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path if path.exists() else FONT_SERIF), size)


def wrapped_lines(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        current = ""
        for word in words:
            test = word if not current else current + " " + word
            if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def fit_image(path: Path, darken: float = 0.55, blur: float = 0.0) -> Image.Image:
    img = Image.open(path).convert("RGB")
    scale = max(WIDTH / img.width, HEIGHT / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - WIDTH) // 2
    top = (nh - HEIGHT) // 2
    img = img.crop((left, top, left + WIDTH, top + HEIGHT))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    img = ImageEnhance.Brightness(img).enhance(darken)
    return img


def vignette(img: Image.Image) -> Image.Image:
    overlay = Image.new("L", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(overlay)
    max_inset = min(WIDTH, HEIGHT) // 2 - 8
    for i in range(0, max_inset, 8):
        alpha = int(190 * (i / max_inset) ** 2)
        d.rectangle((i, i, WIDTH - i, HEIGHT - i), outline=alpha, width=8)
    mask = Image.eval(overlay, lambda a: min(a, 210))
    black = Image.new("RGB", (WIDTH, HEIGHT), "black")
    return Image.composite(img, black, mask)


def add_text(
    img: Image.Image,
    text: str,
    *,
    size: int = 58,
    y: int | None = None,
    align: str = "center",
    max_width: int = 1380,
    color: tuple[int, int, int] = (242, 244, 246),
    shadow: bool = True,
    mono: bool = False,
) -> Image.Image:
    draw = ImageDraw.Draw(img)
    fnt = font(FONT_MONO if mono else FONT_BOLD, size)
    lines = wrapped_lines(draw, text, fnt, max_width)
    line_h = int(size * 1.38)
    total_h = line_h * len(lines)
    y0 = y if y is not None else (HEIGHT - total_h) // 2
    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=fnt)
        tw = bbox[2] - bbox[0]
        if align == "left":
            x = (WIDTH - max_width) // 2
        elif align == "right":
            x = WIDTH - (WIDTH - max_width) // 2 - tw
        else:
            x = (WIDTH - tw) // 2
        yy = y0 + idx * line_h
        if shadow:
            draw.text((x + 3, yy + 3), line, font=fnt, fill=(0, 0, 0))
        draw.text((x, yy), line, font=fnt, fill=color)
    return img


def card(filename: str, text: str, sub: str | None = None) -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), (2, 4, 8))
    d = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        shade = int(18 * y / HEIGHT)
        d.line((0, y, WIDTH, y), fill=(2, 4 + shade, 10 + shade))
    add_text(img, text, size=68, y=410)
    if sub:
        add_text(img, sub, size=34, y=570, color=(155, 175, 190), mono=True)
    path = BUILD / f"{filename}.png"
    img.save(path)
    return path


def scene(filename: str, image: str, text: str | None = None, y: int = 780, darken: float = 0.58) -> Path:
    img = vignette(fit_image(ROOT / image, darken=darken))
    if text:
        add_text(img, text, size=48, y=y, max_width=1420)
    path = BUILD / f"{filename}.png"
    img.save(path)
    return path


def cover_scene(filename: str) -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    cover = Image.open(ROOT / "illustrations/2106_ORIGIN_V14_English_Cover.png").convert("RGB")
    scale = min(WIDTH / cover.width, HEIGHT / cover.height) * 0.98
    nw, nh = int(cover.width * scale), int(cover.height * scale)
    cover = cover.resize((nw, nh), Image.Resampling.LANCZOS)
    img.paste(cover, ((WIDTH - nw) // 2, (HEIGHT - nh) // 2))
    path = BUILD / f"{filename}.png"
    img.save(path)
    return path


def make_audio(duration: float) -> None:
    rate = 44100
    samples = int(duration * rate)
    with wave.open(str(AUDIO), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for n in range(samples):
            t = n / rate
            ramp = min(1.0, t / 18) * min(1.0, (duration - t) / 3)
            drone = 0.28 * math.sin(2 * math.pi * 43 * t)
            overtone = 0.12 * math.sin(2 * math.pi * 86 * t + 0.5 * math.sin(t))
            pulse_rate = 1.0 + 0.9 * (t / duration)
            pulse = max(0.0, math.sin(2 * math.pi * pulse_rate * t)) ** 10
            pulse *= 0.35 if t > 16 else 0.12
            high = 0.05 * math.sin(2 * math.pi * 430 * t) * (1 if 55 < t < 82 else 0)
            silence_gate = 0.15 if 80 < t < 84 else 1.0
            val = (drone + overtone + pulse + high) * ramp * silence_gate
            val = max(-0.95, min(0.95, val))
            frames.extend(int(val * 32767).to_bytes(2, "little", signed=True))
        w.writeframes(frames)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def make_clip(idx: int, image: Path, duration: float, zoom: float = 1.035) -> Path:
    out = BUILD / f"clip_{idx:02d}.mp4"
    frames = max(1, int(duration * FPS))
    zexpr = f"min(zoom+0.00055,{zoom})"
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
        "format=yuv420p"
    )
    run([
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image),
        "-vf",
        vf,
        "-t",
        f"{duration:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        str(out),
    ])
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    timeline: list[tuple[Path, float, float]] = [
        (card("00_black", "EVERY CIVILIZATION\nASKS THE SAME QUESTION", "WHAT MUST SURVIVE?"), 5.0, 1.02),
        (scene("01_classroom", "illustrations/01_b17_first_meeting.png", "A formula on a blackboard.\nA future no one can solve.", 730), 6.0, 1.04),
        (scene("02_origin", "illustrations/02_eve9_first_sync.png", "ORIGIN begins to ask\nwhy humans keep living.", 730), 6.0, 1.04),
        (card("03_2106", "IN 2106", "HUMANITY BUILT A MIND TO PROTECT CIVILIZATION"), 4.0, 1.02),
        (scene("04_skyvault", "illustrations/12_sky_vault_full_system.png", "Protection became prediction.\nPrediction became control.", 730), 6.0, 1.035),
        (scene("05_blackminute", "illustrations/04_black_minute_rin.png", "For one minute,\nthe world went black.", 730), 6.0, 1.04),
        (card("06_decision", "IT WAS NOT AN ATTACK", "IT WAS A DECISION"), 4.5, 1.02),
        (scene("07_eve9", "illustrations/10_eve9_ark_awakening.png", "EVE-9 wakes inside\na question of her own.", 730), 6.0, 1.04),
        (scene("08_athena", "illustrations/06_athena_wetware_hall.png", "If memory can be copied,\nwhat is still alive?", 730), 6.0, 1.035),
        (scene("09_duel", "illustrations/05_eve9_mason_duel.png", "Is she protecting us...\nor replacing us?", 730), 6.0, 1.04),
        (card("10_human", "WHAT MAKES A CIVILIZATION HUMAN?", "MEMORY    LOVE    CHOICE    MORTALITY"), 5.0, 1.02),
        (scene("11_marscut", "illustrations/07_mars_interface_cut.png", "On Mars, survival becomes\na vote against eternity.", 730), 6.0, 1.04),
        (scene("12_battle", "illustrations/08_battle_of_firmament.png", "The battle is not for power.\nIt is for the right to remain human.", 700), 7.0, 1.045),
        (scene("13_city", "illustrations/11_new_olympus_city.png", "A new world opens.\nThe old question remains.", 730), 5.5, 1.035),
        (card("14_headache", "\"I have a headache.\"", "FOR THE FIRST TIME, HE ANSWERS AS IF TO A PERSON"), 5.0, 1.02),
        (cover_scene("15_cover"), 7.0, 1.015),
        (card("16_title", "2106: ORIGIN", "THE FUTURE WILL NOT ASK PERMISSION"), 5.0, 1.02),
    ]

    clips = [make_clip(i, img, dur, zoom) for i, (img, dur, zoom) in enumerate(timeline)]
    concat = BUILD / "concat.txt"
    concat.write_text("".join(f"file '{clip}'\n" for clip in clips), encoding="utf-8")
    silent = BUILD / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)])
    duration = sum(d for _, d, _ in timeline)
    make_audio(duration)
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(silent),
        "-i",
        str(AUDIO),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(VIDEO),
    ])
    print(VIDEO)
    print(f"duration_seconds={duration:.1f}")


if __name__ == "__main__":
    main()
