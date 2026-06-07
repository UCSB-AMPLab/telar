"""
Shared helpers for the build/fetch pipeline scripts.

`capped_read()` bounds how much of a remote response body we read into memory,
so a hostile or runaway endpoint cannot exhaust memory via an unbounded
`response.read()`. The caps are generous multiples of any legitimate payload;
the callers' existing try/except wrappers absorb the ValueError it raises.

Version: v1.5.0
"""

MAX_VERSIONS_BYTES = 64 * 1024          # 64 KB  — versions index JSON
MAX_BUNDLE_BYTES = 10 * 1024 * 1024     # 10 MB  — demo content bundle
MAX_CSV_BYTES = 25 * 1024 * 1024        # 25 MB  — Google Sheets CSV export
MAX_HTML_BYTES = 1 * 1024 * 1024        # 1 MB   — published-sheet HTML


def capped_read(response, limit):
    """Read at most ``limit`` bytes from a urllib response.

    Reads ``limit + 1`` bytes so an over-limit body is detected without
    buffering the whole thing, and raises ValueError if the cap is exceeded.

    Args:
        response: An object with a ``read(n)`` method (e.g. urllib response).
        limit: Maximum number of bytes to accept.

    Returns:
        bytes: The response body (<= limit bytes).

    Raises:
        ValueError: If the body exceeds ``limit`` bytes.
    """
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Response exceeded {limit} bytes")
    return data
