#!/bin/bash
# NEXUS Track 2 · Threat Intelligence · Slice 1
# macOS Bash 3.2 compatible. Run from the repository root:
#     bash setup.sh
set -eu

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install from https://www.python.org/downloads/macos/ then re-run." >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code" >&2
  echo "The Claude Agent SDK drives the CLI, so this must be present before week 1." >&2
  exit 1
fi

python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

git config core.hooksPath scripts/hooks

mkdir -p data/records data/advisories

echo ""
echo "Smoke tests"
python evals/validate_record.py evals/example_record.json
python - <<'PY'
import sys
sys.path.insert(0, ".")
from mcp_server import knowledge_centre_server as s
print("MCP server imports OK:", s.mcp.name)
PY

echo ""
echo "Register the Knowledge Centre MCP server with Claude Code (week 2):"
echo "  claude mcp add knowledge-centre -- \"$PWD/.venv/bin/python\" \"$PWD/mcp_server/knowledge_centre_server.py\""
echo ""
echo "Run the week-1 extraction on an advisory:"
echo "  . .venv/bin/activate"
echo "  python agents/extract_advisory.py data/advisories/fatf-tbml-2020.pdf --advisory-id ADV-2026-0001"
