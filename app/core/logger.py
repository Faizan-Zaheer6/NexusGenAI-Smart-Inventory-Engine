import logging
import sys

# Standard high-fidelity log format for enterprise debugging
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s:%(filename)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(default_level: int = logging.INFO) -> logging.Logger:
    """
    Configures the root logger for cloud environments (Console only to prevent local write crashes).
    """
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Handler (Perfect for Vercel/Cloud stream logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(default_level)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(default_level)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)

    logger = logging.getLogger("nexus_ai")
    logger.info("Logging system initialized. Stream routed to Cloud Console stdout.")
    
    return logger

# Global production singleton instance
logger = setup_logging()