#!/usr/bin/env bash
# Install the flutter-pro-skills suite into one or more coding agents' skill folders.
#
# Usage:
#   ./install.sh [--agent <name>]... [--project <dir>] [--link] [--skills a,b] [--uninstall] [--list]
#
#   --agent      where to install (repeatable). Default: agents + claude
#                  agents    ~/.agents/skills            Codex, Gemini CLI, GitHub Copilot, Cursor,
#                                                        OpenCode, Antigravity (the interoperable path)
#                  claude    ~/.claude/skills            Claude Code (also read by Cursor, Copilot, OpenCode)
#                  cursor    ~/.cursor/skills
#                  gemini    ~/.gemini/skills
#                  copilot   ~/.copilot/skills
#                  opencode  ~/.config/opencode/skills
#   --project    install into <dir>/.agents/skills, <dir>/.claude/skills, ... instead of $HOME
#   --link       symlink instead of copy (for contributors: edits in the repo go live)
#   --skills     comma-separated subset (default: all twelve; they reference each other, so keep them together)
#   --uninstall  remove the suite's skills from the chosen locations
#   --list       print target folders and exit
#
# Agents that read several of these folders may show a skill twice if you install to both;
# pick one location per agent when that happens.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALL_SKILLS="dart-flutter-best-practices dart-naming flutter-ui-practices flutter-architecture flutter-feature-scaffold flutter-testing flutter-error-handling flutter-secure-defaults flutter-navigation flutter-forms flutter-i18n dart-flutter-review"
AGENTS=""; BASE="$HOME"; PROJECT=0; LINK=0; SKILLS="$ALL_SKILLS"; UNINSTALL=0; LIST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENTS="$AGENTS ${2:?--agent needs a name}"; shift 2 ;;
    --project) BASE="$(cd "${2:?--project needs a dir}" && pwd)"; PROJECT=1; shift 2 ;;
    --link) LINK=1; shift ;;
    --skills) SKILLS="$(echo "${2:?--skills needs a list}" | tr ',' ' ')"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --list) LIST=1; shift ;;
    -h|--help) sed -n 2,24p "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
[ -n "$AGENTS" ] || AGENTS="agents claude"

target_for() {
  case "$1" in
    agents)   echo "$BASE/.agents/skills" ;;
    claude)   echo "$BASE/.claude/skills" ;;
    cursor)   echo "$BASE/.cursor/skills" ;;
    gemini)   echo "$BASE/.gemini/skills" ;;
    copilot)  if [ $PROJECT = 1 ]; then echo "$BASE/.github/skills"; else echo "$BASE/.copilot/skills"; fi ;;
    opencode) if [ $PROJECT = 1 ]; then echo "$BASE/.opencode/skills"; else echo "$BASE/.config/opencode/skills"; fi ;;
    *) echo "unknown agent: $1" >&2; return 2 ;;
  esac
}

for s in $SKILLS; do
  [ -f "$REPO/skills/$s/SKILL.md" ] || { echo "unknown skill: $s" >&2; exit 2; }
done

for a in $AGENTS; do
  dest="$(target_for "$a")" || exit 2
  if [ $LIST = 1 ]; then echo "$a -> $dest"; continue; fi
  mkdir -p "$dest"
  for s in $SKILLS; do
    tgt="$dest/$s"
    if [ -e "$tgt" ] || [ -L "$tgt" ]; then
      # only replace things this installer put there (a symlink into this repo, or a copy carrying the suite tag)
      # (dart-flutter-skills is the suite's pre-release name; accept it so upgrades replace old copies)
      if [ -L "$tgt" ] || grep -Eq 'suite: (flutter-pro-skills|dart-flutter-skills)' "$tgt/SKILL.md" 2>/dev/null; then
        rm -rf "${tgt:?}"
      else
        echo "skip $tgt (exists and is not from this suite)" >&2; continue
      fi
    fi
    [ $UNINSTALL = 1 ] && { echo "removed $tgt"; continue; }
    if [ $LINK = 1 ]; then ln -s "$REPO/skills/$s" "$tgt"; else cp -R "$REPO/skills/$s" "$tgt"; fi
    chmod +x "$tgt"/scripts/*.sh "$tgt"/scripts/*.py 2>/dev/null || true
    echo "$([ $LINK = 1 ] && echo linked || echo installed) $s -> $tgt"
  done
done
