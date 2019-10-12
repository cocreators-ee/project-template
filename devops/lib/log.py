import logging

import devops.settings as settings

logging.basicConfig(format=settings.LOG_FORMAT, level=settings.LOG_LEVEL)

try:
    import coloredlogs

    coloredlogs.install(level=settings.LOG_LEVEL, fmt=settings.LOG_FORMAT)
except ImportError:
    print("No colored logs available")

logger = logging.getLogger(__name__)
