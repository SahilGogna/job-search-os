# Decisions

Append-only record of meaningful decisions and why they were made. Keep it terse. Future-you will thank present-you for capturing the *why*, not just the *what*.

---

## 2026-08-17 — Single-profile template, not multi-candidate

**Decision:** Convert job-hunter to one profile per repo (`context/profile.md`, `configs/search.json`), replacing the original multi-candidate `configs/<name>.json` design.

**Why:** Matches the AIS-OS one-person-per-clone pattern this project adopted. Keeps onboarding and job-search simple for a personal tool rather than a recruiting-for-others tool.

**Alternatives considered:** Keep multi-candidate support (`context/<name>/profile.md` per candidate) — rejected; the repo was being converted into a personal template, not a multi-candidate service.

**Owner:** Sahil (with Claude Code)

---

## 2026-08-17 — CLAUDE.md slimmed, procedure lives in skills

**Decision:** Move all step-by-step procedure out of `CLAUDE.md` into `.claude/skills/*/SKILL.md`; `CLAUDE.md` becomes a short pointer manifest.

**Why:** Matches AIS-OS's pattern. Keeps `CLAUDE.md` scannable and each skill self-contained.

**Alternatives considered:** Keep `CLAUDE.md` as the detailed source of truth with skills as thin triggers — rejected, doesn't match the template being adopted.

**Owner:** Sahil

---

## 2026-08-17 — Re-onboarding uses diff-and-ask, not archive-or-overwrite

**Decision:** When re-onboarding with an updated resume, diff against the existing profile and ask what to accept, rather than auto-archiving-and-replacing (AIS-OS's default) or silently overwriting.

**Why:** User wanted control over exactly what changes get applied, not either extreme.

**Alternatives considered:** Archive + overwrite — too blunt. Silent overwrite — loses control/history.

**Owner:** Sahil

---

## 2026-08-17 — Tailored resumes reorder/emphasize only, never rewrite content

**Decision:** `generate_resumes.py` reorders existing skills/bullets toward a posting's matched keywords; never invents or rewrites content, no LLM calls inside the script itself.

**Why:** Avoids fabrication/overstatement risk in a document representing the candidate. Matches this repo's "dumb scripts, no LLM calls inside code" principle.

**Alternatives considered:** Full LLM rewrite per posting (highest tailoring, highest fabrication/cost risk) — rejected. Static re-render with zero tailoring — rejected as too weak to be useful.

**Owner:** Sahil

---

## 2026-08-17 — Company career-site coverage limited to verified APIs only

**Decision:** `configs/companies.json` only lists Greenhouse/Lever/Workday companies whose actual API details (token/org/tenant+shard+site) were confirmed against real endpoint responses. Everything else is marked `"ats": "custom"` with an honest note rather than a guessed value.

**Why:** A wrong tenant/token silently 404s or returns nothing, with no visible error — worse than admitting the gap outright.

**Alternatives considered:** Guess plausible identifiers for all 25 starter companies — this was actually attempted first, and produced *wrong* values for RBC, Loblaw, Enbridge, and TC Energy on the first pass (caught by verification before shipping, not after). That failure is the direct reason this rule exists.

**Owner:** Sahil / Claude Code

---

## 2026-08-17 — Gmail application tracker is strictly read-only

**Decision:** `application-tracker` only ever calls `search_threads`/`get_thread`; never `label_thread`, `label_message`, `create_label`, or any Gmail mutation tool.

**Why:** Explicit user requirement — "we are not making any changes to Gmail itself."

**Alternatives considered:** Auto-labeling matched threads (e.g. `Job Search/Interview`) for inbox organization — considered, explicitly declined by the user.

**Owner:** Sahil

---

## 2026-08-17 — Location filter is country-wide, not province-restricted

**Decision:** `score_jobs.py`'s `passes_location_filter` matches any posting anywhere in the candidate's country (or a remote posting mentioning that country) — not just their specific province.

**Why:** The original province-only filter was both buggy (naive substring match let province code `"ON"` match inside the word "London") and too narrow (dropped legitimate in-country postings outside the candidate's own city, e.g. Vancouver, Halifax) — surfaced live during a demo.

**Alternatives considered:** Keep province-only scope, fix only the substring bug — rejected; company-site postings span many cities nationally, so country-wide coverage was the actual goal.

**Owner:** Sahil

---

## 2026-08-17 — Cross-sheet "new since last run" flags, never drops postings

**Decision:** `push_to_sheets.py` compares today's posting IDs against the most recent previous date-tab and marks a `New Since Last Run` column, but always writes every scored posting regardless of overlap.

**Why:** A still-open posting the candidate hasn't applied to should keep showing up. Dropping it after day one would hide a real opportunity. This is visibility/audit, not filtering.

**Alternatives considered:** Drop postings already seen in the previous sheet for a cleaner daily view — rejected, risks silently hiding a still-open posting.

**Owner:** Sahil

---

## 2026-08-17 — Google Sheets access stays a service-account script, not an MCP

**Decision:** All Sheets read/write logic lives in `scripts/push_to_sheets.py` and `scripts/update_application_tracker.py` via `gspread` + a service account, not a Sheets MCP connector.

**Why:** No Sheets MCP is even available in this environment. More importantly, the merge/dedupe/cross-tab-comparison logic is intricate enough that it needs to be deterministic, testable code — not re-derived by Claude via tool calls on every run. A service account also supports unattended/scheduled runs, which an OAuth-session-based MCP would not. Gmail, by contrast, genuinely needs an MCP: classifying an email's content is real reasoning that has to happen with the content in context — no script could do that instead. See `connections.md` for the full mechanism comparison.

**Alternatives considered:** Use a Sheets MCP if one becomes available — revisit if/when this needs per-user Google identity rather than a shared service account, or if scheduled/unattended runs stop being a requirement.

**Owner:** Sahil

---

## 2026-08-17 — Gmail dashboard is display-only, published as a private Claude Artifact, unconnected to the job-search Sheet

**Decision:** The application-status dashboard is built purely from Gmail-scan data (the Applications tab), never referencing the job-postings Sheet in any way. It's published as a private Claude Artifact — regenerated and republished to the same stable URL whenever the candidate asks — not a live-syncing web app, not externally hosted (e.g. Cloudflare). The "thank-you email" idea is a highlighted flag in the dashboard data, not a drafted or sent email — Gmail access stays fully read-only.

**Why:** Two clarifications from the candidate corrected earlier assumptions mid-session: (1) the job-postings Sheet is an independent deliverable — the tool doesn't track what happens to it, so the dashboard has no reason to reference it; (2) "send a thank-you" meant flag-and-highlight, not an outbound action, which keeps this fully inside the existing read-only Gmail boundary. On hosting: no Sheets MCP exists in this environment, so job data would need embedding into any page either way; email *classification* is genuine reasoning that only happens when Claude is actively running, so a client-side-only live-syncing page would be strictly worse than the already-built read-then-classify flow. A Claude Artifact gives a stable URL, private-by-default access, and zero hosting/auth/secrets setup — matching exactly the "ask Claude to update it" workflow the candidate described.

**Alternatives considered:** External hosting (Cloudflare Pages/Workers) — considered at length; rejected for now given the added auth/secrets/hosting burden on sensitive personal data, with no corresponding benefit since neither option gets true live-sync anyway. Auto-drafting or auto-sending the thank-you email — explicitly declined by the candidate; stays a flag only.

**Owner:** Sahil

---

## 2026-08-17 — Connections setup is its own skill, invoked by onboard but never blocking

**Decision:** A dedicated `connections` skill owns `.env` setup (`APIFY_TOKEN`, `JSON_KEY_BASE_64`, `SHEET_ID`, one at a time) and Gmail MCP verification, with real validation checks (a live Apify ping, an actual `open_sheet()` call, a `list_labels` Gmail call) rather than just confirming a value exists. `onboard` invokes it right after writing `configs/search.json`, but it never blocks the rest of onboarding — a candidate can defer setup and finish later.

**Why:** Requested explicitly — secrets setup is a distinct concern from resume parsing and deserves its own skill rather than being buried inline in onboarding. Validating live (not just checking a string is present) matters because a wrong/expired value would otherwise fail silently until the candidate's first real job-search run, at a much less convenient moment to debug it.

**Alternatives considered:** Fold connections setup directly into `onboard`'s steps — rejected, conflates two different concerns and makes onboarding harder to re-run cleanly. Trust `.env` values without live validation — rejected, matches this repo's broader "verify, don't assume" pattern established earlier this session (e.g. the fabricated-Workday-IDs incident).

**Owner:** Sahil

---

## 2026-08-18 — Claude never touches `.env`; secrets move only through two scripts

**Decision:** Claude must never read, `cat`, `grep`, or `sed` `.env` for any reason. Status comes out via `scripts/check_connections.py` (prints `valid`/`invalid`/`missing`, never a value); values go in via `scripts/set_env_value.py` (stdin or `--from-file-base64`, never argv). Enforced with `deny` rules on `Read(./.env*)` in `.claude/settings.local.json`.

**Why:** An audit prompted by the user found four real problems. (1) `fetch_jobs.py` passed the Apify token as a **URL query parameter**, so any failed request produced a `requests` exception containing the full URL — token included — which printed to stderr and into logs. Fixed to an `Authorization: Bearer` header. (2) Three skills instructed Claude to read `.env` to check what was set, pulling every stored secret into context to answer a yes/no question. (3) The `connections` skill told Claude to run `base64 -i key.json` and paste the result — but that blob *is* the credential. Now encoded in-process by `set_env_value.py`. (4) No rule or enforcement existed at all.

Also on the record, because guardrails should be designed against real failures rather than imagined ones: earlier in this same session Claude read `.env`, printed the Apify token's first six and last four characters, and interpolated the full token into a `curl` command line (exposing it in argv). **The user was advised to rotate `APIFY_TOKEN`.** Those three mistakes are precisely what the two-script boundary and the deny rules now prevent.

**Alternatives considered:** Rely on a written instruction alone — rejected; a rule Claude has to remember is weaker than one the harness enforces. Passing values via `--value` on the command line — rejected; argv is visible in process listings and shell history. Honest limitation recorded: Bash-level deny patterns are defense-in-depth only, since a shell has many ways to read a file, so the written rule still carries real weight there.

**Owner:** Sahil / Claude Code

---

## 2026-08-18 — Onboarding is first-run only; recurring work is split into its own skills

**Decision:** Six skills instead of four. `onboard` handles only first-run setup and hands off to `update-profile` if a profile already exists. `update-profile` (new) owns every later change — a conversational edit ("I got my AWS cert") or a full new resume PDF. `tailor-resumes` (new) is split out of `job-search`, which now ends at the sheet and offers a handoff.

**Why:** The user's framing: onboarding is one-time setup, and anything a candidate *does* repeatedly deserves its own skill. Adding a certificate shouldn't route through a resume-parsing onboarding flow — the two share only a schema, which now lives in `references/profile-schema.md` so neither duplicates it. Splitting resume generation also means a LaTeX failure or an unwanted 40-PDF compile can't ride on top of a search whose results are already safely written to the sheet, and the candidate can pick what's worth generating.

**Alternatives considered:** Keep profile creation and update as one skill — argued for initially on shared-logic grounds, then abandoned: that reasoning only covered the new-resume path and collapsed once the conversational-edit case was raised. Keep tailoring inside `job-search` — rejected; it couples fragile, optional work to a completed result.

**Owner:** Sahil

---

## 2026-08-18 — Explicit selection bypasses the resume score threshold

**Decision:** `generate_resumes.py --only-posting-ids` generates exactly the named postings and ignores `resume_tailoring_min_score`. Omitting the flag preserves threshold filtering.

**Why:** Makes "anything over 75", "just these two", and pasted-JD resumes all work through one mechanism. An explicit human choice should outrank a configured default — including for a manually pasted JD that scores below the bar, which is a legitimate thing to want a resume for.

**Alternatives considered:** A separate `--ignore-threshold` flag — redundant; naming specific postings already *is* the override signal.

**Owner:** Sahil

---

## 2026-08-18 — Renamed from "Job Hunter" to "Job Search OS"

**Decision:** The project is now **Job Search OS** (short form used everywhere; "Job Search Operating System" only if something needs spelling out). Repo renamed to `job-search-os`. Earlier entries in this log still say "job-hunter" — left as-is, since this file is append-only and those entries were accurate when written.

**Why:** "Operating system" describes what it actually became. It's no longer a single script that hunts postings — it's onboarding, a profile that persists, connection management, search, resume tailoring, and an application dashboard, routed between six skills. The name should match the shape.

**Alternatives considered:** Keep "Job Hunter" — it undersells the scope and reads like a one-off script.

**Owner:** Sahil
