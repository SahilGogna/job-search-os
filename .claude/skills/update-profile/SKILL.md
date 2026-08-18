---
name: update-profile
description: Use whenever an existing profile needs to change — "I got my AWS cert", "add this project", "I have a new resume", "update my profile", "my title changed", "I moved to Vancouver". Handles both small conversational edits and a full new resume PDF (parsed and diffed against what's already there). Requires context/profile.md to exist; if it doesn't, run onboard instead.
---

## What this skill does

Owns **every** change to `context/profile.md` after first-run setup. Two paths, one skill, because both are the same intent — "change my profile":

- **Conversational edit** — "I finished the AWS cert", "add my capstone project", "I'm in Vancouver now". No PDF involved.
- **New resume PDF** — parse it and diff against the existing profile, then apply only what's confirmed.

If `context/profile.md` doesn't exist, this is a first run — hand off to `onboard` instead.

Schema and rules for both paths: [`references/profile-schema.md`](../../../references/profile-schema.md).

## Step 1 — Snapshot first

Before writing anything, copy the current `context/profile.md` and `configs/search.json` to `archives/onboard-{YYYY-MM-DD-HHMM}/`. Do this regardless of which path runs or how small the edit is — it's the only undo available.

## Step 2a — Conversational edit

For a small, stated change: apply it directly to the relevant frontmatter section (`certifications`, `projects`, `skills`, `location`, a role's `bullets`, etc.), following the schema in §2.

Confirm what you understood before writing if there's any ambiguity — "adding *AWS Solutions Architect – Associate*, issued July 2026, right?" — but don't interrogate them over a one-line addition. Keep it proportional.

Never add anything they didn't actually say. If they mention a project vaguely, ask for the one-line description rather than inventing one.

## Step 2b — New resume PDF

1. Save it to `resumes/resume.pdf` and parse per §1 (every page, every role, verbatim bullets).
2. **Diff against the existing profile** — new/changed roles, added or dropped skills, new education or certs, changed location or contact details.
3. Present the differences in plain language, not a raw diff dump:
   > *"This resume adds a Senior Analyst role at Beta Inc (Mar 2026–present), three new skills (Airflow, dbt, Looker), and drops Tableau. Everything else matches. Take all of it, some of it, or leave the profile as-is?"*
4. Apply **only** what they confirm. A resume omitting something isn't proof they want it removed — surface the drop and let them decide, don't silently delete.

## Step 3 — Re-derive the config only if it matters

Update `configs/search.json` **only if** something config-relevant actually changed: skills, experience level, location, or the direction of their target roles.

- If it did → re-derive per §3, and **re-confirm the target-roles list** with them (same as onboarding Step 3) before writing.
- If it didn't → leave `configs/search.json` completely alone. A new certification with no new skills shouldn't trigger a config rewrite or a redundant round of questions.

Say which of the two happened, so they know whether their next search behaves differently.

## Step 4 — Close

One line on what changed and where:

> *"Added the AWS cert to your profile. Search config unchanged — no new skills to weight. Snapshot saved in archives/ if you want to roll back."*
