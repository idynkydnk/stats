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

## iPhone app changes

This page covers both the website and the iPhone app. Whenever work includes
`/Users/mila/stats ios`, also add noteworthy app changes to this website's
`data/app_updates.json` in the same task. See `docs/site-updates.md` for the
entry format. Do not rely on website commit history to discover app changes.
Describe what changed directly, without release-status prefaces such as
"prepared for the next app update." Keep stable note IDs when editing wording
so email sharing history survives. Include the notes in the website push when pushing
these updates; do not commit unrelated iOS work just to publish a note.
