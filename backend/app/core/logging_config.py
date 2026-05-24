import logging
import json
import contextvars
from datetime import datetime, timezone

# Context variable to hold execution metadata (thread & asyncio-task safe)
execution_context = contextvars.ContextVar("execution_context", default={})

class JSONFormatter(logging.Formatter):
    def format(self, record):
        ctx = execution_context.get()
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if ctx:
            log_data.update(ctx)
            
        # Support explicit extra fields
        for field in ["run_id", "company_id", "agent_id"]:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)
                
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)

def setup_logging():
    logger = logging.getLogger()
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
