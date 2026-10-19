"""Money math in integer minor units (cents).

All monetary values are integers (cents) everywhere in the system — DB columns,
service logic, and API payloads carry `*_cents`. We never do arithmetic on floats,
which eliminates binary floating-point rounding error entirely.

The one place rounding is unavoidable is a percentage discount, where we round the
*result* half-up to the nearest cent using Decimal (exact base-10 rounding).
"""
from decimal import ROUND_HALF_UP, Decimal


def discount_cents(subtotal_cents: int, percent_off: int) -> int:
    """Return the discount for `percent_off`% of `subtotal_cents`, rounded half-up.

    The discount is clamped to the subtotal so a total can never go negative.
    """
    if percent_off <= 0 or subtotal_cents <= 0:
        return 0
    raw = (Decimal(subtotal_cents) * Decimal(percent_off) / Decimal(100)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return min(int(raw), subtotal_cents)


def format_cents(cents: int) -> str:
    """Render cents as a decimal string, e.g. 1050 -> '10.50'. Display only."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
