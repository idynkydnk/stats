# Game times and timezones

## How would you know which games are in what timezone?

**Existing games:** We don’t. The database only stores a naive datetime (e.g. `2025-02-16 07:00:00`) with no timezone. So we can’t tell if that was entered as 7:00 in California (PST), New York (EST), or somewhere else. There’s no way to “go through” old games and assign a true timezone.

**New games (after the change):** When someone adds a game, we store the browser’s IANA timezone (e.g. `America/Los_Angeles`) in an `entered_timezone` column. Then we know that the stored time is in that zone and can display it with the right label (e.g. “7:00 AM (PST)”).

## Making everything show a time with a timezone

- **New games:** Stored timezone is used when displaying, so the time is shown with the correct zone (e.g. PST/PDT).
- **Old games:** We have no stored timezone. Options:
  1. **Assume one timezone:** Use a single “display timezone” (e.g. your primary zone) and show all old times with that label (e.g. “7:00 AM (PST)”). The time value doesn’t change; we only add a label so it’s clear what zone we’re treating it as.
  2. **Show no label:** Display the time as-is (e.g. “7:00 AM”) and only show a timezone for games that have `entered_timezone` stored.

If you set an “assumed timezone” for display (e.g. in config or env), then “going through all the games” means: when we render any game, we show the stored time plus that timezone label for old games, and the stored time plus the actual stored timezone for new games. So everything can show “right time + timezone” in the sense that every row has a zone label; for old games it’s assumed, for new games it’s the one we saved.
