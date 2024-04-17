from kvdb.utils.logs import logger, null_logger, Logger

# Global Level
_DEBUG_MODE_ENABLED = False
_COMPONENT_DEBUGS = {
    'main': False,
    'queue': False,
    'worker': False,
    'tasks': False,
    'wraps': False,
    'types': False,
}


# autologger = logger if _DEBUG_MODE_ENABLED else null_logger

def get_autologger(component: str) -> 'Logger':
    """
    Returns the autologger
    """
    if _DEBUG_MODE_ENABLED: return logger
    return logger if _COMPONENT_DEBUGS.get(component, False) else null_logger