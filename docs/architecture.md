# Architecture

How Job Hunter is put together: what happens when someone talks to it, which skill handles what, which scripts do the work, and where secrets are allowed to go.

Diagrams are Mermaid, so GitHub renders them inline.

---

## 1. Routing — what happens when someone says something

Everything starts here. The single most important branch is whether a profile exists yet.

```mermaid
flowchart TD
    U(["User says something"]) --> P{"context/profile.md<br/>exists?"}
    P -- No --> ONB["/onboard<br/>first-run setup"]
    P -- Yes --> INTENT{"What are they<br/>asking for?"}

    INTENT -- "'I got my cert'<br/>'here's my new resume'" --> UPD["/update-profile"]
    INTENT -- "'find jobs for me'" --> JS["/job-search"]
    INTENT -- "'make me a resume'<br/>pastes a JD" --> TR["/tailor-resumes"]
    INTENT -- "'check my applications'" --> AT["/application-tracker"]
    INTENT -- "'set up my keys'<br/>'is Gmail connected?'" --> CON["/connections"]

    ONB --> DONE(["Ready to search"])
    UPD --> DONE
    JS -- "offers" --> TR
    TR --> DONE
    AT --> DONE
    CON --> DONE
```

Onboarding wins over the literal request: if there's no profile, "find jobs for me" runs `/onboard` first, because a search without a profile has nothing to search *for*.

---

## 2. `/onboard` — first run only

Runs once. If a profile already exists it hands off to `/update-profile` rather than duplicating that logic.

```mermaid
flowchart TD
    S0["Step 0 — venv ready?<br/>create + pip install if not"] --> S1["Step 1 — ask for the fullest<br/>multi-page resume PDF"]
    S1 --> S2["Step 2 — parse every page,<br/>every role, verbatim bullets"]
    S2 --> S3["Step 3 — propose 5-8 target roles"]
    S3 --> CONF{"Candidate<br/>confirms the list?"}
    CONF -- "edits / adds / removes" --> S3
    CONF -- "approved" --> S4["Step 4 — write<br/>context/profile.md + configs/search.json"]
    S4 --> S5["Step 5 — invoke /connections"]
    S5 --> GM{"Gmail<br/>connected?"}
    GM -- No --> S7
    GM -- Yes --> S6{"Step 6 — want Gmail<br/>application tracking?"}
    S6 -- Yes --> AT["invoke /application-tracker<br/>30-day first scan"]
    S6 -- No --> S7
    AT --> S7["Step 7 — close:<br/>what's set up, what's still missing"]
```

Target roles are **always** confirmed, never silently inferred — a resume can support several directions.

---

## 3. `/update-profile` — every change after setup

```mermaid
flowchart TD
    IN(["Profile change requested"]) --> SNAP["Step 1 — snapshot profile + config<br/>to archives/onboard-{timestamp}/"]
    SNAP --> MODE{"What kind<br/>of change?"}
    MODE -- "'I got my AWS cert'" --> A["Step 2a — apply the edit directly<br/>to the right frontmatter section"]
    MODE -- "new resume PDF" --> B["Step 2b — parse, then diff<br/>against the existing profile"]
    B --> ASK["Present the differences in plain language"]
    ASK --> PICK["Apply only what's confirmed<br/>a dropped item is surfaced, never auto-deleted"]
    A --> Q{"Did anything config-relevant<br/>change? skills / experience /<br/>location / direction"}
    PICK --> Q
    Q -- Yes --> RE["Re-derive configs/search.json<br/>+ re-confirm target roles"]
    Q -- No --> LEAVE["Leave configs/search.json alone"]
    RE --> CLOSE["Step 4 — say what changed and where"]
    LEAVE --> CLOSE
```

A new certificate with no new skills shouldn't trigger a config rewrite or another round of questions — that's what the `Q` branch protects.

---

## 4. `/connections` — check first, only ask about what's broken

This is what makes verifying on **every** run tolerable instead of nagging.

```mermaid
flowchart TD
    IN(["Called by a skill, or directly"]) --> CHK["scripts/check_connections.py --scope ..."]
    CHK --> OK{"Exit code"}
    OK -- "0 — all valid" --> TERSE["One line: 'Connections look good'<br/>STOP — no questions"]
    OK -- "1 — something's wrong" --> COLLECT["Step 2 — ask only for the<br/>flagged keys, one at a time"]
    COLLECT --> WRITE["scripts/set_env_value.py<br/>stdin, or --from-file-base64"]
    WRITE --> REV["Step 3 — re-run check_connections.py<br/>typing a value isn't proof it works"]
    REV --> GM{"Does the caller<br/>need Gmail?"}
    GM -- Yes --> LL["Step 4 — Gmail list_labels<br/>direct MCP call, not a script"]
    GM -- No --> UPD
    LL --> UPD["Step 5 — update connections.md<br/>for what was actually verified"]
    UPD --> REP["Step 6 — report; never block"]
    TERSE --> RET(["Return to caller"])
    REP --> RET
```

Gmail is checked with a direct MCP call because MCP tools aren't reachable from a subprocess — everything else goes through the script.

---

## 5. `/job-search` — ends at the sheet

```mermaid
flowchart TD
    PRE["Prereqs: profile + config exist,<br/>venv ready"] --> CON["/connections — scope apify,sheets"]
    CON --> S0{"Step 0 — which sources?<br/>asked every run"}
    S0 -- "LinkedIn" --> F1
    S0 -- "both" --> F1
    S0 -- "career sites" --> F2
    F1["fetch_jobs.py<br/>Apify → outputs/raw_linkedin.json"] --> SC
    S0 -- "both" --> F2["fetch_companies.py<br/>Greenhouse/Lever/Workday<br/>→ outputs/raw_companies.json"]
    F2 --> SC["score_jobs.py<br/>dedupe ×2 · country filter · age filter<br/>· stable posting_id → outputs/scored.json"]
    SC --> PUSH["push_to_sheets.py<br/>date tab + 'New Since Last Run'"]
    PUSH --> SUM["Step 5 — sheet URL + summary"]
    SUM --> OFFER{"Step 6 — 'N score above 60.<br/>Want resumes?'"}
    OFFER -- Yes --> TR["/tailor-resumes"]
    OFFER -- No --> STOP(["Done — results are safe in the sheet"])
```

The skill deliberately **stops at the sheet**. Resume generation is a separate skill so a LaTeX failure or an unwanted 40-PDF compile can't ride on top of a search that already succeeded.

If `configs/companies.json` doesn't exist, Step 0 is skipped entirely — there's nothing to choose between.

---

## 6. `/tailor-resumes` — five ways in

```mermaid
flowchart TD
    IN(["'Make me a resume'"]) --> LTX{"tectonic or pdflatex<br/>on PATH?"}
    LTX -- No --> INSTALL["try brew install tectonic;<br/>if that fails, stop — nothing works without it"]
    LTX -- Yes --> MODE{"From a search,<br/>or a pasted JD?"}

    MODE -- "search" --> LIST["Read outputs/scored.json,<br/>list qualifying postings"]
    LIST --> PICK{"Which ones?"}
    PICK -- "all above threshold" --> GEN_T["generate_resumes.py<br/>no flag — script's own filter"]
    PICK -- "top N" --> GEN_S
    PICK -- "above a custom bar" --> GEN_S
    PICK -- "these specific ones" --> GEN_S["generate_resumes.py<br/>--only-posting-ids<br/>THRESHOLD BYPASSED"]

    MODE -- "pasted JD" --> MJD["make_manual_posting.py<br/>scores the JD with the same rules"]
    MJD --> SCORE["Report the real score first<br/>'this matches 45% — still want it?'"]
    SCORE --> GEN_S

    GEN_T --> OUT["outputs/tailored_resumes/<br/>YYYY-MM/YYYY-MM-DD/"]
    GEN_S --> OUT
    OUT --> REP["Step 5 — count, location,<br/>and any compile failures named"]
```

`--only-posting-ids` bypassing the threshold is what makes modes 2–5 work: an explicit human choice outranks a configured default, including for a pasted JD that scores below the bar.

Manual-JD resumes are **not** written to the sheet — they didn't come from a search, and adding them would corrupt the record of what each day's search actually found.

---

## 7. `/application-tracker` — Gmail in, dashboard out

```mermaid
flowchart TD
    S0["Step 0 — /connections<br/>scope sheets + Gmail check"] --> GM{"Gmail<br/>authorized?"}
    GM -- No --> STOP(["Stop — nothing works without it"])
    GM -- Yes --> S1["Step 1 — scan window:<br/>since last scan, else 90d<br/>30d if called from onboarding"]
    S1 --> S2["Step 2 — search_threads<br/>keywords + ATS sender domains"]
    S2 --> S3["Step 3 — get_thread, then<br/>classify each: company, role, status"]
    S3 --> S4["Step 4 — update_application_tracker.py<br/>upsert into the Applications tab"]
    S4 --> S5["Step 5 — save archives/gmail_scan_state.json"]
    S5 --> S6["Step 6 — build_dashboard_data.py<br/>counts + follow-up + thank-you flags"]
    S6 --> S7["Step 7 — publish/update the<br/>Claude Artifact dashboard"]
    S7 --> S8["Step 8 — summary + dashboard URL"]
```

**Read-only, always** — `search_threads` and `get_thread` only. Never labels, never mutations, never a drafted or sent email. The "send a thank-you" idea is a *flag on the dashboard*, nothing more.

The dashboard URL is persisted in `archives/dashboard_state.json` so re-runs update the same page instead of creating a new one each time.

---

## 8. The secrets boundary

The one architectural rule that isn't about convenience.

```mermaid
flowchart LR
    subgraph CTX["Claude's context — secrets NEVER live here"]
        C["Skills and reasoning"]
    end

    subgraph SCRIPTS["Scripts — the only place secret values exist"]
        CC["check_connections.py"]
        SEV["set_env_value.py"]
        OTHER["fetch_jobs.py · push_to_sheets.py<br/>build_dashboard_data.py · ..."]
    end

    ENV[(".env")]

    C -- "a value the user just typed<br/>via stdin, never argv" --> SEV
    SEV -- "writes" --> ENV
    ENV -- "load_dotenv, in-process" --> CC
    ENV -- "load_dotenv, in-process" --> OTHER
    CC -- "'valid' / 'invalid' / 'missing'<br/>NEVER a value" --> C
    C -. "BLOCKED by deny rules<br/>and by instruction" .-x ENV
```

Rules this encodes:

- Claude never reads, `cat`s, `grep`s, or `sed`s `.env` — not even to check whether a key is set. `Read(./.env*)` is denied in `.claude/settings.local.json`.
- Status comes out as a word, never a value. No lengths, no prefixes, no suffixes.
- Values go in via **stdin** (argv is visible in process listings) or `--from-file-base64`, which encodes a service-account key in-process so the credential never reaches a terminal.
- API tokens are sent as `Authorization` headers, never URL query params — a token in a URL leaks into `requests` exception messages, which get printed and logged.

---

## 9. Files and where they come from

```mermaid
flowchart TD
    R["resumes/resume.pdf"] --> ONB["/onboard or /update-profile"]
    ONB --> PROF["context/profile.md<br/>PII, gitignored"]
    ONB --> CFG["configs/search.json<br/>personal, gitignored"]
    COMP["configs/companies.json<br/>tracked — not personal"] --> JS

    PROF --> JS["/job-search"]
    CFG --> JS
    JS --> RAW["outputs/raw_linkedin.json<br/>outputs/raw_companies.json"]
    RAW --> SCORED["outputs/scored.json"]
    SCORED --> SHEET[("Google Sheet<br/>date tabs")]
    SCORED --> TR["/tailor-resumes"]
    PROF --> TR
    TPL["templates/resume_template.tex<br/>+ resume.cls"] --> TR
    TR --> PDFS["outputs/tailored_resumes/<br/>YYYY-MM/YYYY-MM-DD/"]

    GMAIL[("Gmail<br/>read-only")] --> AT["/application-tracker"]
    AT --> APPTAB[("Google Sheet<br/>Applications tab")]
    APPTAB --> DASH["outputs/dashboard_data.json"]
    DASH --> ART[("Claude Artifact<br/>dashboard")]
```

The two halves are **deliberately unconnected**: the job-postings sheet and the Gmail dashboard never reference each other. The sheet is what the search found; the dashboard is what email says happened to applications — including ones this tool never surfaced.

---

## Design rules worth knowing

| Rule | Why |
|---|---|
| Scripts are dumb; Claude reasons | No LLM calls inside code. Scripts take a config, produce data — testable in isolation, zero token cost per row. |
| MCP for judgment, scripts for plumbing | Gmail needs an MCP because classifying an email is real reasoning. Sheets is a script because merging rows isn't. |
| Verify, don't assume | Company ATS details are confirmed against real endpoints, never guessed. A stored credential is checked with a live call, not a presence check. |
| Fail visibly, never silently | Per-item failures are logged and skipped; pipeline failures stop the run. A posting whose date can't be parsed is kept *and counted*. |
| Explicit choice beats configuration | `--only-posting-ids` overrides the score threshold, because a person naming a posting outranks a default. |

See [`decisions/log.md`](../decisions/log.md) for the reasoning behind specific choices, and [`connections.md`](../connections.md) for what's wired to what.
