Environment fixtures for `review.sh` (calibration fixes K1 R1/R2, K2 R2 + SDK skip, K3 R1/R2/R3/R9).
`tests/run.sh` copies them to a temp dir and drives them with a stub `dart`; nothing here is compiled.

- `workspace/`: a pub workspace. `app/` is a member (`resolution: workspace`) with no `.dart_tool` of its own
  (the test writes the root's `.dart_tool/package_config.json`). Its `analysis_options.yaml` uses a
  list-form `include:`, and its SDK constraint has a prerelease (`^3.4.0-0`), which BSD sed mangled.
- `codegen_app/`: `part` targets that build_runner never generated, plus files that are generated
  (`*.gen.dart`, a "GENERATED CODE" header, gen-l10n output in `arb-dir`) and must be out of scope.
- `old_sdk_app/`: a pre-null-safety SDK constraint the installed Dart can't analyse.
- `dart3_compat_app/`: `>=2.16.1 <3.0.0`, which Dart 3 reads as `<4.0.0`, so it is analysed.
