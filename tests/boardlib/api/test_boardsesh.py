import datetime
import unittest
import unittest.mock

import requests

import boardlib.api.boardsesh
from tests.boardlib.api.requests_mocks import get_mock_request, MockResponse


UTC = datetime.timezone.utc
CSRF_URL = "https://www.boardsesh.com/api/auth/csrf"
CALLBACK_URL = "https://www.boardsesh.com/api/auth/callback/credentials"
TOKEN_URL = "https://www.boardsesh.com/api/internal/ws-auth"
GRAPHQL_URL = "https://ws.boardsesh.com/graphql"
JSON_HEADERS = {"Accept": "application/json"}
TOKEN_INFO = {"token": "test_token", "authenticated": True, "userId": "test_user"}


def make_tick(**fields):
    tick = {
        "uuid": "test_tick",
        "climbUuid": "TESTCLIMB1",
        "climbName": "test_climb_1",
        "boardType": "kilter",
        "angle": 40,
        "isMirror": False,
        "status": "flash",
        "attemptCount": 1,
        "difficultyName": None,
        "consensusDifficultyName": "6a+/V3",
        "isBenchmark": False,
        "comment": "",
        "climbedAt": "2026-04-01 18:00:00.123",
    }
    tick.update(fields)
    return tick


def process_ticks(*ticks, **kwargs):
    kwargs.setdefault("tz", UTC)
    return boardlib.api.boardsesh.process_ticks(ticks, **kwargs)


def make_session(csrf_response, callback_response=None, token_response=None):
    session = unittest.mock.MagicMock()
    session.get.side_effect = [csrf_response, token_response]
    session.post.return_value = callback_response
    return session


def sign_in_session(callback_response, token_response=None):
    return make_session(
        MockResponse(json_data={"csrfToken": "test_csrf"}),
        callback_response,
        token_response,
    )


def feed_page(items, has_more=False):
    return {"data": {"userAscentsFeed": {"items": items, "hasMore": has_more}}}


def mock_api(ticks, user_id="test_user"):
    """A requests.post mock for the GraphQL API: the profile, then pages of ticks."""

    def post(url, json=None, headers=None):
        if "BoardLibProfile" in json["query"]:
            return MockResponse(json_data={"data": {"profile": {"id": user_id}}})
        offset = json["variables"]["input"]["offset"]
        limit = json["variables"]["input"]["limit"]
        page = ticks[offset : offset + limit]
        return MockResponse(json_data=feed_page(page, offset + limit < len(ticks)))

    return post


class TestBoardsesh(unittest.TestCase):
    def test_login_success(self):
        session = sign_in_session(
            MockResponse(json_data={"url": "https://www.boardsesh.com"}),
            MockResponse(json_data=TOKEN_INFO),
        )
        with unittest.mock.patch("requests.Session", return_value=session):
            self.assertEqual(
                boardlib.api.boardsesh.login("test@example.com", "test"), TOKEN_INFO
            )
        self.assertEqual(
            session.get.call_args_list,
            [
                unittest.mock.call(CSRF_URL, headers=JSON_HEADERS),
                unittest.mock.call(TOKEN_URL, headers=JSON_HEADERS),
            ],
        )
        session.post.assert_called_once_with(
            CALLBACK_URL,
            data={
                "email": "test@example.com",
                "password": "test",
                "csrfToken": "test_csrf",
                "callbackUrl": "https://www.boardsesh.com",
                "json": "true",
            },
            headers=JSON_HEADERS,
            allow_redirects=False,
        )

    def test_login_invalid_credentials(self):
        url = (
            "https://www.boardsesh.com/api/auth/error"
            "?error=CredentialsSignin&provider=credentials"
        )
        for status_code in (requests.codes.unauthorized, requests.codes.ok):
            with self.subTest(status_code=status_code):
                session = sign_in_session(
                    MockResponse(json_data={"url": url}, status_code=status_code)
                )
                with unittest.mock.patch("requests.Session", return_value=session):
                    with self.assertRaisesRegex(ValueError, "Invalid email or password"):
                        boardlib.api.boardsesh.login("test@example.com", "test")
                # No token is requested after a failed sign-in
                session.get.assert_called_once_with(CSRF_URL, headers=JSON_HEADERS)

    def test_login_unauthorized_without_url(self):
        session = sign_in_session(MockResponse(status_code=requests.codes.unauthorized))
        with unittest.mock.patch("requests.Session", return_value=session):
            with self.assertRaisesRegex(ValueError, "Invalid email or password"):
                boardlib.api.boardsesh.login("test@example.com", "test")

    def test_login_other_errors(self):
        for url, message in (
            ("/auth/verify-request?error=EmailNotVerified", "EmailNotVerified"),
            ("https://www.boardsesh.com/api/auth/signin?csrf=true", "CSRF"),
        ):
            with self.subTest(url=url):
                session = sign_in_session(MockResponse(json_data={"url": url}))
                with unittest.mock.patch("requests.Session", return_value=session):
                    with self.assertRaisesRegex(ValueError, message):
                        boardlib.api.boardsesh.login("test@example.com", "test")

    def test_login_blocked(self):
        session = make_session(MockResponse(status_code=requests.codes.forbidden))
        with unittest.mock.patch("requests.Session", return_value=session):
            with self.assertRaisesRegex(
                requests.exceptions.HTTPError, "BOARDSESH_TOKEN"
            ):
                boardlib.api.boardsesh.login("test@example.com", "test")
        # The password is never sent
        session.post.assert_not_called()

    def test_login_server_error(self):
        session = sign_in_session(
            MockResponse(status_code=requests.codes.internal_server_error)
        )
        with unittest.mock.patch("requests.Session", return_value=session):
            with self.assertRaises(requests.exceptions.HTTPError):
                boardlib.api.boardsesh.login("test@example.com", "test")

    def test_login_no_session(self):
        session = sign_in_session(
            MockResponse(json_data={"url": "https://www.boardsesh.com"}),
            MockResponse(json_data={"token": None, "authenticated": False}),
        )
        with unittest.mock.patch("requests.Session", return_value=session):
            with self.assertRaisesRegex(ValueError, "no session"):
                boardlib.api.boardsesh.login("test@example.com", "test")

    @unittest.mock.patch(
        "requests.post",
        side_effect=get_mock_request(json_data={"data": {"profile": {"id": "test_user"}}}),
    )
    def test_graphql(self, mock_post):
        self.assertEqual(
            boardlib.api.boardsesh.graphql("test_token", "query", {"key": "value"}),
            {"profile": {"id": "test_user"}},
        )
        mock_post.assert_called_once_with(
            GRAPHQL_URL,
            json={"query": "query", "variables": {"key": "value"}},
            headers={"Authorization": "Bearer test_token", "Accept": "application/json"},
        )

    @unittest.mock.patch(
        "requests.post",
        side_effect=get_mock_request(
            json_data={
                "errors": [
                    {"message": "Rate limit exceeded", "extensions": {"code": "RATE_LIMITED"}}
                ]
            }
        ),
    )
    def test_graphql_errors(self, mock_post):
        with self.assertRaisesRegex(
            boardlib.api.boardsesh.GraphQLError, "Rate limit exceeded"
        ) as context:
            boardlib.api.boardsesh.graphql("test_token", "query")
        self.assertEqual(
            context.exception.errors[0]["extensions"]["code"], "RATE_LIMITED"
        )

    @unittest.mock.patch(
        "requests.post",
        side_effect=get_mock_request(status_code=requests.codes.bad_gateway),
    )
    def test_graphql_http_error(self, mock_post):
        with self.assertRaises(requests.exceptions.HTTPError):
            boardlib.api.boardsesh.graphql("test_token", "query")

    @unittest.mock.patch(
        "requests.post",
        side_effect=get_mock_request(json_data={"data": {"profile": {"id": "test_user"}}}),
    )
    def test_get_user_id(self, mock_post):
        self.assertEqual(boardlib.api.boardsesh.get_user_id("test_token"), "test_user")
        self.assertIn("profile", mock_post.call_args.kwargs["json"]["query"])

    @unittest.mock.patch(
        "requests.post",
        side_effect=get_mock_request(json_data={"data": {"profile": None}}),
    )
    def test_get_user_id_invalid_token(self, mock_post):
        with self.assertRaisesRegex(ValueError, "expired"):
            boardlib.api.boardsesh.get_user_id("test_token")

    @unittest.mock.patch("time.sleep")
    @unittest.mock.patch("requests.post")
    def test_get_ticks(self, mock_post, mock_sleep):
        first, second, third = (
            make_tick(uuid="tick_1"),
            make_tick(uuid="tick_2"),
            make_tick(uuid="tick_3"),
        )
        mock_post.side_effect = [
            MockResponse(json_data=feed_page([first, second], has_more=True)),
            # A tick logged during the download shifted the pages
            MockResponse(json_data=feed_page([second, third])),
        ]
        self.assertEqual(
            boardlib.api.boardsesh.get_ticks(
                "test_token", "test_user", "moonboard", page_size=2, delay=0.5
            ),
            [first, second, third],
        )
        self.assertEqual(
            [call.kwargs["json"]["variables"] for call in mock_post.call_args_list],
            [
                {
                    "userId": "test_user",
                    "input": {
                        "limit": 2,
                        "offset": offset,
                        "sortBy": "date",
                        "sortOrder": "asc",
                        "boardType": "moonboard",
                    },
                }
                for offset in (0, 2)
            ],
        )
        mock_sleep.assert_called_once_with(0.5)

    @unittest.mock.patch("time.sleep")
    @unittest.mock.patch("requests.post")
    def test_get_ticks_all_boards(self, mock_post, mock_sleep):
        mock_post.side_effect = [MockResponse(json_data=feed_page([make_tick()]))]
        self.assertEqual(
            boardlib.api.boardsesh.get_ticks("test_token", "test_user"), [make_tick()]
        )
        feed_input = mock_post.call_args.kwargs["json"]["variables"]["input"]
        self.assertNotIn("boardType", feed_input)
        self.assertEqual(feed_input["limit"], 50)
        mock_sleep.assert_not_called()

    @unittest.mock.patch("time.sleep")
    @unittest.mock.patch(
        "requests.post",
        side_effect=get_mock_request(json_data=feed_page([], has_more=True)),
    )
    def test_get_ticks_empty_page(self, mock_post, mock_sleep):
        self.assertEqual(boardlib.api.boardsesh.get_ticks("test_token", "test_user"), [])
        mock_post.assert_called_once()

    def test_grade_name(self):
        for name, grade_type, expected in (
            ("6a+/V3", "boulder", "6a+/V3"),
            ("6a+/V3", "font", "6A+"),
            ("6a+/V3", "hueco", "V3"),
            ("V3", "font", "V3"),
            (None, "font", None),
        ):
            with self.subTest(name=name, grade_type=grade_type):
                self.assertEqual(
                    boardlib.api.boardsesh.grade_name(name, grade_type), expected
                )
        with self.assertRaises(ValueError):
            boardlib.api.boardsesh.grade_name("6a+/V3", "yds")

    def test_process_ticks_flash(self):
        self.assertEqual(
            process_ticks(make_tick()),
            [
                {
                    "climb_angle_uuid": "TESTCLIMB1-40",
                    "climb_uuid": "TESTCLIMB1",
                    "board": "kilter",
                    "angle": 40,
                    "climb_name": "test_climb_1",
                    "date": datetime.datetime(2026, 4, 1, 18, 0, 0),
                    "logged_grade": None,
                    "displayed_grade": "6a+/V3",
                    "is_benchmark": False,
                    "tries": 1,
                    "is_mirror": False,
                    "is_ascent": True,
                    "comment": None,
                    "is_repeat": False,
                    "sessions_count": 1,
                    "tries_total": 1,
                }
            ],
        )

    def test_process_ticks_send(self):
        (entry,) = process_ticks(
            make_tick(
                status="send",
                attemptCount=4,
                difficultyName="6b/V4",
                isBenchmark=True,
                isMirror=True,
                comment="test_comment",
                boardType="moonboard",
            ),
            grade_type="font",
        )
        self.assertEqual(
            {
                key: entry[key]
                for key in (
                    "board",
                    "logged_grade",
                    "displayed_grade",
                    "is_benchmark",
                    "is_mirror",
                    "is_ascent",
                    "tries",
                    "comment",
                )
            },
            {
                "board": "moonboard",
                "logged_grade": "6B",
                "displayed_grade": "6A+",
                "is_benchmark": True,
                "is_mirror": True,
                "is_ascent": True,
                "tries": 4,
                "comment": "test_comment",
            },
        )

    def test_process_ticks_tries(self):
        # A flash is 1 try, and every log is at least 1 try
        for status, attempt_count, expected in (
            ("flash", 3, (True, 1)),
            ("send", 0, (True, 1)),
            ("send", None, (True, 1)),
            ("attempt", 0, (False, 1)),
            ("attempt", 5, (False, 5)),
        ):
            with self.subTest(status=status, attempt_count=attempt_count):
                (entry,) = process_ticks(
                    make_tick(status=status, attemptCount=attempt_count)
                )
                self.assertEqual((entry["is_ascent"], entry["tries"]), expected)

    def test_process_ticks_attempts_before_send(self):
        (entry,) = process_ticks(
            make_tick(status="attempt", attemptCount=2),
            make_tick(
                status="send",
                attemptCount=3,
                climbedAt="2026-04-01T18:30:00.000Z",
            ),
        )
        self.assertEqual(entry["date"], datetime.datetime(2026, 4, 1, 18, 30))
        self.assertEqual((entry["is_ascent"], entry["tries"]), (True, 5))
        self.assertEqual(entry["tries_total"], 5)

    def test_process_ticks_attempts_after_send(self):
        (ascent,) = process_ticks(
            make_tick(),
            make_tick(
                status="attempt",
                attemptCount=2,
                climbedAt="2026-04-01 18:30:00",
            ),
        )
        self.assertEqual((ascent["is_ascent"], ascent["tries"]), (True, 1))

    def test_process_ticks_attempts_other_day(self):
        ascent, attempts = process_ticks(
            make_tick(),
            make_tick(status="attempt", attemptCount=2, climbedAt="2026-04-08 18:30:00"),
            make_tick(status="attempt", attemptCount=1, climbedAt="2026-04-08 18:45:00"),
        )
        self.assertEqual((ascent["is_ascent"], ascent["tries"]), (True, 1))
        self.assertEqual(attempts["date"], datetime.datetime(2026, 4, 8, 18, 30))
        self.assertEqual((attempts["is_ascent"], attempts["tries"]), (False, 3))
        self.assertEqual(attempts["tries_total"], 4)
        self.assertEqual(attempts["sessions_count"], 2)
        self.assertTrue(attempts["is_repeat"])

    def test_process_ticks_keeps_boards_and_mirrors_apart(self):
        entries = process_ticks(
            make_tick(status="attempt", attemptCount=2),
            make_tick(boardType="tension", climbedAt="2026-04-01 18:30:00"),
            make_tick(isMirror=True, climbedAt="2026-04-01 18:45:00"),
        )
        self.assertEqual(
            [
                (entry["board"], entry["is_mirror"], entry["is_ascent"], entry["tries"])
                for entry in entries
            ],
            [
                ("kilter", False, False, 2),
                ("tension", False, True, 1),
                ("kilter", True, True, 1),
            ],
        )
        self.assertEqual([entry["is_repeat"] for entry in entries], [False] * 3)

    def test_process_ticks_days_in_timezone(self):
        ticks = (
            make_tick(status="attempt", attemptCount=2, climbedAt="2026-04-01 23:30:00"),
            make_tick(status="send", attemptCount=1, climbedAt="2026-04-02 00:30:00"),
        )
        self.assertEqual(len(process_ticks(*ticks)), 2)
        (entry,) = process_ticks(
            *ticks, tz=datetime.timezone(datetime.timedelta(hours=-4))
        )
        self.assertEqual(entry["date"], datetime.datetime(2026, 4, 1, 20, 30))
        self.assertEqual(entry["tries"], 3)

    def test_process_ticks_empty(self):
        self.assertEqual(process_ticks(), [])

    @unittest.mock.patch("time.sleep")
    @unittest.mock.patch("requests.Session")
    def test_logbook_entries_token(self, mock_session, mock_sleep):
        ticks = [
            make_tick(uuid="tick_3", climbedAt="2026-04-08 18:00:00"),
            make_tick(uuid="tick_1", status="attempt", attemptCount=2),
            make_tick(uuid="tick_2", climbedAt="2026-04-01 18:30:00"),
        ]
        with unittest.mock.patch(
            "requests.post", side_effect=mock_api(ticks)
        ) as mock_post:
            entries = boardlib.api.boardsesh.logbook_entries(
                token="test_token", board_type="kilter", grade_type="hueco", tz=UTC
            )
        self.assertEqual(
            [
                (entry["date"], entry["tries"], entry["displayed_grade"])
                for entry in entries
            ],
            [
                (datetime.datetime(2026, 4, 1, 18, 30), 3, "V3"),
                (datetime.datetime(2026, 4, 8, 18, 0), 1, "V3"),
            ],
        )
        # A token needs no sign-in
        mock_session.assert_not_called()
        self.assertEqual(
            {call.kwargs["headers"]["Authorization"] for call in mock_post.call_args_list},
            {"Bearer test_token"},
        )
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["variables"]["userId"], "test_user"
        )

    @unittest.mock.patch("time.sleep")
    def test_logbook_entries_password(self, mock_sleep):
        session = sign_in_session(
            MockResponse(json_data={"url": "https://www.boardsesh.com"}),
            MockResponse(json_data=TOKEN_INFO),
        )
        with unittest.mock.patch("requests.Session", return_value=session):
            with unittest.mock.patch(
                "requests.post", side_effect=mock_api([make_tick()])
            ) as mock_post:
                entries = boardlib.api.boardsesh.logbook_entries(
                    "test@example.com", "test", tz=UTC
                )
        self.assertEqual([entry["climb_name"] for entry in entries], ["test_climb_1"])
        self.assertEqual(
            mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer test_token"
        )
        self.assertNotIn(
            "boardType", mock_post.call_args.kwargs["json"]["variables"]["input"]
        )

    @unittest.mock.patch("requests.post")
    @unittest.mock.patch("requests.Session")
    def test_logbook_entries_invalid_grade_type(self, mock_session, mock_post):
        with self.assertRaises(ValueError):
            boardlib.api.boardsesh.logbook_entries(token="test_token", grade_type="yds")
        mock_session.assert_not_called()
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
