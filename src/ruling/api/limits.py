"""Rate limits for the public demo: per-client sliding windows plus an hourly budget on model use.

The desk is open to anyone with the link, so one busy client must not run up the model bill or
starve everyone else. Limits are in memory (one replica), keyed by the client's address.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# Requests per window, per client: (limit, seconds).
LIMITS = {
    "check": (8, 60),        # VAR checks and drills, from the desk or over MCP
    "translate": (20, 60),
    "speech": (12, 60),      # stadium announcements read aloud (each is made once, then cached)
    "panel": (6, 60),        # post-match panel reviews (five model calls each, kept with the case file)
    "feed": (6, 60),         # starting or freezing the live feed
}
MODEL_BUDGET = (180, 3600)  # checks that may call the model, all clients together, per hour


class Limiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, seconds: float) -> float:
        """0 if the hit is allowed (and recorded), else the seconds until it would be."""
        now, q = self.clock(), self.hits[key]
        while q and now - q[0] >= seconds:
            q.popleft()
        if len(q) >= limit:
            return round(seconds - (now - q[0]), 1)
        q.append(now)
        return 0.0


def client_of(request: Request) -> str:
    """The caller's address; behind Container Apps ingress it is the first X-Forwarded-For entry."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def enforce(limiter: Limiter, request: Request, kind: str, uses_model: bool = False) -> None:
    limit, seconds = LIMITS[kind]
    wait = limiter.allow(f"{kind}:{client_of(request)}", limit, seconds)
    if not wait and uses_model:
        wait = limiter.allow("model-budget", *MODEL_BUDGET)
        if wait:
            raise HTTPException(429, "The demo's hourly model budget is used up; try again later.",
                                headers={"Retry-After": str(int(wait) + 1)})
    if wait:
        raise HTTPException(429, f"Too many requests; try again in {int(wait) + 1} s.",
                            headers={"Retry-After": str(int(wait) + 1)})
