"""Tests for export_mail._ensure_aware -- the pywin32 COM datetime re-anchor.

pywin32/pywintypes datetimes arrive already "aware" but mislabelled: tzinfo
is a fixed zero/UTC offset while the wall-clock fields are already local
time. _ensure_aware must discard that bogus tzinfo and re-derive the correct
local offset from the wall clock (which varies with DST per-date), NOT trust
`dt.tzinfo is None` (which never fires on real COM values).

Two kinds of test here, deliberately:
  * Zone-independent invariants (always run): construct a pywin32-style
    aware-but-zero-offset datetime and assert wall-clock is preserved and
    the attached offset matches whatever *this* machine's local offset is
    for that date -- passes on any machine, any timezone, in CI.
  * London-pinned tests: pin TZ=Europe/London so exact "+01:00"/"+00:00"
    strings can be asserted through the real formatting path
    (mail_normalize.iso_local_offset), covering both BST (summer) and GMT
    (winter) so DST-per-date is proven, not just "some fixed offset was
    attached". Skipped where time.tzset() is unavailable (Windows).

Run:
    cd /home/cp/Dev/CoS && .venv/bin/python -m pytest tools/mail_extractor/tests -q
"""

import os
import sys
import time
from datetime import datetime, timezone

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

import export_mail  # noqa: E402
import mail_normalize  # noqa: E402


_HAS_TZSET = hasattr(time, "tzset")


# ---------------------------------------------------------------------------
#  Zone-independent invariants
# ---------------------------------------------------------------------------

def test_pywin32_style_aware_zero_offset_wallclock_preserved():
    # Simulates what pywin32 actually hands back: aware, offset zero, but
    # the fields are already local wall clock (not really UTC).
    com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(com_style)
    assert result.replace(tzinfo=None) == datetime(2026, 7, 6, 14, 0)


def test_pywin32_style_aware_zero_offset_gets_local_offset():
    com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(com_style)
    expected_offset = datetime(2026, 7, 6, 14, 0).astimezone().utcoffset()
    # Do NOT assert != timedelta(0): a UTC-configured machine legitimately
    # has offset 0 and that would be a false failure.
    assert result.utcoffset() == expected_offset


def test_naive_input_wallclock_preserved_and_local_offset_attached():
    naive = datetime(2026, 1, 6, 14, 0)
    result = export_mail._ensure_aware(naive)
    assert result.replace(tzinfo=None) == datetime(2026, 1, 6, 14, 0)
    assert result.utcoffset() == datetime(2026, 1, 6, 14, 0).astimezone().utcoffset()


def test_none_passthrough():
    assert export_mail._ensure_aware(None) is None


# ---------------------------------------------------------------------------
#  London-pinned exact strings
# ---------------------------------------------------------------------------

@pytest.fixture
def london_tz():
    if not _HAS_TZSET:
        pytest.skip("time.tzset() unavailable (Windows)")
    orig_tz = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/London"
    time.tzset()
    try:
        yield
    finally:
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        time.tzset()


def test_summer_bst_local_offset(london_tz):
    com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(com_style)
    assert mail_normalize.iso_local_offset(result) == "2026-07-06T14:00:00+01:00"


def test_summer_bst_utc(london_tz):
    com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(com_style)
    assert mail_normalize.iso_utc(result) == "2026-07-06T13:00:00Z"


def test_winter_gmt_local_offset(london_tz):
    com_style = datetime(2026, 1, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(com_style)
    assert mail_normalize.iso_local_offset(result) == "2026-01-06T14:00:00+00:00"


def test_winter_gmt_utc(london_tz):
    com_style = datetime(2026, 1, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(com_style)
    assert mail_normalize.iso_utc(result) == "2026-01-06T14:00:00Z"


def test_naive_input_wallclock_preserved(london_tz):
    naive = datetime(2026, 7, 6, 14, 0)
    result = export_mail._ensure_aware(naive)
    assert mail_normalize.iso_local_offset(result) == "2026-07-06T14:00:00+01:00"


class _WindowsOutOfRange(datetime):
    """A datetime whose .astimezone() fails the way Windows' does for values
    outside roughly 1970..3000. datetime.replace() returns type(self), so the
    naive value produced inside _ensure_aware is still one of these."""

    def astimezone(self, tz=None):
        raise OSError(22, "Invalid argument")


def test_out_of_range_date_does_not_abort_the_run():
    # Outlook sentinels (4501-01-01 "no date", 1601-01-01 FILETIME zero) cannot
    # be localised by Windows; one such item must not kill the whole export.
    result = export_mail._ensure_aware(_WindowsOutOfRange(4501, 1, 1, 0, 0))
    assert result.utcoffset() is not None
    assert result.replace(tzinfo=None) == datetime(4501, 1, 1, 0, 0)


def test_in_range_dates_are_unaffected_by_the_guard():
    normal = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    result = export_mail._ensure_aware(normal)
    assert result.replace(tzinfo=None) == datetime(2026, 7, 6, 14, 0)
    assert result.utcoffset() == datetime(2026, 7, 6, 14, 0).astimezone().utcoffset()


def test_none_still_returns_none():
    assert export_mail._ensure_aware(None) is None
