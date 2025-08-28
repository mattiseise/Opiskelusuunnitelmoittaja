import logging
import json
import os
from typing import Optional


def setup_logger(config_path: str = "config.json") -> logging.Logger:
    """
    Set up logger based on configuration file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configured logger instance
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    log_config = config.get('logging', {})
    
    # Create logger
    logger = logging.getLogger('suunnitelmoittaja')
    logger.setLevel(getattr(logging, log_config.get('level', 'INFO')))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(log_config.get('format', 
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # File handler
    log_file = config.get('files', {}).get('log_file', 'logs/app.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler (if enabled)
    if log_config.get('console_output', True):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_config.get('level', 'INFO')))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger