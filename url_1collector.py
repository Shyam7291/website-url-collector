#!/usr/bin/env python3
"""Website page collector - finds pages that expose documents (PDF/Office).

Enhanced build. Design contract kept from v1: the crawl is *provably bounded*.
Every loop below is guarded by an explicit ceiling AND a visited/signature set,
so no code path can spin forever. What changed is that the same bounded budget
is now spent far more intelligently (see CHANGELOG at the bottom of this file).
"""
from __future__ import annotations

import argparse, asyncio, csv, hashlib, json, logging, os, re, signal, sqlite3, sys, time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from playwright.async_api import async_playwright, Error as PWError, TimeoutError as PWTimeout

# --------------------------------------------------------------------------- #
# Static vocabularies
# --------------------------------------------------------------------------- #
DOC_EXT = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf', '.odt', '.ods', '.odp'}
ASSET_EXT = {'.css', '.js', '.mjs', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.avif', '.ico',
             '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.webm', '.mp3', '.wav', '.zip', '.rar', '.7z',
             '.gz', '.tar', '.dmg', '.exe', '.map'}
DOC_MIME = ('application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument',
            'application/vnd.oasis.opendocument', 'application/vnd.ms-excel',
            'application/vnd.ms-powerpoint', 'application/rtf', 'application/octet-stream')
DOC_HINT = re.compile(
    r'(?:\.(?:pdf|docx?|xlsx?|pptx?|rtf|od[tsp])(?:$|[?#])'
    r'|/(?:downloads?|documents?|files?|uploads?|storage|assets?/docs?|media/docs?|attachments?)(?:/|$)'
    r'|\.ashx(?:$|[?#])|/getfile|/download\.aspx|/viewdocument)', re.I)
# PDF.js / generic embedded-viewer wrappers: ...viewer.html?file=/x.pdf
VIEWER_PARAMS = ('file', 'url', 'src', 'document', 'doc', 'pdf', 'href')
UNSAFE = re.compile(r'/(?:logout|log-out|login|log-in|signin|sign-in|signup|sign-up|register|cart|'
                    r'checkout|basket|my-?account|wp-admin|wp-login|admin|search|share|print)(?:/|$)', re.I)
PKEYS = {'page', 'p', 'paged', 'offset', 'start', 'pagenum', 'pagenumber', 'pg', 'from', 'skip'}
NEXT = re.compile(r'^(?:next|next page|older|older posts?|more|forward|\d{1,4}|page\s*\d{1,4})\s*'
                  r'(?:›|»|→|>|>>)?$', re.I)
NEXT_SYMBOL = re.compile(r'^(?:›|»|→|>|>>|next\s*[›»→>]*)$', re.I)
LOAD = re.compile(r'\b(?:load|show|view|see)\s+(?:\d+\s+)?more\b', re.I)
COOKIE = re.compile(r'^(?:accept(?: all| cookies| all cookies)?|allow all|i agree|agree|ok|got it|'
                    r'understood|continue|dismiss|close|reject all|only necessary)$', re.I)
REVEAL = re.compile(r'\b(?:menu|navigation|nav|accordion|expand|show|reports?|publications?|documents?|'
                    r'resources?|downloads?|archive|library|view all|see all|all years?)\b', re.I)
YEAR = re.compile(r'^(19|20)\d{2}$')

# Vocabulary syntax:  "foo" = exact token match, "foo*" = token prefix match,
# "foo-bar" = consecutive token phrase. This replaces v1 substring matching, which
# misclassified corporate-accountability / our-footprint / photovoltaic and
# false-promoted grid / agriculture.
ESG_STRONG = (
    'esg', 'sustainab*', 'environment*', 'climate', 'climate-change', 'carbon', 'carbon-footprint',
    'footprint', 'emission*', 'ghg', 'greenhouse-gas', 'net-zero', 'netzero', 'decarbon*', 'renewable*',
    'photovoltaic', 'solar', 'wind-power', 'energy-efficiency', 'energy-transition', 'water',
    'water-stewardship', 'waste', 'zero-waste', 'recycl*', 'circular-economy', 'circularity',
    'biodiversity', 'nature', 'natural-capital', 'deforestation', 'pollution', 'social-impact',
    'social-responsibility', 'corporate-responsibility', 'corporate-accountability', 'accountability',
    'csr', 'community', 'community-investment', 'human-right*', 'labor-right*', 'labour-right*',
    'modern-slavery', 'responsible-sourcing', 'responsible-supply-chain', 'supplier-code',
    'supply-chain-standard*', 'diversity', 'inclusion', 'equity', 'dei', 'health-and-safety',
    'occupational-health', 'employee-wellbeing', 'wellbeing', 'governance', 'ethics', 'ethical',
    'compliance', 'code-of-conduct', 'business-conduct', 'anti-corruption', 'anti-bribery',
    'whistleblower', 'whistleblowing', 'risk-management', 'stakeholder*', 'materiality',
    'integrated-report*', 'sustainability-report*', 'responsibility-report*', 'annual-report*',
    'impact-report*', 'tcfd', 'tnfd', 'sasb', 'gri', 'cdp', 'csrd', 'sfdr', 'issb', 'sdg', 'sdgs',
    'taxonomy', 'scope-1', 'scope-2', 'scope-3', 'transition-plan', 'charter', 'disclosure*',
)
ESG_GATEWAY = (
    'about', 'about-us', 'who-we-are', 'company', 'corporate', 'our-approach', 'our-commitment*',
    'responsibility', 'policy', 'policies', 'committee', 'committees', 'board', 'leadership',
    'resource', 'resources', 'report', 'reports', 'reporting', 'publication*', 'document*',
    'download*', 'library', 'archive', 'centre', 'center', 'hub', 'investor*', 'esg-data',
)
# Pages that reliably contain no ESG documents. Exact tokens unless starred.
NEGATIVE = (
    'earning*', 'quarterly-result*', 'financial-result*', 'sec-filing*', 'edgar', '10-k', '10-q',
    '8-k', '20-f', '6-k', 'proxy', 'proxy-statement', 'stock-info', 'stock-quote', 'share-price',
    'shareprice', 'dividend*', 'analyst-coverage', 'credit-rating*', 'debt-information',
    'bond-information', 'investor-presentation*', 'webcast*', 'transcript*', 'news', 'newsroom',
    'news-release*', 'press', 'press-release*', 'press-room', 'media-release*', 'media-centre',
    'media-center', 'event', 'events', 'calendar', 'conference*', 'webinar*', 'podcast*', 'stories',
    'story', 'article', 'articles', 'blog', 'blogs', 'insight', 'insights', 'contact', 'contact-us',
    'email-alert*', 'subscribe', 'subscription*', 'newsletter*', 'customer-support', 'support',
    'help', 'faq', 'faqs', 'request-information', 'request-a-demo', 'demo', 'photo', 'photos',
    'photography', 'image', 'images', 'gallery', 'galleries', 'video', 'videos', 'multimedia',
    'audio', 'youtube', 'vimeo', 'career', 'careers', 'job', 'jobs', 'vacancies', 'recruitment',
    'location', 'locations', 'dealer*', 'store', 'stores', 'shop', 'cart', 'checkout', 'login',
    'logout', 'signin', 'signup', 'register', 'account', 'my-account', 'profile', 'search',
    'share', 'print', 'privacy', 'privacy-policy', 'cookie', 'cookies', 'terms',
    'terms-of-use', 'legal', 'disclaimer', 'accessibility', 'sitemap', 'rss', 'feed',
)
# Path tokens that strongly imply "this page lists documents".
DOC_HUB = ('report', 'reports', 'reporting', 'publication*', 'document*', 'download*', 'library',
           'archive', 'resource', 'resources', 'disclosure*', 'filing*', 'policy', 'policies',
           'data-centre', 'data-center', 'esg-data')


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ext(url: str) -> str:
    name = urlsplit(url).path.rsplit('/', 1)[-1].lower()
    return '.' + name.rsplit('.', 1)[-1] if '.' in name else ''


def env(name, default, typ):
    v = os.getenv(name)
    if v in (None, ''):
        return default
    if typ is bool:
        return v.lower() in ('1', 'true', 'yes', 'on')
    try:
        return typ(v)
    except (TypeError, ValueError):
        logging.warning('Ignoring invalid %s=%r', name, v)
        return default


def canon(value: str) -> list:
    """Lowercase and split into alphanumeric tokens. 'Our_Footprint/2024' -> ['our','footprint','2024']"""
    return [t for t in re.split(r'[^a-z0-9]+', (value or '').lower()) if t]


def compile_vocab(entries) -> tuple:
    """-> (exact set, prefix tuple, phrase tuple). See vocabulary syntax note above."""
    exact, prefixes, phrases = set(), [], []
    for raw in entries:
        star = raw.endswith('*')
        item = raw[:-1] if star else raw
        toks = canon(item)
        if not toks:
            continue
        if len(toks) > 1:
            phrases.append((tuple(toks), star))
        elif star:
            prefixes.append(toks[0])
        else:
            exact.add(toks[0])
    return exact, tuple(prefixes), tuple(phrases)


def match_vocab(tokens, compiled) -> bool:
    exact, prefixes, phrases = compiled
    tset = set(tokens)
    if tset & exact:
        return True
    for t in tokens:
        for pre in prefixes:
            if t.startswith(pre):
                return True
    n = len(tokens)
    for phrase, star in phrases:
        m = len(phrase)
        for i in range(n - m + 1):
            window = tokens[i:i + m]
            if window[:-1] == list(phrase[:-1]) and (
                    window[-1].startswith(phrase[-1]) if star else window[-1] == phrase[-1]):
                return True
    return False


V_STRONG = compile_vocab(ESG_STRONG)
V_GATEWAY = compile_vocab(ESG_GATEWAY)
V_NEGATIVE = compile_vocab(NEGATIVE)
V_DOC_HUB = compile_vocab(DOC_HUB)


def slugify(value: str, limit: int = 60) -> str:
    return re.sub(r'[^a-z0-9]+', '_', (value or '').lower()).strip('_')[:limit] or 'site'


def output_dir_for(seed: str, root: Path) -> Path:
    """Per-seed directory. Includes netloc *and* path plus a hash, so
    http://127.0.0.1:8899/a and http://127.0.0.1:8898/b never collide."""
    p = urlsplit(seed)
    key = slugify((p.netloc or '') + (p.path or ''))
    digest = hashlib.sha1(seed.encode('utf-8', 'ignore')).hexdigest()[:8]
    return root / f'{key}_{digest}'


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    # ---- bounded expansion ----
    max_pagination_pages: int = 12          # real ceiling for the pagination loop (was amputated at 2)
    max_load_more_clicks: int = 5
    max_year_options: int = 4               # now actually drives year-dropdown switching
    max_depth: int = 12
    max_pages_per_website: int = 3000
    max_documents_per_page: int = 50        # was hard-coded 1
    # ---- timing ----
    page_timeout_seconds: int = 45
    delay_between_pages_seconds: float = 0.35
    max_retries: int = 2
    max_runtime_minutes: int = 170
    stabilization_seconds: float = 0.6
    document_head_timeout_seconds: int = 4
    page_attempt_timeout_seconds: int = 75
    page_close_timeout_seconds: int = 5
    # ---- scope ----
    crawl_subdomains: bool = True
    restrict_to_seed_language: bool = True
    allowed_hosts: tuple = ()
    # ---- budgets ----
    max_new_children_per_page: int = 40
    max_homepage_children: int = 100
    max_pages_per_url_family: int = 25
    max_query_variants_per_path: int = 3
    follow_same_family_links_from_detail_pages: bool = False
    prioritize_document_likely_pages: bool = True   # now actually promotes doc hubs
    # ---- query handling ----
    query_parameter_mode: str = 'whitelist'         # 'whitelist' | 'blacklist'
    keep_meaningful_query_parameters: tuple = (
        'year', 'page', 'paged', 'p', 'offset', 'start', 'category', 'cat', 'type', 'section',
        'topic', 'tag', 'id', 'doc', 'document', 'file', 'lang', 'locale', 'sort', 'view', 'q')
    remove_query_parameters: tuple = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_term',
                                      'utm_content', 'fbclid', 'gclid', 'msclkid', 'mc_cid',
                                      'mc_eid', 'ref', 'referrer', '_ga')
    # ---- robots / sitemap ----
    respect_robots_txt: bool = True
    use_sitemap: bool = True
    max_sitemaps: int = 25
    max_sitemap_urls: int = 5000
    # ---- runtime ----
    concurrency: int = 4                    # was single-threaded
    block_heavy_resources: bool = True
    export_checkpoint_pages: int = 25
    recover_orphaned_pages: bool = True     # requeue PROCESSING rows after a crash
    user_agent: str = 'Mozilla/5.0 (compatible; WebsiteURLCollector/2.0)'
    robots_agent: str = 'websiteurlcollector'

    @classmethod
    def load(cls, path):
        raw = {}
        if path and Path(path).exists():
            try:
                raw = json.loads(Path(path).read_text(encoding='utf-8')) or {}
            except (OSError, ValueError) as exc:
                logging.warning('Config %s unreadable (%s); using defaults', path, exc)
                raw = {}
        defaults = cls()
        names = {f.name for f in fields(cls)}
        for k in list(raw):
            if k not in names:
                logging.warning('Ignoring unknown config key %r', k)
                raw.pop(k)
            elif isinstance(getattr(defaults, k), tuple):
                raw[k] = tuple(raw[k])
        c = cls(**raw)
        mapping = {
            'max_pagination_pages': ('MAX_PAGINATION_PAGES', int),
            'max_load_more_clicks': ('MAX_LOAD_MORE_CLICKS', int),
            'max_year_options': ('MAX_YEAR_OPTIONS', int),
            'max_depth': ('MAX_DEPTH', int),
            'max_pages_per_website': ('MAX_PAGES', int),
            'max_documents_per_page': ('MAX_DOCUMENTS_PER_PAGE', int),
            'page_timeout_seconds': ('PAGE_TIMEOUT_SECONDS', int),
            'delay_between_pages_seconds': ('DELAY_BETWEEN_PAGES_SECONDS', float),
            'max_retries': ('MAX_RETRIES', int),
            'max_runtime_minutes': ('MAX_RUNTIME_MINUTES', int),
            'stabilization_seconds': ('STABILIZATION_SECONDS', float),
            'document_head_timeout_seconds': ('DOCUMENT_HEAD_TIMEOUT_SECONDS', int),
            'page_attempt_timeout_seconds': ('PAGE_ATTEMPT_TIMEOUT_SECONDS', int),
            'page_close_timeout_seconds': ('PAGE_CLOSE_TIMEOUT_SECONDS', int),
            'crawl_subdomains': ('CRAWL_SUBDOMAINS', bool),
            'restrict_to_seed_language': ('RESTRICT_TO_SEED_LANGUAGE', bool),
            'max_new_children_per_page': ('MAX_NEW_CHILDREN_PER_PAGE', int),
            'max_homepage_children': ('MAX_HOMEPAGE_CHILDREN', int),
            'max_pages_per_url_family': ('MAX_PAGES_PER_URL_FAMILY', int),
            'max_query_variants_per_path': ('MAX_QUERY_VARIANTS_PER_PATH', int),
            'follow_same_family_links_from_detail_pages': ('FOLLOW_SAME_FAMILY_LINKS_FROM_DETAIL_PAGES', bool),
            'prioritize_document_likely_pages': ('PRIORITIZE_DOCUMENT_LIKELY_PAGES', bool),
            'query_parameter_mode': ('QUERY_PARAMETER_MODE', str),
            'respect_robots_txt': ('RESPECT_ROBOTS_TXT', bool),
            'use_sitemap': ('USE_SITEMAP', bool),
            'max_sitemaps': ('MAX_SITEMAPS', int),
            'max_sitemap_urls': ('MAX_SITEMAP_URLS', int),
            'concurrency': ('CONCURRENCY', int),
            'block_heavy_resources': ('BLOCK_HEAVY_RESOURCES', bool),
            'export_checkpoint_pages': ('EXPORT_CHECKPOINT_PAGES', int),
            'recover_orphaned_pages': ('RECOVER_ORPHANED_PAGES', bool),
            'user_agent': ('USER_AGENT', str),
        }
        for attr, (name, typ) in mapping.items():
            setattr(c, attr, env(name, getattr(c, attr), typ))
        # Clamps - every ceiling must stay >= 1 so loops remain bounded and non-empty.
        c.max_pagination_pages = max(1, c.max_pagination_pages)
        c.max_load_more_clicks = max(0, c.max_load_more_clicks)
        c.max_year_options = max(0, c.max_year_options)
        c.max_documents_per_page = max(1, c.max_documents_per_page)
        c.concurrency = max(1, min(16, c.concurrency))
        c.max_depth = max(0, c.max_depth)
        c.max_pages_per_website = max(1, c.max_pages_per_website)
        if c.query_parameter_mode not in ('whitelist', 'blacklist'):
            c.query_parameter_mode = 'whitelist'
        return c


# --------------------------------------------------------------------------- #
# robots.txt
# --------------------------------------------------------------------------- #
class Robots:
    """Minimal but correct robots.txt evaluator: longest-match wins, allow beats
    disallow on equal length, wildcards and $ supported, Sitemap: collected."""

    def __init__(self, agent: str = 'websiteurlcollector'):
        self.agent = agent.lower()
        self.rules = []          # (allow: bool, compiled regex, specificity: int)
        self.sitemaps = []
        self.loaded = False

    @staticmethod
    def _rx(pattern: str):
        out = ''
        for ch in pattern:
            if ch == '*':
                out += '.*'
            elif ch == '$':
                out += '$'
            else:
                out += re.escape(ch)
        return re.compile('^' + out)

    def parse(self, text: str) -> 'Robots':
        groups, current, expect_agent = {}, [], True
        for raw in (text or '').splitlines():
            line = raw.split('#', 1)[0].strip()
            if not line or ':' not in line:
                continue
            key, value = line.split(':', 1)
            key, value = key.strip().lower(), value.strip()
            if key == 'sitemap':
                if value:
                    self.sitemaps.append(value)
                continue
            if key == 'user-agent':
                if not expect_agent:
                    current, expect_agent = [], True
                if value:
                    current.append(value.lower())
                    groups.setdefault(value.lower(), [])
                continue
            if key in ('allow', 'disallow') and current:
                expect_agent = False
                if not value:            # "Disallow:" with empty value == allow all
                    continue
                for name in current:
                    groups[name].append((key == 'allow', value))
        for name in (self.agent, '*'):
            if name in groups:
                self.rules = [(allow, self._rx(path), len(path)) for allow, path in groups[name]]
                break
        self.loaded = True
        return self

    def allowed(self, url: str) -> bool:
        if not self.rules:
            return True
        p = urlsplit(url)
        target = (p.path or '/') + (('?' + p.query) if p.query else '')
        best = None
        for allow, rx, length in self.rules:
            if rx.match(target) and (best is None or length > best[1] or (length == best[1] and allow)):
                best = (allow, length)
        return True if best is None else best[0]


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #
class Collector:
    def __init__(self, seed, cfg: Config, out_root: Path = None):
        self.cfg = cfg
        self.seed = self.norm_seed(seed)
        self.host = (urlsplit(self.seed).hostname or '').lower()
        parts = self.host.split('.')
        self.base = '.'.join(parts[-2:]) if len(parts) > 1 else self.host
        seed_path = urlsplit(self.seed).path or '/'
        m = re.match(r'^/([a-z]{2}(?:-[a-z]{2})?)(?:/|$)', seed_path, re.I)
        self.language_prefix = ('/' + m.group(1).lower() + '/') if m else None

        self.out = output_dir_for(self.seed, out_root or Path('.'))
        self.out.mkdir(parents=True, exist_ok=True)

        self.processed_since_export = 0
        self.document_cache = {}
        self.robots = Robots(cfg.robots_agent)
        self.started = time.monotonic()
        self.stop = False
        self.page_limit = False
        self.runtime_limit = False
        self.run_delay_seconds = 0.0
        self.run_export_seconds = 0.0
        self.expansion = dict(parent_budget=0, family_limit=0, query_limit=0, same_family=0,
                              after_page_limit=0, negative=0, esg_priority=0, robots_blocked=0,
                              sitemap_seeded=0, orphans_recovered=0)
        self.stats = dict(duplicates=0, pagination_detected=0, pagination_limits=0, pagination_states=0,
                          load_more=0, year_switches=0, max_depth=0, documents=0)
        self._lock = asyncio.Lock()          # guards DB writes + claim across workers

        # isolation_level=None -> autocommit; makes explicit BEGIN IMMEDIATE legal,
        # which is what the atomic claim below needs.
        self.db = sqlite3.connect(self.out / 'crawler.db', timeout=30, isolation_level=None,
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.init_db()

    # ---------------- URL normalization ----------------
    def norm_seed(self, u):
        u = (u or '').strip()
        u = u if re.match(r'^https?://', u, re.I) else 'https://' + u
        p = urlsplit(u)
        if not p.hostname:
            raise ValueError(f'Valid website URL required, got {u!r}')
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))

    def norm(self, u, base=None, parent_view=False):
        """Canonical form. parent_view=True additionally strips pagination keys so a
        page-2 URL collapses onto its parent (used for pagination detection)."""
        try:
            p = urlsplit(urljoin(base or self.seed, (u or '').strip()))
            if p.scheme.lower() not in ('http', 'https') or not p.hostname:
                return None
            scheme = p.scheme.lower()
            host = p.hostname.lower().rstrip('.')
            port = p.port
            net = host if port is None or (scheme == 'http' and port == 80) or \
                (scheme == 'https' and port == 443) else f'{host}:{port}'
            path = re.sub('/+', '/', p.path or '/')
            tail = path.rsplit('/', 1)[-1]
            if path != '/' and not path.endswith('/') and '.' not in tail:
                path += '/'
            remove = {x.lower() for x in self.cfg.remove_query_parameters}
            keep = {x.lower() for x in self.cfg.keep_meaningful_query_parameters}
            q = []
            for k, v in parse_qsl(p.query, keep_blank_values=True):
                kl = k.lower()
                if kl in remove or kl.startswith('utm_'):
                    continue
                if parent_view and kl in PKEYS:
                    continue
                if self.cfg.query_parameter_mode == 'whitelist' and keep and kl not in keep:
                    continue
                q.append((k, v))
            q.sort(key=lambda x: (x[0].lower(), x[1]))
            return urlunsplit((scheme, net, path, urlencode(q, doseq=True), ''))
        except (ValueError, UnicodeError):
            return None

    def internal(self, u):
        h = (urlsplit(u).hostname or '').lower()
        allowed = {x.lower() for x in self.cfg.allowed_hosts}
        return h in allowed or h == self.host or (
            self.cfg.crawl_subdomains and (h == self.base or h.endswith('.' + self.base)))

    def doclike(self, u):
        if ext(u) in DOC_EXT or DOC_HINT.search(u or ''):
            return True
        # PDF.js / embedded viewer wrappers: viewer.html?file=/reports/x.pdf
        for k, v in parse_qsl(urlsplit(u or '').query, keep_blank_values=True):
            if k.lower() in VIEWER_PARAMS and v and (ext(v) in DOC_EXT or DOC_HINT.search(v)):
                return True
        return False

    def viewer_target(self, u):
        """If u is an embedded-viewer wrapper, return the real document URL."""
        for k, v in parse_qsl(urlsplit(u or '').query, keep_blank_values=True):
            if k.lower() in VIEWER_PARAMS and v and (ext(v) in DOC_EXT or DOC_HINT.search(v)):
                return urljoin(u, v)
        return None

    def policy(self, u):
        if not self.internal(u):
            return False, 'external'
        path = (urlsplit(u).path or '/').lower()
        if self.cfg.restrict_to_seed_language and self.language_prefix and \
                not path.startswith(self.language_prefix) and path != '/':
            return False, 'outside seed language path ' + self.language_prefix
        if ext(u) in ASSET_EXT:
            return False, 'static asset'
        if self.doclike(u):
            return False, 'document'
        if UNSAFE.search(urlsplit(u).path or ''):
            return False, 'unsafe route'
        if self.cfg.respect_robots_txt and self.robots.loaded and not self.robots.allowed(u):
            return False, 'blocked by robots.txt'
        return True, ''

    # ---------------- schema ----------------
    def init_db(self):
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA busy_timeout=30000;
        CREATE TABLE IF NOT EXISTS pages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seed_url TEXT NOT NULL, page_url TEXT NOT NULL,
            normalized_url TEXT NOT NULL UNIQUE, parent_url TEXT, link_text TEXT,
            priority INTEGER NOT NULL DEFAULT 2, depth INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'DISCOVERED', page_type TEXT,
            document_found INTEGER NOT NULL DEFAULT 0, document_count INTEGER NOT NULL DEFAULT 0,
            http_status INTEGER,
            pagination_detected INTEGER NOT NULL DEFAULT 0,
            pagination_pages_checked INTEGER NOT NULL DEFAULT 1,
            pagination_limit_reached INTEGER NOT NULL DEFAULT 0,
            document_url TEXT, document_source TEXT,
            url_family TEXT, query_path TEXT, has_query INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            discovered_order INTEGER, processed_order INTEGER,
            discovered_at TEXT, processed_at TEXT, error_message TEXT);
        CREATE TABLE IF NOT EXISTS links(
            id INTEGER PRIMARY KEY AUTOINCREMENT, from_url TEXT NOT NULL, to_url TEXT NOT NULL,
            normalized_to_url TEXT NOT NULL, link_text TEXT, discovered_at TEXT,
            UNIQUE(from_url,normalized_to_url));
        CREATE TABLE IF NOT EXISTS document_evidence(
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_url TEXT NOT NULL, document_url TEXT NOT NULL,
            detection_source TEXT NOT NULL, link_text TEXT, detected_at TEXT NOT NULL,
            UNIQUE(source_url,document_url));
        CREATE TABLE IF NOT EXISTS performance(
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_url TEXT NOT NULL, page_type TEXT,
            http_status INTEGER, total_seconds REAL, navigation_seconds REAL,
            stabilization_seconds REAL, interaction_seconds REAL, scan_seconds REAL,
            other_seconds REAL, retry_count INTEGER, recorded_at TEXT);
        CREATE TABLE IF NOT EXISTS crawl_counters(name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
        -- Indexes: these turn the two O(N) full-table scans per discovered URL
        -- (family_count / query_variant_count in v1) into O(log N) lookups.
        CREATE INDEX IF NOT EXISTS idx_pages_queue  ON pages(status,priority,depth,discovered_order);
        CREATE INDEX IF NOT EXISTS idx_pages_family ON pages(url_family,status);
        CREATE INDEX IF NOT EXISTS idx_pages_qpath  ON pages(query_path,has_query,status);
        CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);
        CREATE INDEX IF NOT EXISTS idx_pages_type   ON pages(page_type);
        CREATE INDEX IF NOT EXISTS idx_evidence_src ON document_evidence(source_url);
        """)

    def recover_orphans(self):
        """A hard kill leaves rows in PROCESSING. v1 never retried them but still
        charged them against the page budget. Requeue them instead."""
        if not self.cfg.recover_orphaned_pages:
            return
        n = self.db.execute(
            "UPDATE pages SET status='DISCOVERED',error_message='Requeued after interrupted run' "
            "WHERE status='PROCESSING'").rowcount
        if n:
            self.expansion['orphans_recovered'] += n
            logging.info('Recovered %s orphaned PROCESSING page(s)', n)

    # ---------------- classification ----------------
    def url_family(self, u):
        p = urlsplit(u)
        parts = [x for x in (p.path or '').lower().split('/') if x]
        host = (p.hostname or '').lower()
        if not parts:
            return host + '/'

        def variable(x):
            if x.isdigit() or YEAR.fullmatch(x):
                return True
            if len(x) > 24 and ('-' in x or '_' in x):
                return True
            if re.fullmatch(r'[0-9a-f]{8,}', x):
                return True
            return False

        normalized = ['{detail}' if variable(x) and i >= 1 else x for i, x in enumerate(parts)]
        if len(normalized) >= 4:
            normalized = normalized[:3] + ['{detail}']
        return host + '/' + '/'.join(normalized) + '/'

    def query_path(self, u):
        p = urlsplit(u)
        return p.scheme + '://' + p.netloc + p.path

    def signals(self, u, text=''):
        """Token-based, so 'corporate-accountability' no longer dies on 'account'
        and 'grid'/'agriculture' no longer count as 'gri'."""
        p = urlsplit(u or '')
        tokens = canon((p.path or '') + ' ' + (p.query or '') + ' ' + (text or ''))
        strong = match_vocab(tokens, V_STRONG)
        negative = match_vocab(tokens, V_NEGATIVE)
        gateway = match_vocab(tokens, V_GATEWAY)
        dochub = match_vocab(tokens, V_DOC_HUB)
        return strong, negative, gateway, dochub

    def priority(self, u, text=''):
        strong, negative, gateway, dochub = self.signals(u, text)
        host = (urlsplit(u or '').hostname or '').lower()
        if strong and dochub:
            return 0
        if strong:
            return 0 if not negative else 1
        if host != self.host and any(k in host for k in ('investor', 'esg', 'sustain', 'responsib')):
            return 0
        if dochub and self.cfg.prioritize_document_likely_pages:
            return 1
        if negative:
            return 9
        if gateway:
            return 2
        return 3

    # ---------------- counters / budgets ----------------
    def increment_counter(self, name, amount=1):
        self.expansion[name] = self.expansion.get(name, 0) + amount
        self.db.execute('INSERT INTO crawl_counters(name,value) VALUES(?,?) '
                        'ON CONFLICT(name) DO UPDATE SET value=value+excluded.value', (name, amount))

    def family_count(self, family):
        return self.db.execute("SELECT COUNT(*) FROM pages WHERE url_family=? AND status!='SKIPPED'",
                               (family,)).fetchone()[0]

    def query_variant_count(self, u):
        return self.db.execute("SELECT COUNT(*) FROM pages WHERE query_path=? AND has_query=1 "
                               "AND status!='SKIPPED'", (self.query_path(u),)).fetchone()[0]

    def live_count(self):
        return self.db.execute("SELECT COUNT(*) FROM pages WHERE status!='SKIPPED'").fetchone()[0]

    # ---------------- discovery ----------------
    def add(self, u, parent, text, depth, priority=None, source='link'):
        n = self.norm(u, parent or self.seed)
        if not n:
            return False
        text = (text or '')[:500]
        if parent:
            self.db.execute('INSERT OR IGNORE INTO links(from_url,to_url,normalized_to_url,link_text,'
                            'discovered_at) VALUES(?,?,?,?,?)', (parent, u, n, text, now()))
        if self.db.execute('SELECT 1 FROM pages WHERE normalized_url=?', (n,)).fetchone():
            self.stats['duplicates'] += 1
            return False

        strong, negative, _, _ = self.signals(n, text)
        if priority is None:
            priority = self.priority(n, text)
        if negative and not strong:
            self.increment_counter('negative')
            return False

        ok, why = self.policy(n)
        if not ok and why == 'blocked by robots.txt':
            self.increment_counter('robots_blocked')

        if self.live_count() >= self.cfg.max_pages_per_website:
            self.page_limit = True
            self.increment_counter('after_page_limit')
            return False

        family = self.url_family(n)
        qpath = self.query_path(n)
        has_query = 1 if urlsplit(n).query else 0
        if ok and priority > 0 and has_query and \
                self.query_variant_count(n) >= self.cfg.max_query_variants_per_path:
            self.increment_counter('query_limit')
            return False
        if ok and priority > 0 and self.family_count(family) >= self.cfg.max_pages_per_url_family:
            self.increment_counter('family_limit')
            return False

        status, typ, err = 'DISCOVERED', None, None
        if depth > self.cfg.max_depth:
            status, typ, err = 'SKIPPED', 'SKIPPED', 'Beyond maximum depth'
        elif not ok:
            status, typ, err = 'SKIPPED', 'SKIPPED', why

        order = self.db.execute('SELECT COALESCE(MAX(discovered_order),0)+1 FROM pages').fetchone()[0]
        try:
            self.db.execute(
                'INSERT INTO pages(seed_url,page_url,normalized_url,parent_url,link_text,priority,depth,'
                'status,page_type,url_family,query_path,has_query,discovered_order,discovered_at,'
                'error_message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (self.seed, u, n, parent, text, priority, depth, status, typ, family, qpath,
                 has_query, order, now(), err))
        except sqlite3.IntegrityError:
            self.stats['duplicates'] += 1
            return False
        if priority == 0:
            self.increment_counter('esg_priority')
        logging.info('Discovered [%s] p=%s d=%s src=%s %s', status, priority, depth, source, n)
        return status == 'DISCOVERED'

    def claim_next(self):
        """Atomic claim so N workers never take the same row.
        Shallow best-first (depth ASC): document hubs sit near the root, whereas v1
        used depth DESC and drilled into the deepest newest branch."""
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute(
                "SELECT * FROM pages WHERE status='DISCOVERED' "
                "ORDER BY priority ASC, depth ASC, discovered_order ASC LIMIT 1").fetchone()
            if row:
                self.db.execute("UPDATE pages SET status='PROCESSING',attempts=attempts+1 WHERE id=?",
                                (row['id'],))
            self.db.execute('COMMIT')
            return row
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def expired(self):
        if time.monotonic() - self.started >= self.cfg.max_runtime_minutes * 60:
            self.runtime_limit = True
            self.stop = True
        return self.stop

    # ---------------- sitemap seeding ----------------
    async def seed_from_sitemap(self, ctx):
        """sitemap.xml often enumerates every document page in one request,
        replacing hours of crawling. Bounded by max_sitemaps / max_sitemap_urls."""
        if not self.cfg.use_sitemap:
            return
        origin = '{0.scheme}://{0.netloc}'.format(urlsplit(self.seed))
        queue = list(dict.fromkeys(
            [s for s in self.robots.sitemaps if s.startswith('http')] +
            [origin + '/sitemap.xml', origin + '/sitemap_index.xml']))
        seen, fetched, added = set(), 0, 0
        while queue and fetched < self.cfg.max_sitemaps and added < self.cfg.max_sitemap_urls:
            sm = queue.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            fetched += 1
            try:
                r = await ctx.request.get(sm, timeout=15000, fail_on_status_code=False)
                if r.status >= 400:
                    continue
                body = await r.text()
            except (PWError, PWTimeout, UnicodeDecodeError):
                continue
            locs = re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', body, re.I)
            is_index = '<sitemapindex' in body[:4000].lower()
            for loc in locs:
                if added >= self.cfg.max_sitemap_urls:
                    break
                if is_index or re.search(r'sitemap[^/]*\.xml(?:\.gz)?$', loc, re.I):
                    if len(queue) + fetched < self.cfg.max_sitemaps:
                        queue.append(loc)
                    continue
                n = self.norm(loc, sm)
                if not n or not self.internal(n):
                    continue
                if self.doclike(n):
                    # A document URL in the sitemap is evidence about its parent directory.
                    parent = urljoin(n, '.')
                    if self.norm(parent) and self.internal(parent):
                        if self.add(parent, self.seed, 'sitemap document folder', 1, 0, 'sitemap'):
                            added += 1
                    continue
                strong, negative, _, dochub = self.signals(n)
                if negative and not strong:
                    continue
                rank = self.priority(n)
                if rank > 2 and not dochub:
                    continue                      # keep sitemap seeding focused
                if self.add(n, self.seed, 'sitemap', 1, rank, 'sitemap'):
                    added += 1
        if added:
            self.increment_counter('sitemap_seeded', added)
            logging.info('Sitemap seeding added %s URL(s) from %s sitemap file(s)', added, fetched)

    async def load_robots(self, ctx):
        if not (self.cfg.respect_robots_txt or self.cfg.use_sitemap):
            return
        origin = '{0.scheme}://{0.netloc}'.format(urlsplit(self.seed))
        try:
            r = await ctx.request.get(origin + '/robots.txt', timeout=12000, fail_on_status_code=False)
            if r.status < 400:
                self.robots.parse(await r.text())
                logging.info('robots.txt loaded: %s rule(s), %s sitemap hint(s)',
                             len(self.robots.rules), len(self.robots.sitemaps))
            else:
                logging.info('robots.txt not available (HTTP %s); no restrictions applied', r.status)
        except (PWError, PWTimeout, UnicodeDecodeError) as exc:
            logging.info('robots.txt fetch failed (%s); no restrictions applied', type(exc).__name__)

    # ---------------- timing wrappers ----------------
    async def settle(self, p, perf=None):
        started = time.perf_counter()
        try:
            await p.wait_for_timeout(int(self.cfg.stabilization_seconds * 1000))
        except PWError:
            pass
        if perf is not None:
            perf['stabilization'] += time.perf_counter() - started

    async def timed_goto(self, p, u, perf=None):
        started = time.perf_counter()
        try:
            return await p.goto(u, wait_until='domcontentloaded',
                                timeout=self.cfg.page_timeout_seconds * 1000)
        finally:
            if perf is not None:
                perf['navigation'] += time.perf_counter() - started

    def record_perf(self, u, page_type, status, started, retry_count, perf=None):
        perf = perf or {'navigation': 0.0, 'stabilization': 0.0, 'interaction': 0.0, 'scan': 0.0}
        total = time.perf_counter() - started
        known = perf['navigation'] + perf['stabilization'] + perf['interaction'] + perf['scan']
        self.db.execute(
            'INSERT INTO performance(source_url,page_type,http_status,total_seconds,navigation_seconds,'
            'stabilization_seconds,interaction_seconds,scan_seconds,other_seconds,retry_count,recorded_at)'
            ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (u, page_type, status, total, perf['navigation'], perf['stabilization'],
             perf['interaction'], perf['scan'], max(0.0, total - known), retry_count, now()))

    # ---------------- page interactions ----------------
    async def cookie(self, p):
        try:
            for role in ('button', 'link'):
                loc = p.get_by_role(role).filter(has_text=COOKIE)
                for i in range(min(await loc.count(), 8)):
                    el = loc.nth(i)
                    if await el.is_visible():
                        await el.click(timeout=1200)
                        return True
        except PWError:
            pass
        return False

    async def reveal(self, p):
        clicked = False
        try:
            selector = ("button:not([type=submit]),[role=button],summary"
                        if p.url.rstrip('/') == self.seed.rstrip('/') else
                        "main button:not([type=submit]),main [role=button],main summary,"
                        "article button:not([type=submit]),[role=main] button:not([type=submit]),"
                        "[role=main] summary")
            loc = p.locator(selector)
            for i in range(min(await loc.count(), 30)):
                el = loc.nth(i)
                try:
                    text = ((await el.inner_text(timeout=350)) or
                            await el.get_attribute('aria-label') or '').strip()
                except PWError:
                    continue
                if not (text and REVEAL.search(text)):
                    continue
                try:
                    if not await el.is_visible():
                        continue
                    expanded = await el.get_attribute('aria-expanded')
                    if expanded == 'true':
                        continue
                    await el.click(timeout=800)
                    clicked = True
                except PWError:
                    pass
        except PWError:
            pass
        return clicked

    async def links(self, p):
        """Every link on the page - used for child discovery."""
        out, seen = [], set()
        for f in p.frames:
            if f != p.main_frame and f.url and not self.internal(f.url):
                continue
            try:
                vals = await f.locator('a[href],area[href]').evaluate_all(
                    "els=>els.slice(0,3000).map(a=>[a.href,"
                    "(a.innerText||a.getAttribute('aria-label')||a.title||'').trim()])")
            except PWError:
                continue
            src = 'page' if f == p.main_frame else 'iframe'
            for u, t in vals:
                if u and u not in seen:
                    seen.add(u)
                    out.append((u, (t or '')[:500], src))
        return out

    async def content_document_links(self, p):
        """Document candidates from page content only, excluding shared chrome.
        Also picks up <embed>/<object>/<iframe> sources, which v1 could not see."""
        out, seen = [], set()
        blocked = ("header,footer,nav,aside,[role=navigation],[role=banner],[role=contentinfo],"
                   ".header,.footer,.navbar,.navigation,.nav-menu,.menu,.sidebar,.cookie,.cookies,"
                   ".cookie-banner,.cookie-consent,.social,.share")
        main = ("main,article,[role=main],.main-content,.page-content,.content-area,"
                ".content-wrapper,.body-content,#content,#main")
        js = ("els=>els.filter(a=>!a.closest('%s')).filter(a=>Boolean(a.closest('%s')))"
              ".map(a=>[a.href,(a.innerText||a.getAttribute('aria-label')||a.title||'').trim()])"
              % (blocked, main))
        fallback = ("els=>els.filter(a=>!a.closest('%s'))"
                    ".map(a=>[a.href,(a.innerText||a.getAttribute('aria-label')||a.title||'').trim()])"
                    % blocked)
        embeds = ("els=>els.map(e=>[e.src||e.data||'',(e.getAttribute('title')||e.getAttribute('aria-label')"
                  "||e.tagName).trim()]).filter(x=>x[0])")
        for f in p.frames:
            if f != p.main_frame and f.url and not self.internal(f.url):
                continue
            is_main = f == p.main_frame
            try:
                vals = await f.locator('a[href],area[href]').evaluate_all(js)
                if not vals:
                    vals = await f.locator('a[href],area[href]').evaluate_all(fallback)
            except PWError:
                vals = []
            try:
                vals = list(vals) + list(await f.locator(
                    'embed[src],object[data],iframe[src]').evaluate_all(embeds))
            except PWError:
                pass
            src = 'main_content' if is_main else 'iframe_main_content'
            for u, t in vals:
                if u and u not in seen:
                    seen.add(u)
                    out.append((u, (t or '')[:500], src))
        return out

    async def confirm(self, ctx, u):
        """HEAD-verify a candidate. Falls back to a ranged GET when HEAD is
        unsupported (405/501) - some CDNs refuse HEAD on documents."""
        if u in self.document_cache:
            return self.document_cache[u]
        if ext(u) in DOC_EXT:
            self.document_cache[u] = True
            return True
        found = False
        timeout = self.cfg.document_head_timeout_seconds * 1000
        try:
            r = await ctx.request.head(u, timeout=timeout, fail_on_status_code=False)
            headers = r.headers
            if r.status in (403, 405, 501):
                r = await ctx.request.get(u, timeout=timeout, fail_on_status_code=False,
                                          headers={'Range': 'bytes=0-1023'})
                headers = r.headers
            ct = (headers.get('content-type') or '').lower()
            cd = (headers.get('content-disposition') or '').lower()
            if 'application/octet-stream' in ct:
                found = bool(DOC_HINT.search(u) or ext(u) in DOC_EXT or 'attachment' in cd)
            else:
                found = any(x in ct for x in DOC_MIME if x != 'application/octet-stream') or \
                    'attachment' in cd
        except (PWError, PWTimeout):
            pass
        self.document_cache[u] = found
        return found

    def is_pagination(self, candidate, parent, text=''):
        q = dict(parse_qsl(urlsplit(candidate).query))
        if any(k.lower() in PKEYS for k in q) and \
                self.norm(candidate, parent_view=True) == self.norm(parent, parent_view=True):
            return True
        t = (text or '').strip()
        if (NEXT.match(t) or NEXT_SYMBOL.match(t)) and not YEAR.fullmatch(t) and \
                urlsplit(candidate).path.rstrip('/') == urlsplit(parent).path.rstrip('/'):
            return True
        return bool(re.search(r'/page/\d+/?$', urlsplit(candidate).path, re.I))

    # ---------------- scanning ----------------
    async def timed_scan(self, p, ctx, parent, depth, response_docs, perf=None):
        started = time.perf_counter()
        try:
            return await self.scan(p, ctx, parent, depth, response_docs)
        finally:
            if perf is not None:
                perf['scan'] += time.perf_counter() - started

    async def scan(self, p, ctx, parent, depth, response_docs):
        """Returns (documents, all_links). documents is a list of
        (document_url, detection_source, link_text) - up to max_documents_per_page."""
        all_links = await self.links(p)
        documents, seen_docs = [], set()
        cap = self.cfg.max_documents_per_page

        # 1) Network-level evidence. In v1 this set was populated, passed in four times,
        #    and never read - so every PDF served via redirect / stream handler / JS fetch
        #    was detected and then silently discarded.
        for u in sorted(response_docs):
            if len(documents) >= cap:
                break
            if u not in seen_docs:
                seen_docs.add(u)
                documents.append((u, 'network_response', ''))

        # 2) Content links + embedded viewers.
        for u, text, src in await self.content_document_links(p):
            if len(documents) >= cap:
                break
            target = self.viewer_target(u) or u
            if target in seen_docs:
                continue
            if self.doclike(target) and await self.confirm(ctx, target):
                seen_docs.add(target)
                documents.append((target, src if target == u else src + '_embedded_viewer', text))

        for u, src, text in documents:
            logging.info('Document evidence source=%s page=%s document=%s', src, parent, u)

        # 3) Child discovery.
        candidates, seen = [], set()
        parent_family = self.url_family(parent)
        parent_parts = [x for x in urlsplit(parent).path.split('/') if x]
        parent_is_detail = len(parent_parts) >= 4 or ('-' in parent_parts[-1] if parent_parts else False)
        for child, text, _ in all_links:
            n = self.norm(child, parent)
            if not n or n in seen or self.doclike(n) or self.is_pagination(n, parent, text):
                continue
            seen.add(n)
            strong, negative, _, _ = self.signals(n, text)
            rank = self.priority(n, text)
            if negative and not strong:
                self.increment_counter('negative')
                continue
            if rank > 0 and parent_is_detail and \
                    not self.cfg.follow_same_family_links_from_detail_pages and \
                    self.url_family(n) == parent_family:
                self.increment_counter('same_family')
                continue
            candidates.append((rank, n, text))
        candidates.sort(key=lambda x: (x[0], x[1]))
        budget = (self.cfg.max_homepage_children if parent.rstrip('/') == self.seed.rstrip('/')
                  else self.cfg.max_new_children_per_page)
        priority_zero = [x for x in candidates if x[0] == 0]
        rest = [x for x in candidates if x[0] > 0]
        for rank, n, text in priority_zero + rest[:budget]:
            self.add(n, parent, text, depth + 1, rank)
        ignored = max(0, len(rest) - budget)
        if ignored:
            self.increment_counter('parent_budget', ignored)
        return documents, all_links

    # ---------------- pagination ----------------
    def next_page_candidates(self, links, current, visited):
        """URL-based next-page links, ranked so the numerically smallest unvisited
        page number comes first."""
        out = []
        cur_num = 1
        for k, v in parse_qsl(urlsplit(current).query):
            if k.lower() in PKEYS and v.isdigit():
                cur_num = int(v)
                break
        m = re.search(r'/page/(\d+)/?$', urlsplit(current).path, re.I)
        if m:
            cur_num = int(m.group(1))
        for u, t, s in links:
            n = self.norm(u, current)
            if not n or not self.internal(n) or n in visited:
                continue
            text = (t or '').strip()
            num = None
            for k, v in parse_qsl(urlsplit(n).query):
                if k.lower() in PKEYS and v.isdigit():
                    num = int(v)
                    break
            if num is None:
                m = re.search(r'/page/(\d+)/?$', urlsplit(n).path, re.I)
                if m:
                    num = int(m.group(1))
            same_path = urlsplit(n).path.rstrip('/') == urlsplit(current).path.rstrip('/')
            # Many sites render page 2 under a child/sibling path (/a/ -> /a/page-2/).
            # Accepting those is safe because the visited set and the DOM-signature
            # set below still bound the walk.
            cur_dir = urlsplit(current).path.rstrip('/').rsplit('/', 1)[0] + '/'
            near_path = urlsplit(n).path.startswith(cur_dir)
            is_next_text = bool((NEXT.match(text) or NEXT_SYMBOL.match(text))
                                and not YEAR.fullmatch(text))
            if num is not None and num > cur_num and \
                    self.norm(n, parent_view=True) == self.norm(current, parent_view=True):
                out.append((num, n, text, s))
            elif num is not None and num > cur_num and re.search(r'/page/\d+', urlsplit(n).path, re.I):
                out.append((num, n, text, s))
            elif is_next_text and (same_path or near_path or num is not None) and \
                    (num is None or num > cur_num):
                # A numbered link pointing at the current page or earlier is not
                # "next" - otherwise a "1" in the pager walks the crawl backwards.
                out.append((num if num is not None else cur_num + 1, n, text, s))
        out.sort(key=lambda x: x[0])
        dedup, seen = [], set()
        for num, n, text, s in out:
            if n not in seen:
                seen.add(n)
                dedup.append((n, text, s))
        return dedup

    async def signature(self, p):
        """DOM fingerprint. Two identical signatures mean the click/navigation did
        nothing - the primary anti-loop brake for pagination and load-more."""
        try:
            text = (await p.locator('main,[role=main],body').first.inner_text(timeout=3000))[:100000]
        except PWError:
            text = ''
        try:
            hrefs = await p.locator('a[href]').evaluate_all(
                "e=>e.slice(0,1000).map(a=>a.href).sort().join('\\n')")
        except PWError:
            hrefs = ''
        return hashlib.sha256((p.url + text + (hrefs or '')).encode(errors='ignore')).hexdigest()

    async def crawl_pagination(self, p, ctx, base_url, depth, response_docs, documents, perf):
        """Bounded pagination walk.

        Termination is guaranteed by FOUR independent brakes; remove any one and the
        loop still terminates:
          1. page ceiling      - at most cfg.max_pagination_pages iterations, hard `for` range
          2. visited URL set   - a URL is never navigated twice
          3. DOM signature set - a page whose content repeats stops the walk
          4. no-candidate exit - no next link / next control ends the walk
        v1 traded this away entirely: it checked page 2 and stopped, despite
        max_pagination_pages being an int config.
        """
        detected = 0
        checked = 1
        limit_reached = 0
        visited = {self.norm(base_url) or base_url}
        signatures = {await self.signature(p)}
        current = base_url

        for _ in range(max(0, self.cfg.max_pagination_pages - 1)):
            if self.expired():
                break
            try:
                links = await self.links(p)
            except PWError:
                break
            cands = self.next_page_candidates(links, current, visited)

            moved = False
            if cands:
                detected = 1
                target = cands[0][0]
                visited.add(target)
                try:
                    await self.timed_goto(p, target, perf)
                    await self.settle(p, perf)
                    moved = True
                    current = target
                except (PWError, PWTimeout):
                    logging.info('Pagination navigation failed: %s', target)
                    break
            else:
                # Fall back to a clickable control (JS pagination without hrefs).
                clicked = False
                try:
                    controls = p.locator("[rel=next],.pagination a,.pagination button,.pager a,"
                                         ".pager button,[aria-label*='next' i],[aria-label*='Next' i],"
                                         "a.next,button.next,li.next>a")
                    for i in range(min(await controls.count(), 20)):
                        el = controls.nth(i)
                        try:
                            text = ((await el.inner_text(timeout=500)) or
                                    await el.get_attribute('aria-label') or '').strip()
                            if not await el.is_visible():
                                continue
                            if await el.get_attribute('aria-disabled') == 'true':
                                continue
                            if await el.is_disabled():
                                continue
                        except PWError:
                            continue
                        if NEXT.match(text) or NEXT_SYMBOL.match(text) or 'next' in text.lower():
                            try:
                                await el.click(timeout=3000)
                                await self.settle(p, perf)
                                clicked = True
                                detected = 1
                                current = p.url
                                visited.add(self.norm(p.url) or p.url)
                                break
                            except PWError:
                                continue
                except PWError:
                    pass
                if not clicked:
                    break
                moved = True

            if not moved:
                break
            sig = await self.signature(p)
            if sig in signatures:               # brake 3: content repeated
                logging.info('Pagination signature repeated; stopping walk at %s', current)
                break
            signatures.add(sig)
            checked += 1
            self.stats['pagination_states'] += 1
            docs, links2 = await self.timed_scan(p, ctx, base_url, depth, response_docs, perf)
            for d in docs:
                if d[0] not in {x[0] for x in documents} and \
                        len(documents) < self.cfg.max_documents_per_page:
                    documents.append(d)
            if self.next_page_candidates(links2, current, visited):
                limit_reached = 1               # more pages existed than the ceiling allowed
        if detected:
            self.stats['pagination_detected'] += 1
        if limit_reached:
            self.stats['pagination_limits'] += 1
        # Return to the canonical URL so later interactions act on the real page.
        if current != base_url:
            try:
                await self.timed_goto(p, base_url, perf)
                await self.settle(p, perf)
            except (PWError, PWTimeout):
                pass
        return detected, checked, limit_reached

    async def crawl_load_more(self, p, ctx, base_url, depth, response_docs, documents, perf):
        """Bounded load-more clicking: click ceiling + signature set."""
        if not self.cfg.max_load_more_clicks:
            return
        signatures = {await self.signature(p)}
        for _ in range(self.cfg.max_load_more_clicks):
            if self.expired():
                return
            try:
                btn = p.get_by_role('button').filter(has_text=LOAD).first
                if not await btn.is_visible():
                    btn = p.get_by_role('link').filter(has_text=LOAD).first
                    if not await btn.is_visible():
                        return
                await btn.click(timeout=3000)
                await self.settle(p, perf)
            except (PWError, PWTimeout):
                return
            sig = await self.signature(p)
            if sig in signatures:
                return
            signatures.add(sig)
            self.stats['load_more'] += 1
            docs, _ = await self.timed_scan(p, ctx, base_url, depth, response_docs, perf)
            for d in docs:
                if d[0] not in {x[0] for x in documents} and \
                        len(documents) < self.cfg.max_documents_per_page:
                    documents.append(d)

    async def crawl_year_options(self, p, ctx, base_url, depth, response_docs, documents, perf):
        """Year dropdowns are the classic ESG-archive gate. max_year_options was a
        dead config field in v1; it now drives a bounded select-and-rescan loop."""
        if not self.cfg.max_year_options:
            return
        try:
            selects = p.locator('select')
            count = min(await selects.count(), 5)
        except PWError:
            return
        switched = 0
        for i in range(count):
            if switched >= self.cfg.max_year_options or self.expired():
                return
            sel = selects.nth(i)
            try:
                if not await sel.is_visible():
                    continue
                options = await sel.locator('option').evaluate_all(
                    "els=>els.map(o=>[o.value,(o.textContent||'').trim()])")
            except PWError:
                continue
            years = [(v, t) for v, t in options if YEAR.fullmatch((t or '').strip())
                     or YEAR.fullmatch((v or '').strip())]
            if not years:
                continue
            years.sort(key=lambda x: (x[1] or x[0]), reverse=True)
            signatures = {await self.signature(p)}
            for value, label in years:
                if switched >= self.cfg.max_year_options or self.expired():
                    return
                try:
                    await sel.select_option(value=value, timeout=3000)
                    await self.settle(p, perf)
                except (PWError, PWTimeout):
                    continue
                sig = await self.signature(p)
                if sig in signatures:
                    continue
                signatures.add(sig)
                switched += 1
                self.stats['year_switches'] += 1
                logging.info('Year option switched to %s on %s', label or value, base_url)
                docs, _ = await self.timed_scan(p, ctx, base_url, depth, response_docs, perf)
                for d in docs:
                    if d[0] not in {x[0] for x in documents} and \
                            len(documents) < self.cfg.max_documents_per_page:
                        documents.append(d)
            return

    # ---------------- page processing ----------------
    def progress(self, current_url):
        done = self.db.execute("SELECT COUNT(*) FROM pages WHERE status IN ('PROCESSED','FAILED')"
                               ).fetchone()[0]
        queued = self.db.execute("SELECT COUNT(*) FROM pages WHERE status='DISCOVERED'").fetchone()[0]
        logging.info('PROGRESS completed=%s queued=%s documents=%s elapsed=%.1fs current=%s',
                     done, queued, self.stats['documents'], time.monotonic() - self.started, current_url)

    def fail_row(self, row, message, status=None, started=None, retries=None, perf=None):
        order = self.db.execute('SELECT COALESCE(MAX(processed_order),0)+1 FROM pages').fetchone()[0]
        self.db.execute("UPDATE pages SET status='FAILED',page_type='FAILED',http_status=?,"
                        "processed_order=?,processed_at=?,error_message=? WHERE id=?",
                        (status, order, now(), message[:2000], row['id']))
        if started is not None:
            self.record_perf(row['normalized_url'], 'FAILED', status, started,
                             retries if retries is not None else self.cfg.max_retries, perf)

    async def process_with_watchdog(self, ctx, row):
        """Hard ceiling for one source page including retries and interactions.
        One bad page is failed; the queue continues.

        v1 closed *every* page in the context on timeout, which killed the pages of
        concurrent tasks. We now track and close only the pages this task opened."""
        timeout = self.cfg.page_attempt_timeout_seconds
        started = time.perf_counter()
        owned = []
        try:
            await asyncio.wait_for(self.process(ctx, row, owned), timeout=timeout)
        except asyncio.TimeoutError:
            logging.error('HARD PAGE TIMEOUT after %ss: %s', timeout, row['normalized_url'])
            for pg in list(owned):
                await self.safe_close(pg)
            async with self._lock:
                self.fail_row(row, f'Hard page timeout after {timeout}s', None, started)
        except Exception as exc:
            logging.exception('Page watchdog caught unexpected error for %s', row['normalized_url'])
            for pg in list(owned):
                await self.safe_close(pg)
            async with self._lock:
                self.fail_row(row, f'Watchdog error: {type(exc).__name__}: {exc}', None, started)

    async def safe_close(self, p):
        if p is None:
            return
        try:
            await asyncio.wait_for(p.close(), timeout=self.cfg.page_close_timeout_seconds)
        except (asyncio.TimeoutError, PWError):
            logging.warning('Page close timed out; continuing')

    async def process(self, ctx, row, owned):
        u = row['normalized_url']
        depth = row['depth']
        self.stats['max_depth'] = max(depth, self.stats['max_depth'])
        page_started = time.perf_counter()
        last = ''
        status = None

        for attempt in range(1, self.cfg.max_retries + 2):
            perf = {'navigation': 0.0, 'stabilization': 0.0, 'interaction': 0.0, 'scan': 0.0}
            p = await ctx.new_page()
            owned.append(p)
            response_docs = set()

            def on_response(r):
                # Cheap sync check first; only pay for headers on plausible hits.
                try:
                    if ext(r.url) in DOC_EXT or DOC_HINT.search(r.url):
                        response_docs.add(r.url)
                        return
                    ct = (r.headers.get('content-type') or '').lower()
                    cd = (r.headers.get('content-disposition') or '').lower()
                    if any(x in ct for x in DOC_MIME if x != 'application/octet-stream') or \
                            'attachment' in cd:
                        response_docs.add(r.url)
                except Exception:
                    pass

            p.on('response', on_response)
            try:
                logging.info('Opening %s attempt %s', u, attempt)
                r = await self.timed_goto(p, u, perf)
                status = r.status if r else None
                if status and status >= 400:
                    raise RuntimeError(f'HTTP status {status}')
                ct = ''
                if r:
                    try:
                        ct = (await r.all_headers()).get('content-type', '').lower()
                    except PWError:
                        ct = ''
                if ct and 'text/html' not in ct and 'application/xhtml' not in ct:
                    # Not HTML: if it is a document, that is still useful evidence.
                    if any(x in ct for x in DOC_MIME):
                        response_docs.add(r.url if r else u)
                    else:
                        raise RuntimeError(f'Unexpected content type {ct}')

                await self.settle(p, perf)
                t0 = time.perf_counter()
                interacted = await self.cookie(p)
                interacted = (await self.reveal(p)) or interacted
                perf['interaction'] += time.perf_counter() - t0
                if interacted:
                    await self.settle(p, perf)

                async with self._lock:
                    documents, _ = await self.timed_scan(p, ctx, u, depth, response_docs, perf)

                pdet, checked, limit = await self.crawl_pagination(
                    p, ctx, u, depth, response_docs, documents, perf)
                await self.crawl_load_more(p, ctx, u, depth, response_docs, documents, perf)
                await self.crawl_year_options(p, ctx, u, depth, response_docs, documents, perf)

                found = bool(documents)
                page_type = 'PDF' if found else 'HTML'
                async with self._lock:
                    order = self.db.execute(
                        'SELECT COALESCE(MAX(processed_order),0)+1 FROM pages').fetchone()[0]
                    self.db.execute(
                        "UPDATE pages SET status='PROCESSED',page_type=?,document_found=?,"
                        "document_count=?,http_status=?,pagination_detected=?,"
                        "pagination_pages_checked=?,pagination_limit_reached=?,document_url=?,"
                        "document_source=?,processed_order=?,processed_at=?,error_message=NULL "
                        "WHERE id=?",
                        (page_type, int(found), len(documents), status, pdet, checked, limit,
                         documents[0][0] if documents else None,
                         documents[0][1] if documents else None, order, now(), row['id']))
                    for doc_url, doc_src, doc_text in documents:
                        self.db.execute(
                            'INSERT OR IGNORE INTO document_evidence(source_url,document_url,'
                            'detection_source,link_text,detected_at) VALUES(?,?,?,?,?)',
                            (u, doc_url, doc_src, (doc_text or '')[:500], now()))
                    self.stats['documents'] += len(documents)
                    self.record_perf(u, page_type, status, page_started, attempt - 1, perf)
                logging.info('Classified %s %s documents=%s', page_type, u, len(documents))
                await self.safe_close(p)
                if p in owned:
                    owned.remove(p)
                return
            except (PWError, PWTimeout, RuntimeError) as e:
                last = f'{type(e).__name__}: {e}'[:2000]
                logging.warning('Attempt failed %s %s', u, last)
                await self.safe_close(p)
                if p in owned:
                    owned.remove(p)
                permanent_4xx = status is not None and 400 <= status < 500 and status not in (408, 429)
                if permanent_4xx:
                    logging.info('Permanent HTTP %s; retries skipped for %s', status, u)
                    break
                if attempt <= self.cfg.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 6))

        async with self._lock:
            self.fail_row(row, last or 'Unknown failure', status, page_started, self.cfg.max_retries)

    # ---------------- export ----------------
    def export(self):
        d = self.out
        cols = ('seed_url,page_url,normalized_url,page_type,parent_url,link_text,priority,depth,status,'
                'http_status,document_found,document_count,pagination_detected,'
                'pagination_pages_checked,pagination_limit_reached,document_url,document_source,'
                'url_family,error_message,discovered_at,processed_at').split(',')
        rows = self.db.execute('SELECT ' + ','.join(cols) +
                               ' FROM pages ORDER BY discovered_order').fetchall()

        def dump(name, header, records):
            with open(d / name, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(records)

        with open(d / 'classified_pages.csv', 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(dict(r) for r in rows)
        dump('pdf_pages.csv', ['source_url', 'document_count'],
             [[r['normalized_url'], r['document_count']] for r in rows if r['page_type'] == 'PDF'])
        dump('html_pages.csv', ['source_url', 'parent_url', 'depth'],
             [[r['normalized_url'], r['parent_url'], r['depth']] for r in rows if r['page_type'] == 'HTML'])
        dump('failed_pages.csv', ['source_url', 'parent_url', 'depth', 'http_status', 'error_message'],
             [[r['normalized_url'], r['parent_url'], r['depth'], r['http_status'], r['error_message']]
              for r in rows if r['status'] == 'FAILED'])
        dump('document_evidence.csv', ['source_url', 'document_url', 'detection_source', 'link_text'],
             self.db.execute('SELECT source_url,document_url,detection_source,link_text '
                             'FROM document_evidence ORDER BY id').fetchall())
        dump('skipped_pages.csv', ['source_url', 'reason', 'depth'],
             [[r['normalized_url'], r['error_message'], r['depth']] for r in rows
              if r['status'] == 'SKIPPED'])
        perf_cols = ['source_url', 'page_type', 'http_status', 'total_seconds', 'navigation_seconds',
                     'stabilization_seconds', 'interaction_seconds', 'scan_seconds', 'other_seconds',
                     'retry_count']
        perf_rows = self.db.execute('SELECT ' + ','.join(perf_cols) +
                                    ' FROM performance ORDER BY id').fetchall()
        with open(d / 'PERFORMANCE_REPORT.csv', 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(perf_cols)
            w.writerows([[r[c] for c in perf_cols] for r in perf_rows])
            if perf_rows:
                totals = [sum(float(r[c] or 0) for r in perf_rows) for c in perf_cols[3:9]]
                w.writerow(['TOTAL', '', '', *['%.3f' % x for x in totals], ''])

    def summary(self):
        c = dict(self.db.execute('SELECT status,COUNT(*) FROM pages GROUP BY status'))
        t = dict(self.db.execute('SELECT page_type,COUNT(*) FROM pages GROUP BY page_type'))
        total = self.db.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
        docs = self.db.execute('SELECT COUNT(*) FROM document_evidence').fetchone()[0]
        logging.info(
            'FINAL seed=%s discovered=%s processed=%s document_pages=%s documents=%s html=%s failed=%s '
            'skipped=%s duplicates=%s pagination=%s pagination_limits=%s pagination_states=%s '
            'load_more=%s year_switches=%s max_depth=%s page_limit=%s runtime_limit=%s runtime=%.1fs '
            'delay=%.1fs export=%.1fs parent_budget=%s family_limit=%s query_limit=%s same_family=%s '
            'after_page_limit=%s negative=%s esg_priority=%s robots_blocked=%s sitemap_seeded=%s '
            'orphans_recovered=%s output=%s',
            self.seed, total, c.get('PROCESSED', 0), t.get('PDF', 0), docs, t.get('HTML', 0),
            c.get('FAILED', 0), c.get('SKIPPED', 0), self.stats['duplicates'],
            self.stats['pagination_detected'], self.stats['pagination_limits'],
            self.stats['pagination_states'], self.stats['load_more'], self.stats['year_switches'],
            self.stats['max_depth'], self.page_limit, self.runtime_limit,
            time.monotonic() - self.started, self.run_delay_seconds, self.run_export_seconds,
            self.expansion['parent_budget'], self.expansion['family_limit'],
            self.expansion['query_limit'], self.expansion['same_family'],
            self.expansion['after_page_limit'], self.expansion['negative'],
            self.expansion['esg_priority'], self.expansion['robots_blocked'],
            self.expansion['sitemap_seeded'], self.expansion['orphans_recovered'], self.out)

    # ---------------- run loop ----------------
    async def worker(self, ctx, name):
        while not self.expired():
            async with self._lock:
                attempted = self.db.execute(
                    "SELECT COUNT(*) FROM pages WHERE status IN ('PROCESSED','FAILED','PROCESSING')"
                ).fetchone()[0]
                if attempted >= self.cfg.max_pages_per_website:
                    self.page_limit = True
                    return
                row = self.claim_next()
            if not row:
                return
            self.progress(row['normalized_url'])
            await self.process_with_watchdog(ctx, row)
            async with self._lock:
                self.processed_since_export += 1
                if self.processed_since_export >= self.cfg.export_checkpoint_pages:
                    t0 = time.perf_counter()
                    self.export()
                    self.run_export_seconds += time.perf_counter() - t0
                    self.processed_since_export = 0
            t0 = time.perf_counter()
            await asyncio.sleep(self.cfg.delay_between_pages_seconds)
            self.run_delay_seconds += time.perf_counter() - t0

    async def run(self):
        self.recover_orphans()
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True,
                                         args=['--disable-dev-shm-usage', '--no-sandbox'])
            ctx = await b.new_context(ignore_https_errors=True, accept_downloads=False,
                                      user_agent=self.cfg.user_agent)
            ctx.set_default_timeout(self.cfg.page_timeout_seconds * 1000)
            if self.cfg.block_heavy_resources:
                async def block_heavy(route):
                    try:
                        if route.request.resource_type in ('image', 'media', 'font'):
                            await route.abort()
                        else:
                            await route.continue_()
                    except PWError:
                        pass
                await ctx.route('**/*', block_heavy)
            try:
                await self.load_robots(ctx)
                if self.cfg.respect_robots_txt and self.robots.loaded and \
                        not self.robots.allowed(self.seed):
                    logging.warning('Seed URL is disallowed by robots.txt: %s', self.seed)
                self.add(self.seed, None, 'Home', 0, 0, 'seed')
                await self.seed_from_sitemap(ctx)
                workers = [asyncio.create_task(self.worker(ctx, f'w{i}'))
                           for i in range(self.cfg.concurrency)]
                await asyncio.gather(*workers, return_exceptions=True)
            finally:
                try:
                    await ctx.close()
                finally:
                    await b.close()

    def close(self):
        try:
            self.db.commit()
        except sqlite3.Error:
            pass
        self.db.close()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def seed_values(manual, path):
    """v1 read only row 1 of seeds.csv via next(DictReader(...)) and silently
    ignored the rest. Now: all CLI values + every CSV row (any of several column
    names) + plain-text one-URL-per-line files."""
    seeds = []
    for item in (manual or []):
        for piece in re.split(r'[,\s]+', item.strip()):
            if piece:
                seeds.append(piece)
    if path and Path(path).exists():
        text = Path(path).read_text(encoding='utf-8-sig', errors='ignore')
        first = text.splitlines()[0] if text.splitlines() else ''
        if ',' in first or re.search(r'website_url|url|seed|site|domain|link', first, re.I):
            reader = csv.DictReader(text.splitlines())
            keys = [k for k in (reader.fieldnames or [])
                    if k and re.search(r'website_url|url|seed|site|domain|link', k, re.I)]
            if keys:
                for row in reader:
                    for k in keys:
                        v = (row.get(k) or '').strip()
                        if v and not v.lower().startswith(('website_url', 'url')):
                            seeds.append(v)
                            break
            else:
                for line in text.splitlines()[1:]:
                    v = line.split(',')[0].strip()
                    if v:
                        seeds.append(v)
        else:
            for line in text.splitlines():
                v = line.strip()
                if v and not v.startswith('#'):
                    seeds.append(v)
    out, seen = [], set()
    for s in seeds:
        key = s.lower().rstrip('/')
        if key not in seen:
            seen.add(key)
            out.append(s)
    if not out:
        raise ValueError('No seed URL supplied (use --website-url or provide seeds.csv)')
    return out


async def amain(a):
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(a.log, encoding='utf-8'))
    except OSError:
        pass
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'),
                        format='%(asctime)sZ %(levelname)s %(message)s',
                        handlers=handlers, force=True)
    cfg = Config.load(a.config)
    seeds = seed_values(a.website_url, a.seeds)
    root = Path(a.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    logging.info('Seeds (%s): %s', len(seeds), ', '.join(seeds))
    failures = 0
    collectors = []
    for seed in seeds:
        try:
            c = Collector(seed, cfg, root)
        except ValueError as exc:
            logging.error('Skipping invalid seed %r: %s', seed, exc)
            failures += 1
            continue
        collectors.append(c)
        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(s, lambda *_: [setattr(x, 'stop', True) for x in collectors])
            except (ValueError, OSError):
                pass
        try:
            logging.info('=== Seed %s -> %s', c.seed, c.out)
            await c.run()
        except Exception:
            logging.exception('Fatal collector error for %s', c.seed)
            failures += 1
        finally:
            try:
                c.export()
                c.summary()
            finally:
                c.close()
        if c.stop and not c.runtime_limit:
            logging.warning('Stop requested; remaining seeds skipped')
            break
    if failures:
        raise SystemExit(f'{failures} seed(s) failed')


def main():
    p = argparse.ArgumentParser(description='Collect website pages that expose PDF/Office documents.')
    p.add_argument('--website-url', action='append', default=None,
                   help='Seed URL (repeatable, or comma-separated).')
    p.add_argument('--config', default='collector_config.json')
    p.add_argument('--seeds', default='seeds.csv')
    p.add_argument('--output-dir', default='output')
    p.add_argument('--log', default='collector.log')
    a = p.parse_args()
    if not a.website_url:
        envval = os.getenv('WEBSITE_URL', '')
        a.website_url = [envval] if envval else []
    try:
        asyncio.run(amain(a))
    except KeyboardInterrupt:
        print('Interrupted', file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        print(f'Collector failed: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

# --------------------------------------------------------------------------- #
# CHANGELOG v1 -> v2
# --------------------------------------------------------------------------- #
# RECALL (documents that v1 detected and threw away, or never reached)
#  1. response_docs is now consumed in scan(). v1 populated it, passed it into
#     scan() four times, and never read it -> every PDF served via redirect,
#     stream handler or JS fetch was silently discarded.
#  2. max_documents_per_page (default 50) replaces the hard-coded `break` that
#     recorded only the first document per page.
#  3. Real bounded pagination loop (crawl_pagination) honouring
#     max_pagination_pages. v1 stopped after page 2 regardless of config.
#  4. max_year_options now drives an actual year-dropdown loop (ESG archives).
#  5. Sitemap + sitemap-index seeding; robots.txt Sitemap: hints included.
#  6. Embedded viewers detected: <embed>/<object>/<iframe> plus PDF.js style
#     ?file=/x.pdf wrappers.
#  7. confirm() falls back to a ranged GET when HEAD returns 403/405/501.
#  8. Shallow best-first queue ordering (priority ASC, depth ASC) - document hubs
#     are near the root; v1's depth DESC drilled into the deepest branch.
#  9. seeds.csv: every row is read (v1 read row 1 only, silently).
#
# PRECISION
# 10. Token/stem vocabulary matcher replaces substring matching:
#     corporate-accountability, our-footprint and photovoltaic are no longer
#     dropped; grid/agriculture no longer match "gri" and skip budgets.
# 11. prioritize_document_likely_pages now actually promotes document hubs.
# 12. Query handling has a real whitelist mode (keep_meaningful_query_parameters
#     was a dead field in v1).
#
# CORRECTNESS / ROBUSTNESS
# 13. Indexed url_family / query_path / has_query columns remove the two O(N)
#     full-table scans that ran for every discovered URL (the real reason runs
#     died on the clock rather than the page budget).
# 14. recover_orphans() requeues PROCESSING rows after a crash; v1 left them
#     unretried while still charging them against the page budget.
# 15. Per-seed DB + per-seed output directory keyed on netloc+path+hash, so
#     127.0.0.1:8899/a and 127.0.0.1:8898/b cannot collide.
# 16. sqlite isolation_level=None (autocommit) makes the atomic
#     BEGIN IMMEDIATE claim legal; claim_next() lets N workers share the queue.
# 17. Watchdog closes only the pages the failing task opened (v1 closed every
#     page in the context, killing concurrent tasks).
# 18. robots.txt evaluator (longest-match, allow-wins, wildcard and $ support).
# 19. Response handler no longer awaits all_headers() on every response.
# 20. Config validation: unknown keys warned, bad env values ignored, all
#     ceilings clamped so no loop bound can become negative or zero.
# 21. skipped_pages.csv export + document_count column for auditability.
#
# ANTI-LOOP GUARANTEE (unchanged in spirit, now enumerated per loop)
#   crawl_pagination : page ceiling + visited URL set + DOM signature set + no-candidate exit
#   crawl_load_more  : click ceiling + signature set + invisible-button exit
#   crawl_year_options: switch ceiling + signature set + option list exhaustion
#   sitemap seeding  : max_sitemaps + max_sitemap_urls + seen set
#   main queue       : URL uniqueness + max_pages_per_website + max_depth
#                      + max_runtime_minutes + per-page watchdog
#   Removing any single brake still leaves the crawl terminating.
