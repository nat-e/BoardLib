import datetime
import unittest

import boardlib.util.logbook


UTC = datetime.timezone.utc


class TestLogbook(unittest.TestCase):
    def test_parse_timestamp(self):
        expected = datetime.datetime(2026, 4, 1, 17, 42, 10)
        for timestamp in (
            "2026-04-01T17:42:10Z",
            "2026-04-01T17:42:10.1Z",
            "2026-04-01T17:42:10.123456Z",
            "2026-04-01T17:42:10.123456789Z",
            "2026-04-01T19:42:10.5+02:00",
            "2026-04-01T17:42:10",
            "2026-04-01 17:42:10",
            "2026-04-01 17:42:10.123",
        ):
            self.assertEqual(
                boardlib.util.logbook.parse_timestamp(timestamp, UTC), expected
            )
        self.assertEqual(
            boardlib.util.logbook.parse_timestamp(
                "2026-04-01T23:42:10Z", datetime.timezone(datetime.timedelta(hours=-4))
            ),
            datetime.datetime(2026, 4, 1, 19, 42, 10),
        )


if __name__ == "__main__":
    unittest.main()
