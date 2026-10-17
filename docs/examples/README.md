# Examples: real output, nothing invented

| File | What it is |
|---|---|
| [`sample-review.md`](sample-review.md) | A full review report in the `dart-flutter-review` template, for the `smelly_app` fixture. Every finding is traced to the raw output below or to a line of the fixture's code |
| [`review-smelly_app.txt`](review-smelly_app.txt) | Raw `review.sh --max 3` output on [`smelly_app`](../../skills/dart-flutter-review/tests/fixtures/smelly_app), with the analyzer sections live (after `flutter pub get --offline`) |
| [`arch-check-mvn_violations.txt`](arch-check-mvn_violations.txt) | `arch_check.py` on an MVN app: auto-detected as `mvn`, so MVN-only rules (ARCH-012, ARCH-112) fire |
| [`arch-check-bloc_violations.txt`](arch-check-bloc_violations.txt) | `arch_check.py` on a Bloc app: auto-detected as `bloc`, so bloc→bloc is ARCH-010 (medium) |
| [`arch-check-profile-override.txt`](arch-check-profile-override.txt) | The same two apps with a different declared pattern (`--profile mvvm`, `--profile riverpod`). The pattern-specific rules switch off, and the universal ones stay |

Only the temp-folder paths were changed (to `path/to/app`).

## Regenerate

From the repo root, after a change to the scripts' output:

```bash
T="$(mktemp -d)"
cp -R skills/dart-flutter-review/tests/fixtures/smelly_app "$T/app"
(cd "$T/app" && flutter pub get --offline)          # optional; without it the analyzer sections are skipped
bash skills/dart-flutter-review/scripts/review.sh "$T/app" --max 3 | sed "s#$T/app#path/to/app#g"

for f in mvn_violations bloc_violations; do
  cp -R "skills/flutter-architecture/tests/fixtures/$f" "$T/$f"
  python3 -I skills/flutter-architecture/scripts/arch_check.py "$T/$f" | sed -E "s#(/private)?$T/$f#path/to/app#g"
done
python3 -I skills/flutter-architecture/scripts/arch_check.py "$T/mvn_violations" --profile mvvm
python3 -I skills/flutter-architecture/scripts/arch_check.py "$T/bloc_violations" --profile riverpod
```

If the excerpt changes, update the lines in `docs/assets/review-preview.svg` to match.
