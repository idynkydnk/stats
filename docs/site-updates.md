# Keeping Site updates current

Every push to main checks each new non-merge commit before deployment. Include
an explicit site-update decision in each commit body. A missing decision fails
the deployment check; add the note to the commit and push the corrected history.
The page reads deployed history on each visit, so no separate publishing job or
email is needed. Kyle still chooses whether and whom to email.

For a noteworthy change, add a paragraph like this to the commit body:

    Site-Update: Save flyers to your phone
    Use the save button to keep a flyer picture or share it with friends.

Keep the title on the Site-Update line. Put the description on the immediately
following lines. A blank line ends the description, so keep internal details in
a separate paragraph. A title alone is supported for small, self-explanatory fixes.

For maintenance, tests, or other work with nothing worth announcing:

    Site-Update: none

Use one or two everyday sentences explaining what someone can do or what now
works better. Avoid file names, code terms, and internal AI instructions. Describe
AI picture changes as requests, not guarantees. Include updates for both players
and Kyle when the behavior matters to them. Do not announce every refactor.

The page displays reviewed historical copy from `data/site_update_copy.json`
and explicit Site-Update paragraphs among the latest 80 non-merge commits.
Unmarked commits and explicit skips do not appear. Full commit IDs preserve
which updates Kyle has already shared. Existing historical copy takes precedence.

The auto-push scripts create generic messages and cannot judge what is noteworthy.
Before using them, commit the work with a Site-Update paragraph yourself. A push
of unmarked automatic commits fails the deployment check rather than publishing
file lists as update descriptions.

Local check before pushing (replace the revisions with the intended push range):

    python3 scripts/check_site_updates.py origin/main HEAD
