 r'|/(?:downloads?|documents?|files?|uploads?|storage|assets?/docs?|media/docs?|attachments?)(?:/|$)'
    r'|\.ashx(?:$|[?#])|/getfile|/download\.aspx|/viewdocument)', re.I)
# PDF.js / generic embedded-viewer wrappers: ...viewer.html?file=/x.pdf
VIEWER_PARAMS = ('file', 'url', 'src', 'document', 'doc', 'pdf', 'href')
UNSAFE = re.compile(r'/(?:logout|log-out|login|log-in|signin|sign-in|signup|sign-up|register|cart|'
                    r'checkout|basket|my-?account|wp-admin|wp-login|admin|search|share|print)(?:/|$)', re.I)
PKEYS = {'page', 'p', 'paged', 'offset', 'start', 'pagenum', 'pagenumber', 'pg', 'from', 'skip'}
NEXT = re.compile(r'^(?:next|next page|older|older posts?|more|forward|\d{1,4}|page\s*\d{1,4})\s*'
                  r'(?:>|>>|->|>|>>)?$', re.I)
NEXT_SYMBOL = re.compile(r'^(?:>|>>|->|>|>>|next\s*[>>>->>]*)$', re.I)
LOAD = re.compile(r'\b(?:load|show|view|see)\s+(?:\d+\s+)?more\b', re.I)
COOKIE = re.compile(r'^(?:accept(?: all| cookies| all cookies)?|allow all|i agree|agree|ok|got it|'
                    r'understood|continue|dismiss|close|reject all|only necessary)$', re.I)
REVEAL = re.compile(r'\b(?:menu|navigation|nav|accordion|expand|show|reports?|publications?|documents?|'
                    r'resources?|downloads?|archive|library|view all|see all|all years?)\b', re.I)
YEAR = re.compile(r'^(19|20)\d{2}$')
ESG_NAV = re.compile(
    r'\b(?:esg|sustainab(?:ility|le)?|environment(?:al)?|climate|social(?: responsibility)?|'
    r'governance|corporate governance|ethics|compliance|polic(?:y|ies)|reports?|disclosures?|'
    r'documents?|charters?|human rights|responsible sourcing|health and safety|board|committees?|'
    r'resources?|responsibility)\b', re.I)
MENU_NAV = re.compile(r'^(?:menu|open menu|navigation|main menu|site menu|more)$', re.I)

# Vocabulary syntax:  "foo" = exact token match, "foo*" = token prefix match,
# "foo-bar" = consecutive token phrase. This replaces v1 substring matching, which
# misclassified corporate-accountability / our-footprint / photovoltaic and
# false-promoted grid / agriculture.
ESG_STRONG = (
    'esg', 'sustainab*', 'environment*', 'climate', 'climate-change', 'carbon', 'carbon-footprint',
    'footprint', 'emission*', 'ghg', 'greenhouse-gas', 'net-zero', 'netzero', 'decarbon*', 'renewable*',
