# kb-standard

**PUBLIC repo** — schema, linter, reusable CI workflows, gitleaks rules, and
document templates shared by every `kb-*` repo under the `SI-Knowledge` org.

This repo intentionally contains **no real project data**. It must never
contain client names, real project names, or real examples — only fictional
placeholders in templates. See the KB concept design doc:
`Skill Intelligence/Company Knowledge Base/02-repo-topology.md` §1.3 for why
this repo is public (free unlimited Actions minutes, reusable workflows
callable from any private repo without extra config, free secret scanning
as a bonus).

## Contents

| Path | Purpose |
|---|---|
| `schema/kb-doc.schema.json` | JSON Schema every document's YAML frontmatter must validate against |
| `schema/kbrepo.schema.json` | JSON Schema for each project repo's `.kbrepo.yml` |
| `rules/gitleaks-th.toml` | gitleaks config with Thai/EdTech-specific rules on top of the default ruleset |
| `templates/*.md` | starting frontmatter + body skeleton per `doc_type` |
| `tools/kb_lint.py` | validates a repo's documents against schema + convention (used by `kb-ci.yml`) |
| `tools/kb_index.py` | regenerates `INDEX.md` / `index/index.json` / `index/llms.txt` (used by `kb-index.yml`) |
| `.github/workflows/kb-ci.yml` | reusable workflow — lint + gitleaks on every PR/push |
| `.github/workflows/kb-index.yml` | reusable workflow — rebuild index on every merge to `main` |

## How a project repo uses this

Each `kb-proj-*` repo has two 6-line workflow files that call the ones here:

```yaml
# .github/workflows/kb-ci.yml
on: [pull_request, push]
jobs:
  kb:
    uses: SI-Knowledge/kb-standard/.github/workflows/kb-ci.yml@main
```

```yaml
# .github/workflows/kb-index.yml
on:
  push:
    branches: [main]
jobs:
  index:
    uses: SI-Knowledge/kb-standard/.github/workflows/kb-index.yml@main
```

Upgrading convention for every repo at once = editing this repo. Once this
has stabilized, pin callers to a tag (`@v1`) instead of `@main` so upgrades
are deliberate.

## Design reference

Full design rationale (risk model, phased rollout, why GitHub Free forces
this shape) lives at:
`Skill Intelligence/Company Knowledge Base/` in the main working repo — not
duplicated here to avoid drift between the two copies.
