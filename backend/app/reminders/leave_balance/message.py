"""What the monthly leave balance notification SAYS. Pure - no database, no
session, no clock.

    Leave Balance Update
    Santhosh Kumar, you have 4 available leave days.

Split out from the dispatcher so the two rules that are easy to get wrong - how
a balance is spelled and when the noun is singular - are asserted directly,
without seeding a ledger to do it.

THE NUMBER IS NEVER DRESSED UP
==============================
`format_days` prints the ledger's own figure. Trailing zeros go (4.00 -> "4",
1.50 -> "1.5") because "4.00 available leave days" reads like an accounting
statement, but nothing else is done to it: a negative balance prints its minus
sign, and zero prints as "0". The ledger deliberately reports loss-of-pay as a
negative number, and an employee who is 1 day overdrawn needs to be told that,
not shown a reassuring 0.

GRAMMAR
=======
"day" for exactly 1, "days" for everything else - including 0, 1.5 and -1, all
of which take the plural in English ("you have -1 available leave days" is the
wording the brief asks for). Only the value 1 is singular, so 1.00 and 1 are the
same sentence and 1.5 is not.
"""
from __future__ import annotations

from decimal import Decimal

# The notification title, identical every month. The month itself is not in the
# title: the message is about the balance the employee has NOW, and the
# notification centre already stamps when it arrived.
TITLE = "Leave Balance Update"

ONE = Decimal("1")
CENTS = Decimal("0.01")


def format_days(value: Decimal) -> str:
    """A balance as it appears in the sentence: "4", "1.5", "0", "-1".

    Quantized to the ledger's own two decimal places first, then stripped of
    trailing zeros. `format(..., "f")` rather than `str()` so a normalized whole
    number never comes out in exponent form ("1E+2" for 100 days of carry).
    """
    quantized = value.quantize(CENTS)
    return format(quantized.normalize(), "f")


def build_message(employee_name: str, days: Decimal) -> str:
    """The notification body for one employee and their own calculated balance."""
    unit = "day" if days == ONE else "days"
    return f"{employee_name}, you have {format_days(days)} available leave {unit}."
