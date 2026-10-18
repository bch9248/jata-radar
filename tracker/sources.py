"""Workday, Greenhouse, Lever, community tables, and transient Brave discovery."""
import html
import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, urlencode, quote
from .core import normalized, INTERN, country_of, canonical, aggregator
from .network import FetchError

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.skip:
            self.skip -= 1
        if tag in ('p', 'div', 'li'):
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def text(raw):
    p = TextParser()
    p.feed(str(raw or ''))
    return re.sub(r'[ \t]+', ' ', ''.join(p.parts)).strip()

class PageParser(TextParser):
    def __init__(self):
        super().__init__()
        self.ld = []
        self.in_ld = False
        self.buffer = []
        self.title = []
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.in_ld = True
            self.buffer = []
        if tag == 'title':
            self.in_title = True
    def handle_endtag(self, tag):
        super().handle_endtag(tag)
        if tag == 'script' and self.in_ld:
            self.ld.append(''.join(self.buffer))
            self.in_ld = False
        if tag == 'title':
            self.in_title = False
    def handle_data(self, data):
        super().handle_data(data)
        if self.in_ld:
            self.buffer.append(data)
        if self.in_title:
            self.title.append(data)

def walk_ld(value):
    if isinstance(value, list):
        for x in value:
            yield from walk_ld(x)
    elif isinstance(value, dict):
        kind = value.get('@type', [])
        if kind == 'JobPosting' or isinstance(kind, list) and 'JobPosting' in kind:
            yield value
        for key in ('@graph', 'mainEntity'):
            yield from walk_ld(value.get(key))

def location_ld(loc):
    if isinstance(loc, list):
        return '; '.join(filter(None, (location_ld(x) for x in loc)))
    if not isinstance(loc, dict):
        return str(loc or '')
    a = loc.get('address', loc)
    if not isinstance(a, dict):
        return str(a)
    country = a.get('addressCountry', '')
    if isinstance(country, dict):
        country = country.get('name', '')
    return ', '.join(str(x) for x in (a.get('addressLocality'), a.get('addressRegion'), country) if x)

def employer_link(posting, page_url, c):
    """An aggregator's JSON-LD may point at the employer's own posting."""
    for key in ('url', 'sameAs'):
        value = posting.get(key)
        for link in value if isinstance(value, list) else [value]:
            try:
                link = canonical(urljoin(page_url, str(link))) if link else ''
            except ValueError:
                continue
            if link and urlsplit(link).hostname != urlsplit(page_url).hostname and not aggregator(link, c):
                return link
    return None

def parse_page(raw, candidate, c=None):
    p = PageParser()
    p.feed(raw)
    postings = []
    for chunk in p.ld:
        try:
            postings.extend(walk_ld(json.loads(chunk)))
        except json.JSONDecodeError:
            continue
    # A multi-job search page is not a job-detail page.
    if len(postings) == 1:
        j = postings[0]
        org = j.get('hiringOrganization') or {}
        out = dict(candidate, title=j.get('title', candidate.get('title', '')),
                   company=org.get('name', '') if isinstance(org, dict) else str(org),
                   location=location_ld(j.get('jobLocation')),
                   description=text(j.get('description')),
                   employment_type=str(j.get('employmentType', '')),
                   posted_at=j.get('datePosted'), deadline=j.get('validThrough'),
                   trusted_detail=True, detail_method='jsonld', live=True)
        if c and aggregator(candidate['url'], c):
            # Third-party copy of a posting: keep its fields as hints only.
            out.update(trusted_detail=False, detail_method='jsonld-aggregator')
            link = employer_link(j, candidate['url'], c)
            if link:
                out['employer_url'] = link
        return out
    # A listing's own title beats the page <title>, which carries site suffixes ("… | Dreamwork").
    return dict(candidate, title=candidate.get('title') or ''.join(p.title).strip() or 'Unverified listing',
                description=text(raw)[:18000], trusted_detail=False, detail_method='html', live=True)

def workday_parts(url):
    u = urlsplit(url)
    parts = [p for p in u.path.split('/') if p]
    parts = [p for p in parts if not re.fullmatch(r'[a-z]{2}-[A-Z]{2}', p)]
    if not u.hostname or not u.hostname.endswith('.myworkdayjobs.com') or not parts:
        raise ValueError('Expected tenant.myworkdayjobs.com/Board URL')
    origin = f'{u.scheme}://{u.netloc}'
    return origin, u.hostname.split('.')[0], parts[0], parts[1:]

def detail(client, candidate, c=None):
    u = urlsplit(candidate['url'])
    if u.hostname and u.hostname.endswith('.myworkdayjobs.com'):
        origin, tenant, board, tail = workday_parts(candidate['url'])
        if not tail or tail[0] != 'job':
            raise FetchError('Not a Workday job detail URL')
        info = client.json(f'{origin}/wday/cxs/{tenant}/{board}/' + '/'.join(tail)).get('jobPostingInfo')
        if not isinstance(info, dict) or not info.get('title'):
            raise FetchError('Missing Workday jobPostingInfo')
        return dict(candidate, title=info['title'], description=text(info.get('jobDescription')),
                    location='; '.join(str(x) for x in [info.get('location'), *(info.get('additionalLocations') or [])] if x),
                    trusted_detail=True, detail_method='workday', live=True,
                    posted_at=info.get('startDate'), employment_type=info.get('timeType') or '')
    return parse_page(client.request(candidate['url'], robots=True), candidate, c)

def collect_workday(client, source, c):
    origin, tenant, board, _ = workday_parts(source['url'])
    result = []
    truncated = False
    for search in source.get('search_terms', ['intern']):
        total = None
        for page in range(c['max_pages']):
            d = client.json(f'{origin}/wday/cxs/{tenant}/{board}/jobs',
                            {'appliedFacets': {}, 'limit': 20, 'offset': page * 20, 'searchText': search})
            if not isinstance(d.get('jobPostings'), list):
                raise FetchError('Workday response lacks jobPostings')
            rows = d['jobPostings']
            # Workday reports the real total only on the first page; later pages say 0.
            if total is None:
                total = d.get('total') if isinstance(d.get('total'), int) else None
            for j in rows:
                if not j.get('externalPath') or not re.search(INTERN, normalized(j.get('title'))):
                    continue
                loc = j.get('locationsText') or ''
                # Multiple locations may include the target; keep unknown too.
                if loc and not country_of(loc) and not re.search(r'\d+ locations', loc, re.I):
                    continue
                result.append(dict(title=j['title'], location=loc, company=source['company'],
                                   url=f'{origin}/{board}{j["externalPath"]}', source=source['id']))
            if len(rows) < 20 or total is not None and (page + 1) * 20 >= total:
                break
        else:
            truncated = True
    return result, truncated

def collect_greenhouse(client, source, c):
    d = client.json(f'https://boards-api.greenhouse.io/v1/boards/{quote(source["board"], safe="")}/jobs?content=true')
    if not isinstance(d.get('jobs'), list):
        raise FetchError('Greenhouse response lacks jobs')
    return [dict(title=j['title'], location=(j.get('location') or {}).get('name') or '',
                 company=source['company'], url=j['absolute_url'], source=source['id'],
                 description=text(j.get('content')), trusted_detail=True, live=True,
                 detail_method='greenhouse') for j in d['jobs']
            if re.search(INTERN, normalized(j.get('title')))], False

def collect_lever(client, source, c):
    rows = client.json(f'https://api.lever.co/v0/postings/{quote(source["board"], safe="")}?mode=json')
    if not isinstance(rows, list):
        raise FetchError('Lever response is not a list')
    out = []
    for j in rows:
        cat = j.get('categories') or {}
        commitment = cat.get('commitment') or ''
        if re.search(INTERN, normalized((j.get('text') or '') + ' ' + commitment)):
            description = text(j.get('description')) + '\n' + '\n'.join(text(x.get('content')) for x in j.get('lists') or [] if isinstance(x, dict))
            out.append(dict(title=j['text'], location=cat.get('location') or '', company=source['company'],
                            url=j['hostedUrl'], source=source['id'], description=description,
                            employment_type=commitment, trusted_detail=True,
                            live=True, detail_method='lever'))
    return out, False

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th') and self.row is not None:
            self.cell = ['', []]
        if tag == 'a' and self.cell is not None:
            href = dict(attrs).get('href')
            if href:
                self.cell[1].append(href)
    def handle_data(self, data):
        if self.cell is not None:
            self.cell[0] += data
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None

def parse_community(raw, source):
    rows = []
    p = TableParser()
    p.feed(raw)
    rows.extend(p.rows)
    for line in raw.splitlines():
        if line.strip().startswith('|'):
            cells = re.split(r'(?<!\\)\|', line.strip().strip('|'))
            rows.append([[text(re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cell)),
                          re.findall(r'\]\((https?://[^)]+)\)', cell) + re.findall(r'href=[\"\'](https?://[^\"\']+)', cell)] for cell in cells])
    headers = None
    last_company = ''
    out = []
    for row in rows:
        labels = [normalized(x[0]) for x in row]
        if any('company' in x for x in labels) and any('role' in x or 'position' in x or 'title' in x for x in labels):
            headers = {name: next((i for i, v in enumerate(labels) if any(x in v for x in aliases)), None)
                       for name, aliases in {'company': ['company'], 'title': ['role', 'position', 'title'],
                                             'location': ['location'], 'url': ['application', 'apply', 'link', 'posting']}.items()}
            if headers['url'] is None:
                headers['url'] = headers['title']
            continue
        if not headers or headers['url'] is None or max(i for i in headers.values() if i is not None) >= len(row):
            continue
        def field(name):
            return row[headers[name]][0].strip() if headers[name] is not None else ''
        company = field('company').strip('* ')
        if company in ('↳', '↪', ''):
            company = last_company
        else:
            last_company = company
        title, location = field('title'), field('location')
        if not country_of(location):
            continue
        links = row[headers['url']][1]
        if links:
            out.append(dict(company=company, title=title, location=location,
                            url=html.unescape(links[0]), source=source['id'], trusted_detail=False))
    if headers is None:
        raise FetchError('Community table schema not recognized; check source URL/layout')
    return out

def collect_community(client, source, c):
    return parse_community(client.request(source['url']), source), False

COLLECTORS = {'workday': collect_workday, 'greenhouse': collect_greenhouse,
              'lever': collect_lever, 'community': collect_community}

def search_candidates(client, queries, c, cursor):
    key = os.environ.get('BRAVE_API_KEY')
    if not key:
        return [], [], cursor
    out, report = [], []
    count = min(c['max_search_queries'], len(queries))
    for offset in range(count):
        q = queries[(cursor + offset) % len(queries)]
        query = q['query'].replace('{year}', str(c['target_year']))
        try:
            d = client.json('https://api.search.brave.com/res/v1/web/search?' + urlencode(
                {'q': query, 'count': min(20, c.get('search_results_per_query', 10)), 'country': q['country_code']}),
                headers={'X-Subscription-Token': key})
            found = 0
            # Discard search titles and snippets: only navigate to result URLs.
            for item in d.get('web', {}).get('results', []):
                url = item.get('url', '')
                if not likely_job_url(url):
                    continue
                out.append({'url': url, 'source': 'search:' + q['id']})
                found += 1
            report.append({'id': q['id'], 'status': 'ok', 'candidates': found})
        except (FetchError, ValueError) as e:
            report.append({'id': q['id'], 'status': 'error', 'error': str(e)})
    return out, report, (cursor + count) % max(1, len(queries))

def likely_job_url(url):
    try:
        u = urlsplit(canonical(url))
    except ValueError:
        return False
    if u.hostname.endswith('.myworkdayjobs.com'):
        return '/job/' in u.path
    if u.hostname == 'www.104.com.tw':
        return bool(re.fullmatch(r'/job/[a-zA-Z0-9]+', u.path))
    if u.hostname.endswith('cake.me'):
        return bool(re.search(r'/companies/[^/]+/jobs/[^/]+', u.path))
    if u.hostname.endswith('yourator.co'):
        return bool(re.search(r'/companies/[^/]+/jobs/[^/]+', u.path))
    return bool(re.search(r'/jobs/(?:results/)?[^/]+|/job/[^/]+|/recruit/[^/]+|/projects/\d+|/internship', u.path))
