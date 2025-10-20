import logging
import sys
from typing import Any

# Configure logging
def setup_logger(name: str = "roco_kingdom") -> logging.Logger:
    """Set up application logger with consistent formatting."""
    logger = logging.getLogger(name)

    # Only add handlers if none exist (avoid duplicate handlers)
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Console handler with formatting
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

# Create default logger
logger = setup_logger()


class LoggerMixin:
    """Mixin to add logging capability to any class."""

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return logging.getLogger(self.__class__.__name__)
