"""Reproducible README and category pages; private applications never rendered."""
import csv
import html
import io
import re
from urllib.parse import quote
from .core import CATEGORIES, COUNTRIES, load, save

def cell(value):
    # 0 is a real count; only missing values render as a dash.
    return html.escape(str('—' if value is None or value == '' else value)).replace('|', '&#124;').replace('\n', ' ')

CATEGORY_LABELS = {'SWE': 'SWE', 'MLE_AI': 'MLE / AI'}
# Short hints for what a posting has not stated yet; nothing is held back for review.
UNSTATED = {'Internship year not confirmed': 'year not stated', 'Summer not explicitly confirmed': 'summer not stated',
            'SWE / MLE-AI role unclear': 'role type unclear', 'Workplace country missing': 'country unclear',
            'No structured job detail': 'details unverified', 'No explicit internship': 'intern not in title'}

def day(j):
    """Employer posting date when known, otherwise the day the tracker found it."""
    posted = str(j.get('posted_at') or '')[:10]
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', posted):
        return posted, 'posted'
    return j['first_seen'][:10], 'found'

def notes(j):
    if j.get('decision') == 'confirmed':
        out = [f'✅ summer {j.get("year")} stated']
    else:
        out = [v for r in j.get('reasons', []) for k, v in UNSTATED.items() if r.startswith(k)]
    return '; '.join(out + j.get('flags', []))

def table(jobs):
    lines = ['| Company | Role | Type | Location | Notes | Status | Apply | Date |',
             '|---|---|---|---|---|---|---|---|']
    for j in jobs:
        url = quote(j['url'], safe=':/?=&%-._~')
        date, kind = day(j)
        lines.append('| ' + ' | '.join([cell(j.get('company')), cell(j.get('title', 'Unverified listing')),
                      cell(CATEGORY_LABELS.get(j.get('category'), 'Other')), cell(j.get('location')),
                      cell(notes(j)), cell(j.get('status', 'unknown')), f'[Apply]({url})', f'{date} ({kind})']) + ' |')
    if not jobs:
        lines.append('| — | No listings yet | — | — | — | — | — | — |')
    return '\n'.join(lines)

def by_day(jobs, heading='###'):
    """Newest first, one table per day."""
    jobs = sorted(jobs, key=lambda j: (day(j)[0], j['first_seen']), reverse=True)
    if not jobs:
        return [table([]), '']
    out = []
    for date in dict.fromkeys(day(j)[0] for j in jobs):
        group = [j for j in jobs if day(j)[0] == date]
        out.extend([f'{heading} {date} · {len(group)} position{"s" * (len(group) != 1)}', '', table(group), ''])
    return out

def render(root, c):
    jobs = load(root / 'data/jobs.json', [])
    health = load(root / 'data/source-health.json', {})
    # Everything found is listed; only closed and out-of-scope (rejected) postings are left out.
    listed = [j for j in jobs if j.get('decision') != 'rejected' and j.get('status') != 'closed']
    counts = ' · '.join(f'[{label}](job-postings/{key.lower()}.md) {sum(j.get("category") == key for j in listed)}'
                        for key, label in CATEGORY_LABELS.items())
    body = ['## Positions — newest first', '',
            f'{len(listed)} open positions · {counts} · Other {sum(j.get("category") not in CATEGORY_LABELS for j in listed)} · [Closed](job-postings/archive.md)', '',
            'Date is the employer\'s posting date when published, otherwise the day this tracker first found the role. '
            'Notes list what the posting has not stated yet (e.g. summer dates) — check the posting before applying.', '']
    body.extend(by_day(listed))
    for category, label in CATEGORY_LABELS.items():
        page = [f'# {c["target_year"]} Internships — {label}', '', '[Back](../README.md)', '']
        page.extend(by_day([j for j in listed if j.get('category') == category], '##'))
        (root / f'job-postings/{category.lower()}.md').write_text('\n'.join(page), encoding='utf-8')
    body.extend(['## Source health', '', '| Source | Last result | Candidates | Note |', '|---|---|---|---|'])
    for s in health.get('sources', []) + health.get('search_queries', []):
        body.append('| ' + ' | '.join(cell(s.get(x, '—')) for x in ('id', 'status', 'candidates', 'error')) + ' |')
    body.extend(['', f'Last sync: {health.get("finished_at", "Not run yet")} · requests: {health.get("requests", 0)}', ''])
    archive = ['# Closed listings', '', '[Back](../README.md)', ''] + by_day([j for j in jobs if j.get('status') == 'closed'], '##')
    (root / 'job-postings/archive.md').write_text('\n'.join(archive), encoding='utf-8')
    (root / 'job-postings/review.md').unlink(missing_ok=True)
    readme = root / 'README.md'
    raw = readme.read_text(encoding='utf-8')
    start, end = '<!-- JOBS:START -->', '<!-- JOBS:END -->'
    if raw.count(start) != 1 or raw.count(end) != 1:
        raise ValueError('README requires exactly one JOBS:START / JOBS:END marker')
    a, tail = raw.split(start, 1)
    _, b = tail.split(end, 1)
    readme.write_text(a + start + '\n\n' + '\n'.join(body) + '\n' + end + b, encoding='utf-8')
    fields = ['id', 'company', 'title', 'location', 'country', 'category', 'year', 'season', 'decision', 'status', 'url', 'first_seen', 'last_seen']
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for j in jobs:
        # Prevent spreadsheet formula execution from untrusted titles.
        row = {k: ("'" + str(v) if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k, v in j.items()}
        writer.writerow(row)
    (root / 'data/jobs.csv').write_text(buf.getvalue(), encoding='utf-8')
