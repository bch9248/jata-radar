"""Local-first persistence, conservative target classification, and URL identity."""
from __future__ import annotations
import hashlib
import html
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ('SWE', 'MLE_AI')
COUNTRIES = ('Japan', 'Taiwan')
APPLICATION_STATES = ('saved', 'applied', 'interview', 'offer', 'rejected', 'withdrawn')

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def load(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)

def config(root=ROOT):
    c = load(root / 'config.json')
    if not c or not isinstance(c.get('target_year'), int):
        raise ValueError('config.json: target_year must be an integer')
    if not c.get('countries') or not set(c['countries']) <= set(COUNTRIES):
        raise ValueError('countries must contain Japan and/or Taiwan')
    for key in ('max_detail_requests', 'max_search_queries', 'max_pages', 'timeout_seconds'):
        if not isinstance(c.get(key), int) or c[key] < 1:
            raise ValueError(f'{key} must be a positive integer')
    if not isinstance(c.get('request_delay_seconds'), (int, float)) or c['request_delay_seconds'] < 0:
        raise ValueError('request_delay_seconds must be nonnegative')
    return c

def env(root=ROOT):
    """Simple .env reader; existing environment wins; never execute shell code."""
    p = root / '.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            if re.fullmatch(r'[A-Z][A-Z0-9_]*', key.strip()):
                os.environ.setdefault(key.strip(), val.strip().strip('\"\''))

def canonical(url):
    u = urlsplit(url.strip())
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('Job URL must be a public HTTP(S) URL without credentials')
    # Retain job identity parameters such as gh_jid/jobId; remove tracking only.
    query = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in
             ('source', 'ref', 'referrer', 'jobsource', 'trackingid', 'hl', 'locale')]
    path = re.sub(r'^/(?:en-US|ja-JP|zh-TW)(?=/)', '', u.path, flags=re.I)
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), path.rstrip('/') or '/', urlencode(sorted(query)), ''))

def job_id(url):
    url = canonical(url)
    u = urlsplit(url)
    # Workday locale and alternate URL shapes resolve to the same requisition.
    req = re.search(r'_(JR[-\w]+|\d{5,}(?:-\d+)?)$', u.path, re.I)
    if 'myworkdayjobs.com' in u.hostname and req:
        key = u.hostname + ':' + req[1].lower()
    elif u.hostname.endswith('google.com') and re.search(r'/jobs/results/(\d+)', u.path):
        key = u.hostname + ':job:' + re.search(r'/jobs/results/(\d+)', u.path)[1]
    else:
        key = url
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def normalized(s):
    return unicodedata.normalize('NFKC', html.unescape(str(s or ''))).lower()

INTERN = r'\bintern(?:ship)?\b|\bco-?op\b|實習|实习|インターン'
ML = r'\b(?:ml|mle|ai|llm|nlp)\b|machine[ -]learning|deep[ -]learning|artificial intelligence|computer vision|data scien(?:ce|tist)|機械学習|深層学習|人工知能|機器學習|深度學習|人工智慧|大語言模型|自然語言|資料科學|データサイエンス|データサイエンティスト|自然言語|大規模言語|生成ai|ディープラーニング'
SWE = r'\b(?:swe|software|backend|back-end|frontend|front-end|full.?stack|devops|sre)\b|ソフトウェア|バックエンド|フロントエンド|フルスタック|webエンジニア|軟體|软件|程式|platform engineer|systems? engineer|web develop|cloud engineer'
SUMMER = r'\bsummer\b|暑期|暑假|夏季|サマー|夏期|夏の'
OTHER_SEASON = r'\b(?:winter|spring|fall|autumn)\b|寒假|寒期|冬季|春季|秋季|冬期'

def country_of(location):
    s = normalized(location)
    found = []
    if re.search(r'\bjapan\b|\bjp\b|\btokyo\b|\bosaka\b|\bkyoto\b|\bfukuoka\b|日本|東京|大阪|京都|福岡', s):
        found.append('Japan')
    if re.search(r'\btaiwan\b|\btw\b|\btaipei\b|\bhsinchu\b|\btaichung\b|\btainan\b|\bkaohsiung\b|台灣|台湾|臺灣|台北|臺北|新竹|台中|臺中|台南|高雄', s):
        found.append('Taiwan')
    return found[0] if len(found) == 1 else None

def schedule(title, description, target_year):
    """Ignore graduation/entry-year sentences. No inference from posting date."""
    title = normalized(title)
    # New graduate cohorts must not become summer-year evidence.
    cohort = r'new grad|graduat|入社|卒業|新卒|畢業|毕业|joiners'
    evidence = []
    if not re.search(cohort, title):
        evidence.append(title)
    for s in re.split(r'[\n.!?。；;]', normalized(description)):
        if re.search(SUMMER, s) and not re.search(cohort, s) and len(s) < 400:
            evidence.append(s)
    years = set()
    season = None
    for s in evidence:
        years.update(int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?!\d)', s))
        if re.search(SUMMER, s):
            season = 'summer'
        elif re.search(OTHER_SEASON, s) and season is None:
            season = 'other'
    year = next(iter(years)) if len(years) == 1 else None
    return year, season, evidence

def classify(job, c):
    title = normalized(job.get('title'))
    desc = normalized(job.get('description'))
    country = country_of(job.get('location', ''))
    category = 'MLE_AI' if re.search(ML, title) else 'SWE' if re.search(SWE, title) else None
    internship = bool(re.search(INTERN, title + ' ' + normalized(job.get('employment_type'))))
    year, season, evidence = schedule(title, desc, c['target_year'])
    reasons = []
    decision = 'review'
    if not internship:
        reasons.append('No explicit internship title/employment type')
        # Clearly full-time non-intern titles are out of scope.
        if re.search(r'full.?time|new grad|新卒|正職|senior|staff|principal', title + ' ' + normalized(job.get('employment_type'))):
            decision = 'rejected'
    if category is None:
        reasons.append('SWE / MLE-AI role unclear')
    if country is None:
        reasons.append('Workplace country missing, ambiguous or outside Japan/Taiwan')
        if job.get('location') and not any(country_of(x) for x in re.split(r'[;/]', job['location'])):
            # Keep unknown locations for human review instead of guessing.
            pass
    elif country not in c['countries']:
        reasons.append('Country excluded by config')
        decision = 'rejected'
    if year is None:
        reasons.append('Internship year not confirmed (entry/graduation year is ignored)')
    elif year != c['target_year']:
        reasons.append(f'Explicit internship year {year} is out of scope')
        decision = 'rejected'
    if season is None:
        reasons.append('Summer not explicitly confirmed')
    elif season != 'summer':
        reasons.append('Explicit off-season internship')
        decision = 'rejected'
    if not job.get('trusted_detail'):
        reasons.append('No structured job detail; verify page manually')
    if not reasons:
        decision = 'confirmed'
    flags = []
    if re.search(r'\brdss\b|研發替代役|研发替代役', title):
        flags.append('RDSS — verify military-service eligibility and duration')
    if re.search(r'\bph\.?d\b|博士', title):
        flags.append('PhD title — check eligibility')
    if re.search(r'japanese|日本語|jlpt', desc):
        flags.append('Japanese mentioned — check requirement')
    if re.search(r'visa|sponsor|work authori|就労|簽證|签证', desc):
        flags.append('Visa/work authorization mentioned — check requirement')
    return dict(country=country, category=category, internship=internship,
                year=year, season=season, decision=decision, reasons=reasons,
                evidence=evidence[:6], flags=flags)

def upsert(jobs, candidate, c):
    candidate = dict(candidate)
    candidate['url'] = canonical(candidate['url'])
    ident = job_id(candidate['url'])
    old = next((j for j in jobs if j['id'] == ident), None)
    created = old is None
    if old is None:
        old = {'id': ident, 'first_seen': now(), 'sources': [], 'status': 'unknown'}
        jobs.append(old)
    # Never erase fetched details with poorer community/search hints.
    for key in ('url', 'company', 'title', 'location', 'description', 'employment_type',
                'trusted_detail', 'posted_at', 'deadline', 'detail_method'):
        value = candidate.get(key)
        if value is not None and value != '' and (key != 'trusted_detail' or value or not old.get(key)):
            if key in ('title', 'location', 'description', 'company') and old.get('trusted_detail') and not candidate.get('trusted_detail'):
                continue
            old[key] = value
    source = candidate.get('source', 'manual')
    if source not in old['sources']:
        old['sources'].append(source)
    old['last_seen'] = now()
    if candidate.get('live'):
        old['last_checked'] = now()
        old['status'] = 'open'
        old['missing_count'] = 0
    old.update(classify(old, c))
    if old.get('manual_review'):
        r = old['manual_review']
        old.update({k: r[k] for k in ('decision', 'country', 'category', 'year', 'season') if k in r})
        old['reasons'] = [r['reason']]
    return old, created
