# Changelog

All notable changes to this project are documented here.

---

## [Unreleased]

---

## 2026-03-07

### Fixed
- **Playoff game times now display correctly as PM.**
  The playoff page on True North Hockey lists times without an AM/PM indicator
  (e.g. `10:30` rather than `10:30 PM`). The scraper was falling back to
  24-hour parsing and treating all playoff games as morning events. The parser
  now assumes PM for any bare time string on the playoff page, matching how
  games are actually scheduled. (`scraper.py` — `_parse_playoff_lines`)

### Documentation
- **README.md** — Added `config.json` and `HOWTO.md` to the project structure
  tree; added `playoff_page_url` to the Customisation settings table.
- **HOWTO.md** — Corrected example playoff times to reflect evening scheduling;
  added a note explaining that the scraper assumes all playoff game times are PM.
- **CHANGELOG.md** — Created this file.

---

## 2026-03-04

### Added
- Playoff schedule scraping (`scrape_playoff_schedule`, `_parse_playoff_lines`).
  The scraper now visits the playoff bracket page, parses team and game
  information from the rendered page text, and merges matching games into the
  calendar feed. Playoff events are prefixed with `[Playoff]` in the title.
- `playoff_page_url` setting in `config.json`. Set to `""` to disable playoff
  scraping (e.g. during the off-season).
- `HOWTO.md` — Plain-English guide for non-technical maintainers covering every
  file, the step-by-step scraper flow, and seasonal update instructions.

---

## 2025 Season

### Added
- Initial project: Playwright-based scraper that intercepts the AJAX schedule
  endpoint on True North Hockey and generates a subscribable `.ics` calendar
  feed served via GitHub Pages.
- GitHub Actions workflow (`update_calendar.yml`) running nightly at 2 AM ET
  to refresh and commit the calendar file automatically.
- `config.json` for user-editable settings (team name, URLs, game duration).
- Eastern timezone (`America/Toronto`) applied to all calendar events.
- Stable event UIDs derived from game date and team names to prevent duplicate
  calendar entries across nightly runs.
