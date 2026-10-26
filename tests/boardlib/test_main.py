import contextlib
import csv
import datetime
import io
import os
import sys
import tempfile
import unittest
import unittest.mock

import boardlib.__main__


KILTER_ENTRY = {
    "climb_angle_uuid": "TESTCLIMB1-40",
    "climb_uuid": "TESTCLIMB1",
    "board": "kilter",
    "angle": 40,
    "climb_name": "test_climb_1",
    "date": datetime.datetime(2026, 4, 1, 18, 0),
    "logged_grade": None,
    "displayed_grade": "6A+/V3",
    "is_benchmark": None,
    "tries": 1,
    "is_mirror": None,
    "is_ascent": True,
    "comment": None,
    "is_repeat": False,
    "sessions_count": 1,
    "tries_total": 1,
}

BOARDSESH_ENTRY = dict(
    KILTER_ENTRY,
    board="moonboard",
    logged_grade="6b/V4",
    is_benchmark=True,
    is_mirror=False,
)


def run_logbook(*arguments):
    """Run `boardlib logbook` with the given arguments and return the CSV rows."""
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "logbook.csv")
        argv = ["boardlib", "logbook", *arguments, "-o", output]
        with unittest.mock.patch.object(sys, "argv", argv):
            boardlib.__main__.main()

        with open(output, encoding="utf-8") as output_file:
            return list(csv.DictReader(output_file))


def without_env(*names):
    """Remove environment variables until the end of the enclosing patch.dict."""
    for name in names:
        os.environ.pop(name, None)


class TestMain(unittest.TestCase):
    @unittest.mock.patch.dict(os.environ, {"KILTER_PASSWORD": "test_password"})
    @unittest.mock.patch(
        "boardlib.api.kilter.logbook_entries", return_value=[KILTER_ENTRY]
    )
    def test_logbook_kilter(self, mock_logbook_entries):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "logbook.csv")
            argv = [
                "boardlib",
                "logbook",
                "kilter",
                "-u",
                "test@example.com",
                "-o",
                output,
            ]
            with unittest.mock.patch.object(sys, "argv", argv):
                boardlib.__main__.main()

            with open(output, encoding="utf-8") as output_file:
                rows = list(csv.DictReader(output_file))

        mock_logbook_entries.assert_called_once_with(
            "kilter", "test@example.com", "test_password"
        )
        self.assertEqual(
            rows,
            [
                {
                    "board": "kilter",
                    "angle": "40",
                    "climb_name": "test_climb_1",
                    "date": "2026-04-01 18:00:00",
                    "logged_grade": "",
                    "displayed_grade": "6A+/V3",
                    "is_benchmark": "",
                    "tries": "1",
                    "is_mirror": "",
                    "sessions_count": "1",
                    "tries_total": "1",
                    "is_repeat": "False",
                    "is_ascent": "True",
                    "comment": "",
                }
            ],
        )

    @unittest.mock.patch(
        "boardlib.api.kilter.logbook_entries", return_value=[KILTER_ENTRY]
    )
    def test_logbook_entries_kilter(self, mock_logbook_entries):
        self.assertEqual(
            list(boardlib.__main__.logbook_entries("kilter", "test", "test")),
            [KILTER_ENTRY],
        )
        mock_logbook_entries.assert_called_once_with("kilter", "test", "test")

    @unittest.mock.patch.dict(os.environ, {"BOARDSESH_PASSWORD": "test_password"})
    @unittest.mock.patch(
        "boardlib.api.boardsesh.logbook_entries", return_value=[BOARDSESH_ENTRY]
    )
    def test_logbook_boardsesh(self, mock_logbook_entries):
        without_env("BOARDSESH_TOKEN")
        rows = run_logbook(
            "boardsesh", "-u", "test@example.com", "--board-type", "moonboard"
        )

        mock_logbook_entries.assert_called_once_with(
            "test@example.com", "test_password", board_type="moonboard", token=None
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (
                rows[0]["board"],
                rows[0]["logged_grade"],
                rows[0]["is_benchmark"],
                rows[0]["is_mirror"],
            ),
            ("moonboard", "6b/V4", "True", "False"),
        )

    @unittest.mock.patch.dict(os.environ, {"BOARDSESH_TOKEN": "test_token"})
    @unittest.mock.patch("getpass.getpass", side_effect=AssertionError("prompted"))
    @unittest.mock.patch(
        "boardlib.api.boardsesh.logbook_entries", return_value=[BOARDSESH_ENTRY]
    )
    def test_logbook_boardsesh_token(self, mock_logbook_entries, mock_getpass):
        without_env("BOARDSESH_PASSWORD")
        rows = run_logbook("boardsesh")

        mock_logbook_entries.assert_called_once_with(
            None, None, board_type=None, token="test_token"
        )
        self.assertEqual(len(rows), 1)

    @unittest.mock.patch.dict(os.environ, {})
    @unittest.mock.patch("boardlib.api.kilter.logbook_entries")
    @unittest.mock.patch("boardlib.api.boardsesh.logbook_entries")
    def test_logbook_argument_errors(self, mock_boardsesh, mock_kilter):
        without_env("BOARDSESH_TOKEN")
        for arguments in (
            ("kilter",),
            ("boardsesh",),
            ("kilter", "-u", "test@example.com", "--board-type", "kilter"),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as context:
                    with contextlib.redirect_stderr(io.StringIO()):
                        run_logbook(*arguments)
                self.assertEqual(context.exception.code, 2)
        mock_boardsesh.assert_not_called()
        mock_kilter.assert_not_called()

    @unittest.mock.patch(
        "boardlib.api.boardsesh.logbook_entries", return_value=[BOARDSESH_ENTRY]
    )
    def test_logbook_entries_boardsesh(self, mock_logbook_entries):
        self.assertEqual(
            list(boardlib.__main__.logbook_entries("boardsesh", "test", "test")),
            [BOARDSESH_ENTRY],
        )
        mock_logbook_entries.assert_called_once_with("test", "test")


if __name__ == "__main__":
    unittest.main()
