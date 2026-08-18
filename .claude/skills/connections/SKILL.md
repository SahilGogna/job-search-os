---
name: connections
description: Use to set up or verify this project's external connections — "set up my API keys", "connect my accounts", "configure secrets", "is Apify/Sheets/Gmail connected". Also run as a pre-flight by onboard, job-search, and application-tracker. Checks APIFY_TOKEN, JSON_KEY_BASE_64, SHEET_ID and the Gmail connector with real calls, and only becomes interactive for something that's actually broken — when everything passes it reports one line and gets out of the way. Never blocks other work.
---

## Hard rule: never touch `.env` yourself

**Never read, `cat`, `grep`, `sed`, `head`, or otherwise open `.env`** — not to check whether a key is set, not to mask values, not to "just verify." The harness denies `Read` on it, but the rule matters for Bash too, where denials can't be airtight.

Secrets cross the boundary in exactly two ways:
- **In**: a value the candidate provides → `scripts/set_env_value.py`
- **Out**: a status word (`valid` / `invalid` / `missing`) → `scripts/check_connections.py`

Never print a secret, or any part of one — not a length, not a prefix, not a suffix. If a value turns out to be wrong, ask for it fresh; don't display what's stored.

## Step 1 — Check first

```
python scripts/check_connections.py --scope <apify,sheets|apify|sheets>
```

Use whatever scope the caller needs (`job-search` → `apify,sheets`; `application-tracker` → `sheets`; standalone/onboard → both).

**Exit 0 → say one line and stop.** e.g. *"Connections look good — Apify and Sheets both valid."* No questions, nothing collected, no further steps. This is the path every healthy recurring run takes, and it's what keeps per-run verification from becoming a nuisance.

**Exit 1 → continue to Step 2**, but only for the keys it actually flagged.

## Step 2 — Collect only what's broken

For each flagged key, one at a time (never all at once):

**APIFY_TOKEN** — "Grab a token from https://console.apify.com/account/integrations and paste it here." Then:
```
printf '%s' "<pasted value>" | python scripts/set_env_value.py --key APIFY_TOKEN --stdin
```

**JSON_KEY_BASE_64** — walk them through it only if they haven't done it:
1. Google Cloud Console → create or reuse a project
2. Enable the Google Sheets API **and** Google Drive API
3. Create a service account → generate a JSON key → download it
4. Ask for the **file path** to that download, then:
```
python scripts/set_env_value.py --key JSON_KEY_BASE_64 --from-file-base64 <path>
```
Do *not* ask them to run `base64` themselves and paste the result — the encoded blob is the credential, and this way it never passes through the conversation at all.

**SHEET_ID** — re-run `check_connections.py --scope sheets` first; it prints the service-account email they need. Tell them to create a Sheet, share it with that email as **Editor**, then paste the ID or the full URL (extract the ID between `/d/` and `/edit`). Write it the same way as APIFY_TOKEN.

Write each value as soon as it's given — don't batch, so partial progress survives an interruption. (`set_env_value.py` isn't allowlisted, so each write prompts for approval. That's deliberate for a secret write.)

## Step 3 — Re-verify

Re-run `check_connections.py` with the same scope. A value being typed isn't proof it works; this is.

## Step 4 — Gmail (only if the caller needs it)

MCP tools can't run from a subprocess, so this one is a direct call: use Gmail's `list_labels` — the cheapest read-only call there is, touching no message content.

- Works → Gmail is connected.
- Fails → the connector isn't authorized. Tell them to connect it in their claude.ai connector settings (or `/mcp` in an interactive session). Note that this only affects `application-tracker` and the dashboard — `job-search` is unaffected.

## Step 5 — Update `connections.md`

For whatever was *actually* verified just now, update that row's `Auth` / `Last checked` with today's date. Don't mark something checked that wasn't, and don't leave a genuinely-working row sitting on a stale "not verified" note.

## Step 6 — Report, never block

Say plainly what's working and what isn't, and what each gap affects:

> *"Apify and Sheets are good. Gmail isn't connected yet — that only affects the application dashboard; job search works fine without it."*

**This never blocks anything.** If they'd rather finish setup later, that's fine — name which skill each gap affects and move on.
