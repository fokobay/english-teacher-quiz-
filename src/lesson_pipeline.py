"""
Lesson pipeline for one group:
Generate → Fetch image → Post → Pin → Quick poll → Record
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.logger            import setup_logger
from src.content_generator import ContentGenerator
from src.image_fetcher     import ImageFetcher
from src.video_builder     import VideoBuilder
from src.telegram_poster   import TelegramPoster
from src.quiz_generator    import QuizGenerator
from src.tracker           import Tracker
from src.cleanup           import cleanup
from src                   import api

log = setup_logger("lesson")

# BUG FIX: WORK_DIR was relative to CWD (workdir/) which breaks when the process
# is started from a directory other than /app. Now anchored to DATA_DIR so it
# always ends up in the same persistent volume as other bot data.
_DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
WORK_DIR  = _DATA_DIR / "workdir"
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Lazy singletons — created on first use so import never fails
# even if env-vars (GROQ_API_KEY, etc.) are not set at import time.
_tracker:  Optional[Tracker]          = None
_gen:      Optional[ContentGenerator] = None
_poster:   Optional[TelegramPoster]   = None
_fetcher:  Optional[ImageFetcher]     = None
_quiz_gen: Optional[QuizGenerator]    = None


def _get_singletons():
    global _tracker, _gen, _poster, _fetcher, _quiz_gen
    if _tracker is None:
        _tracker  = Tracker()
        _gen      = ContentGenerator()
        _poster   = TelegramPoster()
        _fetcher  = ImageFetcher()
        _quiz_gen = QuizGenerator()
    return _tracker, _gen, _poster, _fetcher, _quiz_gen


def run_lesson(chat_id: str) -> bool:
    tracker, gen, poster, fetcher, quiz_gen = _get_singletons()

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = WORK_DIR / f"lesson_{ts}_{str(chat_id)[-6:]}"
    work.mkdir(exist_ok=True)

    try:
        content = _generate_content(tracker, gen, retries=3)
        if not content:
            raise RuntimeError("Content generation failed after 3 retries")

        post_type = content["post_type"]
        text      = content["content"]
        subject   = content.get("subject", post_type)
        keywords  = content.get("image_keywords", [])
        log.info(f"[{chat_id}] Lesson [{post_type}] {subject}")

        bg = fetcher.fetch(post_type, work / "bg.jpg", keywords)

        if post_type == "pronunciation":
            video_path = work / "lesson.mp4"
            VideoBuilder().build_pronunciation(content, bg, video_path)
            msg_id = poster.post_video(
                text, video_path=video_path,
                chat_id=chat_id, post_type=post_type,
            )
        elif bg and bg.exists():
            msg_id = poster.post_photo(
                text, image_path=bg,
                chat_id=chat_id, post_type=post_type,
            )
        else:
            log.warning(f"[{chat_id}] No image — posting text only")
            msg_id = poster.post_text(text, chat_id=chat_id, post_type=post_type)

        if msg_id:
            api.pin(chat_id, int(msg_id))

        time.sleep(2)
        try:
            quiz = quiz_gen.generate(post_type, text)
            if quiz:
                poster.post_poll(quiz, chat_id=chat_id)
        except Exception as e:
            log.warning(f"[{chat_id}] Lesson quiz poll skipped: {e}")

        tracker.record(post_type, subject, text[:80])
        cleanup([work])
        log.info(f"[{chat_id}] Lesson done ✓")
        return True

    except Exception as e:
        log.exception(f"[{chat_id}] Lesson error: {e}")
        cleanup([work])
        return False


def _generate_content(
    tracker: Tracker,
    gen: ContentGenerator,
    retries: int = 3,
) -> Optional[dict]:
    prefer = (tracker.least_used_types(n=3) or [None])[0]
    for attempt in range(retries):
        try:
            content = gen.generate(prefer if attempt == 0 else None)
            subject = content.get("subject", "")
            if subject and tracker.was_posted(subject):
                log.warning(f"Duplicate '{subject}' — retry")
                prefer = None
                continue
            return content
        except Exception as e:
            log.warning(f"Generate attempt {attempt + 1} failed: {e}")
            time.sleep(3)
    return None
