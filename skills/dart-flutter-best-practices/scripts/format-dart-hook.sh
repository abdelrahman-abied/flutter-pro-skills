#!/usr/bin/env bash
# Optional "format on write" hook: runs `dart format` on the .dart file(s) an
# agent (or a person) just wrote, so formatting never depends on anyone
# remembering. Skips generated code. Never blocks: always exits 0.
#
# Input, either of:
#   format-dart-hook.sh <file.dart> [more files...]     # a path as $1 (any hook system, git hooks, scripts)
#   echo '{"tool_input":{"file_path":"lib/a.dart"}}' | format-dart-hook.sh
#                                                        # hook JSON on stdin (Claude Code style)
# Non-.dart paths, generated files, missing files and a missing `dart` are ignored.
#
# --- Claude Code (post-edit hook) ----------------------------------------------
# In ~/.claude/settings.json or a project's .claude/settings.json:
#   "hooks": { "PostToolUse": [ { "matcher": "Edit|Write|MultiEdit",
#     "hooks": [ { "type": "command",
#       "command": "bash ~/.claude/skills/dart-flutter-best-practices/scripts/format-dart-hook.sh" } ] } ] }
# (adjust the path to wherever the suite is installed). Claude Code sends the
# hook JSON on stdin, and this script reads `tool_input.file_path` from it.
#
# --- Any other agent or hook system that can pass a path ------------------------
# Configure it to run this command after a file is written or edited:
#   bash <suite>/dart-flutter-best-practices/scripts/format-dart-hook.sh "<edited file path>"
# If your agent's hook sends JSON on stdin in a different shape, extract the path
# and pass it as $1. Only the Claude Code shape above is parsed from stdin.
#
# --- git pre-commit (.git/hooks/pre-commit, chmod +x) ---------------------------
#   #!/bin/sh
#   git diff --cached --name-only --diff-filter=ACMR -- '*.dart' | while IFS= read -r f; do
#     bash path/to/format-dart-hook.sh "$f" && git add -- "$f"
#   done
# Caveat: `git add` restages the whole file. If you commit partial hunks, use a
# check-only hook instead: `dart format --output=none --set-exit-if-changed <files>`.

format_one() {
  case "$1" in
    *.g.dart|*.freezed.dart|*.gr.dart|*.mocks.dart|*.config.dart|*/generated/*) return 0 ;;
    *.dart) [ -f "$1" ] && command -v dart >/dev/null 2>&1 && dart format "$1" >/dev/null 2>&1 ;;
  esac
  return 0
}

if [ "$#" -gt 0 ]; then
  for f in "$@"; do format_one "$f"; done
elif [ ! -t 0 ]; then
  f="$(python3 -I -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null)"
  [ -n "$f" ] && format_one "$f"
fi
exit 0
