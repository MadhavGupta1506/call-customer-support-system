"""
Shared HTTP client with connection pooling for better performance.
"""
import httpx

# Shared HTTP client with connection pooling and HTTP/2 support
_client = None

def get_http_client() -> httpx.AsyncClient:
    """
    Get or create a shared HTTP client with connection pooling.
    Reusing connections significantly reduces latency.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=15.0,
            http2=True,  # Enable HTTP/2 for faster multiplexing
            verify=False,  # Disable SSL verification for local development
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0
            )
        )
    return _client


async def close_http_client():
    """Close the shared HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
