# Website URL Collector

This is a completely separate GitHub Actions-only collector. It explores a company website and classifies each opened **source page URL** as:

- **PDF**: the HTML page contains at least one detected PDF or supported Office document. The page itself is not necessarily a PDF.
- **HTML**: the page opened successfully, but no document was detected in the allowed initial, pagination, and Load More states.

It does not contain, modify, or run the existing document scraper. The handoff is:

`Company homepage -> Website URL Collector -> pdf_pages.csv -> Existing document scraper`

## Files

```text
website-url-collector/
├── .github/workflows/run-collector.yml
├── url_collector.py
├── requirements.txt
├── collector_config.json
├── seeds.csv
├── .gitignore
└── README.md
```

## Main behavior

1. The seed is inserted into SQLite as `DISCOVERED`.
2. The next deepest and most recently discovered URL is selected, providing depth-first traversal.
3. `pages.normalized_url` is unique, so repeated headers and menus are opened only once.
4. Every discovery relationship is also saved in `links`, including links to an already-known page.
5. Internal HTML pages are queued. External HTML pages, assets, document URLs, unsafe routes, and over-limit pages are recorded as `SKIPPED` but not crawled.
6. The rendered main page and relevant same-company iframes are inspected.
7. One confirmed document is enough for PDF classification. Child-link extraction still continues.
8. Pagination is limited to two states total: initial page plus page 2. Page 2 is not a separate output source URL.
9. Load More or Show More is clicked no more than once.
10. SQLite changes are committed immediately, CSVs are checkpointed after every page, and final export runs even after a collector exception.

## Outputs

- `classified_pages.csv`: full audit, including PDF, HTML, FAILED, and SKIPPED records.
- `pdf_pages.csv`: only PDF-classified source pages, with the required `source_url` header.
- `html_pages.csv`: HTML source pages, parent URLs, and depth.
- `failed_pages.csv`: errors after retries.
- `crawler.db`: SQLite queue and link-edge audit data.
- `collector.log`: crawl activity and final totals.

## Create the repository using only Chrome

1. Sign in to GitHub and select **New repository**.
2. Name it `website-url-collector` and choose the visibility permitted by your organization.
3. Create the repository, optionally with an initial README.
4. Open **Code > Add file > Create new file**.
5. Add each root file from this project, pasting its supplied content and committing it:
   - `url_collector.py`
   - `requirements.txt`
   - `collector_config.json`
   - `seeds.csv`
   - `.gitignore`
   - `README.md`
6. Add the workflow by entering this complete filename in GitHub's filename box:
   `.github/workflows/run-collector.yml`
7. Commit the workflow to the default branch. GitHub creates the nested folders automatically.
8. Open **Actions** and enable workflows if GitHub asks. An organization administrator may need to permit Actions or third-party actions.

You can also extract the supplied ZIP and use **Add file > Upload files**. If nested browser upload is blocked, create the workflow by its full path as described above.

## Run from the GitHub website

1. Open the repository's **Actions** tab.
2. Select **Run Website URL Collector** on the left.
3. Select **Run workflow**.
4. Enter the company homepage in `website_url`. If blank, the first row in `seeds.csv` is used.
5. Keep or change `max_pages` and `max_depth`.
6. Select the green **Run workflow** button.
7. Open the workflow run to monitor logs.
8. When complete, scroll to **Artifacts** and download `url-collector-results`.
9. Extract the artifact ZIP.
10. Give `pdf_pages.csv` to the existing document scraper. It contains source page URLs, not actual document URLs.

Nothing is installed on your laptop. The Ubuntu runner sets up Python, installs the pinned Playwright package, installs Chromium and Linux dependencies, runs the browser headlessly, and uploads results. The workflow follows Playwright's supported `python -m playwright install --with-deps chromium` CI pattern.

## Configuration

The JSON file provides defaults. GitHub Actions inputs override page and depth caps. Supported environment overrides are:

- `MAX_PAGES`
- `MAX_DEPTH`
- `MAX_PAGINATION_PAGES`
- `MAX_LOAD_MORE_CLICKS`
- `MAX_YEAR_OPTIONS`
- `PAGE_TIMEOUT_SECONDS`
- `DELAY_BETWEEN_PAGES_SECONDS`
- `MAX_RETRIES`
- `MAX_RUNTIME_MINUTES`
- `CRAWL_SUBDOMAINS`

`allowed_hosts` can explicitly permit a related host. Unknown query parameters are preserved because they may change content. Known tracking parameters and fragments are removed. Retained parameters are sorted, default ports are removed, repeated path slashes are collapsed, and extensionless paths receive a consistent trailing slash.

## Pagination

The initial page is state 1. The collector allows only one additional state. It recognizes common page query parameters, next/page-2 labels, `rel=next`, pagination or pager containers, and relevant accessibility labels. A four-digit year label is not treated as numeric pagination.

If either allowed state contains a document, the primary parent source page is PDF. Normal detail links discovered in both states are queued. Pagination URLs are not added as separate source pages.

`max_year_options` is present as a safety configuration for a later enhanced year-filter handler. This first conservative release does not click arbitrary year filters because websites frequently use years as archives, filters, or ordinary links.

## Safety and error handling

- Uses one reusable browser context per run.
- Uses `domcontentloaded` plus a short stabilization wait, not only `networkidle`.
- Conservatively accepts or dismisses common cookie controls.
- Only reveals limited menu, accordion, resource, report, and View All controls.
- Does not click login, forms, search, account, cart, checkout, share, print, telephone, or email actions.
- Handles HTTP errors, timeouts, browser failures, SSL errors through `ignore_https_errors`, unexpected content types, and retries.
- A failed page is marked `FAILED`; other queued URLs continue.
- The workflow has a 180-minute timeout and the code stops around 170 minutes, leaving time to export.
- Artifact upload uses `always()`, so partial outputs are uploaded if the run reaches the upload step.

## Known limitations

- CAPTCHAs, bot protection, authenticated pages, closed shadow roots, canvas navigation, and highly custom controls may prevent full discovery.
- Popup or download-only controls are not clicked blindly. Document responses triggered by permitted interactions are detected.
- Same-company iframes are inspected. Unrelated third-party iframe sites are not recursively crawled.
- Some servers reject `HEAD`; direct recognized document extensions still count, but unusual document routes may be missed.
- Base-domain handling is conservative and does not use a public-suffix package. Review `crawl_subdomains` for domains such as `example.co.uk`.
- The first version starts fresh each run and processes one manual seed or the first `seeds.csv` row.
- Sitemap discovery, robots reporting, resume, traces, screenshots, and full year-filter interaction are later enhancements.

Only crawl websites where automated access is authorized, and use respectful limits.

## Troubleshooting

### Workflow is not listed
Check that `.github/workflows/run-collector.yml` is on the default branch and that Actions are enabled. Organization policy may block marketplace actions.

### Chromium installation fails
Open the failed installation step and retry once for a temporary package-service issue. The workflow installs both Chromium and required Linux libraries.

### Artifact is missing
Do not manually cancel the job if partial results are important. Cancellation can prevent later steps. Let the internal runtime limit stop the crawler and reach the `always()` upload step.

### Many 403 or 429 results
Raise `delay_between_pages_seconds`, lower `max_pages`, and confirm that the site permits automated access. The collector does not bypass access controls.

### Too many pages
Lower the workflow's `max_pages` or `max_depth`, disable `crawl_subdomains`, or narrow `allowed_hosts`.

### PDFs are missed
Inspect `collector.log`. Unusual buttons may require a site-specific safe rule. This collector intentionally avoids indiscriminate clicking.
