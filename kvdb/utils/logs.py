import structlog
from structlog.typing import FilteringBoundLogger

# structlog.configure(
#     processors=[
#         structlog.stdlib.add_log_level,
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.StackInfoRenderer(),
#         structlog.processors.format_exc_info,
#         structlog.processors.JSONRenderer()
#     ],
#     context_class=dict,
#     logger_factory=structlog.PrintLoggerFactory(),
#     wrapper_class=structlog.stdlib.BoundLogger,
#     cache_logger_on_first_use=True,
# )

logger: FilteringBoundLogger = structlog.get_logger(__name__)