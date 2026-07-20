class DynamicConfig:
    def __init__(self):
        self.total_concurrency = 250
        self.workers_per_instance = 25
        self.retry_delay = 2.0
        self.max_requests_per_session = 100
        self.requests_per_session = self.max_requests_per_session
        self.sleep_min = 1.0
        self.sleep_max = 2.0

        self.blocked_requests = 0
        self.total_requests = 0

        self.SAFE_MEMORY_LOCK = 85.0
        self.SAFE_CPU_LOCK = 85.0

config = DynamicConfig()