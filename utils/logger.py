import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
    "RESET": "\033[0m",
}

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        log_color = COLORS.get(record.levelname, COLORS["RESET"])
        record.levelname = f"{log_color}{record.levelname}{COLORS['RESET']}"
        return super().format(record)

_logger: Optional[logging.Logger] = None

def setup_logger(name: str = "deepseek_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        return logger
    
    return logger

def init_file_logger(logs_dir: Path) -> None:
    global _logger
    
    if _logger is None:
        _logger = logging.getLogger("deepseek_agent")
        _logger.setLevel(logging.DEBUG)
    
    _logger.handlers = []
    
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"{datetime.now().strftime('%Y%m%d')}.log"
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    _logger.addHandler(file_handler)

def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger
