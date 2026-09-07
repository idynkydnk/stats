# Project instructions

## Site updates

For every change you commit or prepare to push, decide whether Kyle or players
would benefit from knowing about it. Include a `Site-Update: <readable title>`
paragraph in the commit body, with a short plain-language description directly
below it. For work with nothing worth announcing, include `Site-Update: none`.
Follow `docs/site-updates.md`. Do this as part of the work without asking the user.
Avoid code jargon, file names, and technical commit summaries in published notes.
Before pushing, run the site-update check over the commits being pushed. The
main deployment workflow rejects commits missing this decision. Never send an
update email unless the user explicitly requests it.
