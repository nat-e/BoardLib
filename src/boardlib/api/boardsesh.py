"""
Boardsesh support: the logbook of Boardsesh (boardsesh.com), an open-source app for the
Kilter Board, Tension Board, MoonBoard and other LED climbing boards.

Boardsesh signs in on www.boardsesh.com with NextAuth and serves its GraphQL API from
ws.boardsesh.com/graphql. login follows the documented flow: get a CSRF token from
/api/auth/csrf, post the email address and password to
/api/auth/callback/credentials, then exchange the session cookie for a token at
/api/internal/ws-auth. The other functions send that token to the GraphQL API as a
Bearer token, over HTTP POST.

Boardsesh's firewall refuses GET requests from clients that say they are scripts, such
as python-requests, everywhere but its public read API. As of October 2026 this blocks
the first step of login, before the password is sent. Instead, open
https://www.boardsesh.com/api/internal/ws-auth in a browser signed in to Boardsesh and
pass the token shown there to logbook_entries. The firewall leaves the POST requests to
the GraphQL API alone.

The API is meant for integrations acting for a signed-in climber from their own
account, within its rate limits: see https://www.boardsesh.com/docs and
https://www.boardsesh.com/legal.
"""

import time
import urllib.parse

import requests

import boardlib.util.logbook


BOARD = "boardsesh"
WEB_HOST = "https://www.boardsesh.com"
TOKEN_URL = f"{WEB_HOST}/api/internal/ws-auth"
GRAPHQL_URL = "https://ws.boardsesh.com/graphql"
TOKEN_ENV_VAR = "BOARDSESH_TOKEN"
BOARD_TYPES = (
    "kilter",
    "tension",
    "moonboard",
    "decoy",
    "touchstone",
    "grasshopper",
    "soill",
    "woods",
    "spray",
)
GRADE_TYPES = ("boulder", "font", "hueco")
ASCENT_STATUSES = ("flash", "send")
# The most ticks the API returns per request
PAGE_SIZE = 50
# Seconds to wait between pages, to stay well within the API's rate limits
PAGE_DELAY = 1

PROFILE_QUERY = """
query BoardLibProfile {
  profile {
    id
  }
}
"""

TICKS_QUERY = """
query BoardLibTicks($userId: ID!, $input: AscentFeedInput) {
  userAscentsFeed(userId: $userId, input: $input) {
    items {
      uuid
      climbUuid
      climbName
      boardType
      angle
      isMirror
      status
      attemptCount
      difficultyName
      consensusDifficultyName
      isBenchmark
      comment
      climbedAt
    }
    hasMore
  }
}
"""

BLOCKED_MESSAGE = (
    "Boardsesh refused the sign-in request (HTTP 403): its firewall blocks sign-ins "
    "from scripts. Sign in on boardsesh.com in a browser, open "
    f"{TOKEN_URL} there and use the token it shows: set {TOKEN_ENV_VAR} for the "
    "boardlib command, or pass it as token."
)

INVALID_CREDENTIALS_MESSAGE = (
    "Invalid email or password. Boardsesh signs in with the email address of the "
    "account. Accounts that only sign in with Google, Apple or Facebook have no "
    f"password: use a token from {TOKEN_URL} instead."
)


class GraphQLError(Exception):
    """The Boardsesh API answered with errors."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(
            "; ".join(
                error.get("message", "Unknown error")
                if isinstance(error, dict)
                else str(error)
                for error in errors
            )
        )


def raise_for_status(response):
    if response.status_code == requests.codes["forbidden"]:
        raise requests.exceptions.HTTPError(BLOCKED_MESSAGE, response=response)
    response.raise_for_status()


def sign_in_error(response):
    """
    :return: The error of a NextAuth sign-in response, such as "CredentialsSignin",
        or None if the sign-in worked.
    """
    try:
        body = response.json()
    except ValueError:
        body = None
    url = body.get("url") if isinstance(body, dict) else None
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url or "").query)
    if query.get("error"):
        return query["error"][0]
    if query.get("csrf"):
        return "CSRF token rejected"
    if response.status_code == requests.codes["unauthorized"]:
        return "CredentialsSignin"
    return None


def login(username, password):
    """
    Sign in with the email address and password of a Boardsesh account, as the
    boardsesh.com sign-in form does, and get a token for the GraphQL API.

    As of October 2026, Boardsesh's firewall blocks this from scripts: it raises
    requests.exceptions.HTTPError before the password is sent. See the module
    docstring for the alternative.

    :return: The /api/internal/ws-auth response. For example:
        {
            "token": "<token>",
            "authenticated": True,
            "userId": "<id>",
            ...
        }
    """
    session = requests.Session()
    response = session.get(
        f"{WEB_HOST}/api/auth/csrf", headers={"Accept": "application/json"}
    )
    raise_for_status(response)
    csrf_token = response.json()["csrfToken"]

    response = session.post(
        f"{WEB_HOST}/api/auth/callback/credentials",
        data={
            "email": username,
            "password": password,
            "csrfToken": csrf_token,
            "callbackUrl": WEB_HOST,
            "json": "true",
        },
        headers={"Accept": "application/json"},
        allow_redirects=False,
    )
    error = sign_in_error(response)
    if error == "CredentialsSignin":
        raise ValueError(INVALID_CREDENTIALS_MESSAGE)
    if error:
        raise ValueError(f"Boardsesh sign-in failed: {error}")
    raise_for_status(response)

    response = session.get(TOKEN_URL, headers={"Accept": "application/json"})
    raise_for_status(response)
    token_info = response.json()
    if not token_info.get("authenticated") or not token_info.get("token"):
        raise ValueError("Boardsesh sign-in failed: no session was created.")
    return token_info


def graphql(token, query, variables=None):
    """
    Send a query to the Boardsesh GraphQL API.

    :param token: A token from login or from /api/internal/ws-auth. The API answers
        requests with an invalid or expired token as for a signed-out visitor.
    :return: The data of the response.
    :raises GraphQLError: If the API answers with errors.
    """
    response = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("errors"):
        raise GraphQLError(body["errors"])
    response.raise_for_status()
    return body["data"]


def get_user_id(token):
    """
    :return: The id of the signed-in user.
    :raises ValueError: If the API did not accept the token, for example because it
        expired.
    """
    profile = graphql(token, PROFILE_QUERY)["profile"]
    if not profile:
        raise ValueError(
            "Boardsesh did not accept the token. It may have expired: get a new one "
            f"from {TOKEN_URL}."
        )
    return profile["id"]


def get_ticks(token, user_id, board_type=None, page_size=PAGE_SIZE, delay=PAGE_DELAY):
    """
    Get the ticks of the signed-in user, oldest first: their flashes, sends and failed
    attempts, with climb names and grades, as their Boardsesh logbook shows them. Like
    the logbook, this leaves out ticks on climbs Boardsesh does not list, such as
    deleted climbs. A tick's difficultyName is the user's own grade, if they gave one.

    :param user_id: The id from get_user_id.
    :param board_type: One of BOARD_TYPES, or None for all of them.
    :param page_size: Ticks per request, at most 50.
    :param delay: Seconds to wait between requests.
    :return: list of ticks. For example:
        [
            {
                "uuid": "<uuid>",
                "climbUuid": "<uuid>",
                "climbName": "<name>",
                "boardType": "kilter",
                "angle": 40,
                "isMirror": False,
                "status": "send",
                "attemptCount": 3,
                "difficultyName": "6b/V4",
                "consensusDifficultyName": "6a+/V3",
                "isBenchmark": False,
                "comment": "",
                "climbedAt": "2026-04-01 17:42:10.123",
            },
            ...
        ]
    """
    ticks = {}
    offset = 0
    while True:
        feed_input = {
            "limit": page_size,
            "offset": offset,
            "sortBy": "date",
            "sortOrder": "asc",
        }
        if board_type:
            feed_input["boardType"] = board_type
        page = graphql(token, TICKS_QUERY, {"userId": user_id, "input": feed_input})[
            "userAscentsFeed"
        ]
        # A tick logged during the download can shift the pages: count each tick once
        for tick in page["items"]:
            ticks.setdefault(tick["uuid"], tick)
        offset += len(page["items"])
        if not page["hasMore"] or not page["items"]:
            return list(ticks.values())
        time.sleep(delay)


def grade_name(name, grade_type="boulder"):
    """
    :param name: A Boardsesh grade name, such as "6a/V3".
    :param grade_type: "boulder" (e.g. 6a/V3, as Boardsesh names it), "font" (e.g. 6A)
        or "hueco" (e.g. V3).
    """
    if grade_type not in GRADE_TYPES:
        raise ValueError(f"Unknown grade type {grade_type}, use one of {GRADE_TYPES}")
    if not name or grade_type == "boulder" or "/" not in name:
        return name
    font, _, hueco = name.partition("/")
    return font.upper() if grade_type == "font" else hueco


def tick_to_entry(tick, grade_type="boulder", tz=None):
    """
    Turn a tick from get_ticks into a logbook entry. A flash or a send is an ascent: a
    flash is 1 try, a send the number of tries logged with it. An attempt is that
    number of failed tries.
    """
    status = tick.get("status")
    return {
        "climb_angle_uuid": f"{tick.get('climbUuid')}-{tick.get('angle')}",
        "climb_uuid": tick.get("climbUuid"),
        "board": tick.get("boardType"),
        "angle": tick.get("angle"),
        "climb_name": tick.get("climbName"),
        "date": boardlib.util.logbook.parse_timestamp(tick["climbedAt"], tz),
        "logged_grade": grade_name(tick.get("difficultyName"), grade_type),
        "displayed_grade": grade_name(tick.get("consensusDifficultyName"), grade_type),
        "is_benchmark": tick.get("isBenchmark"),
        "tries": 1 if status == "flash" else max(tick.get("attemptCount") or 0, 1),
        "is_mirror": tick.get("isMirror"),
        "is_ascent": status in ASCENT_STATUSES,
        "comment": tick.get("comment") or None,
    }


def process_ticks(ticks, grade_type="boulder", tz=None):
    """
    Turn ticks from get_ticks into logbook entries, sorted by date, as for the Kilter
    Board: failed attempts logged before a send of the same climb, angle and mirror
    setting on the same day are added to its tries, those after a send that day are
    left out, and the others are summed into one entry per day with is_ascent False.
    See boardlib.util.logbook.combine_attempts.

    :param grade_type: "boulder" (e.g. 6a/V3), "font" (e.g. 6A) or "hueco" (e.g. V3).
    :param tz: The timezone for dates and days. Defaults to the local timezone.
    """
    return boardlib.util.logbook.combine_attempts(
        tick_to_entry(tick, grade_type, tz) for tick in ticks
    )


def logbook_entries(
    username=None,
    password=None,
    board_type=None,
    grade_type="boulder",
    tz=None,
    token=None,
):
    """
    Download the Boardsesh logbook, with the same fields as the other boards. The board
    of each entry is its Boardsesh board type, such as "kilter" or "moonboard".

    :param username: The email address of the Boardsesh account. Not needed with a
        token.
    :param password: The password of the account. Not needed with a token.
    :param board_type: One of BOARD_TYPES, or None for all of them.
    :param grade_type: "boulder" (e.g. 6a/V3), "font" (e.g. 6A) or "hueco" (e.g. V3).
    :param tz: The timezone for dates and days. Defaults to the local timezone.
    :param token: A token from /api/internal/ws-auth, opened in a browser signed in to
        Boardsesh, to use instead of signing in with the email and password.
    """
    if grade_type not in GRADE_TYPES:
        raise ValueError(f"Unknown grade type {grade_type}, use one of {GRADE_TYPES}")
    if not token:
        token = login(username, password)["token"]
    ticks = get_ticks(token, get_user_id(token), board_type)
    return process_ticks(ticks, grade_type, tz)
