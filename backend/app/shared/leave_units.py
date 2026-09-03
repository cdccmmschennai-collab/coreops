"""The unit leave is transacted in: the half day.

CoreOps grants, spends and corrects leave in multiples of 0.5 and nothing else.
0, 0.5, 1, 1.5, 2 are leave; 0.1, 0.25, 2.4 are not quantities of leave at all,
and a system that accepts them has no way to render or reconcile them afterwards.

WHY THIS IS A SHARED MODULE
===========================
The rule is enforced in three places that must agree exactly - the PM's balance
correction, the monthly allocation, and the per-day leave fraction on an
attendance record - and it is the kind of rule that rots when it is written out
three times. The DB check constraints under those columns are the floor; this is
the layer that turns a violation into a message a manager can read.

WHY IT REJECTS RATHER THAN ROUNDS
=================================
Rounding 2.4 to 2.5 credits half a day nobody granted, and rounding it to 2.0
takes half a day away without saying so. Both silently invent a decision the
manager did not make, and neither leaves a trace. A refusal is the only handling
that cannot corrupt a balance.
"""
from decimal import Decimal, InvalidOperation

# Leave moves in halves. Expressed as a Decimal so the test is exact: 0.1 + 0.2
# is not 0.3 in binary floating point, and `value % 0.5` inherits that.
HALF = Decimal("0.5")


def is_half_step(value: float | Decimal) -> bool:
    """True when `value` is a whole number of half days.

    Converted through `str` so a float arrives as the decimal the caller wrote
    (`Decimal(str(2.5))` is exactly 2.5, while `Decimal(2.5)` is a long binary
    expansion). Anything that is not a finite number at all is not a half step.
    """
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return False
    if not amount.is_finite():
        return False
    return amount % HALF == 0


def validate_half_step(
    value: float,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Return `value` unchanged, or raise `ValueError` naming what was wrong.

    Raised as a plain `ValueError` because every caller is a pydantic validator:
    FastAPI turns it into the same 422 shape the rest of the API already returns,
    so nothing needs an error path of its own.
    """
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} cannot be less than {_plain(minimum)}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} cannot be more than {_plain(maximum)}.")
    if not is_half_step(value):
        raise ValueError(
            f"{label} must be a multiple of 0.5 - a whole or half day "
            f"(e.g. 0, 0.5, 1, 1.5, 2). Got {_plain(value)}."
        )
    return value


def _plain(value: float) -> str:
    """`2.0` -> '2', `2.5` -> '2.5'. Keeps the message free of noise zeros."""
    return f"{float(value):g}"
