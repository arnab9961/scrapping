import ipaddress
import socket
import urllib.parse
from typing import Tuple, Optional

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
    "local",
    "broadcasthost"
}

def is_ip_private_or_restricted(ip_str: str) -> bool:
    """Checks whether an IP address belongs to private, loopback, link-local, or reserved networks."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_multicast or
            ip.is_reserved or
            ip.is_unspecified
        )
    except ValueError:
        return False

def validate_safe_url(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates that a URL is safe to scrape:
    - Only HTTP and HTTPS schemes.
    - Not empty or malformed.
    - Resolves to a public, non-SSRF IP address.
    - Not pointing to localhost, private subnets (10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12),
      or cloud metadata endpoints (169.254.169.254).
    
    Returns:
        (is_safe: bool, normalized_url: str or None, reason: str or None)
    """
    if not url or not isinstance(url, str):
        return False, None, "URL is required and must be a string."

    clean_url = url.strip()
    try:
        parsed = urllib.parse.urlparse(clean_url)
    except Exception as e:
        return False, None, f"Malformed URL: {e}"

    if parsed.scheme:
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False, None, f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."
    else:
        clean_url = 'https://' + clean_url
        try:
            parsed = urllib.parse.urlparse(clean_url)
        except Exception as e:
            return False, None, f"Malformed URL: {e}"

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, None, f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False, None, "URL must contain a valid hostname."

    # Check blocked hostnames
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        return False, None, f"Access to '{hostname}' is blocked for security (SSRF prevention)."

    # Check direct IP addresses
    if is_ip_private_or_restricted(hostname):
        return False, None, f"Access to private IP address '{hostname}' is blocked."

    # Resolve hostname via DNS to prevent DNS rebinding or localhost aliases
    try:
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for res in resolved_ips:
            ip_candidate = res[4][0]
            if is_ip_private_or_restricted(ip_candidate):
                return False, None, f"Host '{hostname}' resolves to private/restricted IP '{ip_candidate}'."
    except socket.gaierror:
        # If hostname cannot be resolved, we can still report it or allow HTTP client to fail cleanly
        pass
    except Exception as e:
        return False, None, f"Failed resolving hostname: {e}"

    return True, clean_url, None

def is_safe_url(url: str) -> bool:
    """Convenience boolean check."""
    is_safe, _, _ = validate_safe_url(url)
    return is_safe
