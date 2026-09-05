from playwright.async_api import async_playwright, Error as PWError, TimeoutError as PWTimeout

# --------------------------------------------------------------------------- #
# Static vocabularies
# --------------------------------------------------------------------------- #
DOC_EXT = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf', '.odt', '.ods', '.odp'}
ASSET_EXT = {'.css', '.js', '.mjs', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.avif', '.ico',
             '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.webm', '.mp3', '.wav', '.zip', '.rar', '.7z',
             '.gz', '.tar', '.map'}
DOC_MIME = ('application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument',
            'application/vnd.oasis.opendocument', 'application/vnd.ms-excel',
            'application/vnd.ms-powerpoint', 'application/rtf', 'application/octet-stream')
DOC_HINT = re.compile(
    r'(?:\.(?:pdf|docx?|xlsx?|pptx?|rtf|od[tsp])(?:$|[?#])'
