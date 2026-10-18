"""Bounded HTTPS requests, public-address guard, robots-aware page fetching."""
import ipaddress
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
from .core import canonical

class FetchError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def public_url(url):
    canonical(url)
    u = urlsplit(url)
    if u.port not in (None, 80, 443):
        raise FetchError('Nonstandard URL port is not allowed')
    try:
        addresses = socket.getaddrinfo(u.hostname, u.port or 443, type=socket.SOCK_STREAM)
    except OSError as e:
        raise FetchError('DNS resolution failed') from e
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise FetchError('Private/local address is not allowed')

def api_detail(error, headers):
    """A JSON API's short error message (e.g. which parameter failed validation).
    HTML error pages are skipped; credential values are masked if echoed back."""
    if 'json' not in (error.headers.get('Content-Type') or ''):
        return ''
    try:
        detail = ' '.join(error.read(600).decode('utf-8', errors='replace').split())
    except (OSError, AttributeError):
        return ''
    for value in (headers or {}).values():
        if len(value) >= 8:
            detail = detail.replace(value, '***')
    return f': {detail[:240]}' if detail else ''

class Client:
    def __init__(self, c):
        self.c = c
        self.opener = build_opener(NoRedirect())
        self.last = {}
        self.robots = {}
        self.requests = 0

    def request(self, url, payload=None, headers=None, *, robots=False, redirects=0):
        public_url(url)
        host = urlsplit(url).netloc
        if robots:
            self.allowed(url)
        delay = self.c['request_delay_seconds']
        if robots and host in self.robots:
            delay = max(delay, self.robots[host].crawl_delay('InternRadar') or 0)
        wait = delay - (time.monotonic() - self.last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        base = {'User-Agent': 'InternRadar/1.0 (personal internship tracker)', 'Accept': 'application/json, text/html;q=0.9, */*;q=0.8'}
        base.update(headers or {})
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            base['Content-Type'] = 'application/json'
        for attempt in range(3):
            self.last[host] = time.monotonic()
            self.requests += 1
            try:
                with self.opener.open(Request(url, data=data, headers=base), timeout=self.c['timeout_seconds']) as response:
                    raw = response.read(4 * 1024 * 1024 + 1)
                    if len(raw) > 4 * 1024 * 1024:
                        raise FetchError('Response exceeds 4 MiB limit')
                    return raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
            except HTTPError as e:
                if e.code in (301, 302, 303, 307, 308) and e.headers.get('Location'):
                    if redirects >= 4:
                        raise FetchError('Too many redirects', e.code) from e
                    from urllib.parse import urljoin
                    target = urljoin(url, e.headers['Location'])
                    # Credentials are never forwarded to redirected hosts.
                    if headers and any(k.lower() in ('authorization', 'x-subscription-token') for k in headers):
                        raise FetchError('Authenticated API redirect refused', e.code) from e
                    return self.request(target, payload if e.code in (307, 308) else None,
                                        headers, robots=robots, redirects=redirects + 1)
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(min(8, 2 ** (attempt + 1)))
                    continue
                raise FetchError(f'HTTP {e.code}' + api_detail(e, headers), e.code) from e
            except (URLError, TimeoutError, OSError) as e:
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise FetchError(f'Connection failed: {type(e).__name__}') from e

    def json(self, url, payload=None, headers=None):
        try:
            return json.loads(self.request(url, payload, headers))
        except json.JSONDecodeError as e:
            raise FetchError('Expected JSON; received HTML or invalid JSON') from e

    def allowed(self, url):
        u = urlsplit(url)
        if u.netloc not in self.robots:
            p = RobotFileParser()
            try:
                p.parse(self.request(f'{u.scheme}://{u.netloc}/robots.txt').splitlines())
            except FetchError as e:
                if e.status in (404, 410):
                    p.parse([])
                else:
                    # Unknown robot policy: hold for human review.
                    raise FetchError('robots.txt unavailable; page fetch skipped') from e
            self.robots[u.netloc] = p
        if not self.robots[u.netloc].can_fetch('InternRadar', url):
            raise FetchError('robots.txt disallows page fetching')
