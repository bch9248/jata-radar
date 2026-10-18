"""Reproducible README and category pages; private applications never rendered."""
import csv
import html
import io
import re
from datetime import datetime
from urllib.parse import quote
from .core import CATEGORIES, COUNTRIES, load, save

CATEGORY_LABELS = {'SWE': 'SWE — Software Engineering', 'MLE_AI': 'MLE / AI — Machine Learning & AI', None: 'Other Engineering'}
PAGES = {'SWE': 'swe', 'MLE_AI': 'mle_ai', None: 'other'}
README_ROWS = 30
FLAG = {'Japan': '🇯🇵 ', 'Taiwan': '🇹🇼 '}
APPLY = 'https://img.shields.io/badge/Apply-f97316?style=for-the-badge&logoColor=white'
APPLY_CLOSED = 'https://img.shields.io/badge/Closed-9ca3af?style=for-the-badge&logoColor=white'
# What a posting has not stated yet, shown as a small badge; nothing is held back for review.
UNSTATED = {'Internship year not confirmed': 'year not stated', 'Summer not explicitly confirmed': 'summer not stated',
            'No structured job detail': 'details unverified', 'No explicit internship': 'intern not in title'}
FLAG_BADGES = {'RDSS': ('RDSS', 'ff6b6b'), 'PhD': ('PhD', 'a78bfa'), 'Japanese': ('Japanese?', '60a5fa'),
               'Visa': ('visa?', '60a5fa')}
COLUMNS = [('Company', 180), ('Role', 420), ('Location', 180), ('Link', 120), ('Date', 120)]

def cell(value):
    # 0 is a real count; only missing values render as a dash.
    return html.escape(str('—' if value is None or value == '' else value)).replace('|', '&#124;').replace('\n', ' ')

def badge(text, color, height=18, style='plastic', label=None):
    def part(x):
        return quote(x.replace('-', '--').replace('_', '__'), safe='')
    path = (part(label) + '-' if label else '') + part(text)
    alt = html.escape(f'{label}: {text}' if label else text)
    return f'<img height="{height}" alt="{alt}" src="https://img.shields.io/badge/{path}-{color}?style={style}" />'

def day(j):
    """Employer posting date when published, otherwise the day this tracker found the role."""
    posted = str(j.get('posted_at') or '')[:10]
    return posted if re.fullmatch(r'\d{4}-\d{2}-\d{2}', posted) else j['first_seen'][:10]

def newest_first(jobs):
    return sorted(jobs, key=lambda j: (day(j), j['first_seen']), reverse=True)

def badges(j):
    if j.get('decision') == 'confirmed':
        out = [badge(f'summer {j.get("year")}', '22c55e')]
    else:
        out = [badge(v, 'eab308') for r in j.get('reasons', []) for k, v in UNSTATED.items() if r.startswith(k)]
    out += [badge(*b) for f in j.get('flags', []) for k, b in FLAG_BADGES.items() if f.startswith(k)]
    return '<br />' + ' '.join(out) if out else ''

def td(width, content):
    return f'      <td width="{width}" align="left" valign="top">{content}</td>'

def table(jobs, limit=None):
    """JobRadar-style HTML table; repeated companies collapse to ↳."""
    shown = jobs[:limit] if limit else jobs
    lines = ['<table width="100%">', '  <thead>', '    <tr>',
             *[f'      <th width="{w}" align="left" valign="top">{name}</th>' for name, w in COLUMNS],
             '    </tr>', '  </thead>', '  <tbody>']
    previous = None
    for j in shown:
        company = cell(j.get('company'))
        closed = j.get('status') == 'closed'
        apply = f'<a href="{html.escape(j["url"])}"><img height="28" alt="apply" src="{APPLY_CLOSED if closed else APPLY}" /></a>'
        date = datetime.strptime(day(j), '%Y-%m-%d').strftime('%b %d')
        lines += ['    <tr>', td(180, '↳' if company == previous else company),
                  td(420, cell(j.get('title', 'Unverified listing')) + badges(j)),
                  td(180, FLAG.get(j.get('country'), '') + cell(j.get('location'))), td(120, apply), td(120, date), '    </tr>']
        previous = company
    if not jobs:
        lines += ['    <tr>', td(180, '—'), td(420, 'No listings yet'), td(180, '—'), td(120, '—'), td(120, '—'), '    </tr>']
    lines += ['  </tbody>', '</table>']
    if limit and len(jobs) > limit:
        lines.append(f'<p><sub>Showing {limit} of {len(jobs)} opportunities in this section.</sub></p>')
    return '\n'.join(lines)

def summer_internship(j, c):
    return (j.get('internship', True) and j.get('year') == c['target_year'] and j.get('season') == 'summer'
            and j.get('country') in c['countries'])

def render(root, c):
    jobs = load(root / 'data/jobs.json', [])
    health = load(root / 'data/source-health.json', {})
    # Everything found is listed; only closed and out-of-scope (rejected) postings are left out.
    open_jobs = [j for j in jobs if j.get('decision') != 'rejected' and j.get('status') != 'closed']
    # Strict board: the title or JD must state a summer internship in the target year and country.
    listed = newest_first([j for j in open_jobs if summer_internship(j, c)])
    hidden = newest_first([j for j in open_jobs if not summer_internship(j, c)])
    groups = {key: [j for j in listed if (j.get('category') if j.get('category') in PAGES else None) == key] for key in PAGES}
    updated = str(health.get('finished_at', ''))[:10] or 'never'
    countries = ' / '.join(c['countries'])
    body = [f'<h1 align="center">🌏 InternRadar — {" & ".join(c["countries"])} · Summer {c["target_year"]}</h1>', '',
            '<p align="center">', f'  <b>Fresh SWE and MLE / AI internships in {" and ".join(c["countries"])}, newest first.</b>', '</p>', '',
            '<p align="center">',
            '  ' + badge(f'{countries}', '22c55e', 20, 'flat', 'Countries'),
            '  ' + badge(f'{len(listed)}', '60a5fa', 20, 'flat', 'Open roles'),
            '  ' + badge(f'{updated}', 'f97316', 20, 'flat', 'Updated'),
            '  ' + badge(f'MIT', 'eab308', 20, 'flat', 'License'), '</p>', '',
            '<p align="center">',
            '  <a href="./installation.md"><img alt="Setup guide" src="https://img.shields.io/badge/Setup%20guide-f97316?style=for-the-badge" /></a>',
            '  <a href="./config.json"><img alt="Customize config" src="https://img.shields.io/badge/Customize%20config-f59e0b?style=for-the-badge" /></a>',
            '  <a href="./sources.json"><img alt="Sources" src="https://img.shields.io/badge/Sources-fb7185?style=for-the-badge" /></a>',
            '</p>', '', '---', '', '## Browse jobs by category', '']
    for key, label in CATEGORY_LABELS.items():
        body.append(f'- [{label}](./job-postings/{PAGES[key]}.md) — {len(groups[key])} opportunities')
    body += [f'- [Closed](./job-postings/archive.md) — {sum(j.get("status") == "closed" for j in jobs)} listings',
             f'- [Not stated as summer {c["target_year"]}](./job-postings/not-summer.md) — {len(hidden)} internships hidden from the list', '',
             f'Only roles whose title or job description states a summer {c["target_year"]} internship are listed. '
             'Date is the employer\'s posting date when published, otherwise the day this tracker first found the role.', '',
             '## The List 🚴‍♂️', '']
    for key, label in CATEGORY_LABELS.items():
        body += [f'### {label}', '', table(groups[key], README_ROWS), '']
        page = [f'# {label}', '', '[← Back to the main job board](../README.md)', '', table(groups[key])]
        (root / f'job-postings/{PAGES[key]}.md').write_text('\n'.join(page) + '\n', encoding='utf-8')
    body += ['<details>', '<summary><b>Source health</b></summary>', '', '| Source | Last result | Candidates | Note |', '|---|---|---|---|']
    for s in health.get('sources', []) + health.get('search_queries', []):
        body.append('| ' + ' | '.join(cell(s.get(x, '—')) for x in ('id', 'status', 'candidates', 'error')) + ' |')
    body += ['', f'Last sync: {health.get("finished_at", "Not run yet")} · requests: {health.get("requests", 0)}', '', '</details>', '']
    archive = ['# Closed listings', '', '[← Back to the main job board](../README.md)', '',
               table(newest_first([j for j in jobs if j.get('status') == 'closed']))]
    (root / 'job-postings/archive.md').write_text('\n'.join(archive) + '\n', encoding='utf-8')
    unstated = [f'# Not stated as summer {c["target_year"]}', '', '[← Back to the main job board](../README.md)', '',
                'Open internships whose title and job description do not state a summer period '
                '(many are 6-month, year-long, part-time or RDSS roles). Hidden from the main list.', '', table(hidden)]
    (root / 'job-postings/not-summer.md').write_text('\n'.join(unstated) + '\n', encoding='utf-8')
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
