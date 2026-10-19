"""Money rules: integer cents, half-up rounding, non-negative totals."""
from app.money import discount_cents, format_cents


def test_discount_rounds_half_up():
    # 10% of 1005c = 100.5c -> rounds up to 101
    assert discount_cents(1005, 10) == 101
    # 10% of 1004c = 100.4c -> rounds down to 100
    assert discount_cents(1004, 10) == 100


def test_discount_never_exceeds_subtotal():
    # 100% off clamps exactly to the subtotal; total would be 0, never negative.
    assert discount_cents(5000, 100) == 5000
    # Absurd percentages still clamp.
    assert discount_cents(5000, 150) == 5000


def test_zero_cases():
    assert discount_cents(0, 10) == 0
    assert discount_cents(1000, 0) == 0


def test_format_cents():
    assert format_cents(0) == "0.00"
    assert format_cents(1050) == "10.50"
    assert format_cents(9) == "0.09"
