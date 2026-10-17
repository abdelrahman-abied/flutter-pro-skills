# CI mode and the GitHub Action

A review in chat finds problems; CI keeps new ones out. CI mode turns the
mechanical pass into a gate that fails a pull request only on what the pull
request **adds**. Existing debt goes into a committed baseline, so you can turn
the gate on today without fixing the whole codebase first.

## Contents
1. What fails the build
2. GitHub Action
3. Adopting a baseline
4. Local equivalents
5. Outputs and the step summary
6. Troubleshooting

## 1. What fails the build

| Check | Fails CI? |
|---|---|
| Architecture violations (`ARCH-0xx`, `ARCH-1xx`) at or above `fail-on` that are not in the baseline | Yes |
| Analyzer **errors** in scope (full mode only, and only after `pub get`; a pub workspace member uses the workspace root's `.dart_tool/package_config.json`) | Yes |
| Analyzer errors that are likely **codegen cascades** (`uri_has_not_been_generated`, `undefined_*`, `redirect_to_non_class`, `mixin_of_non_class`, … while generated files are missing) | No, collapsed into one line: run `build_runner` first |
| Analyzer results when the analyzer **crashed** (often an analyzer plugin), or when the pubspec SDK constraint excludes the installed SDK | No, the section says why |
| Architecture violations below `fail-on`, or recorded in the baseline | No, reported |
| Analyzer warnings and infos, format, `dart fix` | No, reported |
| Test gaps, error handling, security defaults, the `flutter-security-audit` `scan.sh` pass (whatever its own exit code), navigation, forms, i18n, performance, persistence, networking, design system, accessibility, release, heuristic candidates | No, informational |
| A usage or environment error (no `pubspec.yaml`, bad input, missing base ref) | Yes (exit 2) |

`fail-on` is `high` by default. `medium` also fails on medium violations, and
`low` on everything. Start at `high` and tighten once the baseline shrinks.

Exit codes: `0` pass, `1` CI failure, `2` usage or environment error.

## 2. GitHub Action

The repository root holds a composite action. Pin a tag (`@v1`) or a commit SHA.

```yaml
# .github/workflows/flutter-review.yml
name: Flutter review
on:
  pull_request:
  push:
    branches: [main]

jobs:
  architecture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # base-ref diffs need history
      - uses: abdelrahman-abied/flutter-pro-skills@v1
        id: review
        with:
          path: .                                   # folder with pubspec.yaml
          base-ref: ${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || '' }}
          fail-on: high
          baseline: .github/arch-baseline.json      # optional; see section 3
          flutter: false                            # architecture only: python3, no Flutter SDK
      - if: always()
        run: echo "new violations: ${{ steps.review.outputs.new-violations }}"
```

Full mechanical review (format, analyzer, `dart fix`, architecture, test gaps,
error handling) on a pull request:

```yaml
      - uses: abdelrahman-abied/flutter-pro-skills@v1
        with:
          base-ref: origin/${{ github.base_ref }}
          baseline: .github/arch-baseline.json
          flutter: true
          flutter-version: stable   # or a version such as 3.24.x
```

| Input | Default | Meaning |
|---|---|---|
| `path` | `.` | The project root (the folder with `pubspec.yaml`), relative to the repository root. For a monorepo, run one step per package |
| `base-ref` | empty | Report only `.dart` files changed versus this ref (diffed from the merge base). Empty means the whole project |
| `fail-on` | `high` | `high`, `medium` or `low` |
| `baseline` | empty | An `arch-baseline@1` file, relative to the repository root |
| `flutter` | `false` | `true` installs Flutter with `subosito/flutter-action@v2`, runs `flutter pub get` and the full `review.sh --ci`. `false` runs only `arch_check.py --ci` |
| `flutter-version` | `stable` | A channel (`stable`, `beta`, `master`) or a version, used when `flutter` is `true` |

| Output | Meaning |
|---|---|
| `new-violations` | The number of architecture violations not in the baseline, at any severity |
| `report-path` | The plain-text report on the runner (upload it with `actions/upload-artifact` if you want to keep it) |

`flutter: false` is fast (seconds) and needs only `python3`, which GitHub's
Linux and macOS runners already have. Use `flutter: true` when you also want
analyzer errors to fail the build; it costs a Flutter install and `pub get`.

## 3. Adopting a baseline

1. **Write the baseline once**, from the default branch, at the repository root:

   ```bash
   python3 -I <skills>/flutter-architecture/scripts/arch_check.py . \
     --write-baseline .github/arch-baseline.json
   ```

   Pass the same `--profile` you use in CI if you declare one.
2. **Commit it.** It is plain JSON:
   `{"schema": "flutter-pro-skills/arch-baseline@1", "entries": [{"id", "file", "key"}]}`,
   with one entry per existing violation. `key` is the evidence (the import or
   the offending line) with whitespace normalised and **no line numbers**, so
   adding code above a violation doesn't make it "new". Identical lines in one
   file are counted, so a third copy of a line that is baselined twice is one
   new violation.
3. **Point CI at it** (`baseline:` input, or `--baseline`). From then on, CI
   fails only on violations that aren't in it. The text report says
   `summary: N new, M baselined`, plus how many baseline entries no longer
   match (fixed debt).
4. **Shrink it.** When you fix old violations, regenerate the file with the
   same command and commit the smaller baseline. Review baseline diffs like
   code: a baseline that grows in a pull request is the PR accepting new debt.

Changing the evidence line of a baselined violation (editing the offending
import or line itself) makes it new again. That is deliberate: the line was
touched, so it should be looked at.

## 4. Local equivalents

`<skills>` is the folder holding the suite's skill folders (for example
`.claude/skills`, `.agents/skills`, or a clone of this repository's `skills/`).

```bash
# what the action runs with flutter: false
python3 -I <skills>/flutter-architecture/scripts/arch_check.py . --ci --fail-on high \
  --baseline .github/arch-baseline.json

# ... limited to a branch's changes
git diff --name-only --relative "$(git merge-base origin/main HEAD)" -- '*.dart' > /tmp/changed.txt
python3 -I <skills>/flutter-architecture/scripts/arch_check.py . --ci --files /tmp/changed.txt \
  --baseline .github/arch-baseline.json

# what the action runs with flutter: true (after flutter pub get)
bash <skills>/dart-flutter-review/scripts/review.sh . --ci --fail-on high \
  --baseline .github/arch-baseline.json --diff origin/main

# the action's own entry point, with the inputs as environment variables
INPUT_PATH=. INPUT_FLUTTER=false INPUT_FAIL_ON=high INPUT_BASELINE=.github/arch-baseline.json \
  bash <skills>/dart-flutter-review/scripts/ci_action.sh

# the sibling passes on their own (read-only, python3 only)
python3 -I <skills>/flutter-testing/scripts/test_gaps.py . [--profile <p>]
python3 -I <skills>/flutter-error-handling/scripts/check_errors.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-secure-defaults/scripts/check_secure_defaults.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-navigation/scripts/check_navigation.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-forms/scripts/check_forms.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-i18n/scripts/check_i18n.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-performance/scripts/check_performance.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-persistence/scripts/check_persistence.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-networking/scripts/check_networking.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-release/scripts/check_release.py . [--profile <p>]   # reads Gradle/Xcode/plist/CI files too
python3 -I <skills>/flutter-design-system/scripts/check_design_system.py . [--files <list>] [--profile <p>]
python3 -I <skills>/flutter-accessibility/scripts/check_accessibility.py . [--files <list>] [--profile <p>]
bash <skills>/flutter-security-audit/scan.sh . [--json]   # separate skill; exits 1 on Critical/High by itself

# skip sections in review.sh: --no-security (both security passes), --no-audit, --no-nav,
# --no-forms, --no-i18n, --no-perf, --no-persist, --no-net, --no-ds, --no-a11y, --no-release,
# or one list: --skip audit,nav,forms,i18n,perf,persist,net,ds,a11y,release
```

`echo $?` after any of them: `0` pass, `1` CI failure, `2` usage error.
`--fail-on` only matters with `--ci`. `--baseline` works without `--ci` too:
it reports only new violations and still exits 0.

## 5. Outputs and the step summary

With `$GITHUB_STEP_SUMMARY` set (GitHub sets it in every job), the run appends
a Markdown summary: the result, a table of findings per section, and the top
findings (the most severe architecture, error-handling and test-gap groups,
with an example location each). Locally you can preview it with
`GITHUB_STEP_SUMMARY=/tmp/summary.md bash review.sh . --ci`.

The text report ends with a `== CI RESULT` section that names each reason for
the verdict. `review.sh --ci` and `arch_check.py --ci` print an
`  ci: pass|fail (N at or above <sev>)` line in the architecture section.

## 6. Troubleshooting

- **`base-ref '…' not found`**: check out with `fetch-depth: 0`, or pass a ref
  that exists on the runner (`origin/main`, not `main`, after a default checkout).
- **Analyzer errors "not counted (no pub get)"**: the full mode needs resolved
  packages. The action runs `flutter pub get`; locally, run it yourself.
- **Thousands of analyzer errors, `uri_has_not_been_generated`**: code
  generation hasn't run. Run `dart run build_runner build --delete-conflicting-outputs`
  (and `flutter gen-l10n` if used) before `review.sh`. Without it the
  cascades are collapsed and not counted, but real errors hide among them.
- **`WARNING: no .dart_tool` in a monorepo**: a pub workspace member is
  resolved at the workspace root, so run `pub get` there. review.sh walks up
  to that root and only uses a config that lists the package.
- **`analyzer crashed (…; in analyzer plugin package:x)`**: the Analysis
  Server hit an exception, usually in a plugin. Disable the plugin under
  `analyzer: plugins:` (or `plugins:`) for the CI run, or pin a working version.
- **`ANALYZER (skipped: pubspec sdk constraint …)`**: the installed SDK is
  outside `environment: sdk:` (or the constraint is pre-null-safety, which
  Dart 3 can't analyse). Pin the matching Flutter version (`flutter-version`
  input). `>=2.12.0 <3.0.0` style constraints count as `<4.0.0` on Dart 3.
- **Every violation is new**: the baseline was written with a different
  `--profile`, from a different `path`, or before a mass rename. Regenerate it.
- **A violation you disagree with**: silence it in code with
  `// arch-ignore: ARCH-0xx <reason>` (it then shows as suppressed), rather
  than growing the baseline.
- **Windows runners** aren't supported (the scripts are bash). Use
  `ubuntu-latest` or `macos-latest`.
