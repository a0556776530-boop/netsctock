"""
USD → ILS exchange rate.

Fixed at 3.0 by default.  The user can override the rate in the asset form
(stored per-browser in localStorage); the server-side value is only used for
list-view display of legacy records.
"""

from app.models.settings import USD_BASE_RATE, BINA_FACTOR

FIXED_RATE: float = USD_BASE_RATE


def get_usd_to_nis() -> float:
    return USD_BASE_RATE


def effective_rate() -> float:
    """Combined USD base rate × Bina factor — used for NIS calculations."""
    return USD_BASE_RATE * BINA_FACTOR
