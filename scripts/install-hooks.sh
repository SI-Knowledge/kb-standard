#!/usr/bin/env bash
# install-hooks.sh — install the local pre-commit safety net for a kb-* repo.
#
# Run once per clone:
#   bash .kb-standard/scripts/install-hooks.sh    (if kb-standard is checked out as a sibling/submodule)
# or, from inside any kb-proj-* clone:
#   curl -sSL https://raw.githubusercontent.com/SI-Knowledge/kb-standard/main/scripts/install-hooks.sh | bash
#
# What it does: points this repo's core.hooksPath at .githooks/ and drops in
# a pre-commit hook that runs `gitleaks protect --staged` before every commit
# — the one control that actually blocks a secret from being committed at
# all (CI/PR checks only catch it after it's already pushed).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.githooks"
mkdir -p "$HOOKS_DIR"

# Cache a copy of the gitleaks config locally so the hook works even in a
# plain `git clone` of a kb-proj-* repo (no .kb-standard checkout needed).
# Re-run this script later to refresh it if kb-standard's rules change.
RULES_URL="https://raw.githubusercontent.com/SI-Knowledge/kb-standard/main/rules/gitleaks-th.toml"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$RULES_URL" -o "$HOOKS_DIR/gitleaks-th.toml" || \
    echo "warning: could not fetch gitleaks-th.toml from kb-standard, hook will use gitleaks defaults" >&2
fi

cat > "$HOOKS_DIR/pre-commit" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "pre-commit: gitleaks not installed locally — skipping secret scan." >&2
  echo "  Install it: https://github.com/gitleaks/gitleaks/releases" >&2
  echo "  (this is a WARNING, not a block — install gitleaks to get real protection)" >&2
  exit 0
fi

CONFIG=""
for candidate in \
  ".githooks/gitleaks-th.toml" \
  ".kb-standard/rules/gitleaks-th.toml" \
  "rules/gitleaks-th.toml"; do
  if [ -f "$candidate" ]; then
    CONFIG="$candidate"
    break
  fi
done

if [ -z "$CONFIG" ]; then
  echo "pre-commit: no gitleaks-th.toml found — falling back to gitleaks defaults." >&2
  gitleaks protect --staged --redact --no-banner
else
  gitleaks protect --staged --redact --no-banner --config "$CONFIG"
fi
HOOK

chmod +x "$HOOKS_DIR/pre-commit"
git -C "$REPO_ROOT" config core.hooksPath .githooks

echo "Installed pre-commit hook at $HOOKS_DIR/pre-commit"
echo "core.hooksPath set to .githooks for this repo."
if ! command -v gitleaks >/dev/null 2>&1; then
  echo ""
  echo "WARNING: gitleaks is not installed on this machine yet — the hook will"
  echo "warn but NOT block commits until you install it. Get it from:"
  echo "  https://github.com/gitleaks/gitleaks/releases"
fi
