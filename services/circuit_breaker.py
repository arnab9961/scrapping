import time
import logging
from typing import Dict, Any, Optional
from validators.domain import get_canonical_domain

logger = logging.getLogger("circuit_breaker")

class DomainCircuitBreaker:
    """
    Per-domain Circuit Breaker to prevent hammering failing, dead, or anti-bot blocked domains.
    
    States:
    - CLOSED: Normal operation. Requests proceed.
    - OPEN: Tripped due to repeated failures (403/429/timeouts). Requests fail fast.
    - HALF-OPEN: Cooldown period elapsed. A single probe request is permitted.
    """

    def __init__(self, failure_threshold: int = 3, recovery_time_seconds: float = 300.0):
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        # domain -> {"failures": int, "state": str, "tripped_at": float}
        self.domains: Dict[str, Dict[str, Any]] = {}

    def get_state(self, domain_or_url: str) -> str:
        domain = get_canonical_domain(domain_or_url)
        if not domain:
            return "CLOSED"

        info = self.domains.get(domain)
        if not info:
            return "CLOSED"

        state = info.get("state", "CLOSED")
        if state == "OPEN":
            tripped_at = info.get("tripped_at", 0)
            if time.time() - tripped_at >= self.recovery_time_seconds:
                info["state"] = "HALF-OPEN"
                logger.info(f"🔄 Circuit Breaker for '{domain}' transitioned to HALF-OPEN (cooldown passed)")
                return "HALF-OPEN"
            return "OPEN"

        return state

    def can_request(self, domain_or_url: str) -> bool:
        """Returns True if requests to this domain are allowed."""
        state = self.get_state(domain_or_url)
        return state in ("CLOSED", "HALF-OPEN")

    def record_success(self, domain_or_url: str):
        """Resets failures on successful response."""
        domain = get_canonical_domain(domain_or_url)
        if not domain:
            return

        if domain in self.domains:
            self.domains[domain] = {
                "failures": 0,
                "state": "CLOSED",
                "tripped_at": 0.0
            }

    def record_failure(self, domain_or_url: str, reason: str = ""):
        """Increments failure count and trips circuit if threshold reached."""
        domain = get_canonical_domain(domain_or_url)
        if not domain:
            return

        if domain not in self.domains:
            self.domains[domain] = {
                "failures": 1,
                "state": "CLOSED",
                "tripped_at": 0.0
            }
        else:
            self.domains[domain]["failures"] += 1

        failures = self.domains[domain]["failures"]
        if failures >= self.failure_threshold:
            self.domains[domain]["state"] = "OPEN"
            self.domains[domain]["tripped_at"] = time.time()
            logger.warning(
                f"🚨 Circuit Breaker TRIPPED to OPEN for '{domain}' after {failures} consecutive failures. "
                f"Cooldown: {int(self.recovery_time_seconds)}s. Reason: {reason}"
            )

# Global default singleton
circuit_breaker = DomainCircuitBreaker()
