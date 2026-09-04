import csv
import os
from datetime import datetime, timezone
from pathlib import Path


CLASSIFIED_FILE = Path("classified_pages.csv")
RUN_SUMMARY_FILE = Path("RUN_SUMMARY.csv")
PDF_PAGES_FILE = Path("PDF_PAGES.csv")

SUMMARY_FIELDS = [
    "run_date",
    "seed_url",
    "max_pages_requested",
    "discovered",
    "processed",
    "pdf_pages",
    "html_pages",
    "failed_pages",
    "skipped_pages",
    "remaining_discovered",
    "stop_reason",
    "crawl_complete",
    "page_limit_reached",
    "runtime_limit_reached",
    "max_depth_reached",
]


def read_csv(path):
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def count_status(rows, value):
    return sum(1 for row in rows if row.get("status", "").upper() == value)


def count_type(rows, value):
    return sum(1 for row in rows if row.get("page_type", "").upper() == value)


def has_skip_reason(rows, words):
    words = words.lower()
    for row in rows:
        if row.get("status", "").upper() != "SKIPPED":
            continue
        if words in row.get("error_message", "").lower():
            return True
    return False


def keep_old_summary_rows():
    old_rows = read_csv(RUN_SUMMARY_FILE)
    cleaned = []
    for old in old_rows:
        if not any(str(value or "").strip() for value in old.values()):
            continue
        row = {field: old.get(field, "") for field in SUMMARY_FIELDS}
        if not row["max_pages_requested"]:
            row["max_pages_requested"] = "unknown"
        if not row["stop_reason"]:
            row["stop_reason"] = "LEGACY_RUN"
        if not row["crawl_complete"]:
            row["crawl_complete"] = "unknown"
        cleaned.append(row)
    return cleaned


def main():
    pages = read_csv(CLASSIFIED_FILE)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    max_pages = os.getenv("MAX_PAGES", "unknown")

    processed = count_status(pages, "PROCESSED")
    failed = count_status(pages, "FAILED")
    skipped = count_status(pages, "SKIPPED")
    remaining = count_status(pages, "DISCOVERED") + count_status(pages, "PROCESSING")
    pdf_count = count_type(pages, "PDF")
    html_count = count_type(pages, "HTML")

    page_limit = has_skip_reason(pages, "page limit reached")
    runtime_limit = has_skip_reason(pages, "runtime limit reached")

    if runtime_limit:
        stop_reason = "RUNTIME_LIMIT_REACHED"
        crawl_complete = "false"
    elif page_limit:
        stop_reason = "PAGE_LIMIT_REACHED"
        crawl_complete = "false"
    elif remaining > 0:
        stop_reason = "INCOMPLETE_QUEUE_REMAINS"
        crawl_complete = "false"
    else:
        stop_reason = "QUEUE_EXHAUSTED"
        crawl_complete = "true"

    seed_url = pages[0].get("seed_url", "") if pages else os.getenv("WEBSITE_URL", "")
    max_depth = 0
    for row in pages:
        try:
            max_depth = max(max_depth, int(row.get("depth", "0") or 0))
        except ValueError:
            pass

    latest = {
        "run_date": timestamp,
        "seed_url": seed_url,
        "max_pages_requested": max_pages,
        "discovered": len(pages),
        "processed": processed,
        "pdf_pages": pdf_count,
        "html_pages": html_count,
        "failed_pages": failed,
        "skipped_pages": skipped,
        "remaining_discovered": remaining,
        "stop_reason": stop_reason,
        "crawl_complete": crawl_complete,
        "page_limit_reached": str(page_limit).lower(),
        "runtime_limit_reached": str(runtime_limit).lower(),
        "max_depth_reached": max_depth,
    }

    history = keep_old_summary_rows()
    history.append(latest)
    write_csv(RUN_SUMMARY_FILE, SUMMARY_FIELDS, history)

    pdf_rows = []
    seen = set()
    for row in pages:
        if row.get("page_type", "").upper() != "PDF":
            continue
        source_url = row.get("normalized_url") or row.get("page_url") or ""
        if source_url and source_url not in seen:
            seen.add(source_url)
            pdf_rows.append({"run_date": timestamp, "source_url": source_url})

    write_csv(PDF_PAGES_FILE, ["run_date", "source_url"], pdf_rows)

    print("RUN_SUMMARY.csv updated")
    print("PDF_PAGES.csv updated")
    print("Stop reason:", stop_reason)
    print("Crawl complete:", crawl_complete)
    print("Remaining discovered:", remaining)


if __name__ == "__main__":
    main()
