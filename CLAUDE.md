# Job Search OS

Turns a resume into a scored list of matching job postings — from LinkedIn and company career sites — in a Google Sheet, with tailored resume PDFs on demand and a read-only Gmail dashboard tracking what happened to each application.

## Secrets: no credential enters the conversation

**Never ask the candidate to paste, type, show, repeat, or confirm the *contents* of a credential** — not a token, not a service-account JSON, not a fragment, not "just the first few characters", not to check encoding, not to verify a fix. A value typed into chat is in the transcript permanently and nothing can undo it. The only credential-adjacent thing that may enter the conversation is a **file path**.

Values reach `.env` exactly two ways:
- **The candidate types it into `.env` themselves** (`APIFY_TOKEN`, `SHEET_ID`) — scaffold the file with `scripts/init_env.py`, name the line to fill, and verify afterwards. You never see the value.
- **You encode a file** (`JSON_KEY_BASE_64`) — ask for the path, then `scripts/set_env_value.py --from-file-base64`. Base64 of the whole file is the only supported encoding; it carries the `private_key` field's literal `\n` through untouched.

Status comes out one way: `scripts/check_connections.py` → `valid` / `invalid` / `missing`, never a value.

**Never read, `cat`, `grep`, `sed`, `head`, or otherwise open `.env`** — not to check whether a key is set, not to mask values, not to "just verify." `.claude/settings.json` denies `Read` on it; the rule matters most for Bash, where denials can't be airtight. Never print a secret or any fragment of one — not a length, not a prefix, not a suffix.

**Never move a downloaded credentials file into this repo**, and don't offer to. It gets committed by accident and leaks the whole service account. Reference it by absolute path.

## Routing

| Request | Route |
|---|---|
| anything, and no `context/profile.md` yet | `/onboard` first, whatever they asked for |
| "I got my cert", "add this project", "here's my new resume", "I moved" | `/update-profile` |
| "find jobs", "search for jobs", "what's new today" | `/connections` (`apify,sheets`) → ask LinkedIn/portals/both → `/job-search` → offer `/tailor-resumes` |
| "make me a resume", "tailor my resume", pastes a JD | `/tailor-resumes` |
| "check my applications", "update my dashboard" | `/connections` (`sheets` + Gmail) → `/application-tracker` |
| "set up my keys", "is Gmail connected" | `/connections` |

Skills also check their own prerequisites — this table is about sequencing, not a substitute for those checks.

## Skills

- **`/onboard`** — first run only, in resumable phases checkpointed to `context/setup-state.md`. Preflight (names all three required connections up front) → resume → roles → profile + config, reviewed with the candidate → connections → Gmail tracking opt-in. Prefers a resume **attached to the conversation**; never hunts the filesystem for one. Closes with a ✓ only when Apify, Sheets, and Gmail are all connected — otherwise it says setup is incomplete and what's missing costs. If a profile already exists, use `/update-profile` instead.
- **`/update-profile`** — every profile change after setup: a conversational edit ("add my AWS cert") or a whole new resume PDF (parsed and diffed).
- **`/connections`** — `.env` scaffolding, setup and verification, plus the Gmail connector. Hands over the complete Apify, nine-step Google Cloud, and Gmail sequences up front, and verifies each before advancing. All three connections are **required**: a missing one is unfinished setup, not an opted-out feature. Silent when everything works; interactive only for what's broken.
- **`/job-search`** — asks which sources, fetches, scores, writes the sheet. Ends there and offers resumes.
- **`/tailor-resumes`** — resume PDFs from the last search (all / top N / above a bar / specific ones) or from a pasted JD for a job found anywhere.
- **`/application-tracker`** — read-only Gmail scan → Applications tab → private dashboard Artifact. Never modifies Gmail; never references the job-postings sheet.

## Sources of truth

- `context/profile.md` — the candidate: identity, contact, location, full work history, education, skills, certs, projects.
- `references/profile-schema.md` — the schema for the above, resume-parsing rules, and `configs/search.json` derivation rules. `onboard` and `update-profile` both follow it; keep it the single copy.
- `configs/search.json` — derived search parameters. Personal, gitignored.
- `configs/companies.json` — optional company list for career-site fetching. Not personal; tracked in git.
- `templates/resume_template.tex` (+ `resume.cls`) — what `/tailor-resumes` fills in. The skills table is built row-by-row in `generate_resumes.py`, not by LaTeX: an `l` column never wraps, so anything long must be broken up before it gets there.
- `docs/architecture.md` — the whole flow as diagrams: routing, each skill's steps, the secrets boundary, file lineage. Update it when the flow changes.
- `connections.md` — every external system, and whether it's a `script` or an `mcp` connector, with the reasoning.
- `decisions/log.md` — append-only record of non-obvious decisions. Add to it rather than burying a rationale in a code comment.

## Ground rules

- Use the project venv at `.venv/` — invoke it as `.venv/bin/python`, which is what `.claude/settings.json` allowlists. If it doesn't exist, create it and install `requirements.txt`. Windows paths: see README's Supported platforms.
- If a step fails, print the error and stop. Don't silently fall back or skip.
- Be direct and concise. Lead with what needs action.
