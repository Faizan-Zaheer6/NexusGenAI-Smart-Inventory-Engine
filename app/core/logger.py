import logging
import sys
from pathlib import Path

# Resolve project root dynamically (parent of app directory)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_FILE_PATH = PROJECT_ROOT / "nexus_ai_errors.log"

# Define a standard high-fidelity log format for enterprise debugging
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s:%(filename)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(default_level: int = logging.INFO) -> logging.Logger:
    """
    Configures the root logger to output to both console (stdout) and a dedicated error file.
    """
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(default_level)
    console_handler.setFormatter(formatter)

    # 2. File Handler (Error Logging)
    file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)  # Focus on warnings/errors
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(default_level)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logger = logging.getLogger("nexus_ai")
    logger.info("Logging system initialized. Outputting to Console and %s", LOG_FILE_PATH)
    
    return logger

logger = setup_logging()
