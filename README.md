# Beavers Hockey Calendar

> **New to this project?** See [HOWTO.md](HOWTO.md) for a plain-English guide that explains how everything works without requiring any coding knowledge.

Automatically scrapes the **Beavers** team schedule from
[True North Hockey](https://www.truenorthhockey.com/Stats/StatsTeamStats?divteamID=736)
and publishes a subscribable iCal (`.ics`) feed via GitHub Pages.

A [GitHub Actions](.github/workflows/update_calendar.yml) workflow runs every
night at 2 AM ET, refreshes the schedule, and commits the updated file.

---

## Subscribe to the Calendar

Once you have pushed this repo to GitHub and enabled GitHub Pages (see below),
your calendar URL will be:

```
https://saucer42.github.io/hockey-schedule-ical/hockey_schedule.ics

```

### Apple Calendar (macOS / iOS)

1. Open **Calendar** → **File** → **New Calendar Subscription…**
2. Paste the URL above and click **Subscribe**.
3. Set **Auto-refresh** to **Every hour** (or your preference) and click **OK**.

### Google Calendar

1. Open [Google Calendar](https://calendar.google.com).
2. On the left panel click the **+** next to **Other calendars** → **From URL**.
3. Paste the URL above and click **Add calendar**.

> **Note:** Google Calendar refreshes external iCal subscriptions roughly once
> every 24 hours regardless of the refresh interval set in the feed.

### Outlook (Desktop / Microsoft 365)

1. Go to **File** → **Account Settings** → **Account Settings…** →
   **Internet Calendars** tab → **New…**
2. Paste the URL and click **Add**.

---

## Enable GitHub Pages

1. Push this repository to GitHub.
2. Go to your repo → **Settings** → **Pages**.
3. Under **Source**, select **Deploy from a branch**.
4. Choose the `main` branch and the `/docs` folder, then click **Save**.
5. GitHub will display your Pages URL — append `/hockey_schedule.ics` to get
   the full calendar subscription URL.

---

## Run Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright's headless Chromium browser
playwright install chromium

# 3. Run the scraper
python scraper.py
# → writes docs/hockey_schedule.ics
```

Requires Python 3.11+.

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── update_calendar.yml   # Nightly GitHub Actions job
├── docs/
│   └── hockey_schedule.ics       # Generated calendar feed (GitHub Pages root)
├── scraper.py                    # Playwright scraper + iCal generator
├── requirements.txt
└── README.md
```

---

## How It Works

1. **Playwright** launches a headless Chromium browser and navigates to the
   team stats page.
2. The scraper **intercepts the AJAX response** from the schedule grid endpoint
   (`/Schedule/GetTeamScheduleGrid`) — this is the same JSON that populates the
   JavaScript-rendered table.
3. Each game record is parsed (date, time, home/away teams, rink) and converted
   into a **VEVENT** in the `.ics` file, with Eastern Time (`America/Toronto`)
   applied to all datetimes.
4. The resulting `docs/hockey_schedule.ics` is committed back to the repo and
   immediately served by GitHub Pages.

---

## Customisation

All user-editable settings live in **`config.json`** at the project root. Edit that file — not `scraper.py`.

| Setting | Key in `config.json` | Default |
|---|---|---|
| Team name displayed in event titles | `team_name` | `Beavers` |
| Source page URL (update each season) | `team_page_url` | True North Hockey team page |
| Game duration | `game_duration_hours` | `1` hour |
| Output file name | `output_file` | `docs/hockey_schedule.ics` |
| Workflow run time | `update_calendar.yml` → `cron` | `0 7 * * *` (2 AM ET) |
