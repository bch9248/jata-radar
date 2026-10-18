from __future__ import annotations
import argparse
import json
import os
import re
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from .core import (ROOT, config, env, load, save, now, upsert, canonical, job_id, find, aggregator, merge_duplicates,
                   refresh, settle_status, CATEGORIES, COUNTRIES, APPLICATION_STATES)
from .network import Client, FetchError
from .sources import COLLECTORS, detail, search_candidates
from .render import render

# Parser/adapter failures on one job or source must not abort the whole run.
ITEM_ERRORS = (FetchError, ValueError, KeyError, TypeError, AttributeError)


def store(root, jobs):
    save(root / 'data/jobs.json', jobs)


def sync(root, c, args):
    jobs = load(root / 'data/jobs.json', [])
    if args.offline:
        render(root, c)
        print('Offline render complete; no network requests.')
        return 0
    for j in jobs:
        # Records verified from aggregator pages before they were recognized as such.
        if aggregator(j['url'], c) and j.get('trusted_detail'):
            j.update(trusted_detail=False, detail_method='jsonld-aggregator')
            refresh(j, c)
    merge_duplicates(jobs, c)
    client = Client(c)
    health = {'started_at': now(), 'sources': [], 'search_queries': []}
    candidates = []
    source_list = load(root / 'sources.json')
    if args.source and args.source not in [s['id'] for s in source_list if s.get('enabled')]:
        raise ValueError('Unknown or disabled --source ID')
    for s in source_list:
        if not s.get('enabled') or args.source and s['id'] != args.source:
            continue
        try:
            found, truncated = COLLECTORS[s['type']](client, s, c)
            candidates.extend(found)
            health['sources'].append({'id': s['id'], 'status': 'truncated' if truncated else 'ok',
                                      'candidates': len(found), 'error': 'Pagination limit reached; increase max_pages' if truncated else ''})
        except ITEM_ERRORS as e:
            health['sources'].append({'id': s['id'], 'status': 'error', 'candidates': 0, 'error': str(e)})
    state = load(root / 'data/state.json', {'search_cursor': 0, 'detail_cursor': 0})
    if not args.no_search and not args.source:
        queries = load(root / 'search-queries.json')
        found, reports, state['search_cursor'] = search_candidates(client, queries, c, state.get('search_cursor', 0))
        candidates.extend(found)
        health['search_queries'] = reports
        if not os.environ.get('BRAVE_API_KEY'):
            health['search_queries'].append({'id': 'brave', 'status': 'skipped', 'error': 'BRAVE_API_KEY not set', 'candidates': 0})
    # Merge discovery hints first. Search snippets are never persisted.
    unique = {}
    for candidate in candidates:
        try:
            url = canonical(candidate['url'])
            ident = job_id(url)
            if ident in unique:
                continue
            unique[ident] = candidate
        except (ValueError, KeyError):
            continue
    pending = {}
    added = 0
    for ident, candidate in unique.items():
        existing = find(jobs, ident)
        # Search-only URLs with no independently fetched page aren't persisted.
        if candidate.get('title') or candidate.get('trusted_detail'):
            j, created = upsert(jobs, candidate, c)
            added += created
            if candidate.get('trusted_detail'):
                continue
        # Unverified pages are retried on the same schedule, not every run.
        if not existing:
            pending.setdefault(ident, candidate)
        elif due(existing, c.get('recheck_after_days', 7)):
            # An alias hit rechecks the surviving record's (employer) URL.
            pending.setdefault(existing['id'], dict(candidate, url=existing['url']))
    pending = list(pending.values())
    health['detail_errors'] = []
    # Rotate detail requests to prevent starvation when discovery exceeds budget.
    pending.sort(key=lambda j: canonical(j['url']))
    cursor = state.get('detail_cursor', 0) % max(1, len(pending))
    pending = pending[cursor:] + pending[:cursor]
    n = min(len(pending), c['max_detail_requests'])
    queue = pending[:n]
    attempted = 0
    while queue and attempted < c['max_detail_requests']:
        candidate = queue.pop(0)
        attempted += 1
        try:
            full = detail(client, candidate, c)
            j, created = upsert(jobs, full, c)
            added += created
            employer = full.get('employer_url')
            if employer and not find(jobs, job_id(employer)):
                # Verify the aggregator listing against the employer's own page.
                queue.append({'url': employer, 'source': candidate.get('source', 'manual'), 'company': full.get('company', '')})
            if c.get('ai_enabled') and j.get('description'):
                from .ai import enrich
                try:
                    enrich(client, j, c)
                except (ValueError, FetchError) as e:
                    health['detail_errors'].append({'id': j['id'], 'error': 'AI: ' + str(e)})
        except ITEM_ERRORS as e:
            ident = job_id(candidate['url'])
            health['detail_errors'].append({'id': ident, 'error': str(e)})
            failed = find(jobs, ident)
            if failed:
                # Record the attempt so blocked pages wait for the recheck interval.
                failed.update(last_checked=now(), last_check_error=str(e))
    merge_duplicates(jobs, c)
    state['detail_cursor'] = (cursor + n) % max(1, len(pending))
    health.update(finished_at=now(), requests=client.requests, new_jobs=added,
                  detail_candidates=len(pending), details_attempted=attempted, details_deferred=len(pending) - n)
    save(root / 'data/state.json', state)
    store(root, jobs)
    save(root / 'data/source-health.json', health)
    render(root, c)
    print(json.dumps(health, ensure_ascii=False, indent=2))
    reports = health['sources'] + health['search_queries']
    # No misleading green run when all attempted discovery backends failed.
    return 2 if reports and not any(r['status'] in ('ok', 'truncated') for r in reports) else 0


def due(job, days):
    if not job.get('last_checked'):
        return True
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(job['last_checked']) >= timedelta(days=days)
    except ValueError:
        return True


def check(root, c, args):
    client = Client(c)
    jobs = load(root / 'data/jobs.json', [])
    if args.id:
        find_job(jobs, args.id)
    selected = [j for j in jobs if (not args.id or j['id'] == args.id) and (args.force or due(j, c.get('recheck_after_days', 7)))]
    report = []
    for j in selected[:c['max_detail_requests']]:
        try:
            # upsert applies deadline and manual-status precedence.
            updated, _ = upsert(jobs, detail(client, j, c), c)
            report.append({'id': j['id'], 'status': updated['status']})
        except FetchError as e:
            j['last_checked'] = now()
            j['last_check_error'] = str(e)
            if e.status in (404, 410):
                j['missing_count'] = j.get('missing_count', 0) + 1
                if j['missing_count'] >= c.get('close_after_missing_checks', 2):
                    j['status'] = 'closed'
            else:
                # Consecutive missing checks only; unrelated errors break the streak.
                j['missing_count'] = 0
            settle_status(j)
            report.append({'id': j['id'], 'status': j.get('status', 'unknown'), 'error': str(e)})
        except ITEM_ERRORS as e:
            # Parser/shape failures say nothing about whether the posting still exists.
            j.update(last_checked=now(), last_check_error=str(e), missing_count=0)
            report.append({'id': j['id'], 'status': j.get('status', 'unknown'), 'error': str(e)})
    store(root, jobs)
    save(root / 'data/check-health.json', {'finished_at': now(), 'checks': report, 'deferred': max(0, len(selected) - c['max_detail_requests'])})
    render(root, c)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def add(root, c, args):
    candidate = {'url': canonical(args.url), 'source': 'manual', 'title': args.title or '',
                 'company': args.company or '', 'location': args.location or ''}
    if not args.no_fetch:
        try:
            candidate = detail(Client(c), candidate, c)
        except FetchError as e:
            print(f'Detail unavailable; stored for review: {e}', file=sys.stderr)
    jobs = load(root / 'data/jobs.json', [])
    j, _ = upsert(jobs, candidate, c)
    store(root, jobs)
    render(root, c)
    print(f'{j["id"]} {j["decision"]}: {j.get("title", "Unverified listing")}')


def import_jobs(root, c, args):
    incoming = load(Path(args.file))
    if not isinstance(incoming, list):
        raise ValueError('Import requires a JSON array of job objects')
    for j in incoming:
        if not isinstance(j, dict) or not j.get('url') or not isinstance(j.get('title'), str):
            raise ValueError('Each imported job needs url and title')
        canonical(j['url'])
    jobs = load(root / 'data/jobs.json', [])
    for item in incoming:
        # Imported descriptions are human-provided, not independently verified.
        item = {k: item[k] for k in ('url', 'title', 'company', 'location', 'description', 'employment_type') if k in item}
        item.update(source='import', trusted_detail=False)
        upsert(jobs, item, c)
    store(root, jobs)
    render(root, c)
    print(f'Imported {len(incoming)} candidates. Use review to confirm.')


def find_job(jobs, ident):
    found = next((j for j in jobs if j['id'] == ident), None)
    if not found:
        raise ValueError('Job ID not found; run list')
    return found


def review(root, c, args):
    jobs = load(root / 'data/jobs.json', [])
    j = find_job(jobs, args.id)
    if args.decision == 'reset':
        j.pop('manual_review', None)
        from .core import classify
        j.update(classify(j, c))
    else:
        r = {'decision': args.decision, 'reason': args.reason, 'reviewed_at': now()}
        if args.decision == 'confirmed':
            if not args.country or not args.category:
                raise ValueError('Confirm requires --country and --category; manually verify actual summer 2027 dates')
            if args.country not in c['countries']:
                raise ValueError('Country is outside configured targets')
            r.update(country=args.country, category=args.category, year=c['target_year'], season='summer')
        j['manual_review'] = r
        j.update({k: v for k, v in r.items() if k != 'reviewed_at'})
        j['reasons'] = [args.reason]
    store(root, jobs)
    render(root, c)
    print(f'{j["id"]}: {j["decision"]}')


def application(root, args):
    find_job(load(root / 'data/jobs.json', []), args.id)
    path = root / '.local/applications.json'
    applications = load(path, {})
    applications[args.id] = {'status': args.status, 'notes': args.notes or '', 'updated_at': now()}
    save(path, applications)
    print(f'{args.id}: {args.status} (private local file)')


def notify(root, args):
    # Explicit opt-in command only. Sync never sends a message.
    jobs = [j for j in load(root / 'data/jobs.json', []) if j.get('decision') == 'confirmed' and j.get('status') != 'closed']
    path = root / '.local/notified.json'
    sent = load(path, [])
    unseen = [j for j in jobs if j['id'] not in sent]
    if not unseen:
        print('No new confirmed jobs.')
        return
    body = '\n\n'.join(f'{j.get("company", "?")} | {j.get("title", "?")} | {j.get("location", "?")}\n{j["url"]}' for j in unseen)
    if args.preview:
        print(body)
        return
    required = ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_FROM', 'SMTP_TO']
    if any(not os.environ.get(k) for k in required):
        raise ValueError('SMTP setup incomplete; see .env.example or use notify --preview')
    message = EmailMessage()
    message['Subject'] = f'InternRadar: {len(unseen)} new confirmed internships'
    message['From'] = os.environ['SMTP_FROM']
    recipients = [s.strip() for s in os.environ['SMTP_TO'].split(',') if s.strip()]
    message['To'] = ', '.join(recipients)
    message.set_content(body)
    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', 587)), timeout=20) as smtp:
        smtp.starttls()
        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(message, to_addrs=recipients)
    save(path, sent + [j['id'] for j in unseen])
    print(f'Notification sent for {len(unseen)} jobs.')


def doctor(root, c):
    print(f'Python {sys.version.split()[0]} | target: summer {c["target_year"]} | countries: {", ".join(c["countries"])}')
    sources = load(root / 'sources.json')
    ids = set()
    for s in sources:
        if s['id'] in ids or s['type'] not in COLLECTORS:
            raise ValueError('Invalid or duplicate source ID/type')
        ids.add(s['id'])
        if s.get('enabled'):
            if s['type'] in ('workday', 'community'):
                canonical(s['url'])
            elif not re.fullmatch(r'[a-zA-Z0-9_-]+', s.get('board', '')):
                raise ValueError('ATS source needs a valid board identifier')
    queries = load(root / 'search-queries.json')
    if not queries or len({q['id'] for q in queries}) != len(queries):
        raise ValueError('Search queries empty or duplicate IDs')
    print(f'{sum(bool(s.get("enabled")) for s in sources)} enabled sources, {len(queries)} rotating search queries')
    print('BRAVE_API_KEY: ' + ('set' if os.environ.get('BRAVE_API_KEY') else 'not set — broad search skipped'))
    print('AI: ' + ('enabled' if c.get('ai_enabled') else 'disabled'))
    if c.get('ai_enabled') and not os.environ.get('OPENAI_API_KEY'):
        print('Warning: AI enabled but OPENAI_API_KEY missing; live enrichment will be unavailable')
    print('Configuration valid. This command does not test network access.')


def main(argv=None):
    p = argparse.ArgumentParser(description='2027 Japan/Taiwan summer SWE & MLE/AI internship tracker')
    p.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('sync', help='Collect, verify, classify, deduplicate and render')
    s.add_argument('--offline', action='store_true')
    s.add_argument('--no-search', action='store_true')
    s.add_argument('--source')
    sub.add_parser('render', help='Regenerate README, category pages and CSV')
    sub.add_parser('doctor', help='Validate config without network access')
    s = sub.add_parser('list', help='List jobs / private application states')
    s.add_argument('--decision', choices=['confirmed', 'review', 'rejected'])
    s.add_argument('--category', choices=CATEGORIES)
    s.add_argument('--country', choices=COUNTRIES)
    s.add_argument('--applications', action='store_true')
    s = sub.add_parser('show', help='Show complete job evidence')
    s.add_argument('id')
    s = sub.add_parser('add', help='Fetch a job URL; blocked pages remain review candidates')
    s.add_argument('url')
    for name in ('title', 'company', 'location'):
        s.add_argument('--' + name)
    s.add_argument('--no-fetch', action='store_true')
    s = sub.add_parser('import', help='Import a JSON array for review')
    s.add_argument('file')
    s = sub.add_parser('review', help='Manual confirmation/rejection with audit reason')
    s.add_argument('id')
    s.add_argument('decision', choices=['confirmed', 'rejected', 'reset'])
    s.add_argument('--reason', required=True)
    s.add_argument('--country', choices=COUNTRIES)
    s.add_argument('--category', choices=CATEGORIES)
    s = sub.add_parser('check', help='Recheck job URLs; 404/410 require consecutive checks')
    s.add_argument('--force', action='store_true')
    s.add_argument('--id')
    s = sub.add_parser('close', help='Manually close/reopen a job; "auto" clears the override')
    s.add_argument('id')
    s.add_argument('status', choices=['closed', 'open', 'unknown', 'auto'])
    s.add_argument('--reason', required=True)
    s = sub.add_parser('application', help='Save private application progress')
    s.add_argument('id')
    s.add_argument('status', choices=APPLICATION_STATES)
    s.add_argument('--notes')
    s = sub.add_parser('notify', help='Explicitly send SMTP alert for new confirmed jobs')
    s.add_argument('--preview', action='store_true')
    args = p.parse_args(argv)
    root = args.root.resolve()
    try:
        env(root)
        c = config(root)
        if sys.version_info < (3, 11):
            raise ValueError('Python 3.11 or newer required')
        cmd = args.command
        if cmd == 'sync':
            return sync(root, c, args)
        if cmd == 'render':
            render(root, c)
        elif cmd == 'doctor':
            doctor(root, c)
        elif cmd == 'add':
            add(root, c, args)
        elif cmd == 'import':
            import_jobs(root, c, args)
        elif cmd == 'check':
            check(root, c, args)
        elif cmd == 'review':
            review(root, c, args)
        elif cmd == 'application':
            application(root, args)
        elif cmd == 'notify':
            notify(root, args)
        elif cmd in ('list', 'show', 'close'):
            jobs = load(root / 'data/jobs.json', [])
            if cmd == 'show':
                print(json.dumps(find_job(jobs, args.id), ensure_ascii=False, indent=2))
            elif cmd == 'close':
                j = find_job(jobs, args.id)
                if args.status == 'auto':
                    j.pop('manual_status', None)
                else:
                    # Sticky: later fetches and deadlines do not override a manual status.
                    j['manual_status'] = {'status': args.status, 'reason': args.reason, 'at': now()}
                    j['status'] = args.status
                j['status_note'] = args.reason
                settle_status(j)
                store(root, jobs)
                render(root, c)
            else:
                applications = load(root / '.local/applications.json', {}) if args.applications else {}
                for j in jobs:
                    if any(getattr(args, k) and j.get(k) != getattr(args, k) for k in ('decision', 'category', 'country')):
                        continue
                    print(f'{j["id"]} | {j.get("decision")} | {j.get("country")} | {j.get("category")} | {j.get("company", "?")} | {j.get("title", "Unverified listing")} | {applications.get(j["id"], {}).get("status", "")}')
        return 0
    except (ValueError, KeyError, OSError, FetchError, smtplib.SMTPException) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
