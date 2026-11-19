#!/usr/bin/env bash
# Regression tests for install.sh: install, upgrade over a pre-release copy, foreign-dir safety, uninstall.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/fps-install.XXXXXX")"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; ko(){ echo "FAIL $1"; fail=1; }
n_skills=$(ls -d "$ROOT"/skills/*/ | wc -l | tr -d ' ')

bash "$ROOT/install.sh" --project "$T" --agent agents --agent claude >/dev/null
[ "$(ls "$T/.agents/skills" | wc -l | tr -d ' ')" = "$n_skills" ] && ok "installs all $n_skills skills to .agents/skills" || ko "agents install count"
[ "$(ls "$T/.claude/skills" | wc -l | tr -d ' ')" = "$n_skills" ] && ok "installs all $n_skills skills to .claude/skills" || ko "claude install count"
[ -x "$T/.agents/skills/flutter-architecture/scripts/arch_check.py" ] && ok "scripts are executable" || ko "scripts executable"

# upgrade: a copy tagged with the pre-release suite name must be replaced, not skipped
sed -i.bak 's/suite: flutter-pro-skills/suite: dart-flutter-skills/' "$T/.agents/skills/dart-naming/SKILL.md" && rm -f "$T/.agents/skills/dart-naming/SKILL.md.bak"
echo "stale" > "$T/.agents/skills/dart-naming/STALE"
out="$(bash "$ROOT/install.sh" --project "$T" --agent agents 2>&1)"
{ [ ! -e "$T/.agents/skills/dart-naming/STALE" ] && ! echo "$out" | grep -q 'skip'; } && ok "upgrades over a pre-release copy" || ko "upgrade over pre-release copy"

# safety: a folder with the same name that is not from this suite is left alone
rm -rf "$T/.agents/skills/flutter-testing"; mkdir -p "$T/.agents/skills/flutter-testing"; echo mine > "$T/.agents/skills/flutter-testing/SKILL.md"
bash "$ROOT/install.sh" --project "$T" --agent agents >/dev/null 2>&1
[ "$(cat "$T/.agents/skills/flutter-testing/SKILL.md")" = "mine" ] && ok "never replaces a foreign folder" || ko "foreign folder replaced"

bash "$ROOT/install.sh" --project "$T" --agent agents --agent claude --uninstall >/dev/null 2>&1
left=$(ls "$T/.agents/skills" | tr '\n' ' ')
{ [ "$left" = "flutter-testing " ] && [ -z "$(ls "$T/.claude/skills")" ]; } && ok "uninstall removes only suite copies" || ko "uninstall left: [$left]"

# npm runs the installer through a relative symlink in node_modules/.bin
L="$T/linked"; mkdir -p "$L/node_modules/.bin" "$L/app"
ln -s "$ROOT/install.sh" "$L/node_modules/flutter-pro-skills.sh"
ln -s ../flutter-pro-skills.sh "$L/node_modules/.bin/flutter-pro-skills"
"$L/node_modules/.bin/flutter-pro-skills" --project "$L/app" --agent claude >/dev/null 2>&1
[ "$(ls "$L/app/.claude/skills" 2>/dev/null | wc -l | tr -d ' ')" = "$n_skills" ] && ok "installs through a symlink chain" || ko "install through a symlink"

# Antigravity reads ~/.gemini/config/skills globally and .agents/skills per project, not ~/.agents/skills
H="$T/home"; mkdir -p "$H"
HOME="$H" bash "$ROOT/install.sh" --agent antigravity >/dev/null 2>&1
[ "$(ls "$H/.gemini/config/skills" 2>/dev/null | wc -l | tr -d ' ')" = "$n_skills" ] && ok "antigravity installs to ~/.gemini/config/skills" || ko "antigravity global install"
[ "$(HOME="$H" bash "$ROOT/install.sh" --agent antigravity --list --project "$T")" = "antigravity -> $(cd "$T" && pwd)/.agents/skills" ] && ok "antigravity with --project targets .agents/skills" || ko "antigravity project target"
HOME="$H" bash "$ROOT/install.sh" --agent antigravity --uninstall >/dev/null 2>&1
[ -z "$(ls "$H/.gemini/config/skills")" ] && ok "antigravity uninstall" || ko "antigravity uninstall"
bash "$ROOT/install.sh" --help | grep -q 'antigravity' && ok "--help lists antigravity" || ko "--help misses antigravity"

# the npm package carries the same version as every skill
pkg_version="$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/package.json")"
versions="$(grep -h '^  version:' "$ROOT"/skills/*/SKILL.md | sort -u)"
[ "$versions" = "  version: \"$pkg_version\"" ] && ok "package.json and every SKILL.md are at $pkg_version" || ko "version drift: package.json=$pkg_version skills=[$versions]"

# package contents: `files` overrides .gitignore, so fixtures and bytecode (which holds local paths) must be excluded by name
if command -v npm >/dev/null 2>&1; then
  # a stray .pyc proves the exclusion works even on a clean checkout
  stray="$ROOT/skills/dart-naming/__pycache__"; had_stray=0; [ -e "$stray" ] && had_stray=1
  mkdir -p "$stray"; : > "$stray/probe.cpython-314.pyc"
  listing="$(cd "$ROOT" && npm pack --dry-run --json 2>/dev/null)"
  rm -f "$stray/probe.cpython-314.pyc"; [ $had_stray = 1 ] || rmdir "$stray"
  verdict="$(printf '%s' "$listing" | python3 -I -c '
import json, sys
paths = [f["path"] for f in json.load(sys.stdin)[0]["files"]]
bad = [p for p in paths if "/tests/" in p or "__pycache__" in p or p.endswith(".pyc")]
skills = sum(p.endswith("/SKILL.md") for p in paths)
print("bad:" + ",".join(bad[:3]) if bad else "skills:%d" % skills)
' 2>&1)"
  [ "$verdict" = "skills:$n_skills" ] && ok "npm package has all $n_skills skills, no tests or bytecode" || ko "npm package contents: $verdict"
else
  ok "npm package contents (skipped, npm not installed)"
fi

exit $fail
