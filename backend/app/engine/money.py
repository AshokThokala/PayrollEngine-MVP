"""Money helpers. All amounts are Decimal rupees; never use float for money."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

ZERO = Decimal("0")


def D(value) -> Decimal:
    """Convert int/str/float/Decimal to Decimal safely (floats go through str)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def rupee(amount) -> Decimal:
    """Round to the nearest whole rupee, half up (EPFO/TDS convention)."""
    return D(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def rupee_up(amount) -> Decimal:
    """Round up to the next whole rupee (ESIC convention for contributions)."""
    return D(amount).quantize(Decimal("1"), rounding=ROUND_CEILING)


def paise(amount) -> Decimal:
    return D(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
