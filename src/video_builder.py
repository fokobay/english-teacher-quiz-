"""
Builds a pronunciation teaching video (1080x1080, TTS audio, 5 slides).
Uses MoviePy + gTTS + Pillow.
"""

import re
import numpy as np
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from src.logger import setup_logger

logger = setup_logger("video")

W, H    = 1080, 1080
FPS     = 24
ACCENT  = (50, 200, 255)
DARK_BG = (10, 25, 50)


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    fname = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for base in [
        "/run/current-system/sw/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/dejavu",
    ]:
        try:
            return ImageFont.truetype(f"{base}/{fname}", size)
        except Exception:
            continue
    return ImageFont.load_default()


def _center_text(draw, text, font, y, color, shadow=True):
    bb = draw.textbbox((0, 0), text, font=font)
    x  = (W - (bb[2] - bb[0])) // 2
    for dx in (-3, -2, -1, 0, 1, 2, 3):
        for dy in (-3, -2, -1, 0, 1, 2, 3):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)


def _wrap_centered(draw, text, font, y_start, color, max_width=900, line_gap=10):
    words  = text.split()
    lines  = []
    line   = ""
    for w in words:
        test = (line + " " + w).strip()
        bb   = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] > max_width and line:
            lines.append(line)
            line = w
        else:
            line = test
    if line:
        lines.append(line)

    y = y_start
    for ln in lines:
        bb = draw.textbbox((0, 0), ln, font=font)
        h  = bb[3] - bb[1]
        _center_text(draw, ln, font, y, color)
        y += h + line_gap
    return y


def _header(draw, text):
    draw.rectangle([0, 0, W, 120], fill=(*DARK_BG, 230))
    draw.rectangle([0, 0, W, 6],   fill=ACCENT)
    _center_text(draw, text, _font(50), 30, ACCENT)


def _footer(draw, text):
    draw.rectangle([0, H - 100, W, H], fill=(*DARK_BG, 210))
    draw.rectangle([0, H - 6,   W, H], fill=ACCENT)
    _center_text(draw, text, _font(36, bold=False), H - 78, (180, 180, 200))


class VideoBuilder:

    def build_pronunciation(self, content: dict, bg_path: Optional[Path], out: Path) -> Path:
        p        = self._parse(content["content"])
        word     = p.get("word",     "Word")
        phonetic = p.get("phonetic", "")
        wrong    = p.get("wrong",    "wrong version")
        correct  = p.get("correct",  "correct version")
        examples = p.get("examples", [])
        trick    = p.get("trick",    "Practice makes perfect!")

        bg = self._make_bg(bg_path)

        script     = (f"{word}. {word}. {word}. "
                      f"Correct pronunciation: {word}. "
                      + ". ".join(examples[:2])
                      + f". Memory tip: {trick}")
        audio_path = out.parent / "tts.mp3"
        gTTS(text=script, lang="en", slow=False).save(str(audio_path))
        audio = AudioFileClip(str(audio_path))
        total = audio.duration

        fixed_durs  = [3, 4, 4, 3]
        slide4_dur  = max(total - sum(fixed_durs), 4)
        seg_durs    = [3, 4, 4, slide4_dur, 3]
        if sum(seg_durs) > total:
            slide4_dur = max(total - 14, 2)
            seg_durs   = [3, 4, 4, slide4_dur, 3]

        frames = [
            self._slide_word(bg, word, phonetic),
            self._slide_listen(bg, word),
            self._slide_compare(bg, wrong, correct),
            self._slide_examples(bg, word, examples),
            self._slide_tip(bg, trick),
        ]

        # BUG FIX: original code only closed `video` inside the try block.
        # If write_videofile() raised an exception mid-write the VideoFileClip
        # object leaked file handles.  Now video is declared before try so
        # finally can always close it safely.  Added a nested try/except inside
        # finally to prevent a secondary exception from masking the original.
        video = None
        try:
            clips = [ImageClip(f, duration=d) for f, d in zip(frames, seg_durs)]
            video = concatenate_videoclips(clips, method="compose").set_audio(audio).set_duration(total)
            video.write_videofile(str(out), fps=FPS, codec="libx264",
                                  audio_codec="aac", preset="ultrafast",
                                  threads=1, logger=None)
        finally:
            try:
                if video is not None:
                    video.close()
            except Exception:
                pass
            try:
                audio.close()
            except Exception:
                pass
            audio_path.unlink(missing_ok=True)

        logger.info("Pronunciation video ready ✓")
        return out

    # ── Slides ────────────────────────────────────────────────────────

    def _slide_word(self, bg, word, phonetic):
        img  = Image.fromarray(bg.copy())
        draw = ImageDraw.Draw(img)
        _header(draw, "🎤  PRONUNCIATION")
        _center_text(draw, word.upper(), _font(130), H // 2 - 110, ACCENT)
        if phonetic:
            _center_text(draw, phonetic, _font(64, False), H // 2 + 50, (200, 200, 200))
        _footer(draw, "Listen carefully  👂")
        return np.array(img)

    def _slide_listen(self, bg, word):
        img  = Image.fromarray(bg.copy())
        draw = ImageDraw.Draw(img)
        _header(draw, "🔊  LISTEN & REPEAT")
        _center_text(draw, word.upper(), _font(110), H // 2 - 90, (255, 255, 255))
        _center_text(draw, "Say it 3 times aloud!", _font(56, False), H // 2 + 60, ACCENT)
        _footer(draw, "Repeat after the audio  🗣")
        return np.array(img)

    def _slide_compare(self, bg, wrong, correct):
        img  = Image.fromarray(bg.copy())
        draw = ImageDraw.Draw(img)
        _header(draw, "❌  WRONG   vs   ✅  CORRECT")

        draw.rectangle([40, 150, W - 40, 490], fill=(70, 10, 10))
        draw.rectangle([40, 150, W - 40, 156], fill=(255, 80, 80))
        _center_text(draw, "❌  WRONG", _font(58), 170, (255, 80,  80))
        _wrap_centered(draw, wrong,     _font(52, False), 255, (255, 180, 180), max_width=940)

        draw.rectangle([40, 530, W - 40, 870], fill=(10, 60, 20))
        draw.rectangle([40, 530, W - 40, 536], fill=(80, 255, 120))
        _center_text(draw, "✅  CORRECT", _font(58), 550, (80, 255, 120))
        _wrap_centered(draw, correct,    _font(52, False), 635, (160, 255, 190), max_width=940)

        _footer(draw, "Practice the correct one!  💪")
        return np.array(img)

    def _slide_examples(self, bg, word, examples):
        img  = Image.fromarray(bg.copy())
        draw = ImageDraw.Draw(img)
        _header(draw, "📝  EXAMPLE SENTENCES")
        y = 160
        for i, ex in enumerate(examples[:3], 1):
            if y > 840:
                break
            _center_text(draw, f"— {i} —", _font(46), y, ACCENT)
            y += 58
            y = _wrap_centered(draw, ex, _font(44, False), y, (220, 220, 220),
                               max_width=960, line_gap=12)
            y += 32
        _footer(draw, "Use it in a sentence today!  ✍️")
        return np.array(img)

    def _slide_tip(self, bg, trick):
        img  = Image.fromarray(bg.copy())
        draw = ImageDraw.Draw(img)
        _header(draw, "💡  MEMORY TRICK")
        draw.rectangle([50, 200, W - 50, 820], fill=(15, 35, 70))
        draw.rectangle([50, 200, W - 50, 208], fill=ACCENT)
        draw.rectangle([50, 812, W - 50, 820], fill=ACCENT)
        _wrap_centered(draw, trick, _font(54, False), 280, (255, 255, 255),
                       max_width=940, line_gap=18)
        _footer(draw, "Follow for daily English tips!  🔔")
        return np.array(img)

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_bg(self, bg_path: Optional[Path]) -> np.ndarray:
        if bg_path and bg_path.exists():
            img    = Image.open(bg_path).convert("RGB")
            iw, ih = img.size
            s      = min(iw, ih)
            img    = img.crop(((iw - s) // 2, (ih - s) // 2, (iw + s) // 2, (ih + s) // 2))
            img    = img.resize((W, H), Image.LANCZOS)
            img    = img.filter(ImageFilter.GaussianBlur(4))
            img    = ImageEnhance.Color(img).enhance(0.5)
        else:
            arr  = np.zeros((H, W, 3), dtype=np.uint8)
            dark = np.array(DARK_BG, dtype=np.float32)
            for y in range(H):
                arr[y] = (dark * (1 - y / H * 0.3)).astype(np.uint8)
            img = Image.fromarray(arr)
        return (np.array(img).astype(np.float32) * 0.55).astype(np.uint8)

    def _parse(self, text: str) -> dict:
        result   = {}
        examples = []
        lines    = text.replace("\\n", "\n").split("\n")

        for line in lines:
            c  = re.sub(r"\*+", "", line).strip()
            c  = re.sub(r"_(.+?)_", r"\1", c).strip()
            ll = c.lower()

            if not result.get("word"):
                m = re.search(r"([A-Za-z]{2,})\s+(/[^/]+/)", c)
                if m:
                    result["word"]     = m.group(1).capitalize()
                    result["phonetic"] = m.group(2)
                else:
                    m2 = re.match(r"(?:word|🔤)[:\s]+([A-Za-z\-']{2,})", c, re.IGNORECASE)
                    if m2:
                        result["word"] = m2.group(1).strip().capitalize()

            if not result.get("phonetic"):
                m = re.search(r"/([^/]{1,30})/", c)
                if m and len(m.group(1)) > 1:
                    result["phonetic"] = "/" + m.group(1) + "/"

            # BUG FIX: the "correct" branch checked `"mistake" not in ll` but
            # a line like "✅ Correct: /ˈwɔːtər/" contains neither "wrong" nor
            # "mistake" yet the word "correct" appears — that's fine.  The real
            # issue was that BOTH branches required a ":" in the line, so a line
            # like "✅ Correct /ˈwɔːtər/" (space instead of colon) was silently
            # dropped.  Relaxed the colon requirement: split on first ":" OR
            # first space after the keyword.
            if ("wrong" in ll or "❌" in line or "people say" in ll):
                # Extract value after ":" or after the keyword itself
                val = c.split(":", 1)[-1].strip().strip('"').strip("'") if ":" in c else ""
                if not val:
                    # Try to grab everything after the emoji / keyword
                    m = re.search(r"(?:wrong|❌|people say)[:\s]+(.+)", c, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip().strip('"').strip("'")
                if val and not result.get("wrong"):
                    result["wrong"] = val

            elif ("correct" in ll or "✅" in line) and "wrong" not in ll and "mistake" not in ll:
                val = c.split(":", 1)[-1].strip().strip('"').strip("'") if ":" in c else ""
                if not val:
                    m = re.search(r"(?:correct|✅)[:\s]+(.+)", c, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip().strip('"').strip("'")
                if val and len(val) > 3 and not result.get("correct"):
                    result["correct"] = val

            elif c.startswith(("•", "→", "-")) and len(c) > 5:
                examples.append(c.lstrip("•→- ").strip())

            elif ("trick" in ll or "tip" in ll or "memory" in ll) and ":" in c:
                val = c.split(":", 1)[-1].strip()
                if len(val) > 10 and not result.get("trick"):
                    result["trick"] = val

        result["examples"] = examples[:3]

        if not result.get("word"):
            result["word"] = "English"
        if not result.get("wrong"):
            result["wrong"] = "Incorrect pronunciation"
        if not result.get("correct"):
            result["correct"] = "Correct pronunciation"
        if not result.get("trick"):
            result["trick"] = "Practice makes perfect — say it 3 times aloud!"

        return result
