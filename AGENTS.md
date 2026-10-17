# Working on this repository (for AI coding agents and humans)

This repo is a suite of twelve Agent Skills for Dart & Flutter. Before changing anything:

1. Read `docs/CONTRACTS.md`. It defines what crosses skill boundaries: rule IDs,
   the architecture-profile JSON, the finding format, CLIs, portability rules and
   test expectations. If you change a contract, update every dependent skill in the
   same change.
2. Keep skills **agent-neutral**. Don't use vendor-specific tool names as
   instructions, and always give a fallback. Cross-skill links use the skill
   name plus a relative path (`../flutter-architecture/SKILL.md`).
3. Scripts are bash (macOS 3.2 compatible) plus python3 stdlib only. They're
   read-only towards the analysed project, and exit 0 when a report is produced.
4. Don't hand-edit the rows of `skills/dart-flutter-best-practices/references/effective-dart.md`.
   They're generated from dart.dev, so regenerate them instead.
5. Before you finish, run `bash tests/run_all.sh`. It must print `ALL PASSED`.

Using these skills *in your own Flutter project* instead? See the README's
"Using with any agent" section.
