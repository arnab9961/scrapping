import pytest
import time
from services.circuit_breaker import DomainCircuitBreaker
from tools import DomainRateLimiter

def test_circuit_breaker_tripping_and_recovery():
    cb = DomainCircuitBreaker(failure_threshold=2, recovery_time_seconds=0.2)
    domain = "https://failing-domain.com/page1"

    # Initially closed
    assert cb.can_request(domain) is True
    assert cb.get_state(domain) == "CLOSED"

    # First failure: still closed
    cb.record_failure(domain, "HTTP 500")
    assert cb.can_request(domain) is True
    assert cb.get_state(domain) == "CLOSED"

    # Second failure: reaches threshold -> trips to OPEN
    cb.record_failure(domain, "HTTP 429 Rate limited")
    assert cb.can_request(domain) is False
    assert cb.get_state(domain) == "OPEN"

    # Wait for recovery cooldown
    time.sleep(0.25)
    assert cb.get_state(domain) == "HALF-OPEN"
    assert cb.can_request(domain) is True

    # Probe request succeeds -> returns to CLOSED
    cb.record_success(domain)
    assert cb.get_state(domain) == "CLOSED"
    assert cb.can_request(domain) is True

def test_domain_rate_limiter_distinct_domains():
    limiter = DomainRateLimiter(default_delay=0.1)
    
    # Timing request to domain A
    t0 = time.time()
    limiter.wait_for_domain("https://domain-a.com/page1")
    t1 = time.time()
    # First request should be immediate
    assert (t1 - t0) < 0.05

    # Request to DIFFERENT domain B should NOT be delayed by domain A!
    t2 = time.time()
    limiter.wait_for_domain("https://domain-b.com/page1")
    t3 = time.time()
    assert (t3 - t2) < 0.05

    # Request to SAME domain A should be delayed by default_delay
    t4 = time.time()
    limiter.wait_for_domain("https://domain-a.com/page2")
    t5 = time.time()
    assert (t5 - t4) >= 0.08
