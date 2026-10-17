# Contributing to flutter-pro-skills

<div dir="rtl">

**أهلاً بيك!** لو بتكتب Flutter بالعربي، المشروع ده معمول علشانك كمان. أي مساهمة
مرحّب بيها: بلاغ عن نتيجة غلط (false positive)، قاعدة جديدة، fixture، أو حتى
تصحيح كلمة في التوثيق. ممكن تفتح الـ issue أو تكتب في النقاش بالعربي من غير أي
مشكلة، وهنرد عليك. باقي الملف ده بالإنجليزي علشان يفضل مرجع واحد للكل.

</div>

Thanks for helping. The single most useful thing you can send is a **false
positive report**: a finding the skills raised on real code that was actually
fine. Every rule in this suite got sharper because someone ran it on a real app.

## How the suite is organised

```
skills/
  dart-flutter-best-practices/   entry point: WRITE mode, Effective Dart, lints
  dart-naming/                   naming (NAME-*)
  flutter-ui-practices/          widgets, lifecycle, performance (UI-*)
  flutter-architecture/          detection + arch_check.py (ARCH-*, AP-*)
  dart-flutter-review/           review orchestrator + review.sh
  …                              newer skills (testing, error handling, scaffold)
tests/run_all.sh                 runs everything
docs/CONTRACTS.md                the rules that cross skill boundaries
```

Each skill is a folder with a `SKILL.md`, `references/` (loaded on demand),
optional `scripts/`, and `tests/run.sh`. Anything that crosses a skill
boundary (rule IDs, the `arch_check --json` profile, the finding format, CLI
flags) is defined once in **[`docs/CONTRACTS.md`](docs/CONTRACTS.md)**. Read it
before you change one of those, and update every dependent skill in the same PR.

## Run the tests

```bash
bash tests/run_all.sh
```

It validates every `SKILL.md` frontmatter, runs each skill's `tests/run.sh`,
and syntax-checks the shell scripts. It must end with `ALL PASSED`. You don't
need the Flutter SDK: the parts that need `dart` are skipped, not failed.
CI runs the same command on Ubuntu and macOS.

To try the tools on your own app (they're read-only):

```bash
bash skills/dart-flutter-review/scripts/review.sh path/to/app
python3 -I skills/flutter-architecture/scripts/arch_check.py path/to/app --json
```

## Report a false positive (the most valuable contribution)

Open a **False positive** issue. The form asks for:

1. The **rule ID** (`ARCH-012`, `UI-future-in-build`, `NAME-get-prefix`, …).
2. The **smallest code snippet** that triggers it. Strip anything private.
3. The **detected profile**: the `"profile"` object from
   `python3 -I skills/flutter-architecture/scripts/arch_check.py path/to/app --json`.
   Half of all false positives turn out to be a wrong detection (for example,
   MVVM read as MVN), and the profile tells us that right away.
4. **Why it's fine**, ideally citing the pattern's own source (the Flutter
   architecture guide, bloclibrary.dev, riverpod.dev, the MVN spec).

If you can, add a regression fixture in the same PR. The fix usually lands
faster that way.

## Propose a new rule

Open a **New rule** issue first, so we can agree on the ID and the scope. A PR
that adds a rule needs:

- **An ID** with the right prefix: `ARCH-0xx` (import graph), `ARCH-1xx` (code
  pattern), `AP-<slug>` (judgment only), `ERR-0xx`/`ERR-<slug>` (error handling),
  `TEST-<slug>` (testing), `UI-`/`NAME-`/`ED-<slug>`. Add it to the catalog in
  `docs/CONTRACTS.md` §6, with its default severity and the profiles it applies to.
- **A fixture that triggers it**, under the skill's `tests/fixtures/`, with an
  assertion in `tests/run.sh`.
- **A clean fixture that doesn't trigger it**: the nearest legitimate code.
  This is the part that stops false positives.
- **A false-positive note** in the rule's reference entry: when the rule does
  *not* apply, and which patterns it's off for. The patterns disagree, so
  "applies to all" needs a reason.
- **A source.** Tie the rule to Effective Dart, the Flutter docs, or the
  pattern's canonical source, at that source's strength (DO/DON'T, PREFER/AVOID,
  CONSIDER).

## Style rules

- **Agent-neutral wording.** These skills run in Claude Code, Codex, Cursor,
  Copilot, Gemini CLI, OpenCode and more. Don't write vendor tool names as
  instructions ("use the Task tool"). Say "spawn a sub-agent if your agent
  supports it" and give a fallback. Name the project instructions file as
  "`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, …", not one of them alone.
- **Scripts:** `bash` that runs on macOS **bash 3.2** (no associative arrays,
  no `mapfile`, no GNU-only flags), plus `python3` ≥3.8 with the **standard
  library only**, always run as `python3 -I`. Scripts never modify the project
  they analyse. Exit `0` when a report is produced and `2` on a usage error.
- **SKILL.md:** at most 500 lines, references one level deep, and any reference
  over 300 lines starts with a `## Contents` list.
- **Voice:** explain *why*, use the imperative, and skip the all-caps MUSTs.
  Match the reference you're editing.
- Don't hand-edit the rows of `references/effective-dart.md`. They're
  generated from dart.dev.

## Pull requests

Keep PRs small and focused, one rule or one fix each. The PR template has a
short checklist: tests pass, a fixture was added, CONTRACTS was updated if
needed, and the wording is agent-neutral.

## Release process (maintainers)

1. Bump `metadata.version` in every changed `SKILL.md` (semver: a new rule is
   minor, a fix is patch, a changed contract or removed rule is major).
2. Run `bash tests/run_all.sh` and check that it prints `ALL PASSED`.
3. Tag `vX.Y.Z`, move the major tag (`v1`) so `uses: abdelrahman-abied/flutter-pro-skills@v1`
   keeps working, and publish a GitHub release with the notes. The exact
   commands are in [`docs/PUBLISHING.md`](docs/PUBLISHING.md).

## Code of conduct

Be kind and assume good faith. Critique code, not people. Maintainers may
remove comments or contributors that make this a worse place to learn.

By contributing, you agree that your contribution is licensed under the
project's [MIT license](LICENSE).
