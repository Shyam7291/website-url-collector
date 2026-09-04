import csv
import os
from pathlib import Path


def read_csv(filename):
    path = Path(filename)
    if not path.exists() or path.stat().st_size == 0:
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def clean(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def link(value):
    value = clean(value)
    return f"{value}" if value.startswith("http") else value


classified = read_csv("classified_pages.csv")
failed = read_csv("failed_pages.csv")
summary_file = os.environ["GITHUB_STEP_SUMMARY"]

pdf_pages = [
    row for row in classified
    if row.get("page_type") == "PDF"
]

html_pages = [
    row for row in classified
    if row.get("page_type") == "HTML"
]

skipped_pages = [
    row for row in classified
    if row.get("status") == "SKIPPED"
]

processed_pages = [
    row for row in classified
    if row.get("status") == "PROCESSED"
]

with open(summary_file, "a", encoding="utf-8") as output:
    output.write("# Website URL Collector Results\n\n")

    output.write("## Run totals\n\n")
    output.write("| Result | Count |\n")
    output.write("| --- | ---: |\n")
    output.write(f"| Discovered records | {len(classified)} |\n")
    output.write(f"| Processed pages | {len(processed_pages)} |\n")
    output.write(f"| PDF pages | {len(pdf_pages)} |\n")
    output.write(f"| HTML pages | {len(html_pages)} |\n")
    output.write(f"| Failed pages | {len(failed)} |\n")
    output.write(f"| Skipped records | {len(skipped_pages)} |\n\n")

    output.write("## PDF pages and detected documents\n\n")

    if pdf_pages:
        output.write("| Source page | Detected document | Detection area |\n")
        output.write("| --- | --- | --- |\n")

        for row in pdf_pages[:500]:
            source = link(
                row.get("normalized_url") or row.get("page_url")
            )
            document = link(row.get("document_url"))
            area = clean(row.get("document_source"))

            output.write(
                f"| {source} | {document} | {area} |\n"
            )
    else:
        output.write("No PDF-classified pages were found.\n")

    output.write("\n## HTML pages\n\n")

    if html_pages:
        output.write("| Source page | Parent URL | Depth |\n")
        output.write("| --- | --- | ---: |\n")

        for row in html_pages[:500]:
            source = link(
                row.get("normalized_url") or row.get("page_url")
            )
            parent = link(row.get("parent_url"))
            depth = clean(row.get("depth"))

            output.write(
                f"| {source} | {parent} | {depth} |\n"
            )
    else:
        output.write("No HTML-classified pages were found.\n")

    output.write("\n## Failed pages\n\n")

    if failed:
        output.write("| Source page | HTTP | Error |\n")
        output.write("| --- | ---: | --- |\n")

        for row in failed[:200]:
            source = link(row.get("source_url"))
            status = clean(row.get("http_status"))
            error = clean(row.get("error_message"))

            output.write(
                f"| {source} | {status} | {error} |\n"
            )
    else:
        output.write("No pages failed.\n")
