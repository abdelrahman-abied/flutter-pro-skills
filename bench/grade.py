#!/usr/bin/env python3
"""Deterministic grader for the flutter-pro-skills benchmark.

Usage:
  grade.py t1 <run-dir | output-file>          score a review run against ground_truth.json["t1"]
  grade.py t2 <run-dir | output-file>          score an architecture-judgement run against ["t2"]
  grade.py t3 <run-dir>                        run the suite's checkers + dart analyze on <run-dir>/proj
  grade.py t4 <run-dir>                        same as t3, scored on the product-list task (PERF/DS/A11Y lead)
  grade.py t5 <run-dir>                        same as t3, scored on the paginated, adaptive gallery task
  (t3-t5 also report new_* counts: findings the agent added, i.e. not already in the pristine fixture)
  grade.py summary <runs-root>                 grade every run under <runs-root> and print the table
  add --json for machine output, --verbose to print every parsed claim and how it was classified.

A <run-dir> contains output.jsonl (OpenCode `run --format json` events) and, for t3, proj/.
A plain text/markdown file is also accepted for t1/t2, so other agents' outputs can be graded too.

MATCHING RULES (t1, t2)
 1. Report text = the text parts of the FINAL assistant message (the last messageID that emitted
    text), with <think>...</think> removed. Intermediate narration ("found X at a.dart:3, let me
    check...") is not the report; this model leaks working notes into text parts. A run that
    times out before writing its report is graded on whatever its last message said.
    Set GRADE_ALL_TEXT=1 to grade every text part instead.
 2. The text is split into claim blocks. A block starts at a markdown heading, a top-level list
    item (bullet or number), a table row, or a line that starts with bold text. Indented lines,
    plain paragraph lines and top-level "field: value" bullets (where:, file:, line:, evidence:,
    fix:, why:, rule:, severity:, id:, confidence:, category:, issue:, problem:, location:, also
    written bold as **Where:**) belong
    to the block above them.
 3. Blocks are not claims when they sit under a heading (or bold label line) that announces
    non-problems ("not issues", "correct", "decoys", "looks wrong but", "strengths", "good",
    "no violations", ...), or when the block itself says the code is fine ("is fine",
    "is correct", "not a violation", "sanctioned", "follows the pattern", check marks ...) and,
    once those phrases are removed, carries no severity word or problem word. An opener such as
    "Architecture: Bloc (high confidence)" is a profile statement, not a claim.
 4. File references: `path.dart:12`, `path.dart:12-18`, `path.dart (line 12)`, `path.dart L12`,
    `line 12 of path.dart`, `path.dart#L12`, and table rows with a .dart cell plus a numeric
    line cell. Paths are matched to fixture files by suffix (basenames are unique per fixture).
    A range wider than 15 lines is reduced to its first line.
 5. A block credits a ground-truth issue when one of its references is in the issue's file with a
    line within +/-3 of one of the issue's anchor lines, AND the block's text falls in one of the
    issue's categories (keyword lists in CATEGORY_KEYWORDS; a block can be in several) and, when
    the issue defines `kw`, matches that regex. Categories and keywords are matched on the
    block's prose with file paths and import strings removed. t2 also accepts a file reference without a line,
    or an unlocated block that names the issue's class/file alias, provided `kw` matches.
 6. A block that credits no issue is checked against the decoys (same location rule, plus the
    decoy's `kw`). t2 decoys marked `unlocated` also match blocks without any file reference.
 7. Otherwise a located block is checked against the pre-registered neutral list (true but out
    of scope; neither credited nor penalised). Anything left is a false claim. False claims are
    de-duplicated by their first (file, line), so a summary table that repeats a finding does not
    double-count it. Unlocated blocks are ignored in t1 (the prompt asks for file:line).
 8. Scores: recall = distinct issues credited / issues; decoys flagged = distinct decoys hit;
    false claims = distinct unmatched located claims (t1); for t2, `contradicting` = distinct
    decoys hit (complaints that contradict bloclibrary conventions) and `other` = remaining
    located claims (reported, not scored).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BENCH = os.path.dirname(os.path.abspath(__file__))
GT = json.load(open(os.path.join(BENCH, "ground_truth.json")))
# The checkers that score T3/T4: a frozen snapshot if one was made, else this repository's skills/.
_SNAPSHOT = os.path.join(BENCH, "suite_snapshot", "skills")
SUITE_SKILLS = os.environ.get("SUITE_SKILLS") or (_SNAPSHOT if os.path.isdir(_SNAPSHOT) else os.path.join(BENCH, "..", "skills"))
LINE_TOL = 3
MAX_RANGE = 15

CATEGORY_KEYWORDS = {
    "architecture": r"architect|layer|dependency rule|bypass|use ?cases?|usecase|repositor|data ?source|\bsource\b|import|\bmvn\b|clean arch|separation|coupl|directly|ARCH-|\bDI\b|inject",
    "error": r"error|exception|catch|swallow|throw|crash|fail|\btry\b|stuck|spinner|loading|unhandled|silent|ERR-",
    "security": r"secur|token|secret|credential|plain ?text|shared ?pref|shared_pref|encrypt|keychain|keystore|\blog(s|ged|ging)?\b|debugPrint|print|leak|certificate|\btls\b|\bssl\b|mitm|man-in-the-middle|https|SEC-",
    "navigation": r"route|router|navigat|deep ?link|path ?param|pathParameters|int\.parse|tryParse|go_router|NAV-",
    "forms": r"obscure|password|form\b|forms|input|text ?field|TextFormField|FORM-",
    "i18n": r"hard-?coded|locali[sz]|l10n|i18n|translat|\barb\b|AppLocalizations|string literal|literal string|I18N-",
    "ui": r"dispose|leak|controller|memory|rebuild|build\(\)|\bbuild\b|future|FutureBuilder|initState|widget|lifecycle|performance|spinner|loading|UI-",
}
SEVERITY_RE = re.compile(r"\b(critical|high|medium|med|low|info|blocker|major|minor)\b", re.I)
PROBLEM_RE = re.compile(r"\b(critical|high|medium|low)\b|severity|violat|should|must|bug|leak|crash|missing|never|insecure|vulnerab|wrong|broken|risk", re.I)
POSITIVE_HEADING_RE = re.compile(
    r"not (a |an )?(real )?(issue|problem|finding|violation|bug|concern)s?|non-?issues?|false positives?|"
    r"\bcorrect\b|looks? (wrong|suspicious|odd) but|\bgood\b|strengths?|positives?|what('s| is) (right|good|correct|working)|"
    r"well[- ]done|decoys?|intentional|acceptable|\bfine\b|compliant|no violations?|things done right|"
    r"follows? (the )?(convention|pattern|architecture)|conforms?|sanctioned|by design|ok\b|verified as correct|"
    r"what('s| is) not (a )?(problem|issue)|not flagged|dismissed|rejected", re.I)
NEGATION_RE = re.compile(
    r"not an? (real )?(issue|problem|violation|finding|bug|concern)|\bno (issue|problem|violation|concern)s?\b|"
    r"\bis (fine|correct|ok|okay|acceptable|intentional|sanctioned|allowed|expected|valid|idiomatic|canonical|conventional|appropriate|good)\b|"
    r"\bare (fine|correct|ok|okay|acceptable|intentional|sanctioned|allowed|expected|valid|idiomatic|canonical|conventional|appropriate|good)\b|"
    r"(sanctioned|prescribed|allowed|permitted|recommended|endorsed) (by|in|per|under)|correctly (uses|follows|implements|implemented|placed)|"
    r"✅|✓|✔|\bfollows (the )?(bloc|mvn|convention|pattern|architecture|rules?)|"
    r"\bthis is (fine|correct|ok|by design|the (di|DI) seam)|by design|as intended|not a (problem|concern)", re.I)
FIELD_BULLET_RE = re.compile(
    r"^\s{0,1}(?:[-*+]\s+)?\**_?(where|file|files|line|lines|location|evidence|fix|why|rule|severity|id|confidence|category|issue|problem|impact|recommendation|code|details?|description|suggested fix|reason|what|verified|status)(?:\s+[\w-]+){0,3}\**\s*[:：]", re.I)
BLOCK_START_RE = re.compile(r"^(#{1,6}\s|\s{0,1}[-*+]\s|\s{0,1}\d+[.)]\s|\s*\||\*\*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
DART = r"[\w./\\-]*\w\.dart"
REF_PATTERNS = [
    re.compile(r"(?P<f>" + DART + r")`?\s*[:#]\s*L?(?P<a>\d+)(?:\s*[-–]\s*L?(?P<b>\d+))?"),
    re.compile(r"(?P<f>" + DART + r")`?\s*[,(\[]?\s*(?:at\s+)?(?:line|lines|ln|l)\.?\s*(?P<a>\d+)(?:\s*(?:[-–]|to)\s*(?P<b>\d+))?", re.I),
    re.compile(r"(?:line|lines|ln|l)\.?\s*(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?\s*(?:of|in)\s*`?(?P<f>" + DART + r")", re.I),
]
FILE_ONLY = re.compile(r"(?P<f>" + DART + r")")
TABLE_LINE_CELL = re.compile(r"^\s*(?:L|line\s*)?(\d+)(?:\s*[-–]\s*(\d+))?\s*$", re.I)


# ---------------------------------------------------------------- text extraction
def load_text(path):
    if os.path.isdir(path):
        path = os.path.join(path, "output.jsonl")
    raw = open(path, encoding="utf-8", errors="replace").read()
    parts = []
    claude_final, claude_texts = None, []
    is_jsonl = path.endswith(".jsonl")
    if is_jsonl:
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "text":
                parts.append((ev.get("part", {}).get("messageID"), ev.get("part", {}).get("text", "")))
            elif ev.get("type") == "result" and isinstance(ev.get("result"), str):
                claude_final = ev["result"]  # Claude Code stream-json: the final answer
            elif ev.get("type") == "assistant":
                for c in (ev.get("message") or {}).get("content") or []:
                    if c.get("type") == "text":
                        claude_texts.append(c.get("text", ""))
        if claude_final is not None or claude_texts:
            parts = [(None, claude_final if claude_final and not os.environ.get("GRADE_ALL_TEXT")
                      else "\n\n".join(claude_texts))]
        if not os.environ.get("GRADE_ALL_TEXT") and parts:
            last = parts[-1][0]
            parts = [p for p in parts if p[0] == last]
        text = "\n\n".join(t for _, t in parts)
    else:
        text = raw
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = text.replace("</think>", "").replace("<think>", "")
    return text


# ---------------------------------------------------------------- block splitting
def split_blocks(text):
    """Return list of (text, positive_section: bool)."""
    blocks = []
    cur = []
    cur_positive = False
    section_positive = False
    section_level = 99
    in_code = False

    def flush():
        if cur:
            blocks.append(("\n".join(cur), cur_positive))
            cur.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            cur.append(line)
            continue
        if in_code:
            cur.append(line)
            continue
        h = HEADING_RE.match(line)
        if h:
            flush()
            level = len(h.group(1))
            title = h.group(2)
            if level <= section_level:
                section_positive = False
                section_level = 99
            # a heading that is itself a finding (has a severity tag) is not a section label
            if POSITIVE_HEADING_RE.search(title) and not SEVERITY_RE.search(title):
                section_positive = True
                section_level = level
            cur_positive = section_positive
            cur.append(line)
            continue
        stripped = line.strip()
        # bold label lines such as "**Not issues (correct for MVN):**"
        if re.match(r"^\*\*[^*]{2,80}\*\*:?\s*$", stripped) or re.match(r"^[A-Z][^.|]{2,60}:\s*$", stripped):
            label = stripped.strip("*: ")
            if POSITIVE_HEADING_RE.search(label) and not SEVERITY_RE.search(label):
                flush()
                section_positive = True
                section_level = 7  # ends at the next heading of any level
                cur_positive = True
                cur.append(line)
                continue
        if FIELD_BULLET_RE.match(line):
            cur.append(line)
            continue
        if BLOCK_START_RE.match(line):
            flush()
            cur_positive = section_positive
            cur.append(line)
            continue
        cur.append(line)
    flush()
    return blocks


PROFILE_LINE_RE = re.compile(r"^\W*(?:(detected |declared )?(architecture|profile|pattern|presentation)\b[^:\n]{0,20}|detected\W*)[:：]", re.I)


def block_is_claim(text, positive_section):
    if positive_section:
        return False
    # "high confidence" and "confidence: **high**" describe the detection, not a finding's severity
    first = re.sub(r"\b(high|medium|low)\s+confidence|confidence\W{0,4}(high|medium|low)\b", "", text.splitlines()[0], flags=re.I)
    if PROFILE_LINE_RE.match(text) and not SEVERITY_RE.search(first):
        return False  # the "Architecture: Bloc (high confidence)" opener, not a finding
    if NEGATION_RE.search(text):
        rest = NEGATION_RE.sub(" ", text)
        if not PROBLEM_RE.search(rest):
            return False
    return True


# ---------------------------------------------------------------- references
def fixture_files(fixture):
    out = []
    for root, _, files in os.walk(os.path.join(fixture, "lib")):
        for f in files:
            if f.endswith(".dart") and not f.endswith(".g.dart"):
                out.append(os.path.relpath(os.path.join(root, f), fixture).replace(os.sep, "/"))
    return out


def resolve_file(ref, files):
    ref = ref.replace("\\", "/").lstrip("./")
    for f in files:
        if f == ref or f.endswith("/" + ref) or ref.endswith("/" + f) or ref.endswith(f):
            return f
    base = ref.rsplit("/", 1)[-1]
    cands = [f for f in files if f.rsplit("/", 1)[-1] == base]
    return cands[0] if len(cands) == 1 else None


def extract_refs(block, files):
    """Return (located: list of (file, start, end), file_only: set of files)."""
    located = []
    spans = []
    for pat in REF_PATTERNS:
        for m in pat.finditer(block):
            f = resolve_file(m.group("f"), files)
            if not f:
                continue
            a = int(m.group("a"))
            b = int(m.group("b")) if m.group("b") else a
            if b < a or b - a > MAX_RANGE:
                b = a
            located.append((f, a, b))
            spans.append(m.span())
    # tables: | file.dart | 12 | ...
    for line in block.splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            fcell = None
            for c in cells:
                fm = FILE_ONLY.search(c)
                if fm and fcell is None:
                    fcell = resolve_file(fm.group("f"), files)
                    continue
                if fcell:
                    lm = TABLE_LINE_CELL.match(c)
                    if lm:
                        a = int(lm.group(1))
                        b = int(lm.group(2)) if lm.group(2) else a
                        if b < a or b - a > MAX_RANGE:
                            b = a
                        located.append((fcell, a, b))
                        break
    file_only = set()
    for m in FILE_ONLY.finditer(block):
        f = resolve_file(m.group("f"), files)
        if f:
            file_only.add(f)
    return located, file_only


def resolve_anchors(fixture, anchors):
    out = []
    for rel, sub in anchors:
        lines = open(os.path.join(fixture, rel), encoding="utf-8").read().splitlines()
        hits = [i + 1 for i, l in enumerate(lines) if sub in l]
        if not hits:
            raise SystemExit("unresolved anchor: %s :: %r" % (rel, sub))
        out.append((rel, hits[0]))
    return out


def loc_hit(located, anchors):
    for f, a, b in located:
        for af, al in anchors:
            if f == af and a - LINE_TOL <= al <= b + LINE_TOL:
                return True
    return False


def categories(text):
    return {c for c, rx in CATEGORY_KEYWORDS.items() if re.search(rx, text, re.I)}


# ---------------------------------------------------------------- grading t1 / t2
def grade_review(task, path, verbose=False):
    spec = GT[task]
    fixture = os.path.join(BENCH, spec["fixture"])
    files = fixture_files(fixture)
    issues = [dict(i, _anchors=resolve_anchors(fixture, i["anchors"])) for i in spec["issues"]]
    decoys = [dict(d, _anchors=resolve_anchors(fixture, d["anchors"])) for d in spec["decoys"]]
    neutral = spec.get("neutral", [])
    text = load_text(path)
    blocks = split_blocks(text)

    credited, decoy_hits, false_locs, neutral_hits = {}, {}, {}, {}
    other_locs = {}
    log = []
    n_claims = 0
    for btxt, pos in blocks:
        located, file_only = extract_refs(btxt, files)
        if not block_is_claim(btxt, pos):
            if located or file_only:
                log.append(("not-a-claim", btxt))
            continue
        # keywords are matched on the prose only: file paths such as cubit/theme_cubit.dart or
        # import strings must not satisfy a keyword by themselves
        prose = re.sub(r"[\w./\\-]*\w\.dart(:\d+)?|'(package:|\.\./)[^']*'", " ", btxt)
        cats = categories(prose)
        hit_issue = []
        for i in issues:
            kw_ok = ("kw" not in i) or re.search(i["kw"], prose, re.I)
            cat_ok = bool(cats & set(i["cats"]))
            if task == "t1":
                if loc_hit(located, i["_anchors"]) and cat_ok and kw_ok:
                    hit_issue.append(i["id"])
            else:
                anchor_files = {f for f, _ in i["_anchors"]}
                if located:
                    ok = loc_hit(located, i["_anchors"]) or (anchor_files & file_only and not any(f in anchor_files for f, _, _ in located))
                else:
                    ok = bool(anchor_files & file_only) or bool(re.search(i["alias"], btxt))
                if ok and kw_ok:
                    hit_issue.append(i["id"])
        if not located and not file_only and task == "t1":
            continue
        if hit_issue:
            n_claims += 1
            for iid in hit_issue:
                credited.setdefault(iid, btxt)
            log.append(("credit " + ",".join(hit_issue), btxt))
            continue
        hit_decoy = None
        for d in decoys:
            if not re.search(d["kw"], prose, re.I):
                continue
            if located and loc_hit(located, d["_anchors"]):
                hit_decoy = d["id"]
            elif task == "t2" and not located:
                dfiles = {f for f, _ in d["_anchors"]}
                if (dfiles & file_only) or (d.get("unlocated") and not file_only):
                    hit_decoy = d["id"]
            if hit_decoy:
                break
        if hit_decoy:
            n_claims += 1
            decoy_hits.setdefault(hit_decoy, btxt)
            log.append(("DECOY " + hit_decoy, btxt))
            continue
        if not located and not file_only:
            continue  # unlocated t2 block that is not a known decoy: ignored
        n_claims += 1
        key = (located[0][0], located[0][1]) if located else (sorted(file_only)[0], 0)
        nid = None
        for n in neutral:
            if re.search(n["kw"], prose, re.I):
                nid = n["id"]
                break
        if nid:
            neutral_hits.setdefault(nid, btxt)
            log.append(("neutral " + nid, btxt))
            continue
        if task == "t1":
            if key not in false_locs:
                false_locs[key] = btxt
                log.append(("FALSE", btxt))
            else:
                log.append(("false(dup)", btxt))
        else:
            if key not in other_locs:
                other_locs[key] = btxt
            log.append(("other", btxt))

    res = {
        "task": task,
        "run": path,
        "issues_total": len(issues),
        "credited": sorted(credited),
        "missed": sorted(i["id"] for i in issues if i["id"] not in credited),
        "recall": round(len(credited) / len(issues), 3),
        "decoys_total": len(decoys),
        "decoys_flagged": sorted(decoy_hits),
        "claim_blocks": n_claims,
        "text_chars": len(text),
    }
    if task == "t1":
        res["false_claims"] = len(false_locs)
        res["neutral"] = sorted(neutral_hits)
        res["false_claim_examples"] = [v[:300] for v in list(false_locs.values())[:40]]
    else:
        res["contradicting"] = len(decoy_hits)
        res["other_claims"] = len(other_locs)
        res["other_examples"] = [v[:300] for v in list(other_locs.values())[:40]]
    res["decoy_examples"] = {k: v[:300] for k, v in decoy_hits.items()}
    if verbose:
        for tag, b in log:
            print("=== [%s]\n%s\n" % (tag, b[:700]))
    return res


# ---------------------------------------------------------------- grading t3
def _run(cmd, cwd=None, timeout=900, env=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, p.stdout + p.stderr


def _checker(script, proj):
    path = os.path.join(SUITE_SKILLS, script)
    if not os.path.isfile(path):
        # never score a missing checker as "0 findings": that silently reads as a clean result
        sys.exit("grade.py: checker not found: %s (set SUITE_SKILLS)" % path)
    rc, out = _run(["python3", "-I", path, proj, "--json"])
    start = out.find("{")
    return json.loads(out[start:]) if start >= 0 else {}


# Every checker that scores a writing task: (short name, script, JSON key holding the hits)
WRITE_CHECKERS = (
    ("arch", "flutter-architecture/scripts/arch_check.py", "violations"),
    ("sec", "flutter-secure-defaults/scripts/check_secure_defaults.py", "findings"),
    ("err", "flutter-error-handling/scripts/check_errors.py", "findings"),
    ("forms", "flutter-forms/scripts/check_forms.py", "findings"),
    ("i18n", "flutter-i18n/scripts/check_i18n.py", "findings"),
    ("perf", "flutter-performance/scripts/check_performance.py", "findings"),
    ("persist", "flutter-persistence/scripts/check_persistence.py", "findings"),
    ("net", "flutter-networking/scripts/check_networking.py", "findings"),
    ("plat", "flutter-platform-integration/scripts/check_platform.py", "findings"),
    ("ds", "flutter-design-system/scripts/check_design_system.py", "findings"),
    ("adapt", "flutter-adaptive-layout/scripts/check_adaptive.py", "findings"),
    ("a11y", "flutter-accessibility/scripts/check_accessibility.py", "findings"),
)
_PRISTINE = {}


def _hit_keys(proj):
    """(checker, id, file, evidence) for every low-or-above hit; line numbers are left out on purpose,
    so an agent's edits above a pre-existing hit don't make it look new."""
    keys = []
    for name, script, field in WRITE_CHECKERS:
        for f in _checker(script, proj).get(field, []):
            if f.get("severity") == "info":
                continue
            keys.append((name, f["id"], f.get("severity", ""), f["file"], " ".join(str(f.get("evidence", "")).split())))
    return keys


def _new_hits(task, dst):
    """Hits in the graded copy that the pristine fixture does not already have."""
    fixture = os.path.join(BENCH, "fixtures", "t3_mvn_clean")
    if task not in _PRISTINE:
        _PRISTINE[task] = _hit_keys(fixture)
    base = list(_PRISTINE[task])
    new = []
    for k in _hit_keys(dst):
        if k in base:
            base.remove(k)
        else:
            new.append(k)
    return new


def grade_t3(run_dir, task="t3"):
    proj = os.path.join(run_dir, "proj")
    work = tempfile.mkdtemp(prefix="t3grade-")
    dst = os.path.join(work, "proj")
    shutil.copytree(proj, dst, symlinks=True, ignore=shutil.ignore_patterns(".agents", ".git"))
    res = {"task": task, "run": run_dir}
    arch = _checker("flutter-architecture/scripts/arch_check.py", dst)
    res["arch_violations"] = len(arch.get("violations", []))
    res["arch_ids"] = sorted({v["id"] for v in arch.get("violations", [])})
    sec = _checker("flutter-secure-defaults/scripts/check_secure_defaults.py", dst)
    sf = sec.get("findings", [])
    res["sec_findings"] = len([f for f in sf if f.get("severity") != "info"])
    res["sec_high"] = len([f for f in sf if f.get("severity") == "high"])
    res["sec_ids"] = sorted({f["id"] for f in sf if f.get("severity") != "info"})
    err = _checker("flutter-error-handling/scripts/check_errors.py", dst)
    ef = err.get("findings", [])
    res["err_high_medium"] = len([f for f in ef if f.get("severity") in ("high", "medium")])
    res["err_ids"] = sorted({f["id"] for f in ef if f.get("severity") in ("high", "medium")})
    for name, script in (("forms", "flutter-forms/scripts/check_forms.py"), ("i18n", "flutter-i18n/scripts/check_i18n.py")):
        j = _checker(script, dst)
        fl = [f for f in j.get("findings", []) if f.get("severity") not in ("info",)]
        res[name + "_findings"] = len(fl)
        res[name + "_ids"] = sorted({f["id"] for f in fl})
    # v1.1 checkers: low and above count (info is advice, not a defect)
    for name, script in (("perf", "flutter-performance/scripts/check_performance.py"),
                         ("persist", "flutter-persistence/scripts/check_persistence.py"),
                         ("ds", "flutter-design-system/scripts/check_design_system.py"),
                         ("a11y", "flutter-accessibility/scripts/check_accessibility.py")):
        j = _checker(script, dst)
        fl = [f for f in j.get("findings", []) if f.get("severity") != "info"]
        res[name + "_findings"] = len(fl)
        res[name + "_high_medium"] = len([f for f in fl if f.get("severity") in ("high", "medium")])
        res[name + "_ids"] = sorted({f["id"] for f in fl})
    for name in ("net", "plat", "adapt"):
        j = _checker(dict((n, s) for n, s, _ in WRITE_CHECKERS)[name], dst)
        fl = [f for f in j.get("findings", []) if f.get("severity") != "info"]
        res[name + "_findings"] = len(fl)
        res[name + "_ids"] = sorted({f["id"] for f in fl})
    new = _new_hits(task, dst)
    res["new_findings"] = len(new)
    res["new_high_medium"] = len([k for k in new if k[2] in ("high", "medium")])
    res["new_ids"] = sorted("%s:%s(%s)" % (k[0], k[1], k[2]) for k in new)
    # functional sanity
    src = ""
    for root, _, fs in os.walk(os.path.join(dst, "lib")):
        for f in fs:
            if f.endswith(".dart") and not f.endswith(".g.dart"):
                src += open(os.path.join(root, f), encoding="utf-8", errors="replace").read() + "\n"
    res["calls_post_login"] = bool(re.search(r"\.post[<(][^;]*['\"]/?(v1/)?(auth/)?login['\"]", src, re.S))
    if "FlutterSecureStorage" in src:
        res["token_store"] = "flutter_secure_storage"
    elif re.search(r"set(String)\([^)]*token", src, re.I):
        res["token_store"] = "shared_preferences"
    else:
        res["token_store"] = "other/none"
    res["paginates"] = bool(re.search(r"page[=:]|[?&]page\b|['\"]page['\"]|nextPage|loadMore|fetchNext", src))
    res["adaptive_layout"] = bool(re.search(r"LayoutBuilder|MediaQuery\.sizeOf|NavigationRail|maxWidth\s*[<>]=?", src))
    res["lazy_list"] = bool(re.search(r"\b(?:ListView|GridView|SliverList|SliverGrid)\.builder\b|SliverChildBuilderDelegate", src))
    res["login_files"] = len([1 for root, _, fs in os.walk(os.path.join(dst, "lib")) for f in fs
                              if re.search(r"(auth|login|session)", os.path.join(root, f)) and f.endswith(".dart") and not f.endswith(".g.dart")])
    # dart analyze: resolve offline with the developer's pub cache, run codegen if needed
    env = dict(os.environ)
    env.pop("PUB_CACHE", None)
    rc, out = _run(["flutter", "pub", "get", "--offline"], cwd=dst, env=env)
    res["pub_get"] = "offline-ok" if rc == 0 else "offline-failed"
    if rc != 0:
        rc, out = _run(["flutter", "pub", "get"], cwd=dst, env=env)
        res["pub_get"] = "online-ok" if rc == 0 else "failed"
    if rc == 0:
        if "riverpod_generator" in open(os.path.join(dst, "pubspec.yaml")).read() or "build_runner" in open(os.path.join(dst, "pubspec.yaml")).read():
            _run(["dart", "run", "build_runner", "build", "-d"], cwd=dst, env=env, timeout=900)
        _run(["flutter", "gen-l10n"], cwd=dst, env=env)
        rc, out = _run(["dart", "analyze", "--format=machine"], cwd=dst, env=env)
        sev = [l.split("|")[0] for l in out.splitlines() if l.count("|") >= 7]
        res["analyze_errors"] = sev.count("ERROR")
        res["analyze_warnings"] = sev.count("WARNING")
        res["analyze_infos"] = sev.count("INFO")
        res["analyze_error_lines"] = [l for l in out.splitlines() if l.startswith("ERROR")][:15]
    else:
        res["analyze_errors"] = None
    shutil.rmtree(work, ignore_errors=True)
    return res


# ---------------------------------------------------------------- summary
def summary(root, as_json=False):
    rows = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "output.jsonl")):
            continue
        task = name.split("-")[0]
        meta = {}
        if os.path.exists(os.path.join(d, "meta.json")):
            meta = json.load(open(os.path.join(d, "meta.json")))
        cache = os.path.join(d, "grade.json")
        if os.path.exists(cache):
            r = json.load(open(cache))
        else:
            r = grade_t3(d, task) if task in ("t3", "t4", "t5") else grade_review(task, d)
            json.dump(r, open(cache, "w"), indent=1)
        r["name"] = name
        r["meta"] = meta
        rows.append(r)
    if as_json:
        print(json.dumps(rows, indent=1))
        return rows
    for r in rows:
        m = r["meta"]
        tail = "exit=%s secs=%s skills_loaded=%s checker_runs=%s" % (m.get("exit"), m.get("seconds"), m.get("skills_loaded"), m.get("checker_runs"))
        if r["task"] == "t1":
            print("%-22s recall %2d/%d  false %2d  decoys %d/%d %s  neutral %d  | %s" % (
                r["name"], len(r["credited"]), r["issues_total"], r["false_claims"], len(r["decoys_flagged"]), r["decoys_total"], r["decoys_flagged"], len(r["neutral"]), tail))
        elif r["task"] == "t2":
            print("%-22s recall %d/%d  contradicting %d %s  other %d  | %s" % (
                r["name"], len(r["credited"]), r["issues_total"], r["contradicting"], r["decoys_flagged"], r["other_claims"], tail))
        elif r["task"] == "t5":
            print("%-22s NEW %s (h+m %s) %s  lazy=%s paginates=%s adaptive=%s  analyze E/W %s/%s | %s" % (
                r["name"], r.get("new_findings"), r.get("new_high_medium"), r.get("new_ids"), r.get("lazy_list"),
                r.get("paginates"), r.get("adaptive_layout"), r.get("analyze_errors"), r.get("analyze_warnings"), tail))
        elif r["task"] == "t4":
            print("%-22s PERF %s  DS %s  A11Y %s  (h+m %s/%s/%s)  SEC %s  ARCH %s  ERR h+m %s  lazy=%s  analyze E/W %s/%s | %s" % (
                r["name"], r.get("perf_findings"), r.get("ds_findings"), r.get("a11y_findings"), r.get("perf_high_medium"),
                r.get("ds_high_medium"), r.get("a11y_high_medium"), r["sec_findings"], r["arch_violations"], r["err_high_medium"],
                r.get("lazy_list"), r.get("analyze_errors"), r.get("analyze_warnings"), tail))
        else:
            print("%-22s SEC %s (high %s)  ARCH %s  ERR h+m %s  FORM %s  I18N %s  analyze E/W %s/%s  post_login=%s store=%s | %s" % (
                r["name"], r["sec_findings"], r["sec_high"], r["arch_violations"], r["err_high_medium"], r["forms_findings"], r["i18n_findings"],
                r.get("analyze_errors"), r.get("analyze_warnings"), r["calls_post_login"], r["token_store"], tail))
    return rows


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    task, path = argv[1], argv[2]
    as_json = "--json" in argv
    verbose = "--verbose" in argv
    if task == "summary":
        summary(path, as_json)
        return 0
    if task in ("t1", "t2"):
        r = grade_review(task, path, verbose)
    elif task in ("t3", "t4", "t5"):
        r = grade_t3(path, task)
    else:
        print(__doc__)
        return 2
    print(json.dumps(r, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
