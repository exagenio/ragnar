import time
import threading
import os


class TokenRateLimiter:
    """Token rate limiter"""

    def __init__(self, max_tokens_per_minute, max_requests_per_minute):
        """Initialize rate limiter"""
        self.max_tokens = max_tokens_per_minute
        self.max_requests = max_requests_per_minute
        try:
            self.poll_seconds = float(os.getenv("LLM_RATE_LIMIT_POLL_SECONDS", "0.05"))
        except (TypeError, ValueError):
            self.poll_seconds = 0.05
        self.tokens_used = 0
        self.requests_used = 0
        self.lock = threading.Lock()
        self.window_start = time.time()

    def consume(self, tokens, requests=1):
        """Consume quota for both tokens and request count."""
        while True:
            with self.lock:
                now = time.time()

                # Reset token window every minute
                if now - self.window_start >= 60:
                    self.tokens_used = 0
                    self.requests_used = 0
                    self.window_start = now

                if (
                    self.tokens_used + tokens <= self.max_tokens
                    and self.requests_used + requests <= self.max_requests
                ):
                    self.tokens_used += tokens
                    self.requests_used += requests
                    return

            time.sleep(self.poll_seconds)


rate_limiter = TokenRateLimiter(
    max_tokens_per_minute=int(os.getenv("MAX_LLM_TOKENS_PER_MINUTE", "1200000")),
    max_requests_per_minute=int(os.getenv("MAX_LLM_REQUESTS_PER_MINUTE", "45")),
)
