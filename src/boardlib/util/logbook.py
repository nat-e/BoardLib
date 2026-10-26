"""
Logbook helpers for apps that log each send or set of failed tries as its own entry,
such as the new Kilter Board app and Boardsesh.
"""

import collections
import datetime
import re


def parse_timestamp(timestamp, tz=None):
    """
    Convert a UTC timestamp, such as "2026-04-01T17:42:10.123456Z" or
    "2026-04-01 17:42:10.123", to a naive datetime in the given timezone, to the
    second. A timestamp without an offset is taken to be in UTC.

    :param tz: The target timezone. Defaults to the local timezone.
    """
    # Before Python 3.11, fromisoformat needs an explicit offset and 3 or 6 fractional digits.
    timestamp = re.sub(
        r"\.(\d+)",
        lambda match: "." + match.group(1)[:6].ljust(6, "0"),
        timestamp.replace("Z", "+00:00"),
    )
    parsed = datetime.datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(tz).replace(tzinfo=None, microsecond=0)


def climb_key(entry):
    return (
        entry["climb_uuid"] or entry["climb_name"],
        entry["is_mirror"],
        entry["angle"],
    )


def add_session_counts(logbook):
    """
    Add sessions_count, tries_total and is_repeat to date-sorted logbook entries, as
    for the Aurora boards. For each climb, angle and mirror setting: the number of
    days with an entry so far, the number of tries so far, and whether there is an
    earlier entry.
    """
    days = collections.defaultdict(set)
    tries_totals = collections.defaultdict(int)
    for entry in logbook:
        key = climb_key(entry)
        entry["is_repeat"] = key in tries_totals
        days[key].add(entry["date"].date())
        entry["sessions_count"] = len(days[key])
        tries_totals[key] += entry["tries"]
        entry["tries_total"] = tries_totals[key]
    return logbook


def combine_attempts(entries):
    """
    Turn entries of single logs into logbook entries, sorted by date. Each entry
    needs at least climb_uuid, climb_name, angle, is_mirror, date, tries and
    is_ascent.

    Each ascent stays an entry. The tries of entries without an ascent are added to
    the next ascent of the same climb at the same angle on the same day, like the
    attempts of the Aurora boards. Entries without an ascent after an ascent of the
    climb that day are left out, as the climb was already sent. Other entries without
    an ascent are summed into one entry per day with is_ascent False.
    """
    entries = sorted(entries, key=lambda entry: entry["date"])

    logbook = []
    attempts = {}
    sent = set()
    for entry in entries:
        key = climb_key(entry) + (entry["date"].date(),)
        if entry["is_ascent"]:
            earlier_attempts = attempts.pop(key, None)
            if earlier_attempts:
                entry["tries"] += earlier_attempts["tries"]
            sent.add(key)
            logbook.append(entry)
        elif key in sent:
            continue
        elif key in attempts:
            attempts[key]["tries"] += entry["tries"]
        else:
            attempts[key] = entry

    logbook = sorted(logbook + list(attempts.values()), key=lambda entry: entry["date"])
    return add_session_counts(logbook)
