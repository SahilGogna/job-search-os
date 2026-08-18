# Job Hunter

Turns a resume into a scored list of matching job postings — from LinkedIn and company career sites — in a Google Sheet, with tailored resume PDFs on demand and a read-only Gmail dashboard tracking what happened to each application.

## Secrets: never touch `.env`

**Never read, `cat`, `grep`, `sed`, `head`, or otherwise open `.env`** — not to check whether a key is set, not to mask values, not to "just verify." The harness denies `Read` on it; the rule matters most for Bash, where denials can't be airtight.

Secrets cross the boundary exactly two ways:
- **In** — a value the candidate provides → `scripts/set_env_value.py` (via stdin or `--from-file-base64`, never argv)
- **Out** — a status word → `scripts/check_connections.py` (`valid` / `invalid` / `missing`, never a value)

Never print a secret or any fragment of one — not a length, not a prefix, not a suffix. Scripts load `.env` internally; that's the only place secret values live.

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

- **`/onboard`** — first run only. Resume → `context/profile.md` + `configs/search.json`, then connections, then the Gmail opt-in. If a profile already exists, use `/update-profile` instead.
- **`/update-profile`** — every profile change after setup: a conversational edit ("add my AWS cert") or a whole new resume PDF (parsed and diffed).
- **`/connections`** — `.env` setup and verification, plus the Gmail connector check. Silent when everything works; interactive only for what's broken.
- **`/job-search`** — asks which sources, fetches, scores, writes the sheet. Ends there and offers resumes.
- **`/tailor-resumes`** — resume PDFs from the last search (all / top N / above a bar / specific ones) or from a pasted JD for a job found anywhere.
- **`/application-tracker`** — read-only Gmail scan → Applications tab → private dashboard Artifact. Never modifies Gmail; never references the job-postings sheet.

## Sources of truth

- `context/profile.md` — the candidate: identity, contact, location, full work history, education, skills, certs, projects.
- `references/profile-schema.md` — the schema for the above, resume-parsing rules, and `configs/search.json` derivation rules. `onboard` and `update-profile` both follow it; keep it the single copy.
- `configs/search.json` — derived search parameters. Personal, gitignored.
- `configs/companies.json` — optional company list for career-site fetching. Not personal; tracked in git.
- `templates/resume_template.tex` (+ `resume.cls`) — what `/tailor-resumes` fills in.
- `connections.md` — every external system, and whether it's a `script` or an `mcp` connector, with the reasoning.
- `decisions/log.md` — append-only record of non-obvious decisions. Add to it rather than burying a rationale in a code comment.

## Ground rules

- Use the project venv at `.venv/`. If it doesn't exist, create it and install `requirements.txt`.
- If a step fails, print the error and stop. Don't silently fall back or skip.
- Be direct and concise. Lead with what needs action.
