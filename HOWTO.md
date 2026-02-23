# How This Project Works — Plain English Guide

> This guide is written for someone who wants to understand and maintain this project without needing to know how to code. Every technical term is explained. Line numbers reference `scraper.py` so you can look at the real code and follow along.

---

## What does this project do?

Imagine you have a personal assistant who, every single night at 2 AM, goes to the True North Hockey website, writes down every game on your team's schedule, and then updates the calendar on your phone — automatically, without you doing anything.

That's exactly what this project does. It's a small program that:

1. Opens the True North Hockey website (like a browser, but invisible)
2. Reads your team's schedule
3. Converts that schedule into a format every calendar app understands (Apple Calendar, Google Calendar, Outlook)
4. Saves the result to a file that your calendar app checks every day

Once it's set up, you never touch it again. It just runs.

---

## The Files and What They Do

### `config.json` — The Settings Sheet

This is the only file you need to edit when something changes. Think of it like a settings page in an app. It contains:

```json
{
  "team_name": "Beavers",
  "team_page_url": "https://www.truenorthhockey.com/Stats/StatsTeamStats?divteamID=736",
  "game_duration_hours": 1,
  "output_file": "docs/hockey_schedule.ics"
}
```

- **`team_name`** — The name that shows up in your calendar events (e.g. "Beavers vs Mustangs")
- **`team_page_url`** — The web address of your team's page on True North Hockey. The important part is the number at the end (`divteamID=736`). This number identifies your specific team and changes each season.
- **`game_duration_hours`** — How long the calendar blocks are. Set to `1` for a 1-hour block per game.
- **`output_file`** — Where the finished calendar file gets saved. You don't need to change this.

**How to update for a new season:** See the dedicated section below.

---

### `scraper.py` — The Robot Worker

This is the main program. It does all the actual work. You don't need to edit this file anymore — it reads its settings from `config.json` automatically.

In plain English, this program:
1. Reads `config.json` to get the team URL and settings
2. Opens an invisible web browser
3. Visits the True North Hockey website
4. Eavesdrops on a hidden data signal the website sends to load the schedule table
5. Reads each game out of that signal
6. Figures out the correct year for each game date
7. Writes everything into a calendar file

---

### `docs/hockey_schedule.ics` — The Calendar File

This is the finished product. Your calendar app (Apple Calendar, Google Calendar, Outlook) reads this file to show you the schedule.

The `.ics` extension stands for **iCalendar** — a standard file format that every calendar app in the world can read, the same way every music app can play an `.mp3`. The file is just a text file with a specific structure. If you opened it in Notepad, you'd see something like:

```
BEGIN:VEVENT
SUMMARY:Beavers vs Mustangs | Rinx 3
DTSTART;TZID=America/Toronto:20250916T211500
DTEND;TZID=America/Toronto:20250916T221500
...
END:VEVENT
```

Each block like this (`BEGIN:VEVENT` to `END:VEVENT`) is one game on your calendar.

---

### `.github/workflows/update_calendar.yml` — The Alarm Clock

This file tells GitHub's servers when and how to run the robot. You don't edit this unless you want to change the time it runs.

The key line is:
```yaml
- cron: "0 7 * * *"
```

This is a timer instruction in a format called **cron**. It means: "run this at 7:00 AM UTC every day." Since UTC is 5 hours ahead of Eastern Time, that's 2:00 AM ET.

Every night GitHub's servers automatically:
1. Download your project files
2. Install the required tools
3. Run `scraper.py`
4. Save the updated calendar file back to your project

This happens even when your computer is off.

---

### `requirements.txt` — The Shopping List

Before the robot can run, it needs certain tools installed. This file lists them:

```
playwright>=1.42.0
icalendar>=5.0.12
tzdata>=2024.1
```

- **playwright** — The tool that lets Python control a web browser (like a remote control for Chrome)
- **icalendar** — The tool that knows how to write `.ics` calendar files in the correct format
- **tzdata** — A database of time zones for the whole world (needed so the program knows what "Eastern Time" means)

GitHub Actions reads this list and installs everything before running the scraper. When you run it locally, you install them yourself with `pip install -r requirements.txt`.

---

## How the Robot Works, Step by Step

This section walks through what happens when `scraper.py` runs, in plain English with the actual line numbers so you can follow along.

### Step 1 — Read the settings (`scraper.py` lines 16–29)

```python
with _CONFIG_FILE.open() as _f:
    _cfg = json.load(_f)
```

The very first thing the program does is open `config.json` and read it. This is like the robot checking its instruction sheet before starting work. Every variable it needs — the team URL, the team name, the game duration — comes from this file.

---

### Step 2 — Open an invisible web browser (`scraper.py` lines 57–66)

```python
browser = await pw.chromium.launch(headless=True)
context = await browser.new_context(user_agent="Mozilla/5.0 ...")
page = await context.new_page()
```

The program starts a real web browser (Chrome/Chromium) that runs completely invisibly in the background. `headless=True` means "run without showing a window." It also tells the browser to identify itself as a regular user's browser (`user_agent`) so the website doesn't block it.

---

### Step 3 — Set up an eavesdropper (`scraper.py` lines 68–86)

```python
async def on_response(response):
    if SCHEDULE_ENDPOINT in response.url:
        data = await response.json()
        items = data.get("dt", {}).get("it") or []
        captured.extend(items)

page.on("response", on_response)
```

Before visiting the website, the program sets up a listener. Modern websites like True North Hockey don't load all their data in the initial page load — they make a separate, hidden request in the background to fetch the actual schedule data. This is called an **AJAX request**.

`page.on("response", on_response)` means: "whenever the browser receives any response from any server, call the `on_response` function." Inside that function, it checks: is this the schedule data we want? If yes, grab it and store it.

The schedule data comes back as **JSON** — a structured text format that computers use to send data. It looks like a nested set of labelled boxes: `data → "dt" → "it"` → list of games.

---

### Step 4 — Visit the website (`scraper.py` line 90)

```python
await page.goto(TEAM_PAGE_URL, wait_until="networkidle", timeout=60_000)
await page.wait_for_timeout(5_000)
```

The browser visits the team page URL from `config.json`. `wait_until="networkidle"` means "wait until the page has fully loaded and no more data is being downloaded." Then it waits an extra 5 seconds just to be safe (some data arrives late).

While the page loads, the eavesdropper from Step 3 is silently listening and catches the schedule data packet when it arrives.

---

### Step 5 — Detect the season year (`scraper.py` lines 110–134)

```python
match = re.search(r'\b(\d{2})/(\d{2})\b', text)
fall_year   = 2000 + int(match.group(1))
spring_year = 2000 + int(match.group(2))
```

The True North Hockey website shows the current season in the page header, like "Winter 25/26". The program reads the full page text and searches for that pattern (two 2-digit numbers separated by a slash).

This is important because game dates on the website say things like "Sep 16" without a year. The program needs to know: is that September 2025 or September 2026? By knowing the season is "25/26", it can figure out that September belongs to 2025 (fall) and January belongs to 2026 (spring).

---

### Step 6 — Parse each game (`scraper.py` lines 261–294)

```python
def parse_game(raw: dict, fall_year: int, spring_year: int) -> dict | None:
    date_str  = _get(raw, "gameDate", "GameDate", ...)
    time_str  = _get(raw, "gameTime", "GameTime", ...)
    home_team = _get(raw, "homeTeamName", "HomeTeamName", ...)
    ...
    aware_dt = naive_dt.replace(tzinfo=EASTERN_TZ)
    return { "datetime": aware_dt, "rink": rink, ... }
```

For each raw game record from the JSON, the program extracts the useful pieces: date, time, home team, away team, rink, and scores. It converts the date+time into a proper timestamp with the Eastern timezone attached. If a game record is missing a date or has an unreadable format, it's skipped with a warning.

---

### Step 7 — Build the calendar file (`scraper.py` lines 333–368)

```python
cal = Calendar()
cal.add("x-wr-calname", f"{TEAM_NAME} Hockey Schedule")
...
for game in games:
    event = Event()
    event.add("summary",  _event_title(game))   # "Beavers vs Mustangs | Rinx 3"
    event.add("dtstart",  start)
    event.add("dtend",    end)
    event.add("location", game["rink"])
    cal.add_component(event)

return cal.to_ical()
```

The program creates a `Calendar` object (like a blank calendar) and adds one `Event` object for each game. Each event gets:
- A **title** ("Beavers vs Mustangs | Rinx 3")
- A **start time** (game time in Eastern timezone)
- An **end time** (start + 1 hour)
- A **location** (the rink name)
- A **description** (full game details + final score if available)
- A **unique ID** — so if the same game appears in two consecutive nightly runs, your calendar app doesn't create a duplicate. The ID is built from the date and team names, so it's always the same for the same game.

Finally, `cal.to_ical()` converts the whole thing into the `.ics` text format and saves it to `docs/hockey_schedule.ics`.

---

## How to Change the URL for a New Season

At the start of each new season, True North Hockey assigns your team a new page URL with a different `divteamID` number. Here's how to update the project:

**Step 1** — Go to the True North Hockey website and navigate to your team's schedule page.

**Step 2** — Look at the URL in your browser's address bar. It will look something like:
```
https://www.truenorthhockey.com/Stats/StatsTeamStats?divteamID=736
```
The number at the end (here `736`) is the team ID for the current season.

**Step 3** — Open `config.json` in any text editor (Notepad, VS Code, etc.)

**Step 4** — Find this line:
```json
"team_page_url": "https://www.truenorthhockey.com/Stats/StatsTeamStats?divteamID=736",
```

**Step 5** — Replace the old number with the new one. For example, if the new URL shows `divteamID=891`:
```json
"team_page_url": "https://www.truenorthhockey.com/Stats/StatsTeamStats?divteamID=891",
```

**Step 6** — Save the file. That's it.

The next time the nightly automation runs (or you run `python scraper.py` manually), it will use the new URL automatically.

> **Tip:** You can also change the team for a completely different team the same way — just paste their full URL into `team_page_url` and update `team_name` to their name.

---

## How the Nightly Automation Works

The automation is powered by **GitHub Actions** — a feature built into GitHub that lets you run programs on GitHub's own servers on a schedule.

Here's what happens every night:

1. **2:00 AM Eastern Time** — GitHub's servers wake up and read the instructions in `.github/workflows/update_calendar.yml`
2. **They set up a fresh computer** — GitHub spins up a temporary Linux server just for this task
3. **They download your project** — The server gets a copy of all your files from GitHub
4. **They install the tools** — Python, Playwright, and the libraries from `requirements.txt`
5. **They run the scraper** — `python scraper.py` runs and creates an updated `hockey_schedule.ics`
6. **They save the result** — The updated `.ics` file is committed back to your GitHub repository with a message like "chore: update hockey schedule [2026-01-15 07:00 UTC]"
7. **GitHub Pages serves the file** — Within seconds, the new `.ics` file is available at your public GitHub Pages URL
8. **Your calendar app picks it up** — The next time your phone/computer syncs the calendar subscription, it downloads the new file

Your calendar on your phone typically refreshes once every 24 hours, so changes show up within a day.

---

## Glossary

**iCal / .ics**
A file format for calendar data. The "iCal" name comes from Apple iCalendar, but it's now a universal standard. Any calendar app (Apple, Google, Outlook, etc.) can read `.ics` files. Think of it like `.mp3` for music — one format, works everywhere.

**Playwright / Headless Browser**
Playwright is a tool that lets a Python program control a real web browser (Chrome) without showing any window. "Headless" means "no visible head (screen)." It's used here because the True North Hockey schedule table is built by JavaScript running in the browser — a regular web request wouldn't see the schedule data.

**AJAX**
Short for "Asynchronous JavaScript and XML." It's the technique websites use to load data in the background after the page first loads, without refreshing the whole page. When you scroll to the schedule table on True North Hockey, the table data is fetched via an AJAX request behind the scenes. This project intercepts that request to get the raw data.

**JSON**
Short for "JavaScript Object Notation." It's a text format for structured data that computers send to each other over the internet. It looks like a series of labelled values: `{"name": "Beavers", "score": 3}`. The True North Hockey website sends the schedule as JSON in the AJAX response.

**GitHub Actions**
A service built into GitHub that can run programs automatically on a schedule. Think of it as a serverless cron job — you define what to run and when, and GitHub's computers handle everything. No server to manage.

**Cron**
A standard format for scheduling recurring tasks on computers. The schedule `0 7 * * *` means "at minute 0 of hour 7, every day of every month, every day of the week." Cron expressions are read left to right: minute, hour, day-of-month, month, day-of-week.

**GitHub Pages**
A free feature of GitHub that serves files from your repository as a public website. In this project, the `docs/` folder is served at `https://<your-username>.github.io/<repo-name>/`. The `hockey_schedule.ics` file in that folder becomes available at a public URL that your calendar app can subscribe to.

**Timezone / TZID**
Times in the calendar file are stored with a timezone label (`America/Toronto` = Eastern Time). This is important because your phone might be in a different timezone — the calendar app reads the timezone and converts the time correctly. Without it, a 9:15 PM game in Toronto might show up as 6:15 PM if you're viewing the calendar on a computer set to Pacific Time.

**UID (Unique Identifier)**
Every event in an `.ics` file has a unique ID string. Calendar apps use this to recognize when an event has been updated versus when it's a brand new event. If the same game appears in the file on two different nights (before and after a score is added), the calendar app updates the existing event rather than creating a duplicate. In this project, the UID is built from the game date and team names.
