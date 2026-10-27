# BoardLib 🧗‍♀️

Utilities for interacting with climbing board APIs.

## Installation 🦺

`python3 -m pip install boardlib`

## Usage ⌨️

Use `boardlib --help` for a full list of supported board names and feature flags.

### Databases 💾

To download the climb database for a given board:

`boardlib database <board_name> <database_path> --username <board_username>`

This command will first download a [sqlite](https://www.sqlite.org/index.html) database file to the given path. After downloading, the database will then use the sync API to synchronize it with the latest available data. The database will only contain the "shared," public data. User data is not synchronized. If a database already exists as `database_path`, the command will skip the download step and only perform the synchronization.

NOTE: The Moonboard is not currently supported for the database command. Contributions are welcome.

#### Supported Boards 🛹

All [Aurora Climbing](https://auroraclimbing.com/) based boards (Tension, etc.). The Kilter Board database can be downloaded but no longer synchronized, see [Kilter Board](#kilter-board-).

### Logbooks 📚

First, use the `database` command to download the SQLite database file for the board of interest. The database is not required for the Kilter Board, Boardsesh or any version of the Moonboard. Then download your logbook entries for a given board:

`boardlib logbook <board_name> --username=<board_username> --output=<output_file_name> --database-path=<database_path>`

The password is read from the `<BOARD_NAME>_PASSWORD` environment variable (for example `KILTER_PASSWORD`), or prompted for if that is not set.

This outputs a CSV file with the following fields:

```json
["board", "angle", "climb_name", "date", "logged_grade", "displayed_grade", "is_benchmark", "tries", "is_mirror", "sessions_count", "tries_total", "is_repeat", "is_ascent", "comment"]
```

#### Supported Boards 🛹

Currently all [Aurora Climbing](https://auroraclimbing.com/) based boards (Tension, etc.), the [Kilter Board](#kilter-board-), the [Moonboard](https://moonboard.com/) and the boards logged with [Boardsesh](#boardsesh-). The Moonboard web API currently appears to be broken for some iterations of the board, including 2016 and 2024.

### Images 📸

First, use the `database` command to download the SQLite database file for the board of interest. Then download the images for a given board:

`boardlib images <board_name> <database_file> <output_directory>`

This will fetch all of the images for the given board and place them in `output_directory`.

#### Supported Boards 🛹

All [Aurora Climbing](https://auroraclimbing.com/) based boards (Tension, etc.), except the Kilter Board since March 2026.

### Kilter Board 🆕

In March 2026, Kilter left Aurora Climbing for a new app and shut down the old Aurora server (kilterboardapp.com), so the Aurora endpoints no longer work for the Kilter Board. Since then:

- `boardlib logbook kilter` downloads your logbook from the new Kilter app. Sign in with the email address of your Kilter account, as the old username is rejected. No database is needed:

  `boardlib logbook kilter --username=<kilter_account_email> --output=<output_file_name>`

- The new app only has the logs made with it, from late March 2026 on.
- The new API has no benchmark or mirror information, so `is_benchmark` and `is_mirror` are empty. `logged_grade` and `comment` come from your rating of the climb at that angle, if you rated it. Failed tries logged after a send of the same climb and angle on the same day are left out. Dates are in your computer's timezone.
- `boardlib database kilter` can still download the database bundled with the last Aurora-based Kilter app (climbs up to January 2026, with the same climb UUIDs as the new app), but it can no longer be synchronized, and `boardlib images kilter` no longer works.

### Boardsesh 🔗

[Boardsesh](https://www.boardsesh.com/) is an open-source app for the Kilter Board, Tension Board, MoonBoard and other LED boards. `boardlib logbook boardsesh` downloads your Boardsesh logbook, for all boards or for one board type (kilter, tension, moonboard, decoy, touchstone, grasshopper, soill, woods or spray):

`boardlib logbook boardsesh --username=<boardsesh_account_email> [--board-type=<board_type>] --output=<output_file_name>`

- The password is read from `BOARDSESH_PASSWORD`, or prompted for. As of October 2026, Boardsesh's firewall blocks sign-ins from scripts, before the password is sent, and BoardLib then stops with an HTTP 403 error. Instead, sign in on [boardsesh.com](https://www.boardsesh.com/) in your browser, open [boardsesh.com/api/internal/ws-auth](https://www.boardsesh.com/api/internal/ws-auth) in it, and set the `BOARDSESH_TOKEN` environment variable to the value of `token` shown there. With a token, BoardLib does not sign in and needs no username or password. The token gives access to your Boardsesh account until it expires: keep it as secret as your password. It also works for accounts that sign in with Google, Apple or Facebook.
- The `board` of each entry is its Boardsesh board type, such as `kilter` or `moonboard`. `logged_grade` is your own grade of the climb, if you graded it, and `displayed_grade` the climb's consensus grade at that angle, both as Boardsesh names them (for example `6a+/V3`).
- A flash or a send is an ascent: a flash is 1 try, a send the number of tries logged with it. Failed attempts logged earlier the same day on the same climb, angle and mirror setting are added to the tries of the send, attempts after a send that day are left out, and other attempts are summed into one entry per day with `is_ascent` False, as for the Kilter Board. Dates are in your computer's timezone.
- Like the Boardsesh logbook, the download leaves out logs of climbs that Boardsesh does not list, such as deleted climbs.
- BoardLib reads your logbook 50 entries at a time, one request per second, to stay within Boardsesh's rate limits. The Boardsesh API is meant for tools that act for a signed-in climber from their own account: see the [Boardsesh API documentation](https://www.boardsesh.com/docs).

## Bugs 🐞 and Feature Requests 🗒️

Please create an issue in the [issue tracker](https://github.com/lemeryfertitta/BoardLib/issues) to report bugs or request additional features. Contributions are welcome and appreciated.
