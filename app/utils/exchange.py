"""
USD → ILS exchange rate.

Fixed at 3.0 by default.  The user can override the rate in the asset form
(stored per-browser in localStorage); the server-side value is only used for
list-view display of legacy records.
"""

FIXED_RATE: float = 3.0

_override: dict = {'rate': FIXED_RATE}


def get_usd_to_nis() -> float:
    """Return the current USD → NIS rate."""
    return _override['rate']


def set_usd_to_nis(rate: float) -> None:
    """Allow runtime override (e.g. from an admin API route)."""
    if rate > 0:
        _override['rate'] = rate
