"""Constants of machine notation.

A constant is a JSON value. In this package it is one of

    None, bool, str, int, float, list, dict

A number written without a fraction or an exponent is a whole number (an
``int``) while it fits sixty-four bits, signed or unsigned; any other number
is a ``float``. ``1`` and ``1.0`` are therefore two different constants, as
they are in the reference, whose JSON value keeps whole numbers and floats
apart.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any

_WHOLE_MIN = -(2 ** 63)
_WHOLE_MAX = 2 ** 64 - 1


def _float_of(text: str) -> float:
    value = float(text)
    if math.isinf(value) or math.isnan(value):
        raise ValueError(f"{text!r} is not a number a constant can hold")
    return value


def _whole_of(text: str):
    value = int(text)
    if value == 0 and text.startswith("-"):
        # A whole number has no sign to keep at zero: `-0` is the float, as
        # the reference reads it.
        return -0.0
    if _WHOLE_MIN <= value <= _WHOLE_MAX:
        return value
    # Beyond sixty-four bits a number is the nearest float.
    return _float_of(text)


def _not_a_value(text: str):
    raise ValueError(f"{text} is not a JSON value")


def _refuse_half_characters(value: Any) -> None:
    """Refuse a value one of whose strings holds half of a surrogate pair: an
    escape for one half without the other (``"\\ud800"``) is read by the JSON
    decoder as a string that is not text."""
    if isinstance(value, str):
        for character in value:
            if 0xD800 <= ord(character) <= 0xDFFF:
                raise ValueError(f"the escape \\u{ord(character):04x} names half a character")
    elif isinstance(value, list):
        for item in value:
            _refuse_half_characters(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _refuse_half_characters(key)
            _refuse_half_characters(item)


def decode_constant(text: str) -> Any:
    """Read one JSON value from its text. Raises ``ValueError`` on text that
    is not one JSON value."""
    value = json.loads(
        text,
        parse_int=_whole_of,
        parse_float=_float_of,
        parse_constant=_not_a_value,
    )
    _refuse_half_characters(value)
    return value


def constants_equal(a: Any, b: Any) -> bool:
    """Compare two constants as JSON values: a whole number and a float are
    never equal, nor a boolean and a number; an object's keys carry no
    order."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a == b
    if isinstance(a, int) or isinstance(b, int):
        return isinstance(a, int) and isinstance(b, int) and a == b
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, float) and isinstance(b, float) and a == b
    if isinstance(a, list) or isinstance(b, list):
        return (
            isinstance(a, list)
            and isinstance(b, list)
            and len(a) == len(b)
            and all(constants_equal(x, y) for x, y in zip(a, b))
        )
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(constants_equal(a[key], b[key]) for key in a)
    return False


def constant_text(value: Any) -> str:
    """Write a constant as notation writes it: compact JSON, an object's keys
    in order, numbers and strings spelled as the reference spells them. The
    same value has one text in every implementation, so canonical notation
    is the same text everywhere."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _string_text(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return float_text(value)
    if isinstance(value, list):
        return "[" + ",".join(constant_text(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                _string_text(key) + ":" + constant_text(value[key]) for key in sorted(value)
            )
            + "}"
        )
    raise TypeError(f"{type(value).__name__} is not a constant of machine notation")


_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _string_text(text: str) -> str:
    """A JSON string with exactly the escapes the reference writes: the
    quote, the backslash and the control characters. Everything else — ``<``,
    ``&``, any character outside ASCII — is written as it is."""
    out = ['"']
    for char in text:
        escaped = _ESCAPES.get(char)
        if escaped is not None:
            out.append(escaped)
        elif char < " ":
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def float_text(value: float) -> str:
    """Write a float as the shortest decimal that reads back as the same
    float, laid out as the reference lays it out: plain digits with a decimal
    point while the number has at most sixteen digits before the point and
    fewer than five zeros after it, an exponent (with its sign, ``e+16`` and
    ``e-7``) otherwise. A float that is a whole number keeps its ``.0``, so
    it reads back as a float."""
    if math.isinf(value) or math.isnan(value):
        raise ValueError(f"{value!r} is not a number a constant can hold")
    if value == 0:
        return "-0.0" if math.copysign(1.0, value) < 0 else "0.0"
    sign = ""
    if value < 0:
        sign = "-"
        value = -value
    # `repr` is the shortest text that reads back as this float.
    shortest = Decimal(repr(value))
    digits = "".join(str(digit) for digit in shortest.as_tuple().digits).rstrip("0")
    count = len(digits)
    # The value is 0.DIGITS × 10^point.
    point = shortest.adjusted() + 1
    if count <= point <= 16:
        return sign + digits + "0" * (point - count) + ".0"
    if 0 < point <= 16:
        return sign + digits[:point] + "." + digits[point:]
    if -5 < point <= 0:
        return sign + "0." + "0" * (-point) + digits
    # An exponent carries its sign, `+` included.
    power = str(point - 1)
    if point > 0:
        power = "+" + power
    if count == 1:
        return sign + digits + "e" + power
    return sign + digits[:1] + "." + digits[1:] + "e" + power
