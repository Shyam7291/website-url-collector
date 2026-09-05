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
