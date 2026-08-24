---
name: connections
description: Use to set up or verify this project's external connections — "set up my API keys", "connect my accounts", "configure secrets", "is Apify/Sheets/Gmail connected". Also run as a pre-flight by onboard, job-search, and application-tracker. Checks APIFY_TOKEN, JSON_KEY_BASE_64, SHEET_ID and the Gmail connector with real calls, and only becomes interactive for something that's actually broken — when everything passes it reports one line and gets out of the way. Never blocks other work.
---

## Hard rule: no credential ever enters the conversation

**Never ask the candidate to paste, type, show, repeat, or confirm the *contents* of a
credential** — not an API token, not a service-account JSON, not a fragment of one, not
"just the first few characters", not to check encoding, not to verify a fix. A value
typed into chat is in the transcript permanently, and nothing downstream can undo that.

The only credential-adjacent thing that may enter the conversation is a **file path**.

Values reach `.env` exactly two ways:

| Value | How it gets there |
|---|---|
| `APIFY_TOKEN`, `SHEET_ID` | The candidate types it **into `.env` themselves**, in their own editor. You never see it. |
| `JSON_KEY_BASE_64` | You ask for the **path** to the downloaded JSON, and run `set_env_value.py --from-file-base64`. You never see the contents. |

When a value turns out to be wrong, the fix is always *"re-open `.env` and correct that
line"* — never *"show me what you entered"* and never *"paste it again"*.

**Never read, `cat`, `grep`, `sed`, `head`, or otherwise open `.env`** — not to check
whether a key is set, not to mask values, not to "just verify." `.claude/settings.json`
denies it, but the rule matters for Bash too, where denials can't be airtight. Status
comes only from `check_connections.py`, which prints `valid` / `invalid` / `missing` and
never a value. Never print a secret or any part of one — not a length, not a prefix, not
a suffix.

## Step 1 — Check first

```
.venv/bin/python scripts/check_connections.py --scope <apify,sheets|apify|sheets>
```

Use whatever scope the caller needs (`job-search` → `apify,sheets`;
`application-tracker` → `sheets`; standalone/onboard → both).

**Exit 0 → say one line and stop.** e.g. *"Connections look good — Apify and Sheets both
valid."* No questions, nothing collected, no further steps. This is the path every
healthy recurring run takes, and it's what keeps per-run verification from becoming a
nuisance.

**Exit 1 → continue to Step 2**, but only for the keys it actually flagged.

## Step 2 — Scaffold `.env`, then hand over the whole sequence

```
.venv/bin/python scripts/init_env.py
```

Creates `.env` from `example.env` if it doesn't exist and prints its absolute path. It
never overwrites an existing file and never reads one back. Tell the candidate that path
and ask them to open it in their editor — they'll be editing it directly, and it stays
open for the rest of setup.

Then give them **the complete instructions for everything that's flagged, up front, in
one message** — before asking for anything. Do not dole these out a link at a time and do
not wait to be asked for the steps. Only include the sections for keys that actually came
back broken.

### If `APIFY_TOKEN` is flagged

> 1. Create an account at https://console.apify.com
> 2. Settings → **API & Integrations**
> 3. Create a new token
> 4. Copy it into the `APIFY_TOKEN=` line in `.env`, save the file, and tell me

### If `JSON_KEY_BASE_64` or `SHEET_ID` is flagged — all nine steps, in order

> 1. Create a Google Cloud project — https://console.cloud.google.com
> 2. Enable the **Google Sheets API**
> 3. Enable the **Google Drive API**
> 4. **Credentials** → **Create Credentials** → **Service Account**
> 5. Skip every optional step (grants, user access) — none are needed
> 6. Open the service account → **Keys** tab → **Add Key** → **Create New Key** → **JSON** → download
> 7. Create the Google Sheet this project writes to, **signed in as the same Google account**
> 8. Copy the sheet ID out of its URL — the segment after `/d/` and before `/edit`, and put it in the `SHEET_ID=` line in `.env`
> 9. **Share that sheet with the service account's `client_email`, as Editor.** ← this is the step almost everyone misses. The sheet is invisible to the service account until you do it, and nothing will work. I'll give you the exact address to share with in a moment, and I'll verify it before we move on.

Two things to say plainly alongside step 6:

- **Keep the downloaded `.json` file outside this repo.** Do not move or copy it in, and
  do not offer to. A credentials file inside a git working tree gets committed by
  accident, and that leaks the entire service account. Leave it in Downloads or anywhere
  else outside the project; reference it by absolute path.
- **Don't open it and paste anything out of it.** Give me the file's path and I encode it
  in place.

## Step 3 — Collect, one key at a time, verifying each before advancing

Never batch. Never advance past a key that isn't `valid`.

**`APIFY_TOKEN`** — wait for them to say they've saved it, then:
```
.venv/bin/python scripts/check_connections.py --scope apify
```
`valid` → move on. `invalid`/`missing` → say what it means (wrong or revoked token / line
still empty) and ask them to correct that line in `.env` and save again. Never ask to see
it.

**`JSON_KEY_BASE_64`** — ask only for the **absolute path** to the downloaded JSON, then:
```
.venv/bin/python scripts/set_env_value.py --key JSON_KEY_BASE_64 --from-file-base64 <path>
```
This base64-encodes the whole file in-process; the blob never appears in a terminal, a
clipboard, or this conversation. Base64 is the only supported encoding and it is the
answer to the `private_key` newline question — the literal `\n` sequences inside the key
are carried through untouched, so there is nothing to escape, unescape, quote, or strip.

If `check_connections.py` reports *"this is raw JSON, not base64"*, the file's contents
were pasted into `.env` by hand. Fix: clear that line in `.env`, and give me the path.

**`SHEET_ID` and the share step** — now run:
```
.venv/bin/python scripts/check_connections.py --scope sheets
```
On success this prints `JSON_KEY_BASE_64: valid (service account: <email>)`. That email
is not a secret — it's the address the sheet must be shared with. **Give it to them
verbatim** and have them complete step 9: open the sheet → Share → paste that address →
**Editor** → Send.

Then re-run the same check and **require `SHEET_ID: valid` before continuing**. Until
then you'll see one of:

- `SHEET_ID: invalid (permission denied -- share the sheet with the service account above as Editor)` → step 9 isn't done, or was done for a different sheet
- `SHEET_ID: invalid (not found, or not shared with the service account above)` → the ID in `.env` is wrong, or the sheet belongs to a different Google account than the one that made the project
- `SHEET_ID: missing` → the line in `.env` is still empty

Say which one it is and the single next action. Don't move on hoping it resolves itself —
this is the failure that surfaces later as an unexplained job-search crash.

**Checkpoint as you go.** After each key verifies, note it in `context/setup-state.md`
(create it if absent) so an interrupted setup resumes at the right key instead of
starting over:

```markdown
# Setup state
- [x] APIFY_TOKEN — valid (2026-08-24)
- [x] JSON_KEY_BASE_64 — valid (2026-08-24)
- [ ] SHEET_ID — waiting on the share step
- [ ] Gmail connector
```

On entry, read this file if it exists and say which parts you're skipping and why.

## Step 4 — Re-verify everything together

```
.venv/bin/python scripts/check_connections.py --scope <original scope>
```

A value being typed isn't proof it works; this is. Per-key checks in Step 3 can pass
individually while the pair is still wrong, so this final full-scope run is not
redundant.

## Step 5 — Gmail connector

**Gmail is a required connection**, not an optional extra. Without it there is no
application tracking and no dashboard — the candidate would never be told about an
interview invite, a rejection, or a follow-up that's overdue. Ask for it the same way you
asked for the other two; don't offer it as something to skip.

MCP tools can't run from a subprocess, so verification is a direct call: use Gmail's
`list_labels` — the cheapest read-only call there is, touching no message content.

**Works** → Gmail is connected. Move on.

**Fails** → the connector isn't authorized. Give them the steps, not just the diagnosis:

> 1. Open your connector settings on claude.ai (or run `/mcp` in an interactive session)
> 2. Find **Gmail** and connect it
> 3. Approve the Google sign-in prompt
> 4. Tell me when it's done and I'll verify

Say plainly what it's for and what it will and won't do:

- It unlocks `/application-tracker` — the inbox scan that finds your applications and
  builds the status dashboard.
- It is **read-only by design**. This project only ever calls `search_threads` and
  `get_thread`. It never labels, never sends, never drafts, never modifies a message or a
  thread. That's a hard rule, not a setting.

Then re-run `list_labels` to confirm rather than taking their word for it.

If they can't connect it right now, don't stall the whole run — record it and carry it
forward, so the caller's close can report setup as incomplete. But ask first; never skip
straight past it.

## Step 6 — Update `connections.md`

For whatever was *actually* verified just now, update that row's `Auth` / `Last checked`
with today's date. Don't mark something checked that wasn't, and don't leave a
genuinely-working row sitting on a stale "not verified" note.

## Step 7 — Report

Say plainly what's working and what isn't, and what each gap actually costs. All three
connections — Apify, Sheets, Gmail — are required, so report a gap as unfinished setup,
not as a preference they've expressed:

> *"Apify and Sheets are good. Gmail still isn't connected — until it is, I can't track
> your applications or build the dashboard, so nothing will flag an interview invite or a
> rejection. Job search itself will still run."*

Be accurate about scope: a Gmail gap genuinely doesn't stop `job-search`, and saying
otherwise is a lie they'll catch. What changes is the framing — it's a missing piece of
setup to come back to, not an optional feature they've opted out of.

**Don't hard-block.** If they'd rather finish later, that's their call — name what each
gap costs, leave `context/setup-state.md` accurate so it resumes cleanly, and move on.
Whoever called this skill is responsible for reflecting an unfinished setup in how it
closes.

## Windows

Commands here use `.venv/bin/python`. On Windows that path is `.venv\Scripts\python` —
see the Supported platforms section of `README.md`.
