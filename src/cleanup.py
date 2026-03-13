import shutil
from pathlib import Path
from src.logger import setup_logger

logger = setup_logger("cleanup")


def cleanup(paths: list):
    for p in paths:
        try:
            path = Path(p)
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
        except Exception as e:
            logger.warning(f"Cleanup failed {p}: {e}")
