"""Tests for capdag.bifaci.cartridge_json — mirroring the reference capdag tests.

Tests use TEST###: comments matching the Rust implementation for cross-tracking.
"""

from capdag.bifaci.cartridge_json import format_rfc3339_utc, install_timestamp_now


# TEST7153: ``installed_at`` is a real RFC3339 UTC timestamp, at known epoch
# instants and at the instants that break naive date arithmetic — a leap day,
# the day after one, and a century year that is NOT a leap year. Emitting a bare
# epoch count with a ``Z`` appended would satisfy "some string ending in Z" and
# satisfy nothing else; every reader and every fixture in the tree treats this
# field as a parseable timestamp.
def test_7153_install_timestamp_is_rfc3339_utc():
    cases = [
        (0, "1970-01-01T00:00:00Z"),
        (1_000_000_000, "2001-09-09T01:46:40Z"),
        # 2024-02-29 — a leap day in a leap year divisible by 4.
        (1_709_164_800, "2024-02-29T00:00:00Z"),
        # The instant after it: the rollover a naive +1 gets wrong.
        (1_709_251_199, "2024-02-29T23:59:59Z"),
        # 2100-03-01 — 2100 is divisible by 100 but not 400, so it has NO
        # Feb 29. A leap rule of "divisible by 4" lands a day early.
        (4_107_542_400, "2100-03-01T00:00:00Z"),
    ]
    for secs, want in cases:
        assert format_rfc3339_utc(secs) == want, f"epoch {secs}"

    # The live producer emits the same shape, and a plausible present instant —
    # a broken epoch-to-civil conversion typically lands in 1970 or the far
    # future rather than producing a malformed string.
    now = install_timestamp_now()
    assert len(now) == 20, f"not RFC3339-shaped: {now}"
    assert now.endswith("Z"), f"not UTC-marked: {now}"
    year = int(now[:4])
    assert 2020 <= year < 2200, f"the current year came out as {year}: {now}"
