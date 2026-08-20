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
from datetime import datetime, timezone

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
