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

exit $fail
