#!/usr/bin/env python3
"""
kb_lint.py — validate KB documents against kb-doc.schema.json + repo conventions.

Usage:
    python kb_lint.py [--repo-root .] [--fast]

Exit code: 0 = pass (warnings allowed), 1 = at least one error.
Errors are printed as GitHub Actions annotations (::error file=...,line=...::msg)
so they show up inline on the PR diff. A markdown summary is written to
$GITHUB_STEP_SUMMARY when that env var is set.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import frontmatter
import jsonschema
import yaml

REPO_ROOT = Path(sys.argv[sys.argv.index("--repo-root") + 1]) if "--repo-root" in sys.argv else Path(".")
FAST = "--fast" in sys.argv
STANDARD_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_DOC = json.loads((STANDARD_ROOT / "schema" / "kb-doc.schema.json").read_text(encoding="utf-8"))
SCHEMA_REPO = json.loads((STANDARD_ROOT / "schema" / "kbrepo.schema.json").read_text(encoding="utf-8"))

ALLOWED_DOC_FOLDERS = {
    "overview": {"00-overview"},
    "decision": {"10-decisions"},
    "sop": {"20-operations"},
    "meeting-note": {"50-meetings"},
    "spec": {"40-technical"},
    "client-profile": {"30-clients"},
    "contract-summary": {"30-clients"},
    "postmortem": {"20-operations", "90-archive"},
    "faq": {"60-reference"},
    "glossary": {"60-reference"},
    "reference": {"60-reference"},
    "proposal": {"00-overview", "30-clients"},
}

FORBIDDEN_EXTENSIONS = {".env", ".pem", ".p12", ".pfx", ".kdbx", ".xlsx", ".docx", ".pptx", ".pdf"}
FORBIDDEN_FILENAMES_RE = re.compile(r"^(id_rsa.*|credentials\.json)$", re.IGNORECASE)

errors: list[tuple[str, int, str]] = []
warnings: list[tuple[str, int, str]] = []


def err(path: str, line: int, msg: str) -> None:
    errors.append((path, line, msg))


def warn(path: str, line: int, msg: str) -> None:
    warnings.append((path, line, msg))


def git_last_modified(path: Path) -> datetime.date | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return datetime.date.fromisoformat(out) if out else None
    except Exception:
        return None


def check_kbrepo_yml() -> dict | None:
    kbrepo_path = REPO_ROOT / ".kbrepo.yml"
    if not kbrepo_path.exists():
        err(".kbrepo.yml", 1, "missing .kbrepo.yml at repo root")
        return None
    data = yaml.safe_load(kbrepo_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, SCHEMA_REPO)
    except jsonschema.ValidationError as e:
        err(".kbrepo.yml", 1, f"schema violation: {e.message}")
        return None
    if len(data.get("managers", [])) < 2:
        warn(".kbrepo.yml", 1, "only 1 manager on file — bus factor risk, add a second manager when available")
    return data


SENSITIVITY_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


def lint_file(path: Path, kbrepo: dict | None, all_ids: dict[str, Path]) -> None:
    rel = str(path.relative_to(REPO_ROOT))

    if path.suffix.lower() in FORBIDDEN_EXTENSIONS or FORBIDDEN_FILENAMES_RE.match(path.name):
        err(rel, 1, f"forbidden file type in KB repo (binary/secret-shaped file): {path.name}")
        return

    if path.suffix.lower() != ".md":
        return
    if path.name in ("README.md", "INDEX.md", "AGENTS.md", "CONTRIBUTING.md"):
        return  # structural files, not KB documents — no frontmatter required

    try:
        post = frontmatter.load(path)
    except Exception as e:
        err(rel, 1, f"failed to parse frontmatter: {e}")
        return

    meta = post.metadata
    try:
        jsonschema.validate(meta, SCHEMA_DOC)
    except jsonschema.ValidationError as e:
        loc = ".".join(str(p) for p in e.path) or "(root)"
        err(rel, 1, f"frontmatter schema violation at '{loc}': {e.message}")
        return  # further checks assume required fields exist

    doc_id = meta["id"]
    if doc_id in all_ids and all_ids[doc_id] != path:
        err(rel, 1, f"duplicate id '{doc_id}' also used by {all_ids[doc_id]}")
    all_ids[doc_id] = path

    if kbrepo is not None:
        if meta["project"] != kbrepo["project"]:
            err(rel, 1, f"project '{meta['project']}' does not match .kbrepo.yml project '{kbrepo['project']}'")
        if SENSITIVITY_RANK[meta["sensitivity"]] > SENSITIVITY_RANK[kbrepo["max_sensitivity"]]:
            err(rel, 1, f"sensitivity '{meta['sensitivity']}' exceeds repo max_sensitivity '{kbrepo['max_sensitivity']}'")

    allowed_folders = ALLOWED_DOC_FOLDERS.get(meta["doc_type"])
    if allowed_folders and rel.split("/")[0] not in allowed_folders:
        warn(rel, 1, f"doc_type '{meta['doc_type']}' is usually placed in {allowed_folders}, found in '{rel.split('/')[0]}'")

    if not FAST:
        last_mod = git_last_modified(path)
        stated = datetime.date.fromisoformat(str(meta["last_updated"]))
        if last_mod and abs((last_mod - stated).days) > 1:
            err(rel, 1, f"last_updated ({stated}) does not match git log ({last_mod}), off by >1 day")

        review_by = datetime.date.fromisoformat(str(meta["review_by"]))
        if review_by < datetime.date.today():
            warn(rel, 1, f"review_by ({review_by}) has passed — document may be stale")

        if meta.get("summary_en_status") == "ai-draft":
            created = datetime.date.fromisoformat(str(meta["created"]))
            if (datetime.date.today() - created).days > 30:
                warn(rel, 1, "summary_en_status is still 'ai-draft' after 30+ days — needs manager review")

    word_count = len(post.content.split())
    if word_count > 300 and not meta.get("summary_en") and not meta.get("summary_th"):
        err(rel, 1, "body > 300 words but no summary_en/summary_th provided")
    if word_count > 2000:
        warn(rel, 1, f"body is {word_count} words (> 2000) — consider splitting into multiple files")

    if "คำถามที่ยังไม่ชัด" not in post.content and "Open questions" not in post.content:
        warn(rel, 1, "missing 'คำถามที่ยังไม่ชัด / ข้อจำกัดของข้อมูลนี้' section")

    if meta.get("source_of_truth") is False and not meta.get("canonical"):
        err(rel, 1, "source_of_truth=false requires a 'canonical' pointer")


def main() -> int:
    kbrepo = check_kbrepo_yml()
    all_ids: dict[str, Path] = {}

    md_files = [
        p for p in REPO_ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts
    ]
    for path in md_files:
        lint_file(path, kbrepo, all_ids)

    for path, line, msg in errors:
        print(f"::error file={path},line={line}::{msg}")
    for path, line, msg in warnings:
        print(f"::warning file={path},line={line}::{msg}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("## kb-lint result\n\n")
            f.write(f"- Errors: **{len(errors)}**\n- Warnings: **{len(warnings)}**\n\n")
            if errors:
                f.write("| file | message |\n|---|---|\n")
                for path, _, msg in errors:
                    f.write(f"| `{path}` | {msg} |\n")
            if warnings:
                f.write("\n<details><summary>Warnings</summary>\n\n| file | message |\n|---|---|\n")
                for path, _, msg in warnings:
                    f.write(f"| `{path}` | {msg} |\n")
                f.write("\n</details>\n")

    print(f"\nkb-lint: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
