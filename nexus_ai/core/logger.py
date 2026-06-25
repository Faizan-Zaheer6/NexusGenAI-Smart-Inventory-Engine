import logging
from pathlib import Path

# Resolve project root (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_FILE_PATH = PROJECT_ROOT / "nexus_ai_errors.log"

# Create logger
logger = logging.getLogger("nexus_ai")
logger.setLevel(logging.INFO)

# Console handler (INFO and above)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
console_handler.setFormatter(console_formatter)

# File handler (WARNING and above)
file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setLevel(logging.WARNING)
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s")
file_handler.setFormatter(file_formatter)

# Add handlers if not already added (avoid duplicate handlers on reload)
if not logger.handlers:
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
