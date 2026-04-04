# utils/rate_limiter.py

import time
import threading

class TokenRateLimiter:
    def __init__(self, max_tokens_per_minute):
        self.max_tokens = max_tokens_per_minute
        self.tokens_used = 0
        self.lock = threading.Lock()
        self.window_start = time.time()

    def consume(self, tokens):
        while True:
            with self.lock:
                now = time.time()

                # reset every minute
                if now - self.window_start >= 60:
                    self.tokens_used = 0
                    self.window_start = now

                if self.tokens_used + tokens <= self.max_tokens:
                    self.tokens_used += tokens
                    return

            time.sleep(0.2)

rate_limiter = TokenRateLimiter(max_tokens_per_minute=1_200_000)