import os



from lzl.logging import (
    get_logger, 
    null_logger, 
    Logger,
    NullLogger
)

logger_level: str = os.getenv('LOGGER_LEVEL', 'INFO').upper()
logger = get_logger(
    __name__, 
    logger_level
)
