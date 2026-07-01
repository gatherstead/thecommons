import json
import logging


def sse_frame(event, data):
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class QueueLoggingHandler(logging.Handler):
    def __init__(self, q, thread_ident):
        super().__init__()
        self.q = q
        self.ident = thread_ident

    def emit(self, record):
        if record.thread != self.ident:
            return  # isolate concurrent runs to this worker thread
        self.q.put(("log", {
            "stage": getattr(record, "stage", ""),
            "level": record.levelname,
            "message": self.format(record),
            "ts": record.created,
        }))
