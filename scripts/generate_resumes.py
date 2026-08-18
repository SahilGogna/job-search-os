"""Generate tailored resume PDFs for scored postings above a match-score threshold.

For every posting in --scored-in whose match_score is above the configured
threshold (config field "resume_tailoring_min_score", default 60), this:

  1. Loads the candidate's full profile from the YAML frontmatter of --profile.
  2. Reorders the profile's skills list and each role's bullets so the ones
     overlapping that posting's already-matched skills surface first.
  3. Fills the LaTeX --template's placeholder tokens with the reordered content,
     stripping any %%SECTION:NAME:START/END%% block whose data is empty
     (e.g. no `projects` or `leadership` in the profile) rather than leaving
     unfilled placeholder text in a real resume.
  4. Compiles the filled .tex to a PDF via tectonic (preferred) or pdflatex.
     Any .cls/.sty files sitting next to --template (e.g. resume.cls) are
     copied alongside so custom document classes resolve.

This never invents or rewrites content -- it only reorders/emphasizes what is
already in the profile, matching the rest of this repo's "dumb scripts, no LLM
calls inside code" convention. Claude Code / the job-search skill is the layer
that decides *when* to run this; the script itself does no reasoning.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

DEFAULT_MIN_SCORE = 60

LATEX_SPECIAL = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

SECTION_MARKER = re.compile(r"%%SECTION:(\w+):START%%.*?%%SECTION:\1:END%%\n?", re.DOTALL)


def escape_latex(text: str) -> str:
    return "".join(LATEX_SPECIAL.get(ch, ch) for ch in str(text))


def load_profile(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---"):
        print(f"ERROR: {path} has no YAML frontmatter to read", file=sys.stderr)
        sys.exit(1)
    parts = text.split("---", 2)
    if len(parts) < 3:
        print(f"ERROR: {path} has malformed YAML frontmatter", file=sys.stderr)
        sys.exit(1)
    data = yaml.safe_load(parts[1]) or {}
    if not isinstance(data, dict):
        print(f"ERROR: {path} frontmatter did not parse to a mapping", file=sys.stderr)
        sys.exit(1)
    return data


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")
    return cleaned[:60] or "untitled"


def normalize(text: str) -> str:
    """Lowercase and fold underscores to spaces so config skill *keys* (which are
    snake_case identifiers, e.g. "power_bi") compare equal to natural-language
    skill names or resume prose ("Power BI")."""
    return re.sub(r"\s+", " ", str(text).lower().replace("_", " ")).strip()


def matched_keywords(item: dict) -> set[str]:
    raw = item.get("skills_matched") or ""
    return {normalize(s) for s in raw.split(",") if s.strip()}


def reorder_skills(skills: list[str], keywords: set[str]) -> list[str]:
    def rank(skill: str) -> tuple[int, str]:
        normalized = normalize(skill)
        hit = any(kw in normalized or normalized in kw for kw in keywords)
        return (0 if hit else 1, normalized)

    return sorted(skills, key=rank)


def bullet_score(bullet: str, keywords: set[str]) -> int:
    normalized = normalize(bullet)
    return sum(1 for kw in keywords if kw in normalized)


def reorder_experience(experience: list[dict], keywords: set[str]) -> list[dict]:
    tailored = []
    for role in experience:
        bullets = list(role.get("bullets", []))
        bullets.sort(key=lambda b: bullet_score(b, keywords), reverse=True)
        tailored.append({**role, "bullets": bullets})
    return tailored


def render_address_line_1(profile: dict) -> str:
    location = profile.get("location") or {}
    location_str = ", ".join(
        part for part in [location.get("city"), location.get("region"), location.get("country")] if part
    )
    parts = [p for p in [profile.get("phone"), location_str] if p]
    return " \\\\ ".join(escape_latex(p) for p in parts)


def render_address_line_2(profile: dict) -> str:
    # resume.cls issues \nofiles, which disables the .aux file hyperref needs,
    # so links are rendered as plain escaped text rather than \href.
    parts = []
    email = profile.get("email")
    if email:
        parts.append(escape_latex(email))
    for url in (profile.get("links") or {}).values():
        if url:
            parts.append(escape_latex(url))
    return " \\\\ ".join(parts)


def render_education_block(education: list[dict]) -> str:
    lines = []
    for entry in education:
        degree = escape_latex(entry.get("degree", ""))
        institution = escape_latex(entry.get("institution", ""))
        dates = escape_latex(entry.get("dates", ""))
        lines.append(f"{{\\bf {degree}}}, {institution} \\hfill {{{dates}}}\\\\")
    return "\n".join(lines)


def render_experience_block(experience: list[dict]) -> str:
    blocks = []
    for role in experience:
        company = escape_latex(role.get("company", ""))
        dates = escape_latex(role.get("dates", ""))
        title = escape_latex(role.get("title", ""))
        location = escape_latex(role.get("location", ""))
        bullets = "\n".join(f"\\item {escape_latex(b)}" for b in role.get("bullets", []))
        blocks.append(
            f"\\begin{{rSubsection}}{{{company}}}{{{dates}}}{{{title}}}{{{location}}}\n"
            f"{bullets}\n"
            f"\\end{{rSubsection}}"
        )
    return "\n\n".join(blocks)


def render_projects_block(projects: list[dict]) -> str:
    items = []
    for project in projects:
        title = escape_latex(project.get("title", ""))
        description = escape_latex(project.get("description", ""))
        items.append(f"\\item \\textbf{{{title}.}} {{{description}}}")
    if not items:
        return ""
    return "\n".join(items)


def render_leadership_block(leadership: list[dict]) -> str:
    items = []
    for entry in leadership:
        title = escape_latex(entry.get("title", ""))
        description = escape_latex(entry.get("description", ""))
        items.append(f"\\item \\textbf{{{title}.}} {{{description}}}" if title else f"\\item {description}")
    if not items:
        return ""
    return "\\begin{itemize}\n" + "\n".join(items) + "\n\\end{itemize}"


def strip_empty_sections(tex: str, empty_names: set[str]) -> str:
    def _strip(match: re.Match) -> str:
        name = match.group(1)
        return "" if name in empty_names else match.group(0)

    return SECTION_MARKER.sub(_strip, tex)


def strip_section_markers(tex: str) -> str:
    """Remove the remaining %%SECTION:...%% marker lines for sections we kept."""
    return re.sub(r"%%SECTION:\w+:(START|END)%%\n?", "", tex)


def find_latex_engine() -> tuple[str, list[str]] | None:
    if shutil.which("tectonic"):
        return "tectonic", ["tectonic", "--outdir", "{outdir}", "{texfile}"]
    if shutil.which("pdflatex"):
        return "pdflatex", [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            "{outdir}",
            "{texfile}",
        ]
    return None


def compile_pdf(tex_path: Path, out_dir: Path) -> tuple[bool, str]:
    engine = find_latex_engine()
    if engine is None:
        return False, "no LaTeX engine found in PATH (looked for tectonic, pdflatex)."
    _, cmd_template = engine
    cmd = [part.format(outdir=str(out_dir), texfile=str(tex_path)) for part in cmd_template]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-15:]
        return False, "\n".join(tail)
    return True, ""


def build_tex(template_text: str, profile: dict, keywords: set[str]) -> str:
    skills = reorder_skills(list(profile.get("skills", [])), keywords)
    experience = reorder_experience(list(profile.get("experience", [])), keywords)
    projects = list(profile.get("projects", []))
    leadership = list(profile.get("leadership", []))

    projects_block = render_projects_block(projects)
    leadership_block = render_leadership_block(leadership)

    replacements = {
        "{{FULL_NAME}}": escape_latex(profile.get("name", "")),
        "{{ADDRESS_LINE_1}}": render_address_line_1(profile),
        "{{ADDRESS_LINE_2}}": render_address_line_2(profile),
        "{{SUMMARY}}": escape_latex(profile.get("summary", "")),
        "{{SKILLS_LIST}}": escape_latex(", ".join(skills)),
        "{{EDUCATION_BLOCK}}": render_education_block(list(profile.get("education", []))),
        "{{EXPERIENCE_BLOCK}}": render_experience_block(experience),
        "{{PROJECTS_BLOCK}}": projects_block,
        "{{LEADERSHIP_BLOCK}}": leadership_block,
    }

    empty_sections = set()
    if not projects_block:
        empty_sections.add("PROJECTS")
    if not leadership_block:
        empty_sections.add("LEADERSHIP")

    tex = strip_empty_sections(template_text, empty_sections)
    tex = strip_section_markers(tex)
    for token, value in replacements.items():
        tex = tex.replace(token, value)
    return tex


def copy_template_assets(template: Path, dest_dir: Path) -> None:
    for asset in template.parent.glob("*.cls"):
        shutil.copy(asset, dest_dir / asset.name)
    for asset in template.parent.glob("*.sty"):
        shutil.copy(asset, dest_dir / asset.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--scored-in", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    if not args.profile.exists():
        print(f"ERROR: profile not found at {args.profile}. Run the onboard skill first.", file=sys.stderr)
        return 1
    if not args.template.exists():
        print(f"ERROR: template not found at {args.template}.", file=sys.stderr)
        return 1

    config = json.loads(args.config.read_text())
    scored = json.loads(args.scored_in.read_text())
    if not isinstance(scored, list):
        print("ERROR: scored input must be a JSON list", file=sys.stderr)
        return 1

    threshold = int(config.get("resume_tailoring_min_score", DEFAULT_MIN_SCORE))
    qualifying = [item for item in scored if int(item.get("match_score", 0)) > threshold]

    # Nest under <out-dir>/<YYYY-MM>/<YYYY-MM-DD>/ rather than dumping every run's
    # PDFs flat -- same date-ownership pattern push_to_sheets.py uses for tab_name.
    today = date.today()
    run_dir = args.out_dir / today.strftime("%Y-%m") / today.isoformat()

    if not qualifying:
        print(f"Generated 0 tailored resumes (of {len(scored)} postings scoring > {threshold}) → {run_dir}")
        return 0

    if find_latex_engine() is None:
        print(
            "ERROR: no LaTeX engine found in PATH (looked for tectonic, pdflatex). "
            "Install one, e.g. `brew install tectonic`, then re-run.",
            file=sys.stderr,
        )
        return 1

    profile = load_profile(args.profile)
    template_text = args.template.read_text()

    tex_dir = run_dir / "tex"
    run_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)
    copy_template_assets(args.template, tex_dir)

    generated = 0
    failures = 0
    for item in qualifying:
        company = item.get("company", "")
        title = item.get("job_title", "")
        posting_id = sanitize_filename(item.get("apply_link", "") or f"{company}{title}")[:16]
        slug = f"{sanitize_filename(company)}_{sanitize_filename(title)}_{posting_id}"

        keywords = matched_keywords(item)
        tex_content = build_tex(template_text, profile, keywords)
        tex_path = tex_dir / f"{slug}.tex"
        tex_path.write_text(tex_content)

        ok, error = compile_pdf(tex_path, tex_dir)
        if not ok:
            failures += 1
            print(f"WARNING: LaTeX compile failed for '{title}' at '{company}':\n{error}", file=sys.stderr)
            continue

        compiled_pdf = tex_dir / f"{slug}.pdf"
        if not compiled_pdf.exists():
            failures += 1
            print(f"WARNING: compiler reported success but no PDF found for '{title}' at '{company}'", file=sys.stderr)
            continue

        final_pdf = run_dir / f"{slug}.pdf"
        shutil.move(str(compiled_pdf), str(final_pdf))
        generated += 1

    print(
        f"Generated {generated} tailored resumes (of {len(qualifying)} postings scoring > {threshold}, "
        f"{failures} failed) → {run_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
