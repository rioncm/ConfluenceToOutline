"""
Logging configuration for the Confluence processing system.

This module provides centralized logging setup with consistent formatting
and configurable levels for different components.
"""
import logging
import sys
from typing import Optional


def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up logging configuration for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to also log to a file
        
    Returns:
        Configured logger instance
    """
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get the main logger
    logger = logging.getLogger('confluence_processor')
    logger.setLevel(level)
    
    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Name for the logger (usually __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f'confluence_processor.{name}')


class ProgressLogger:
    """
    Helper class for logging progress of long-running operations.
    """
    
    def __init__(self, logger: logging.Logger, operation: str, total: int):
        self.logger = logger
        self.operation = operation
        self.total = total
        self.current = 0
        self.logger.info(f"Starting {operation} - {total} items to process")
    
    def update(self, increment: int = 1, message: str = ""):
        """Update progress counter and log if needed."""
        self.current += increment
        
        # Log progress at 25%, 50%, 75%, 100%
        progress_percent = (self.current / self.total) * 100
        if self.current == self.total or progress_percent in [25, 50, 75]:
            status_msg = f"{self.operation} progress: {self.current}/{self.total} ({progress_percent:.0f}%)"
            if message:
                status_msg += f" - {message}"
            self.logger.info(status_msg)
    
    def complete(self, message: str = ""):
        """Mark operation as complete."""
        complete_msg = f"Completed {self.operation} - {self.total} items processed"
        if message:
            complete_msg += f" - {message}"
        self.logger.info(complete_msg)