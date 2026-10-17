## What and why

<!-- One or two sentences. Link the issue: Fixes #123 -->

## Checklist

- [ ] `bash tests/run_all.sh` prints `ALL PASSED`
- [ ] Added or updated a fixture (a triggering one **and** a clean one for a new or changed rule) with an assertion in `tests/run.sh`
- [ ] Updated `docs/CONTRACTS.md` if this changes a rule ID, the profile JSON, the finding format or a CLI flag, and updated every dependent skill
- [ ] Wording is agent-neutral: no vendor tool names as instructions, and a fallback is given
- [ ] Scripts stay bash 3.2 compatible, stdlib-only Python (`python3 -I`), and read-only
- [ ] Bumped `metadata.version` in the changed `SKILL.md` files (or this is docs/tests only)

## Notes for the reviewer

<!-- False positives you checked for, real apps you ran it on, trade-offs. -->
