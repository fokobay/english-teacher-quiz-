import logging, sys

def setup_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)-12s] %(levelname)-7s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        log.addHandler(h)
    log.setLevel(logging.INFO)
    return log
