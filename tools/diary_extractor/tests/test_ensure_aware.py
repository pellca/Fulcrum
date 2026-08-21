"""Tests for export_diary._ensure_aware -- the pywin32 COM datetime re-anchor.

pywin32/pywintypes datetimes arrive already "aware" but mislabelled: tzinfo
is a fixed zero/UTC offset while the wall-clock fields are already local
time. _ensure_aware must discard that bogus tzinfo and re-derive the correct
local offset from the wall clock (which varies with DST per-date), NOT trust
`dt.tzinfo is None` (which never fires on real COM values).

Two kinds of test here, deliberately:
  * IsoUtcTests / zone-independent invariant: constructs a pywin32-style
    aware-but-zero-offset datetime and asserts wall-clock is preserved and
    the attached offset matches whatever *this* machine's local offset is
    for that date -- passes on any machine, any timezone, in CI.
  * London-pinned tests: pin TZ=Europe/London so exact "+01:00"/"+00:00"
    strings can be asserted through the real formatting path (diary_merge),
    covering both BST (summer) and GMT (winter) so DST-per-date is proven,
    not just "some fixed offset was attached". Skipped where time.tzset()
    is unavailable (Windows).

Run:
    python -m unittest tests.test_ensure_aware          # from the repo root
    python -m unittest tests.test_ensure_aware -v
"""

import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

# Make export_diary / diary_merge importable when run from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import diary_merge  # noqa: E402
import export_diary  # noqa: E402


_HAS_TZSET = hasattr(time, "tzset")


class EnsureAwareZoneIndependentTests(unittest.TestCase):
    """Invariants that hold regardless of the machine's local timezone."""

    def test_pywin32_style_aware_zero_offset_wallclock_preserved(self):
        # Simulates what pywin32 actually hands back: aware, offset zero,
        # but the fields are already local wall clock (not really UTC).
        com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(com_style)
        self.assertEqual(
            datetime(2026, 7, 6, 14, 0), result.replace(tzinfo=None),
            "wall-clock fields must be unchanged by re-anchoring")

    def test_pywin32_style_aware_zero_offset_gets_local_offset(self):
        com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(com_style)
        expected_offset = datetime(2026, 7, 6, 14, 0).astimezone().utcoffset()
        self.assertEqual(
            expected_offset, result.utcoffset(),
            "offset must be the locally-correct offset for that date, "
            "whatever this machine's timezone is (do not assert != 0: "
            "a UTC-configured machine legitimately has offset 0)")

    def test_naive_input_wallclock_preserved_and_local_offset_attached(self):
        naive = datetime(2026, 1, 6, 14, 0)
        result = export_diary._ensure_aware(naive)
        self.assertEqual(datetime(2026, 1, 6, 14, 0), result.replace(tzinfo=None))
        self.assertEqual(datetime(2026, 1, 6, 14, 0).astimezone().utcoffset(),
                          result.utcoffset())


@unittest.skipUnless(_HAS_TZSET, "time.tzset() unavailable (Windows)")
class EnsureAwareLondonPinnedTests(unittest.TestCase):
    """Exact-string assertions through the real formatting path, with the
    process timezone pinned to Europe/London so BST vs GMT is deterministic."""

    def setUp(self):
        self._orig_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/London"
        time.tzset()

    def tearDown(self):
        if self._orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._orig_tz
        time.tzset()

    def test_summer_bst_local_offset(self):
        com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(com_style)
        self.assertEqual("2026-07-06T14:00:00+01:00",
                          diary_merge._iso_local_offset(result))

    def test_summer_bst_utc(self):
        com_style = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(com_style)
        self.assertEqual("2026-07-06T13:00:00Z", diary_merge.iso_utc(result))

    def test_winter_gmt_local_offset(self):
        com_style = datetime(2026, 1, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(com_style)
        self.assertEqual("2026-01-06T14:00:00+00:00",
                          diary_merge._iso_local_offset(result))

    def test_winter_gmt_utc(self):
        com_style = datetime(2026, 1, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(com_style)
        self.assertEqual("2026-01-06T14:00:00Z", diary_merge.iso_utc(result))

    def test_naive_input_wallclock_preserved(self):
        naive = datetime(2026, 7, 6, 14, 0)
        result = export_diary._ensure_aware(naive)
        self.assertEqual("2026-07-06T14:00:00+01:00",
                          diary_merge._iso_local_offset(result))


if __name__ == "__main__":
    unittest.main()


class OutOfRangeDateTests(unittest.TestCase):
    """Outlook hands out sentinel dates that Windows cannot localise.

    4501-01-01 is Outlook's "no end date" on an endless recurring series and
    1601-01-01 is FILETIME zero. A naive .astimezone() routes through the
    platform's local time conversion, which on Windows raises
    OSError [Errno 22] outside roughly 1970..3000 -- aborting the whole
    export over one junk date. glibc happily converts them, so this cannot be
    reproduced by simply passing the date on Linux: the failure is simulated
    with a datetime subclass whose astimezone() raises exactly as Windows does.
    """

    class _WindowsOutOfRange(datetime):
        """A datetime whose .astimezone() fails the way Windows' does.

        datetime.replace() returns type(self), so the naive value produced
        inside _ensure_aware is still one of these and still raises.
        """

        def astimezone(self, tz=None):
            raise OSError(22, "Invalid argument")

    def test_out_of_range_date_does_not_abort_the_run(self):
        sentinel = self._WindowsOutOfRange(4501, 1, 1, 0, 0)
        result = export_diary._ensure_aware(sentinel)
        self.assertIsNotNone(result.utcoffset(), "must come back aware")
        self.assertEqual(
            result.replace(tzinfo=None),
            datetime(4501, 1, 1, 0, 0),
            "wall clock must be preserved",
        )

    def test_filetime_epoch_does_not_abort_the_run(self):
        result = export_diary._ensure_aware(self._WindowsOutOfRange(1601, 1, 1, 0, 0))
        self.assertIsNotNone(result.utcoffset())

    def test_in_range_dates_are_unaffected_by_the_guard(self):
        # the guard must not change the normal path: a real July date still
        # gets this machine's actual offset for that date
        normal = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        result = export_diary._ensure_aware(normal)
        self.assertEqual(result.replace(tzinfo=None), datetime(2026, 7, 6, 14, 0))
        self.assertEqual(result.utcoffset(), datetime(2026, 7, 6, 14, 0).astimezone().utcoffset())

    def test_local_utcoffset_now_returns_a_timedelta(self):
        self.assertIsInstance(export_diary._local_utcoffset_now(), timedelta)
