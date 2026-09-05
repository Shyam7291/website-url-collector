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
            'max_esg_navigation_clicks_per_page': ('MAX_ESG_NAVIGATION_CLICKS_PER_PAGE', int),
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
        c.max_esg_navigation_clicks_per_page = max(0, c.max_esg_navigation_clicks_per_page)
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
                              sitemap_seeded=0, orphans_recovered=0, esg_reveals=0,
                              unconfirmed_network_documents=0)
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
