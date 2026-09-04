import csv
from datetime import datetime, timezone
from pathlib import Path


SUMMARY_FILE = Path("RUN_SUMMARY.csv")
PDF_FILE = Path("PDF_PAGES.csv")
CLASSIFIED_FILE = Path("classified_pages.csv")

SUMMARY_FIELDS = [
    "run_date",
    "seed_url",
    "discovered",
    "processed",
    "pdf_pages",
    "html_pages",
    "failed_pages",
    "skipped_pages",
]


def load_rows(path):
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save_rows(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    pages = load_rows(CLASSIFIED_FILE)
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    seed_url = ""
    if pages:
        seed_url = pages[0].get("seed_url", "")

    processed = 0
    pdf_count = 0
    html_count = 0
    failed_count = 0
    skipped_count = 0
    pdf_rows = []
    seen_pdf_urls = set()

    for page in pages:
        status = page.get("status", "").upper()
        page_type = page.get("page_type", "").upper()

        if status == "PROCESSED":
            processed += 1
        elif status == "FAILED":
            failed_count += 1
        elif status == "SKIPPED":
            skipped_count += 1

        if page_type == "PDF":
            pdf_count += 1
            source_url = page.get("normalized_url") or page.get("page_url") or ""
            if source_url and source_url not in seen_pdf_urls:
                seen_pdf_urls.add(source_url)
                pdf_rows.append({"run_date": run_time, "source_url": source_url})
        elif page_type == "HTML":
            html_count += 1

    summary_rows = load_rows(SUMMARY_FILE)
    summary_rows.append(
        {
            "run_date": run_time,
            "seed_url": seed_url,
            "discovered": len(pages),
            "processed": processed,
            "pdf_pages": pdf_count,
            "html_pages": html_count,
            "failed_pages": failed_count,
            "skipped_pages": skipped_count,
        }
    )

    save_rows(SUMMARY_FILE, SUMMARY_FIELDS, summary_rows)
    save_rows(PDF_FILE, ["run_date", "source_url"], pdf_rows)

    print("RUN_SUMMARY.csv updated")
    print("PDF_PAGES.csv updated")
    print("PDF source pages:", len(pdf_rows))


if __name__ == "__main__":
    main()
