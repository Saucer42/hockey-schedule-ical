#!/usr/bin/env python3
"""
Scrapes the Beavers hockey team schedule from True North Hockey and
generates a subscribable iCal (.ics) feed in the docs/ folder.

Strategy:
  1. Use Playwright to load the JS-rendered page.
  2. Intercept the AJAX response from /Schedule/GetTeamScheduleGrid.
  3. Parse game records and write docs/hockey_schedule.ics.
"""

import asyncio
import json
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Configuration — edit config.json to change these settings, not this file
# ---------------------------------------------------------------------------

_CONFIG_FILE = Path(__file__).parent / "config.json"
with _CONFIG_FILE.open() as _f:
    _cfg = json.load(_f)

TEAM_PAGE_URL       = _cfg["team_page_url"]
TEAM_NAME           = _cfg["team_name"]
GAME_DURATION_HOURS = int(_cfg["game_duration_hours"])
SCHEDULE_ENDPOINT   = "/Schedule/GetTeamScheduleGrid"
EASTERN_TZ          = ZoneInfo("America/Toronto")

OUTPUT_DIR  = Path(_cfg["output_file"]).parent
OUTPUT_FILE = Path(_cfg["output_file"])


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

async def scrape_schedule() -> tuple[list[dict], int, int]:
    """
    Launch headless Chromium, navigate to the team page, and:
      - Intercept the AJAX response carrying the schedule grid data.
      - Read the season label (e.g. "25/26") from the page header to
        determine the fall and spring years dynamically.

    Returns (games, fall_year, spring_year).
    """
    captured: list[dict] = []
    fall_year: int | None = None
    spring_year: int | None = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        async def on_response(response):
            if SCHEDULE_ENDPOINT in response.url:
                try:
                    data = await response.json()
                    items = data.get("dt", {}).get("it") or []
                    if items:
                        print(
                            f"[scraper] Captured {len(items)} game records "
                            f"from {response.url}"
                        )
                        captured.extend(items)
                    else:
                        print(
                            f"[scraper] Schedule endpoint responded but "
                            f"'dt.it' is empty. Full payload: {data}"
                        )
                except Exception as exc:
                    print(f"[scraper] Could not parse JSON response: {exc}")

        page.on("response", on_response)

        print(f"[scraper] Navigating to {TEAM_PAGE_URL} …")
        await page.goto(TEAM_PAGE_URL, wait_until="networkidle", timeout=60_000)

        # Extra wait in case grid data loads after networkidle fires
        await page.wait_for_timeout(5_000)

        # --- Extract season years from the page header ---
        # The page shows a label like "Winter 25/26"; grab the YY/YY part.
        page_text = await page.inner_text("body")
        fall_year, spring_year = _parse_season_years(page_text)

        # If no data was captured via interception, attempt DOM fallback
        if not captured:
            print("[scraper] Attempting DOM fallback …")
            captured.extend(await _dom_fallback(page))

        await browser.close()

    return captured, fall_year, spring_year


def _parse_season_years(text: str) -> tuple[int, int]:
    """
    Extract the season years from page text containing a label like "25/26".

    Returns (fall_year, spring_year), e.g. (2025, 2026).
    Falls back to the current and next calendar year if no match is found.
    """
    match = re.search(r'\b(\d{2})/(\d{2})\b', text)
    if match:
        fall_year   = 2000 + int(match.group(1))
        spring_year = 2000 + int(match.group(2))
        print(f"[scraper] Detected season: {match.group(0)} → {fall_year}/{spring_year}")
        return fall_year, spring_year

    # Fallback: infer from today's date
    today = datetime.now()
    if today.month >= 9:
        fall_year, spring_year = today.year, today.year + 1
    else:
        fall_year, spring_year = today.year - 1, today.year
    print(
        f"[scraper] Season label not found in page; "
        f"falling back to {fall_year}/{spring_year}."
    )
    return fall_year, spring_year


async def _dom_fallback(page) -> list[dict]:
    """
    Fallback: read game rows directly from the rendered schedule table.

    The grid renders rows with a <tr> per game; column order is assumed to
    match: Date | Time | Rink | Home | Home Score | Away | Away Score.
    Adjust the column indices below if the site changes layout.
    """
    rows = await page.query_selector_all("table#grdSchedule tr, table.schedule tr")
    games: list[dict] = []
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 4:
            continue
        texts = [await c.inner_text() for c in cells]
        # Best-effort mapping; true field names may differ
        games.append(
            {
                "gameDate":     texts[0].strip() if len(texts) > 0 else "",
                "gameTime":     texts[1].strip() if len(texts) > 1 else "",
                "rinkName":     texts[2].strip() if len(texts) > 2 else "",
                "homeTeamName": texts[3].strip() if len(texts) > 3 else "",
                "homeScore":    texts[4].strip() if len(texts) > 4 else "",
                "awayTeamName": texts[5].strip() if len(texts) > 5 else "",
                "awayScore":    texts[6].strip() if len(texts) > 6 else "",
            }
        )
    if games:
        print(f"[scraper] DOM fallback found {len(games)} rows.")
    else:
        print("[scraper] DOM fallback found no rows.")
    return games


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _get(data: dict, *keys: str, default: str = "") -> str:
    """Case-insensitive multi-key dict lookup."""
    for key in keys:
        for candidate in (key, key.lower(), key.upper()):
            val = data.get(candidate)
            if val is not None:
                return str(val).strip()
    return default


def _infer_year(month: int, fall_year: int, spring_year: int) -> int:
    """
    Return the correct calendar year for a game month given the season.

    Sep–Dec belong to the fall half  → fall_year   (e.g. 2025)
    Jan–Aug belong to the spring half → spring_year (e.g. 2026)
    """
    return fall_year if month >= 9 else spring_year


def _parse_date(date_str: str, fall_year: int, spring_year: int) -> datetime | None:
    """
    Parse a date string into a naive datetime (time set to 00:00).

    Handles both the yearless site format "Mon DD" (e.g. "Sep 16") and
    conventional formats that already include a year.
    """
    # Yearless formats used by this site: "Sep 16", "Sep  6"
    for fmt in ("%b %d", "%B %d"):
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            return d.replace(year=_infer_year(d.month, fall_year, spring_year))
        except ValueError:
            continue

    # Fallback: conventional formats that include a year
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def _parse_time(time_str: str) -> tuple[int, int] | None:
    """
    Parse a time string and return (hour, minute) in 24-hour form, or None.

    "12:00 AM" is treated as midnight (00:00), not as noon, per Python's
    normal %I:%M %p handling — this is already correct because strptime
    maps "12 AM" → 0 and "12 PM" → 12.  We keep an explicit note here
    for clarity.
    """
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I:%M:%S %p"):
        try:
            t = datetime.strptime(time_str.strip().upper(), fmt)
            return t.hour, t.minute
        except ValueError:
            continue
    return None


def _parse_datetime(
    date_str: str, time_str: str, fall_year: int, spring_year: int
) -> datetime | None:
    """
    Combine a date string and an optional time string into a naive datetime.
    Returns None if the date cannot be parsed.
    """
    parsed_date = _parse_date(date_str, fall_year, spring_year)
    if parsed_date is None:
        return None

    if not time_str:
        return parsed_date

    hm = _parse_time(time_str)
    if hm is not None:
        return parsed_date.replace(hour=hm[0], minute=hm[1])

    # Time string present but unparseable — keep date, log a warning
    print(f"[parser] Could not parse time '{time_str}'; using midnight.")
    return parsed_date


def parse_game(raw: dict, fall_year: int, spring_year: int) -> dict | None:
    """Convert a raw API dict into a structured game record."""
    date_str = _get(raw, "gameDate", "GameDate", "date", "Date")
    time_str = _get(raw, "gameTime", "GameTime", "time", "Time")
    rink      = _get(raw, "rinkName", "RinkName", "rink", "Rink",
                     "location", "Location", "facility", "Facility")
    home_team = _get(raw, "homeTeamName", "HomeTeamName",
                     "homeTeam", "HomeTeam", "home", "Home")
    away_team = _get(raw, "awayTeamName", "AwayTeamName",
                     "awayTeam", "AwayTeam", "away", "Away")
    home_score = _get(raw, "homeScore", "HomeScore",
                      "homeGoals", "HomeGoals", "hg", "HG")
    away_score = _get(raw, "awayScore", "AwayScore",
                      "awayGoals", "AwayGoals", "ag", "AG")

    if not date_str:
        print(f"[parser] Skipping record with no date: {raw}")
        return None

    naive_dt = _parse_datetime(date_str, time_str, fall_year, spring_year)
    if naive_dt is None:
        print(f"[parser] Could not parse date: '{date_str}' (time: '{time_str}')")
        return None

    aware_dt = naive_dt.replace(tzinfo=EASTERN_TZ)

    return {
        "datetime":   aware_dt,
        "rink":       rink,
        "home_team":  home_team,
        "away_team":  away_team,
        "home_score": home_score,
        "away_score": away_score,
    }


# ---------------------------------------------------------------------------
# iCal generation
# ---------------------------------------------------------------------------

def _event_title(game: dict) -> str:
    home = game["home_team"] or "Home"
    away = game["away_team"] or "Away"
    rink = game["rink"]

    # Put our team first, indicate whether home or away
    if away.strip().lower() == TEAM_NAME.lower():
        title = f"{TEAM_NAME} @ {home}"
    else:
        title = f"{TEAM_NAME} vs {away}"

    if rink:
        title += f" | {rink}"

    return title


def _event_description(game: dict) -> str:
    lines = [
        f"Home: {game['home_team'] or 'TBD'}",
        f"Away: {game['away_team'] or 'TBD'}",
    ]
    if game["home_score"] and game["away_score"]:
        lines.append(
            f"Final: {game['home_team']} {game['home_score']} – "
            f"{game['away_score']} {game['away_team']}"
        )
    if game["rink"]:
        lines.append(f"Rink: {game['rink']}")
    return "\n".join(lines)


def generate_ics(games: list[dict]) -> bytes:
    """Build and return a valid .ics file as bytes."""
    cal = Calendar()
    cal.add("prodid", f"-//{TEAM_NAME} Hockey//truenorthhockey.com//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"{TEAM_NAME} Hockey Schedule")
    cal.add("x-wr-timezone", "America/Toronto")
    cal.add(
        "x-wr-caldesc",
        f"Game schedule for the {TEAM_NAME} – True North Hockey.",
    )

    for game in games:
        start = game["datetime"]
        end   = start + timedelta(hours=GAME_DURATION_HOURS)

        # Build a stable UID from date+teams so re-runs don't create duplicates
        uid_base = (
            f"{start.strftime('%Y%m%dT%H%M%S')}"
            f"-{game['home_team']}-{game['away_team']}"
        ).replace(" ", "_")
        uid = f"{uid_base}@truenorthhockey.com"

        event = Event()
        event.add("summary",     _event_title(game))
        event.add("dtstart",     start)
        event.add("dtend",       end)
        event.add("location",    game["rink"] or "TBD")
        event.add("description", _event_description(game))
        event.add("uid",         uid)

        cal.add_component(event)

    return cal.to_ical()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=== Hockey Schedule Scraper ===")
    raw_games, fall_year, spring_year = await scrape_schedule()

    if not raw_games:
        print("ERROR: No game data retrieved. Check the scraper output above.")
        sys.exit(1)

    print(f"\n[parser] Parsing {len(raw_games)} raw records …")
    games = [
        g for raw in raw_games
        if (g := parse_game(raw, fall_year, spring_year)) is not None
    ]
    print(f"[parser] {len(games)} games successfully parsed.")

    if not games:
        print("ERROR: Parsing produced no valid games.")
        sys.exit(1)

    # Sort chronologically
    games.sort(key=lambda g: g["datetime"])

    print(f"\n[ical] Writing {len(games)} events to {OUTPUT_FILE} …")
    ics_bytes = generate_ics(games)
    OUTPUT_FILE.write_bytes(ics_bytes)
    print(f"[ical] Done – {len(ics_bytes):,} bytes written.")
    print(f"\nFirst game : {games[0]['datetime']}  {_event_title(games[0])}")
    print(f"Last game  : {games[-1]['datetime']}  {_event_title(games[-1])}")


if __name__ == "__main__":
    asyncio.run(main())
