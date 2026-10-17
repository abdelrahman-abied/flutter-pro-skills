#!/usr/bin/env python3
"""Validate every skills/*/SKILL.md against the Agent Skills spec and the suite contracts.

Checks (agentskills.io/specification + docs/CONTRACTS.md §2):
  - frontmatter present; name == folder, 1-64 chars, [a-z0-9-], no leading/trailing/double hyphen
  - description 1-1024 chars (warn above 900)
  - license + metadata.suite present
  - SKILL.md <= 500 lines
  - every relative file path mentioned in backticks under references/ scripts/ assets/ exists
  - references > 300 lines start with a Contents section
  - no vendor-tool instructions (Skill tool, Agent tool, Task tool, ToolSearch, PostToolUse...) outside
    lines that also say "e.g."/"for example"/"such as" (labelled examples are allowed)
Stdlib only. Exit 1 on any error.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, 'skills')
NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
VENDOR_RE = re.compile(r'\b(Skill tool|Agent tool|Task tool|ToolSearch|PostToolUse|Read tool|Edit tool|Write tool)\b')
EXAMPLE_RE = re.compile(r'e\.g\.|for example|such as|example|like |\(.*Claude Code.*\)|Claude Code', re.I)
PATH_RE = re.compile(r'`((?:references|scripts|assets|tests)/[\w./-]+)`')

errors, warnings = [], []


def frontmatter(text):
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None, text
    fm, body = m.group(1), text[m.end():]
    data, key = {}, None
    for line in fm.split('\n'):
        if re.match(r'^\S[^:]*:', line):
            key, _, val = line.partition(':')
            key = key.strip()
            data[key] = val.strip().strip('"').strip("'")
        elif key and line.startswith('  '):
            data[key] = (data[key] + '\n' + line).strip()
    return data, body


for skill in sorted(os.listdir(SKILLS)):
    d = os.path.join(SKILLS, skill)
    if not os.path.isdir(d):
        continue
    p = os.path.join(d, 'SKILL.md')
    tag = f'skills/{skill}'
    if not os.path.isfile(p):
        errors.append(f'{tag}: missing SKILL.md')
        continue
    text = open(p, encoding='utf-8').read()
    fm, body = frontmatter(text)
    if fm is None:
        errors.append(f'{tag}: no YAML frontmatter')
        continue
    name, desc = fm.get('name', ''), fm.get('description', '')
    if name != skill:
        errors.append(f'{tag}: name "{name}" != folder')
    if not (1 <= len(name) <= 64) or not NAME_RE.match(name):
        errors.append(f'{tag}: invalid name "{name}"')
    if not (1 <= len(desc) <= 1024):
        errors.append(f'{tag}: description length {len(desc)} (must be 1-1024)')
    elif len(desc) > 900:
        warnings.append(f'{tag}: description {len(desc)} chars (>900 target)')
    if (': ' in desc or ' #' in desc) and desc[:1] not in '"\'':
        errors.append(f'{tag}: description is not valid strict YAML (unquoted ": " or " #"); rephrase or quote it')
    if 'license' not in fm:
        errors.append(f'{tag}: missing license')
    if 'suite: flutter-pro-skills' not in fm.get('metadata', ''):
        errors.append(f'{tag}: metadata.suite must be flutter-pro-skills')
    n = text.count('\n') + 1
    if n > 500:
        errors.append(f'{tag}: SKILL.md has {n} lines (max 500)')
    # referenced files exist
    for f in [os.path.join(d, 'SKILL.md')] + [os.path.join(r, x) for r, _, xs in os.walk(os.path.join(d, 'references')) for x in xs]:
        if not f.endswith('.md'):
            continue
        t = open(f, encoding='utf-8').read()
        for rel in set(PATH_RE.findall(t)):
            rel = rel.rstrip('.,:;)')
            if '<' in rel or '*' in rel:
                continue
            if not os.path.exists(os.path.join(d, rel)):
                errors.append(f'{tag}: {os.path.relpath(f, d)} references missing file `{rel}`')
        for i, line in enumerate(t.split('\n'), 1):
            if VENDOR_RE.search(line) and not EXAMPLE_RE.search(line):
                errors.append(f'{tag}: {os.path.relpath(f, d)}:{i} vendor-specific tool instruction: {line.strip()[:90]}')
        if '/references/' in f and t.count('\n') > 300 and not re.search(r'^##\s+Contents', t, re.M):
            errors.append(f'{tag}: {os.path.relpath(f, d)} is >300 lines without a "## Contents" section')
    print(f'PASS skill {skill}: name ok, description {len(desc)} chars, {n} lines' if not any(e.startswith(tag + ':') for e in errors) else f'FAIL skill {skill}')

for w in warnings:
    print(f'WARN {w}')
for e in errors:
    print(f'FAIL {e}')
sys.exit(1 if errors else 0)
