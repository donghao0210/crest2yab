# crest2yab

Move your **spaces, tabs and logins (cookies)** from the [Crest](https://github.com/pauljoda/Crest) browser to the
[Yab](https://yetanotherbrowser.com) browser on macOS.

Yab can import from Arc and Dia, but not from Crest. This script fills that gap.

> [!WARNING]
> **Unofficial, unsupported, use at your own risk.** Read the [Disclaimer](#disclaimer) before running it.
> `write-spaces` **replaces everything in Yab's sidebar**, so it suits a fresh Yab install best.
> A backup is made first.

## Use it with an AI agent (easiest)

The repo includes a skill that walks Claude Code or Codex through every step. The agent runs the
commands; you quit the browsers and click **Allow** on the Keychain prompts. It is told never to
read your cookie values, and to ask before it changes Yab.

**Claude Code**
```bash
claude plugin marketplace add donghao0210/crest2yab
claude plugin install crest2yab@crest2yab
```

**Codex**
```bash
codex plugin marketplace add donghao0210/crest2yab
codex plugin add crest2yab@crest2yab
```

**Any agent that reads skills** (copy the folder in by hand)
```bash
git clone https://github.com/donghao0210/crest2yab
cp -R crest2yab/skills/crest2yab ~/.claude/skills/   # Claude Code
cp -R crest2yab/skills/crest2yab ~/.agents/skills/   # Codex and other agents
```

Then restart the agent and say: *"Move my Crest spaces and logins into Yab."*

An agent opened inside a clone of this repo picks up the same instructions from `AGENTS.md`
(and `CLAUDE.md` for Claude Code).

## What it moves

| From Crest | To Yab |
|---|---|
| Spaces (name, emoji, colour) | Spaces |
| Pinned tabs | Pinned tabs |
| Saved tabs, including nested folders and custom tab names | Saved tabs, same folders |
| Open tabs | Open tabs |
| Cookies (your logins), separately for each space | Cookies for the matching space |

**Not moved:** archived tabs, history, passwords, extensions, Crest Start Page and Settings tabs,
and cookies from sites Crest ran in its WebKit engine (usually very few).

Tested with **Crest 0.9.1** and **Yab 0.47.10** on macOS. Neither browser documents these files, so
a browser update can break this script. Run `plan` first; it changes nothing.

## Requirements

- macOS, with both browsers in `/Applications`
- [uv](https://docs.astral.sh/uv/) (`brew install uv`), or Python 3.9+ with `pip install cryptography`
- Yab opened at least once (finish its onboarding first)

## Usage

Clone the repo, then run these in order from its folder, using `uv run crest2yab.py <step>`
(or `python3 crest2yab.py <step>`). `crest2yab.py` is a link to the real script in
`skills/crest2yab/scripts/`.

| # | Step | Browsers | What happens |
|---|---|---|---|
| 1 | `plan` | either | Dry run. Shows what will move and writes a preview to `./crest2yab-preview/`. |
| 2 | `check-keys` | either | macOS asks twice for Keychain access; click **Allow**. Proves the cookies can be read. Prints counts only. |
| 3 | `write-spaces` | **Yab quit** | Backs up `~/Library/Application Support/Yab`, then replaces Yab's spaces and tabs with Crest's. |
| 4 | *(by hand)* | | Open Yab, **click into every space and let one page load in each**, then quit Yab (⌘Q). This makes Yab create each space's cookie store itself. |
| 5 | `profiles` | either | Every space should say `ready`. |
| 6 | `inject-cookies` | **both quit** | Copies each Crest space's cookies into its Yab space. |

Then open Yab. Sites you were logged into should still be logged in.

**Shared space.** Yab has one built-in space whose sign-ins are shared. One Crest space goes there,
by default your Crest default space. Choose another with `--shared "Personal"`, passed on every step.
Every other space gets its own sign-ins, as it had in Crest.

**A space says "NOT YET"** after step 4: load a page in that space in Yab, quit Yab, then run
`inject-cookies "That Space"` for that space only.

## Undo

- **Cookies only:** each space's previous cookie database is saved beside it as `Cookies.pre-crest`.
  Rename it back to `Cookies` while Yab is quit.
- **Everything:** quit Yab, delete `~/Library/Application Support/Yab`, and rename the
  `Yab.backup-<date>` folder next to it to `Yab`.

Crest itself is only ever read, never changed.

## How it works

Both browsers are built on Chromium. On macOS, Chromium encrypts each cookie with a key kept in your
login Keychain ("Crest Safe Storage" and "Yab Safe Storage"). The script:

1. reads Crest's spaces from `Crest/ControlPlane/session.sqlite` and writes them in Yab's format
   (`spaces.json` plus one `session-<space>.json` per space)
2. decrypts each Crest cookie with Crest's key, re-encrypts it with Yab's key, and writes it into
   the cookie database of the matching Yab space

Each encrypted cookie includes a hash of its site, so a wrong key is detected and never written.
Decrypted values exist only in memory: they are not printed, logged or saved anywhere else.
The script makes no network connections. It is one file, so please read it before you run it.

## Security notes

- Cookies are your logins. Anyone holding them can act as you on those sites. Run this only on your
  own Mac, for your own browser data.
- macOS asks before the script can read each browser's Keychain key. "Allow" grants access once;
  "Always Allow" lets `security` read that key again without asking. Choose "Allow".
- Some sites, Google in particular, can tie a login to the original browser and may ask you to sign
  in again. That is expected.

## Disclaimer

- **Unofficial.** This project is not affiliated with, endorsed by, sponsored by, or supported by the
  makers of Crest or Yab. Product names are used only to describe what the tool works with, and
  belong to their owners.
- **No warranty, no liability.** This software is provided "as is", without warranty of any kind, under
  the [MIT License](LICENSE). The authors are not responsible for any lost or damaged data, lost
  logins, account lockouts, security incidents, or any other harm from using it, misusing it, or
  being unable to use it. You run it entirely at your own risk.
- **Your data, your responsibility.** Use it only on a Mac and browser profiles that you own or are
  authorised to manage. Do not use it to access anyone else's data or accounts. You are responsible
  for following the terms of service of the browsers and websites involved, and any applicable law.
- **Back up first.** The script makes a backup, but you should keep your own backup of anything you
  cannot afford to lose.
- **No support obligation.** Issues and pull requests are welcome but may not get a response. Vendors:
  if you'd like this removed, or you ship an official importer, open an issue.

## License

[MIT](LICENSE)
