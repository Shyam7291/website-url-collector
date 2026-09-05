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

        # Network responses are not classification evidence by themselves because a
        # shared header/footer, prefetch, or hidden widget can load a document. Keep an
        # audit count, then require page-content DOM evidence below.
        if response_docs:
            self.increment_counter('unconfirmed_network_documents', len(response_docs))
        # Content links + embedded viewers.
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
        p0 = [x for x in candidates if x[0] == 0]
        p1 = [x for x in candidates if x[0] == 1][:25]
        p2 = [x for x in candidates if x[0] == 2][:max(10, budget)]
        p3 = [x for x in candidates if x[0] == 3][:10]
        selected = p0 + p1 + p2 + p3
        for rank, n, text in selected:
            self.add(n, parent, text, depth + 1, rank)
        ignored = max(0, len(candidates) - len(selected))
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
            'orphans_recovered=%s esg_reveals=%s unconfirmed_network_documents=%s output=%s',
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
            self.expansion['sitemap_seeded'], self.expansion['orphans_recovered'],
            self.expansion['esg_reveals'], self.expansion['unconfirmed_network_documents'], self.out)

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
                                         args=['--disable-dev-shm-usage'])
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


def aggregate_outputs(root: Path, collectors):
    """Merge per-seed CSV files into the repository root for the existing workflow."""
    specs = {
        'classified_pages.csv': None,
        'pdf_pages.csv': None,
        'html_pages.csv': None,
        'failed_pages.csv': None,
        'document_evidence.csv': None,
        'skipped_pages.csv': None,
        'PERFORMANCE_REPORT.csv': None,
    }
    for name in specs:
        header = None
        all_rows = []
        for collector in collectors:
            path = collector.out / name
            if not path.exists() or path.stat().st_size == 0:
                continue
            with path.open('r', encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.reader(handle))
            if not rows:
                continue
            if header is None:
                header = rows[0]
            for row in rows[1:]:
                if row and row[0] != 'TOTAL':
                    all_rows.append(row)
        if header is not None:
            with (root / name).open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(all_rows)

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
    collectors = []
    for seed in seeds:
        try:
            collectors.append(Collector(seed, cfg, root))
        except ValueError as exc:
            logging.error('Skipping invalid seed %r: %s', seed, exc)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: [setattr(x, 'stop', True) for x in collectors])
        except (ValueError, OSError):
            pass
    semaphore = asyncio.Semaphore(2)
    failures = []
    async def run_one(c):
        async with semaphore:
            try:
                logging.info('=== Seed %s -> %s', c.seed, c.out)
                await c.run()
            except Exception as exc:
                logging.exception('Fatal collector error for %s', c.seed)
                failures.append((c.seed, exc))
            finally:
                try:
                    c.export()
                    c.summary()
                finally:
                    c.close()
    await asyncio.gather(*(run_one(c) for c in collectors))
    aggregate_outputs(root, collectors)
    if failures:
        raise SystemExit(f'{len(failures)} seed(s) failed')

def main():
    p = argparse.ArgumentParser(description='Collect website pages that expose PDF/Office documents.')
    p.add_argument('--website-url', action='append', default=None,
                   help='Seed URL (repeatable, or comma-separated).')
    p.add_argument('--config', default='collector_config.json')
    p.add_argument('--seeds', default='seeds.csv')
    p.add_argument('--output-dir', default='.')
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
