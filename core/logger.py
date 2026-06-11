import logging
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        return json.dumps(log_data, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',
        'INFO': '\033[92m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[95m',
        'RESET': '\033[0m'
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def get_logger(name: str, log_level: str = 'INFO') -> logging.Logger:
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(log_level.upper())
    logger.propagate = False
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    file_handler = RotatingFileHandler(
        'process_priority_manager.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = JsonFormatter()
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


def log_with_context(logger: logging.Logger, level: str, message: str, **kwargs: Any):
    extra = kwargs.copy()
    record = logger.makeRecord(
        logger.name,
        getattr(logging, level.upper()),
        '',
        0,
        message,
        (),
        None
    )
    record.extra = extra
    logger.handle(record)


class StructuredLogger:
    def __init__(self, name: str):
        self._logger = get_logger(name)
    
    def debug(self, message: str, **kwargs: Any):
        self._logger.debug(message, extra=kwargs)
    
    def info(self, message: str, **kwargs: Any):
        self._logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs: Any):
        self._logger.warning(message, extra=kwargs)
    
    def error(self, message: str, **kwargs: Any):
        self._logger.error(message, extra=kwargs)
    
    def critical(self, message: str, **kwargs: Any):
        self._logger.critical(message, extra=kwargs)
    
    def exception(self, message: str, **kwargs: Any):
        self._logger.exception(message, extra=kwargs)