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
    max_esg_navigation_clicks_per_page: int = 8
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
