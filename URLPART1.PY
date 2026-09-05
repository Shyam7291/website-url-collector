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
        target_host = (urlsplit(u).hostname or '').lower()
        if self.cfg.restrict_to_seed_language and self.language_prefix and \
                target_host == self.host and not path.startswith(self.language_prefix) and path != '/':
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
        seen, fetched, added, neutral_added = set(), 0, 0, 0
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
                    if neutral_added >= 50:
                        continue
                    neutral_added += 1
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
        """Reveal bounded navigation controls, then ESG controls, and rescan after clicks.
        Buttons and summaries only are clicked. Ordinary anchors are never activated.
        A root page on any related subdomain is treated as a homepage.
        """
        clicked = False
        clicked_keys = set()
        click_count = 0
        page_path = urlsplit(p.url).path or '/'
        is_host_homepage = page_path.rstrip('/') == ''
        selectors = (
            "header button:not([type=submit]),header [role=button],header summary,"
            "button[aria-haspopup=menu],[role=button][aria-haspopup=menu],"
            "main button:not([type=submit]),main [role=button],main summary,"
            "article button:not([type=submit]),article [role=button],article summary,"
            "[role=main] button:not([type=submit]),[role=main] [role=button],[role=main] summary"
        )
        for stage in ('menu', 'esg'):
            while click_count < self.cfg.max_esg_navigation_clicks_per_page:
                candidate = None
                label = ''
                key = None
                try:
                    loc = p.locator(selectors)
                    for i in range(min(await loc.count(), 100)):
                        el = loc.nth(i)
                        try:
                            text = ((await el.inner_text(timeout=350)) or
                                    await el.get_attribute('aria-label') or
                                    await el.get_attribute('title') or '').strip()
                            identity = (text.lower(), await el.get_attribute('id') or '',
                                        await el.get_attribute('class') or '')
                            if identity in clicked_keys or not await el.is_visible():
                                continue
                            if await el.get_attribute('aria-expanded') == 'true':
                                continue
                            if stage == 'menu' and is_host_homepage and MENU_NAV.search(text):
                                candidate, label, key = el, text, identity
                                break
                            if stage == 'esg' and ESG_NAV.search(text):
                                candidate, label, key = el, text, identity
                                break
                        except PWError:
                            continue
                    if candidate is None:
                        break
                    before = len(await self.links(p))
                    await candidate.click(timeout=1200)
                    clicked_keys.add(key)
                    click_count += 1
                    clicked = True
                    await p.wait_for_timeout(250)
                    after = len(await self.links(p))
                    self.increment_counter('esg_reveals')
                    logging.info('ESG navigation revealed label=%s new_links=%s page=%s',
                                 label, max(0, after - before), p.url)
                except PWError:
                    break
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
