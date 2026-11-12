---
name: crest2yab
description: Use when someone wants to move, migrate, import or transfer their Crest browser data — spaces, pinned tabs, saved tabs, folders, open tabs, or logins/cookies — into the Yab browser on macOS. Triggers include "switch from Crest to Yab", "Yab can't import from Crest", "bring my Crest spaces into Yab", "keep my logins when moving to Yab". Runs the bundled crest2yab.py one step at a time, with the user confirming each step that changes anything.
---

# Crest → Yab migration

The bundled script `scripts/crest2yab.py` (next to this file) moves Crest's spaces, tabs and cookies
into Yab. Yab's own importer only supports Arc and Dia. The script is unofficial: it reads and writes
both browsers' undocumented files. It was tested with Crest 0.9.1 and Yab 0.47.10 on macOS.

## Rules — follow all of them

1. **Never look at cookie values.** Do not print, `cat`, `strings`, `sqlite3 select` or log
   `value`/`encrypted_value` from any `Cookies` or `Login Data` file, and do not modify the script to
   do so. Cookies are the user's logins. Counts and site names (`host_key`) are fine if needed.
2. **Say this first, before running anything:** this tool is unofficial and not affiliated with Crest
   or Yab, the user runs it at their own risk (MIT license, no warranty), and `write-spaces`
   **replaces everything in Yab's sidebar**. A backup is made, but it suits a fresh Yab best.
3. **Get explicit confirmation before `write-spaces`**, after showing the `plan` output. Only then
   pass `--yes`. Your shell can't answer the script's own `yes` prompt.
4. **The user quits the browsers, not you.** Ask them to quit with ⌘Q and wait for them to say it's
   done. Do not `kill`/`pkill` either browser, because that can leave half-written data behind.
5. **Keychain prompts need the user.** `check-keys` and `inject-cookies` make macOS ask for
   "Crest Safe Storage" and "Yab Safe Storage". Warn the user just before, and tell them to click
   **Allow** (not "Always Allow"). The command waits until they click, so use a timeout of 3+ minutes.
6. **Never change anything in `~/Library/Application Support/Crest`.** The script only reads it.
7. Only for the user's own Mac and browser data. Stop if this looks like someone else's data.

## Setup

- macOS only, with both apps in `/Applications`, and Yab opened at least once (onboarding finished).
- Run with `uv run <skill-dir>/scripts/crest2yab.py ...`. `uv` installs the one dependency
  (`cryptography`) by itself. If `uv` is missing, ask before installing it (`brew install uv`), or
  use `python3 -m pip install --user cryptography` and then `python3 <script> ...`.
- **`--shared`:** Yab has one built-in space whose sign-ins are shared. One Crest space becomes that
  space; by default it's Crest's default space. Ask the user which space they want there. Pass the
  same `--shared "<name>"` on every step, **before** the step name:
  `uv run crest2yab.py --shared "Personal" plan`.

## Steps

| # | Command | Needs | Tell the user / check |
|---|---|---|---|
| 1 | `plan` | nothing | Show the per-space table (pinned/saved/open tabs, cookie counts). Changes nothing. |
| 2 | `check-keys` | Keychain clicks | Every line should say `0 failed`. If any fail, **stop**: a browser update may have changed the format. |
| 3 | `write-spaces --yes` | Yab quit, user confirmed (rule 3) | Report the backup path it prints. |
| 4 | *(user, by hand)* | | "Open Yab, click into every space and let one page load in each, then quit Yab with ⌘Q." This makes Yab create each space's cookie store itself. |
| 5 | `profiles` | | Every space should say `ready`. |
| 6 | `inject-cookies` | Crest **and** Yab quit, Keychain clicks | Each line ends `N OK, 0 failed`. |

Then ask the user to open Yab and check a few sites they were logged into. Google may ask them to
sign in again; that's expected.

## When something goes wrong

- **A space shows `NOT YET` / `SKIPPING`:** no page finished loading there. Ask the user to load a
  page in that space, then quit Yab, then run `inject-cookies "<that space>"` (keep the same
  `--shared`). Worth it only if Crest had real logins there: `plan` shows its cookie count.
- **"… is running – quit it with Cmd+Q first":** ask the user to quit that app (rule 4).
- **Keychain error / "did you click Deny?":** run the step again and ask them to click Allow.
- **Crest data "unexpected format" or decrypt failures:** stop and tell the user the browser
  version is probably newer than the script supports. Don't improvise around it.
- **Yab is broken or empty afterwards — undo:** with Yab quit, rename
  `~/Library/Application Support/Yab` to `Yab.broken`, then rename the `Yab.backup-<date>` folder
  printed in step 3 to `Yab`. For cookies only: each `Yab/Chromium/space-*/Cookies.pre-crest` is the
  previous cookie file. Rename it back to `Cookies` while Yab is quit.

## What is not moved

Archived tabs, history, passwords, extensions, Start Page/Settings tabs, and cookies from sites Crest
ran in its WebKit engine (usually very few). Say so if the user asks for any of these.
