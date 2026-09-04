
#!/usr/bin/env python3
"""Separate GitHub Actions website page collector."""
import argparse, asyncio, csv, hashlib, json, logging, os, re, signal, sqlite3, sys, time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from playwright.async_api import async_playwright, Error as PWError, TimeoutError as PWTimeout

DOC_EXT={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.rtf','.odt','.ods','.odp'}
ASSET_EXT={'.css','.js','.png','.jpg','.jpeg','.svg','.gif','.webp','.ico','.woff','.woff2','.ttf','.mp4','.mp3','.zip','.rar','.7z'}
DOC_MIME=('application/pdf','application/msword','application/vnd.openxmlformats-officedocument','application/vnd.ms-excel','application/vnd.ms-powerpoint','application/rtf')
DOC_HINT=re.compile(r'(?:\.(?:pdf|docx?|xlsx?|pptx?)(?:$|[?#])|/(?:downloads?|documents?|files?|uploads?|storage)(?:/|$)|\.ashx(?:$|[?#]))',re.I)
UNSAFE=re.compile(r'/(?:logout|login|signin|signup|cart|checkout|account|search|share|print)(?:/|$)',re.I)
PKEYS={'page','p','paged','offset','start'}
NEXT=re.compile(r'^(?:next|older|more|2|page 2)\s*(?:›|»|→)?$',re.I)
LOAD=re.compile(r'\b(?:load more|show more)\b',re.I)
COOKIE=re.compile(r'^(?:accept(?: all)?|allow all|agree|got it|continue|dismiss|close)$',re.I)
REVEAL=re.compile(r'\b(?:menu|navigation|nav|accordion|expand|reports?|publications?|documents?|resources?|view all)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def ext(url):
    n=urlsplit(url).path.rsplit('/',1)[-1].lower()
    return '.'+n.rsplit('.',1)[-1] if '.' in n else ''
def env(name,default,typ):
    v=os.getenv(name)
    if v in (None,''): return default
    return v.lower() in ('1','true','yes','on') if typ is bool else typ(v)

@dataclass
class Config:
    max_pagination_pages:int=2; max_load_more_clicks:int=1; max_year_options:int=2
    max_depth:int=12; max_pages_per_website:int=3000; page_timeout_seconds:int=45
    delay_between_pages_seconds:float=0.35; max_retries:int=2; max_runtime_minutes:int=170
    crawl_subdomains:bool=True; stabilization_seconds:float=0.6
    restrict_to_seed_language:bool=True; export_checkpoint_pages:int=25
    block_heavy_resources:bool=True; document_head_timeout_seconds:int=4
    keep_meaningful_query_parameters:tuple=('year','page','category','type','section')
    remove_query_parameters:tuple=('utm_source','utm_medium','utm_campaign','utm_term','utm_content','fbclid','gclid')
    allowed_hosts:tuple=()
    @classmethod
    def load(cls,path):
        raw=json.loads(Path(path).read_text()) if Path(path).exists() else {}
        names={f.name for f in fields(cls)}
        for k in list(raw):
            if k not in names: raw.pop(k)
            elif isinstance(getattr(cls(),k),tuple): raw[k]=tuple(raw[k])
        c=cls(**raw)
        mapping={'max_pagination_pages':('MAX_PAGINATION_PAGES',int),'max_load_more_clicks':('MAX_LOAD_MORE_CLICKS',int),'max_year_options':('MAX_YEAR_OPTIONS',int),'max_depth':('MAX_DEPTH',int),'max_pages_per_website':('MAX_PAGES',int),'page_timeout_seconds':('PAGE_TIMEOUT_SECONDS',int),'delay_between_pages_seconds':('DELAY_BETWEEN_PAGES_SECONDS',float),'max_retries':('MAX_RETRIES',int),'max_runtime_minutes':('MAX_RUNTIME_MINUTES',int),'crawl_subdomains':('CRAWL_SUBDOMAINS',bool),'restrict_to_seed_language':('RESTRICT_TO_SEED_LANGUAGE',bool),'export_checkpoint_pages':('EXPORT_CHECKPOINT_PAGES',int),'block_heavy_resources':('BLOCK_HEAVY_RESOURCES',bool),'document_head_timeout_seconds':('DOCUMENT_HEAD_TIMEOUT_SECONDS',int)}
        for a,(e,t) in mapping.items(): setattr(c,a,env(e,getattr(c,a),t))
        c.max_pagination_pages=max(1,c.max_pagination_pages); return c

class Collector:
    def __init__(self,seed,cfg):
        self.cfg=cfg; self.seed=self.norm_seed(seed); self.host=urlsplit(self.seed).hostname.lower()
        ps=self.host.split('.'); self.base='.'.join(ps[-2:]) if len(ps)>1 else self.host
        seed_path=urlsplit(self.seed).path or '/'
        match=re.match(r'^/([a-z]{2}(?:-[a-z]{2})?)(?:/|$)',seed_path,re.I)
        self.language_prefix=('/'+match.group(1).lower()+'/') if match else None
        self.processed_since_export=0
        self.document_cache={}
        self.current_perf=None
        self.run_delay_seconds=0.0
        self.run_export_seconds=0.0
        self.started=time.monotonic(); self.stop=False; self.page_limit=False; self.runtime_limit=False
        self.stats=dict(duplicates=0,pagination_detected=0,pagination_limits=0,pagination_states=0,load_more=0,max_depth=0)
        self.db=sqlite3.connect('crawler.db'); self.db.row_factory=sqlite3.Row; self.init_db()
    def norm_seed(self,u):
        u=u.strip(); u=u if re.match(r'^https?://',u,re.I) else 'https://'+u
        p=urlsplit(u)
        if not p.hostname: raise ValueError('Valid website URL required')
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',p.query,''))
    def norm(self,u,base=None,parent_view=False):
        try:
            p=urlsplit(urljoin(base or self.seed,u.strip()))
            if p.scheme.lower() not in ('http','https') or not p.hostname:return None
            scheme=p.scheme.lower(); host=p.hostname.lower().rstrip('.'); port=p.port
            net=host if port is None or (scheme=='http' and port==80) or (scheme=='https' and port==443) else f'{host}:{port}'
            path=re.sub('/+','/',p.path or '/'); tail=path.rsplit('/',1)[-1]
            if path!='/' and not path.endswith('/') and '.' not in tail:path+='/'
            rem={x.lower() for x in self.cfg.remove_query_parameters}; q=[]
            for k,v in parse_qsl(p.query,keep_blank_values=True):
                kl=k.lower()
                if kl in rem or kl.startswith('utm_') or (parent_view and kl in PKEYS):continue
                q.append((k,v))
            q.sort(key=lambda x:(x[0].lower(),x[1]))
            return urlunsplit((scheme,net,path,urlencode(q,doseq=True),''))
        except (ValueError,UnicodeError):return None
    def internal(self,u):
        h=(urlsplit(u).hostname or '').lower(); allowed={x.lower() for x in self.cfg.allowed_hosts}
        return h in allowed or h==self.host or (self.cfg.crawl_subdomains and (h==self.base or h.endswith('.'+self.base)))
    def doclike(self,u):return ext(u) in DOC_EXT or bool(DOC_HINT.search(u))
    def policy(self,u):
        if not self.internal(u):return False,'external'
        path=(urlsplit(u).path or '/').lower()
        if self.cfg.restrict_to_seed_language and self.language_prefix and not path.startswith(self.language_prefix):
            return False,'outside seed language path '+self.language_prefix
        if ext(u) in ASSET_EXT:return False,'static asset'
        if self.doclike(u):return False,'document'
        if UNSAFE.search(urlsplit(u).path):return False,'unsafe route'
        return True,''
    def init_db(self):
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY AUTOINCREMENT,seed_url TEXT NOT NULL,page_url TEXT NOT NULL,normalized_url TEXT NOT NULL UNIQUE,parent_url TEXT,link_text TEXT,depth INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'DISCOVERED',page_type TEXT,document_found INTEGER NOT NULL DEFAULT 0,http_status INTEGER,pagination_detected INTEGER NOT NULL DEFAULT 0,pagination_pages_checked INTEGER NOT NULL DEFAULT 1,pagination_limit_reached INTEGER NOT NULL DEFAULT 0,document_url TEXT,document_source TEXT,discovered_order INTEGER,processed_order INTEGER,discovered_at TEXT,processed_at TEXT,error_message TEXT);
        CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY AUTOINCREMENT,from_url TEXT NOT NULL,to_url TEXT NOT NULL,normalized_to_url TEXT NOT NULL,link_text TEXT,discovered_at TEXT,UNIQUE(from_url,normalized_to_url));
        CREATE TABLE IF NOT EXISTS document_evidence(id INTEGER PRIMARY KEY AUTOINCREMENT,source_url TEXT NOT NULL,document_url TEXT NOT NULL,detection_source TEXT NOT NULL,detected_at TEXT NOT NULL,UNIQUE(source_url,document_url));
        CREATE TABLE IF NOT EXISTS performance(id INTEGER PRIMARY KEY AUTOINCREMENT,source_url TEXT NOT NULL,page_type TEXT,http_status INTEGER,total_seconds REAL,navigation_seconds REAL,stabilization_seconds REAL,interaction_seconds REAL,scan_seconds REAL,other_seconds REAL,retry_count INTEGER,recorded_at TEXT);
        """); self.db.commit()
    def add(self,u,parent,text,depth):
        n=self.norm(u,parent or self.seed)
        if not n:return False
        if parent:self.db.execute('INSERT OR IGNORE INTO links(from_url,to_url,normalized_to_url,link_text,discovered_at) VALUES(?,?,?,?,?)',(parent,u,n,text[:500],now()))
        if self.db.execute('SELECT 1 FROM pages WHERE normalized_url=?',(n,)).fetchone():
            self.stats['duplicates']+=1; self.db.commit(); logging.debug('Duplicate ignored %s',n); return False
        ok,why=self.policy(n); status='DISCOVERED'; typ=err=None
        count=self.db.execute("SELECT COUNT(*) FROM pages WHERE status!='SKIPPED'").fetchone()[0]
        if depth>self.cfg.max_depth:status,typ,err='SKIPPED','SKIPPED','Beyond maximum depth'
        elif not ok:status,typ,err='SKIPPED','SKIPPED',why
        elif count>=self.cfg.max_pages_per_website:status,typ,err,self.page_limit='SKIPPED','SKIPPED','Page limit reached',True
        order=self.db.execute('SELECT COALESCE(MAX(discovered_order),0)+1 FROM pages').fetchone()[0]
        self.db.execute('INSERT INTO pages(seed_url,page_url,normalized_url,parent_url,link_text,depth,status,page_type,discovered_order,discovered_at,error_message) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(self.seed,u,n,parent,text[:500],depth,status,typ,order,now(),err)); self.db.commit()
        logging.info('Discovered [%s] depth=%s %s',status,depth,n); return status=='DISCOVERED'
    def next(self):return self.db.execute("SELECT * FROM pages WHERE status='DISCOVERED' ORDER BY depth DESC,discovered_order DESC LIMIT 1").fetchone()
    def expired(self):
        if time.monotonic()-self.started>=self.cfg.max_runtime_minutes*60:self.runtime_limit=True;self.stop=True
        return self.stop
    async def settle(self,p):
        started=time.perf_counter();await p.wait_for_timeout(int(self.cfg.stabilization_seconds*1000))
        if self.current_perf is not None:self.current_perf['stabilization']+=time.perf_counter()-started
    async def timed_goto(self,p,u):
        started=time.perf_counter()
        try:return await self.timed_goto(p,u)
        finally:
            if self.current_perf is not None:self.current_perf['navigation']+=time.perf_counter()-started
    def record_perf(self,u,page_type,status,started,retry_count):
        perf=self.current_perf or {'navigation':0.0,'stabilization':0.0,'interaction':0.0,'scan':0.0}
        total=time.perf_counter()-started
        known=perf['navigation']+perf['stabilization']+perf['interaction']+perf['scan']
        other=max(0.0,total-known)
        self.db.execute('INSERT INTO performance(source_url,page_type,http_status,total_seconds,navigation_seconds,stabilization_seconds,interaction_seconds,scan_seconds,other_seconds,retry_count,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u,page_type,status,total,perf['navigation'],perf['stabilization'],perf['interaction'],perf['scan'],other,retry_count,now()))
        self.db.commit()

    async def cookie(self,p):
        try:
            for role in ('button','link'):
                loc=p.get_by_role(role).filter(has_text=COOKIE)
                for i in range(min(await loc.count(),8)):
                    if await loc.nth(i).is_visible():
                        await loc.nth(i).click(timeout=1200);return True
        except PWError:pass
        return False
    async def reveal(self,p):
        clicked=False
        try:
            # Homepage may reveal global navigation. Deeper pages prioritize content controls.
            selector="button:not([type=submit]),[role=button]" if p.url.rstrip('/')==self.seed.rstrip('/') else "main button:not([type=submit]),main [role=button],article button:not([type=submit]),[role=main] button:not([type=submit])"
            loc=p.locator(selector)
            for i in range(min(await loc.count(),30)):
                el=loc.nth(i); text=((await el.inner_text(timeout=350)) or await el.get_attribute('aria-label') or '').strip()
                if text and REVEAL.search(text) and await el.is_visible() and await el.get_attribute('aria-expanded')=='false':
                    try:await el.click(timeout=800);clicked=True
                    except PWError:pass
        except PWError:pass
        return clicked
    async def links(self,p):
        """All links are used for child-page discovery."""
        out=[];seen=set()
        for f in p.frames:
            if f!=p.main_frame and f.url and not self.internal(f.url):continue
            try: vals=await f.locator('a[href],area[href]').evaluate_all("els=>els.map(a=>[a.href,(a.innerText||a.getAttribute('aria-label')||a.title||'').trim()])")
            except PWError:continue
            src='page' if f==p.main_frame else 'iframe'
            for u,t in vals:
                if u and u not in seen:seen.add(u);out.append((u,t[:500],src))
        return out
    async def content_document_links(self,p):
        """Document candidates only from page content, excluding shared chrome."""
        out=[];seen=set()
        selector='a[href],area[href]'
        js="""els=>els.filter(a=>{
          const blocked=a.closest('header,footer,nav,aside,[role=navigation],[role=banner],[role=contentinfo],.header,.footer,.navbar,.navigation,.nav-menu,.menu,.sidebar,.cookie,.cookies,.cookie-banner,.cookie-consent,.social,.share');
          if(blocked)return false;
          return Boolean(a.closest('main,article,[role=main],.main-content,.page-content,.content-area,.content-wrapper,.body-content'));
        }).map(a=>[a.href,(a.innerText||a.getAttribute('aria-label')||a.title||'').trim()])"""
        fallback="""els=>els.filter(a=>!a.closest('header,footer,nav,aside,[role=navigation],[role=banner],[role=contentinfo],.header,.footer,.navbar,.navigation,.nav-menu,.menu,.sidebar,.cookie,.cookies,.cookie-banner,.cookie-consent,.social,.share')).map(a=>[a.href,(a.innerText||a.getAttribute('aria-label')||a.title||'').trim()])"""
        for f in p.frames:
            if f!=p.main_frame and f.url and not self.internal(f.url):continue
            try:
                vals=await f.locator(selector).evaluate_all(js)
                if not vals:vals=await f.locator(selector).evaluate_all(fallback)
            except PWError:continue
            src='main_content' if f==p.main_frame else 'iframe_main_content'
            for u,t in vals:
                if u and u not in seen:seen.add(u);out.append((u,t[:500],src))
        return out
    async def confirm(self,ctx,u):
        if u in self.document_cache:return self.document_cache[u]
        if ext(u) in DOC_EXT:self.document_cache[u]=True;return True
        found=False
        try:
            r=await ctx.request.head(u,timeout=self.cfg.document_head_timeout_seconds*1000,fail_on_status_code=False)
            ct=r.headers.get('content-type','').lower();cd=r.headers.get('content-disposition','').lower()
            found=any(x in ct for x in DOC_MIME) or 'attachment' in cd
        except PWError:pass
        self.document_cache[u]=found;return found
    def is_pagination(self,candidate,parent,text=''):
        q=dict(parse_qsl(urlsplit(candidate).query))
        if any(k.lower() in PKEYS for k in q) and self.norm(candidate,parent_view=True)==self.norm(parent,parent_view=True):return True
        return bool(NEXT.match(text.strip()) and urlsplit(candidate).path.rstrip('/')==urlsplit(parent).path.rstrip('/'))
    async def timed_scan(self,p,ctx,parent,depth,response_docs):
        started=time.perf_counter()
        try:return await self.scan(p,ctx,parent,depth,response_docs)
        finally:
            if self.current_perf is not None:self.current_perf['scan']+=time.perf_counter()-started
    async def scan(self,p,ctx,parent,depth,response_docs):
        all_links=await self.links(p);found=False;document_url=None;document_source=None
        for u,_,src in await self.content_document_links(p):
            if self.doclike(u) and await self.confirm(ctx,u):
                found=True;document_url=u;document_source=src
                logging.info('Document evidence source=%s page=%s document=%s',src,parent,u);break
        for u,t,_ in all_links:
            n=self.norm(u,parent)
            if not n or self.doclike(n) or self.is_pagination(n,parent,t):continue
            self.add(n,parent,t,depth+1)
        return found,all_links,document_url,document_source
    def page2_candidates(self,links,current):
        out=[]
        for u,t,s in links:
            n=self.norm(u,current)
            if not n or not self.internal(n):continue
            q=dict(parse_qsl(urlsplit(n).query)); num=None
            for k,v in q.items():
                if k.lower() in PKEYS and v.isdigit():num=int(v);break
            if num==2 or (NEXT.match(t.strip()) and not re.match(r'^(19|20)\d{2}$',t.strip())):out.append((n,t,s))
        return out
    async def signature(self,p):
        try:
            text=(await p.locator('main,[role=main],body').first.inner_text(timeout=3000))[:100000]
            hrefs=await p.locator('a[href]').evaluate_all("e=>e.slice(0,1000).map(a=>a.href).sort().join('\\n')")
            return hashlib.sha256((p.url+text+hrefs).encode(errors='ignore')).hexdigest()
        except PWError:return hashlib.sha256(p.url.encode()).hexdigest()
    async def process(self,ctx,row):
        u=row['normalized_url'];depth=row['depth'];self.stats['max_depth']=max(depth,self.stats['max_depth'])
        page_started=time.perf_counter();self.current_perf={'navigation':0.0,'stabilization':0.0,'interaction':0.0,'scan':0.0}
        self.db.execute("UPDATE pages SET status='PROCESSING' WHERE id=?",(row['id'],));self.db.commit();last='';status=None
        for attempt in range(1,self.cfg.max_retries+2):
            p=await ctx.new_page();response_docs=set()
            async def response(r):
                try:
                    h=await r.all_headers();ct=h.get('content-type','').lower();cd=h.get('content-disposition','').lower()
                    if any(x in ct for x in DOC_MIME) or 'attachment' in cd or ext(r.url) in DOC_EXT:response_docs.add(r.url)
                except PWError:pass
            p.on('response',response)
            try:
                logging.info('Opening %s attempt %s',u,attempt);r=await self.timed_goto(p,u);status=r.status if r else None
                if status and status>=400:raise RuntimeError(f'HTTP status {status}')
                ct=(await r.all_headers()).get('content-type','').lower() if r else ''
                if ct and 'text/html' not in ct and 'application/xhtml' not in ct:raise RuntimeError(f'Unexpected content type {ct}')
                await self.settle(p)
                interaction_started=time.perf_counter()
                interacted=await self.cookie(p)
                interacted=(await self.reveal(p)) or interacted
                self.current_perf['interaction']+=time.perf_counter()-interaction_started
                if interacted:await self.settle(p)
                found,links,document_url,document_source=await self.timed_scan(p,ctx,u,depth,response_docs);checked=1;pdet=0;limit=0
                cands=self.page2_candidates(links,u)
                if cands and self.cfg.max_pagination_pages>1:
                    pdet=1;self.stats['pagination_detected']+=1;sig=await self.signature(p)
                    await self.timed_goto(p,cands[0][0]);await self.settle(p)
                    if await self.signature(p)!=sig:
                        checked=2;self.stats['pagination_states']+=1;f2,l2,d2,s2=await self.timed_scan(p,ctx,u,depth,response_docs);found|=f2
                        if f2 and not document_url:document_url,document_source=d2,s2
                        if self.page2_candidates(l2,u):limit=1
                    await self.timed_goto(p,u);await self.settle(p)
                elif cands:pdet=limit=1;self.stats['pagination_detected']+=1
                if checked==1 and self.cfg.max_pagination_pages>1:
                    try:
                        controls=p.locator("[rel=next],.pagination a,.pager a,[aria-label*='next' i],[aria-label='Page 2' i]")
                        for i in range(min(await controls.count(),20)):
                            el=controls.nth(i);text=((await el.inner_text(timeout=500)) or await el.get_attribute('aria-label') or '').strip()
                            if await el.is_visible() and (NEXT.match(text) or 'next' in text.lower()):
                                sig=await self.signature(p);await el.click(timeout=3000);await self.settle(p);pdet=1;self.stats['pagination_detected']+=1
                                if await self.signature(p)!=sig:
                                    checked=2;self.stats['pagination_states']+=1
                                    f2,_,d2,s2=await self.timed_scan(p,ctx,u,depth,response_docs);found|=f2
                                    if f2 and not document_url:document_url,document_source=d2,s2
                                break
                    except PWError:pass
                if self.cfg.max_load_more_clicks:
                    try:
                        b=p.get_by_role('button').filter(has_text=LOAD).first
                        if await b.is_visible():
                            sig=await self.signature(p);await b.click(timeout=3000);await self.settle(p)
                            if await self.signature(p)!=sig:
                                self.stats['load_more']+=1
                                fm,_,dm,sm=await self.timed_scan(p,ctx,u,depth,response_docs);found|=fm
                                if fm and not document_url:document_url,document_source=dm,sm
                    except PWError:pass
                if limit:self.stats['pagination_limits']+=1
                order=self.db.execute('SELECT COALESCE(MAX(processed_order),0)+1 FROM pages').fetchone()[0]
                self.db.execute("UPDATE pages SET status='PROCESSED',page_type=?,document_found=?,http_status=?,pagination_detected=?,pagination_pages_checked=?,pagination_limit_reached=?,document_url=?,document_source=?,processed_order=?,processed_at=?,error_message=NULL WHERE id=?",('PDF' if found else 'HTML',int(found),status,pdet,checked,limit,document_url,document_source,order,now(),row['id']))
                if found and document_url:self.db.execute('INSERT OR IGNORE INTO document_evidence(source_url,document_url,detection_source,detected_at) VALUES(?,?,?,?)',(u,document_url,document_source,now()))
                self.db.commit();page_type='PDF' if found else 'HTML';logging.info('Classified %s %s evidence=%s',page_type,u,document_url or 'none');await p.close();self.record_perf(u,page_type,status,page_started,attempt-1);self.current_perf=None;return
            except (PWError,PWTimeout,RuntimeError) as e:
                last=f'{type(e).__name__}: {e}'[:2000];logging.warning('Attempt failed %s %s',u,last);await p.close()
                permanent_4xx=status is not None and 400<=status<500 and status not in (408,429)
                if permanent_4xx:
                    logging.info('Permanent HTTP %s; retries skipped for %s',status,u);break
                if attempt<=self.cfg.max_retries:await asyncio.sleep(min(2**attempt,6))
        order=self.db.execute('SELECT COALESCE(MAX(processed_order),0)+1 FROM pages').fetchone()[0]
        self.db.execute("UPDATE pages SET status='FAILED',page_type='FAILED',http_status=?,processed_order=?,processed_at=?,error_message=? WHERE id=?",(status,order,now(),last,row['id']));self.db.commit()
        self.record_perf(u,'FAILED',status,page_started,self.cfg.max_retries);self.current_perf=None
    def export(self):
        cols='seed_url,page_url,normalized_url,page_type,parent_url,link_text,depth,status,http_status,document_found,pagination_detected,pagination_pages_checked,pagination_limit_reached,document_url,document_source,error_message,discovered_at,processed_at'.split(',')
        rows=self.db.execute('SELECT '+','.join(cols)+' FROM pages ORDER BY discovered_order').fetchall()
        with open('classified_pages.csv','w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(dict(r) for r in rows)
        with open('pdf_pages.csv','w',newline='',encoding='utf-8-sig') as f:w=csv.writer(f);w.writerow(['source_url']);w.writerows([[r['normalized_url']] for r in rows if r['page_type']=='PDF'])
        with open('html_pages.csv','w',newline='',encoding='utf-8-sig') as f:w=csv.writer(f);w.writerow(['source_url','parent_url','depth']);w.writerows([[r['normalized_url'],r['parent_url'],r['depth']] for r in rows if r['page_type']=='HTML'])
        with open('failed_pages.csv','w',newline='',encoding='utf-8-sig') as f:w=csv.writer(f);w.writerow(['source_url','parent_url','depth','http_status','error_message']);w.writerows([[r['normalized_url'],r['parent_url'],r['depth'],r['http_status'],r['error_message']] for r in rows if r['status']=='FAILED'])
        with open('document_evidence.csv','w',newline='',encoding='utf-8-sig') as f:w=csv.writer(f);w.writerow(['source_url','document_url','detection_source']);w.writerows(self.db.execute('SELECT source_url,document_url,detection_source FROM document_evidence ORDER BY id'))
        perf_cols=['source_url','page_type','http_status','total_seconds','navigation_seconds','stabilization_seconds','interaction_seconds','scan_seconds','other_seconds','retry_count']
        perf_rows=self.db.execute('SELECT '+','.join(perf_cols)+' FROM performance ORDER BY id').fetchall()
        with open('PERFORMANCE_REPORT.csv','w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f);w.writerow(perf_cols);w.writerows([[r[c] for c in perf_cols] for r in perf_rows])
            if perf_rows:
                totals=[sum(float(r[c] or 0) for r in perf_rows) for c in perf_cols[3:9]]
                w.writerow(['TOTAL','','',*['%.3f'%x for x in totals],''])

    def summary(self):
        c=dict(self.db.execute('SELECT status,COUNT(*) FROM pages GROUP BY status'));t=dict(self.db.execute('SELECT page_type,COUNT(*) FROM pages GROUP BY page_type'));total=self.db.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
        logging.info('FINAL seed=%s discovered=%s processed=%s PDF=%s HTML=%s failed=%s skipped=%s duplicates=%s pagination=%s pagination_limits=%s pagination_states=%s load_more=%s max_depth=%s page_limit=%s runtime_limit=%s runtime_seconds=%.1f configured_delay_seconds=%.1f export_seconds=%.1f',self.seed,total,c.get('PROCESSED',0),t.get('PDF',0),t.get('HTML',0),c.get('FAILED',0),c.get('SKIPPED',0),self.stats['duplicates'],self.stats['pagination_detected'],self.stats['pagination_limits'],self.stats['pagination_states'],self.stats['load_more'],self.stats['max_depth'],self.page_limit,self.runtime_limit,time.monotonic()-self.started,self.run_delay_seconds,self.run_export_seconds)
    async def run(self):
        self.add(self.seed,None,'Home',0)
        async with async_playwright() as pw:
            b=await pw.chromium.launch(headless=True,args=['--disable-dev-shm-usage']);ctx=await b.new_context(ignore_https_errors=True,accept_downloads=False,user_agent='Mozilla/5.0 (compatible; WebsiteURLCollector/1.0)');ctx.set_default_timeout(self.cfg.page_timeout_seconds*1000)
            if self.cfg.block_heavy_resources:
                async def block_heavy(route):
                    if route.request.resource_type in ('image','media','font'):await route.abort()
                    else:await route.continue_()
                await ctx.route('**/*',block_heavy)
            try:
                while not self.expired():
                    row=self.next()
                    if not row:break
                    await self.process(ctx,row);self.processed_since_export+=1
                    if self.processed_since_export>=self.cfg.export_checkpoint_pages:
                        export_started=time.perf_counter();self.export();self.run_export_seconds+=time.perf_counter()-export_started;self.processed_since_export=0
                    delay_started=time.perf_counter();await asyncio.sleep(self.cfg.delay_between_pages_seconds);self.run_delay_seconds+=time.perf_counter()-delay_started
            finally:await ctx.close();await b.close()

def seed_value(manual,path):
    if manual.strip():return manual.strip()
    with open(path,newline='',encoding='utf-8-sig') as f:r=next(csv.DictReader(f),None)
    if not r or not r.get('website_url'):raise ValueError('No seed URL supplied')
    return r['website_url'].strip()
async def amain(a):
    logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'),format='%(asctime)sZ %(levelname)s %(message)s',handlers=[logging.FileHandler('collector.log',encoding='utf-8'),logging.StreamHandler(sys.stdout)],force=True)
    c=Collector(seed_value(a.website_url,a.seeds),Config.load(a.config))
    for s in (signal.SIGINT,signal.SIGTERM):signal.signal(s,lambda *_:setattr(c,'stop',True))
    try:logging.info('Seed URL %s',c.seed);await c.run()
    except Exception:logging.exception('Fatal collector error');raise
    finally:c.export();c.summary();c.db.commit();c.db.close()
def main():
    p=argparse.ArgumentParser();p.add_argument('--website-url',default=os.getenv('WEBSITE_URL',''));p.add_argument('--config',default='collector_config.json');p.add_argument('--seeds',default='seeds.csv');a=p.parse_args()
    try:asyncio.run(amain(a))
    except Exception as e:print(f'Collector failed: {e}',file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
