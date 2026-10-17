# Publishing checklist (maintainer)

A copy-paste runbook for the first public release, and for later releases.
Run it from the repo root. Nothing in this repo runs these commands for you.

```bash
cd path/to/flutter-pro-skills
```

The tagline, used as the repo description and in the posts:

> Agent Skills that write and review Dart & Flutter code by your app's own architecture: MVVM, MVN, Bloc, Clean, Riverpod, GetX.

---

## 0. Pre-flight

```bash
gh auth status                       # logged in as abdelrahman-abied
bash tests/run_all.sh                # must print ALL PASSED
git status --short                   # review what's left; .research-sources/ must NOT appear (it's gitignored)
grep -rn "/Users/\|/private/tmp" --include='*.md' --include='*.txt' --include='*.svg' . | grep -v -e .research-sources -e docs/PUBLISHING.md   # expect no output
grep -h '^  version:' skills/*/SKILL.md | sort | uniq -c    # the versions you're about to tag
```

Commit everything that should ship:

```bash
git add -A
git commit -m "Release v1.0.0"
```

Set the version once. Use the version the `SKILL.md` files carry: if they say
`1.1.0`, release `v1.1.0` and keep the `v1` major tag.

```bash
VERSION=v1.0.0
```

## 1. Create the repo and push

```bash
gh repo create abdelrahman-abied/flutter-pro-skills --public --source . --push \
  --description "Agent Skills that write and review Dart & Flutter code by your app's own architecture: MVVM, MVN, Bloc, Clean, Riverpod, GetX."
```

## 2. Topics (20, GitHub's maximum)

```bash
gh repo edit abdelrahman-abied/flutter-pro-skills \
  --add-topic flutter,dart,agent-skills,ai-agents,claude-code,codex,cursor,github-copilot,gemini-cli,opencode \
  --add-topic clean-architecture,mvvm,mvn,bloc,riverpod,getx,code-review,static-analysis,best-practices,linter
```

## 3. Homepage, features, labels

```bash
gh repo edit abdelrahman-abied/flutter-pro-skills \
  --homepage "https://github.com/abdelrahman-abied/flutter-pro-skills#readme" \
  --enable-discussions --enable-issues --enable-wiki=false

# labels used by the issue forms (bug already exists by default)
gh label create false-positive --color D93F0B --description "A rule fired on correct code" -R abdelrahman-abied/flutter-pro-skills
gh label create new-rule       --color 0E8A16 --description "Proposal for a new rule"      -R abdelrahman-abied/flutter-pro-skills
gh label create triage         --color FBCA04 --description "Needs a first look"           -R abdelrahman-abied/flutter-pro-skills
```

## 4. Social preview (manual, there's no API for it)

1. Open https://github.com/abdelrahman-abied/flutter-pro-skills/settings
2. **General › Social preview › Edit › Upload an image…**
3. Pick `docs/assets/social-preview.png` (1280×640). The source is `docs/assets/social-preview.svg`.
4. Check it with any link-preview tool, or paste the repo URL into a draft post on X or LinkedIn.

## 5. Tags: `vX.Y.Z` plus the moving `v1`

The `v1` tag is what `uses: abdelrahman-abied/flutter-pro-skills@v1` resolves
to in workflows. Move it on every 1.x release.

```bash
git tag -a "$VERSION" -m "flutter-pro-skills $VERSION"
git tag -fa v1 -m "flutter-pro-skills v1 (latest: $VERSION)"
git push origin "$VERSION"
git push origin v1 --force
```

## 6. GitHub release

```bash
gh release create "$VERSION" -R abdelrahman-abied/flutter-pro-skills \
  --title "flutter-pro-skills $VERSION" \
  --notes-file - <<'EOF'
Agent Skills for Dart & Flutter that **detect your app's architecture** (MVVM, MVN, Bloc, MVC, GetX, Provider, Riverpod, Clean) and judge the code by **that** pattern's rules.

- `dart-flutter-best-practices`: write mode, Effective Dart, a stricter lint set
- `dart-naming`, `flutter-ui-practices`: naming, lifecycle, performance
- `flutter-architecture`: architecture detection plus an import-graph checker (`arch_check.py`, 28 rules)
- `dart-flutter-review`: a mechanical pass, then parallel reviewers, verification of every High finding, and one ranked report

Install: `npx skills add abdelrahman-abied/flutter-pro-skills`, or clone and run `./install.sh`.
Works with Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, OpenCode and any agent that reads SKILL.md.
See docs/examples/ for real output.
EOF
```

If the root `action.yml` exists, the release page offers **Publish this
Action to the GitHub Marketplace**. Tick it, and choose the *Code quality*
and *Continuous integration* categories.

## 7. Post-publish checks

```bash
# the skills CLI finds and installs the suite (run in a throwaway folder);
# it should list every skill under skills/ and install them side by side
cd "$(mktemp -d)" && npx skills add abdelrahman-abied/flutter-pro-skills; cd -

# a fresh clone works and passes
git clone https://github.com/abdelrahman-abied/flutter-pro-skills /tmp/fps-check && bash /tmp/fps-check/tests/run_all.sh

# CI is green on the tag
gh run list -R abdelrahman-abied/flutter-pro-skills --limit 3
```

On GitHub, check that:
- [ ] the README images (`docs/assets/*.svg`) render in both light and dark mode
- [ ] the issue forms appear under **New issue**, plus a blank-issue option
- [ ] the topics and the social preview are shown
- [ ] `docs/examples/sample-review.md` renders

## 8. Where to announce

Post over a few days rather than all at once, and answer comments the same day.

- [ ] **r/FlutterDev**: a text post that leads with the "judged by its own pattern" idea and the `arch-compare.svg` image. Read the sub's self-promotion rules first.
- [ ] **Flutter Discord** (the community server's showcase or tools channel)
- [ ] **X**: tag @FlutterDev and @dart_lang; attach `arch-compare.svg` exported as a PNG, or the social card
- [ ] **LinkedIn**: the English post below, plus the image
- [ ] **Arabic Flutter communities**: Arabic Flutter groups on Facebook, Telegram and LinkedIn, Flutter Egypt, and GDG/Flutter meetups in Egypt and the Gulf. Use the Arabic post below
- [ ] **Skills directories and lists** (check each one's current submission process):
  - skills.sh (the `npx skills` directory; installs make it show up)
  - agentskills.io (the standard's site): look for a showcase or submission link
  - the "awesome" lists for Agent Skills / Claude Code skills (open a PR adding one line)
  - `Solido/awesome-flutter` (a PR under tooling or code quality)
- [ ] **Flutter / Dart newsletters**: Flutter Tap, Flutter Weekly, Dart Weekly
- [ ] **dev.to / Medium**: a write-up built from `docs/examples/sample-review.md`

## 9. Announcement drafts

### English

> **flutter-pro-skills: AI code review for Flutter that knows *your* architecture**
>
> Most Flutter agent rules force one stack: MVVM + ChangeNotifier, or Riverpod + MVVM, or Cubit + Clean. Point them at a Bloc app or an MVN app and you get noise.
>
> flutter-pro-skills detects the architecture first (MVVM, MVN, Bloc, MVC, GetX, Provider, Riverpod, Clean) and judges the code by **that** pattern's own rules. A view model calling a repository is fine under the Flutter team's MVVM guide, but it's ARCH-012 under MVN. Bloc → bloc is ARCH-010 under Bloc, while notifier → notifier through `ref.watch` is sanctioned under MVN.
>
> What's inside:
> • an import-graph checker with 28 architecture rules (Python stdlib, read-only)
> • a review that runs format/analyze/fix, then parallel reviewer agents, verifies every High finding, and returns one ranked report
> • Effective Dart, naming, widget lifecycle and performance guidance
>
> Works in Claude Code, Codex, Cursor, Copilot, Gemini CLI and OpenCode.
> `npx skills add abdelrahman-abied/flutter-pro-skills`
> https://github.com/abdelrahman-abied/flutter-pro-skills
>
> False-positive reports are the most valuable feedback. Please send them.

### العربية

> **flutter-pro-skills: مراجعة كود Flutter بالذكاء الاصطناعي حسب المعمارية بتاعتك**
>
> أغلب الـ rules والـ skills الموجودة للـ AI agents بتفرض عليك stack واحد: يا MVVM مع ChangeNotifier، يا Riverpod مع MVVM، يا Cubit مع Clean. ولو مشروعك Bloc أو MVN، بتطلعلك ملاحظات كتير ملهاش لازمة.
>
> المجموعة دي بتكتشف معمارية التطبيق الأول (MVVM, MVN, Bloc, MVC, GetX, Provider, Riverpod, Clean)، وبعدين تحكم على الكود بقواعد النمط ده هو بالذات. يعني الـ view model اللي بينادي الـ repository مباشرة صح حسب دليل فريق Flutter لـ MVVM، لكنه مخالفة ARCH-012 في MVN. والـ bloc اللي بيعتمد على bloc تاني مخالفة ARCH-010 في Bloc، أما notifier بيعمل `ref.watch` لـ notifier تاني فده مسموح في MVN.
>
> فيها:
> • أداة بتحلل الـ imports فيها 28 قاعدة معمارية (Python من غير أي مكتبات خارجية، ومش بتعدّل أي حاجة في مشروعك)
> • مراجعة كاملة: format و analyze و dart fix، وبعدين agents بيراجعوا بالتوازي، وكل ملاحظة High بتتأكد قبل ما تظهر، وفي الآخر تقرير واحد مرتب حسب الأهمية
> • إرشادات Effective Dart والتسمية ودورة حياة الـ widgets والأداء
>
> شغالة مع Claude Code و Codex و Cursor و Copilot و Gemini CLI و OpenCode.
> `npx skills add abdelrahman-abied/flutter-pro-skills`
> https://github.com/abdelrahman-abied/flutter-pro-skills
>
> المشروع مفتوح المصدر (MIT). لو لقيت ملاحظة غلط على كود سليم (false positive)، افتح issue، دي أهم مساهمة ممكن تقدمها، وممكن تكتبها بالعربي.

---

## Later releases

1. Bump `metadata.version` in the changed `SKILL.md` files.
2. `bash tests/run_all.sh` → `ALL PASSED`.
3. If the output format changed, regenerate `docs/examples/` and `docs/assets/review-preview.svg` (see `docs/examples/README.md`).
4. Repeat steps 5–6 with the new `VERSION`. Keep moving `v1` until a breaking change, then start `v2`.
