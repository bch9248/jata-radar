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

def table(jobs, review=False):
    lines = ['| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |',
             '|---|---|---|---|---|---|---|---|']
    for j in sorted(jobs, key=lambda j: j['first_seen'], reverse=True):
        title = cell(j.get('title', 'Unverified listing'))
        if review:
            title += '<br><sub>' + cell('; '.join(j.get('reasons', []))) + '</sub>'
        url = quote(j['url'], safe=':/?=&%-._~')
        lines.append('| ' + ' | '.join([cell(j.get('company')), title, cell(j.get('location')),
                      cell(f'{j.get("year") or "?"} / {j.get("season") or "?"}'),
                      cell('; '.join(j.get('flags', [])) or 'Unknown — read JD'),
                      cell(j.get('status', 'unknown')), f'[Apply]({url})', j['first_seen'][:10]]) + ' |')
    if not jobs:
        lines.append('| — | No confirmed listings yet | — | — | — | — | — | — |')
    return '\n'.join(lines)

def render(root, c):
    jobs = load(root / 'data/jobs.json', [])
    health = load(root / 'data/source-health.json', {})
    confirmed = [j for j in jobs if j.get('decision') == 'confirmed' and j.get('status') != 'closed']
    review = [j for j in jobs if j.get('decision') == 'review' and j.get('status') != 'closed']
    body = []
    for category, label in [('SWE', 'SWE — Software Engineering'), ('MLE_AI', 'MLE / AI — Machine Learning & AI')]:
        subset = [j for j in confirmed if j.get('category') == category]
        body.extend([f'## {label}', '', f'[Full list](job-postings/{category.lower()}.md) · {len(subset)} listings', ''])
        for country in c['countries']:
            body.extend([f'### {country}', '', table([j for j in subset if j.get('country') == country]), ''])
        page = [f'# {c["target_year"]} Summer Internships — {label}', '', '[Back](../README.md)', '']
        for country in c['countries']:
            page.extend([f'## {country}', '', table([j for j in subset if j.get('country') == country]), ''])
        (root / f'job-postings/{category.lower()}.md').write_text('\n'.join(page), encoding='utf-8')
    body.extend(['## Needs review', '', f'{len(review)} candidates · [Review queue](job-postings/review.md). Unknown year, summer dates, location or page structure is never silently approved.', '',
                 '## Source health', '', '| Source | Last result | Candidates | Note |', '|---|---|---|---|'])
    for s in health.get('sources', []) + health.get('search_queries', []):
        body.append('| ' + ' | '.join(cell(s.get(x, '—')) for x in ('id', 'status', 'candidates', 'error')) + ' |')
    body.extend(['', f'Last sync: {health.get("finished_at", "Not run yet")} · requests: {health.get("requests", 0)}', '',
                 'Only a successful job-detail fetch marks a listing open. Source absence, HTTP 403/429 and network failures do not mark it closed. Run `check` weekly; dynamic closed-page messages can still require manual review.', ''])
    (root / 'job-postings/review.md').write_text('# Candidates — verify before applying\n\n[Back](../README.md)\n\n' + table(review, True) + '\n', encoding='utf-8')
    (root / 'job-postings/archive.md').write_text('# Closed listings\n\n[Back](../README.md)\n\n' + table([j for j in jobs if j.get('status') == 'closed']) + '\n', encoding='utf-8')
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
