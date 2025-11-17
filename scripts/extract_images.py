#!/usr/bin/env python3
"""
Extract image metadata and HubSpot context information from exported HubSpot pages.

Usage examples:
    python scripts/extract_images.py sample.html
    python scripts/extract_images.py exported_pages/ --csv-out image-report.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract image metadata plus HubSpot location context from HTML exports."
    )
    parser.add_argument(
        "targets",
        nargs="+",
        type=Path,
        help="HTML files or directories containing HTML exports.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Optional base URL used to resolve relative image paths. "
        "Defaults to the page's canonical URL if available.",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Optional path to write CSV output (falls back to JSON on stdout).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Number of parallel workers (default: sequential).",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort on the first file processing error.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def resolve_targets(targets: Sequence[Path]) -> List[Path]:
    html_files: List[Path] = []
    for target in targets:
        if target.is_dir():
            for candidate in target.rglob("*"):
                if candidate.is_file() and candidate.suffix.lower() in {".html", ".htm"}:
                    html_files.append(candidate)
        elif target.is_file():
            if target.suffix.lower() in {".html", ".htm"}:
                html_files.append(target)
            else:
                logging.warning("Skipping non-HTML file %s", target)
        else:
            logging.warning("Skipping missing path %s", target)
    if not html_files:
        raise FileNotFoundError("No HTML files found for the provided targets.")
    return html_files


def load_html(path: Path) -> BeautifulSoup:
    with path.open("r", encoding="utf-8") as fp:
        return BeautifulSoup(fp, "html.parser")


def canonical_url(soup: BeautifulSoup, fallback: Optional[str]) -> Optional[str]:
    link = soup.find("link", rel="canonical")
    href = link["href"] if link and link.has_attr("href") else None
    return href or fallback


def normalize_src(src: Optional[str], base_url: Optional[str]) -> Optional[str]:
    if not src:
        return None
    if src.startswith(("http://", "https://", "data:")):
        return src
    return urljoin(base_url, src) if base_url else src


def parse_srcset(value: Optional[str], base_url: Optional[str]) -> List[str]:
    if not value:
        return []
    entries: List[str] = []
    for item in value.split(","):
        chunk = item.strip()
        if not chunk:
            continue
        if " " in chunk:
            url_part, descriptor = chunk.split(None, 1)
            entries.append(f"{normalize_src(url_part, base_url)} {descriptor}")
        else:
            entries.append(normalize_src(chunk, base_url) or chunk)
    return entries


def extract_hubspot_path(src: Optional[str]) -> Optional[str]:
    if not src or src.startswith("data:"):
        return None
    parsed = urlparse(src)
    # Relative URLs will have empty scheme/netloc; absolute will fill both.
    path = parsed.path
    if not path:
        # handle protocol-relative like //example/path.png
        if src.startswith("//"):
            path = urlparse(f"http:{src}").path
    return path or None


def extract_hubspot_folder(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    clean_path = path.split("?", 1)[0]
    pure = PurePosixPath(clean_path)
    parts = [p for p in pure.parts if p not in {"/", ""}]
    folder_parts: List[str] = []
    if "hubfs" in parts:
        hub_idx = parts.index("hubfs")
        folder_parts = parts[hub_idx + 1 : len(parts) - 1]
    elif "hs-fs" in parts:
        hs_idx = parts.index("hs-fs")
        folder_parts = parts[hs_idx + 1 : len(parts) - 1]
    else:
        folder_parts = parts[:-1]
    return "/".join(folder_parts) if folder_parts else None


def describe_parent_chain(tag: Tag, depth: int = 6) -> List[Dict[str, Optional[str]]]:
    chain: List[Dict[str, Optional[str]]] = []
    current = tag.parent
    steps = 0
    while current and steps < depth:
        chain.append(
            {
                "name": current.name,
                "id": current.get("id"),
                "classes": current.get("class"),
                "data_hs_type": current.get("data-hs-cos-type"),
                "data_hs_general": current.get("data-hs-cos-general-type"),
            }
        )
        current = current.parent
        steps += 1
    return chain


def nearest_heading(tag: Tag) -> Optional[str]:
    for ancestor in tag.parents:
        if ancestor.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = ancestor.get_text(strip=True)
            if text:
                return text
    # Fall back to previous siblings headings
    prev = tag.previous_sibling
    while prev:
        if isinstance(prev, Tag) and prev.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = prev.get_text(strip=True)
            if text:
                return text
        prev = prev.previous_sibling
    return None


def collect_images(soup: BeautifulSoup, base_url: Optional[str]) -> List[Dict]:
    images: List[Dict] = []
    for img in soup.find_all("img"):
        normalized_src = normalize_src(img.get("src"), base_url)
        hubspot_path = extract_hubspot_path(img.get("src")) or extract_hubspot_path(
            normalized_src
        )
        hubspot_folder = extract_hubspot_folder(hubspot_path)
        record = {
            "src": normalized_src,
            "raw_src": img.get("src"),
             "hubspot_path": hubspot_path,
            "hubspot_folder": hubspot_folder,
            "alt": img.get("alt"),
            "title": img.get("title"),
            "width": img.get("width"),
            "height": img.get("height"),
            "loading": img.get("loading"),
            "srcset": parse_srcset(img.get("srcset"), base_url),
            "parent_chain": describe_parent_chain(img),
            "nearest_heading": nearest_heading(img),
        }

        # Include any data-* attributes that might reference HubSpot modules.
        data_attrs = {k: v for k, v in img.attrs.items() if k.startswith("data-")}
        if data_attrs:
            record["data_attributes"] = data_attrs

        images.append(record)
    return images


def format_parent_chain(chain: List[Dict]) -> str:
    parts: List[str] = []
    for entry in chain:
        name = entry.get("name") or ""
        identifier = entry.get("id")
        classes = entry.get("classes")
        descriptor = name
        if identifier:
            descriptor += f"#{identifier}"
        if classes:
            descriptor += "." + ".".join(classes)
        parts.append(descriptor.strip("."))
    return " > ".join(filter(None, parts))


def build_report(path: Path, base_url_override: Optional[str]) -> Dict:
    soup = load_html(path)
    page_base = base_url_override or canonical_url(soup, None)
    return {
        "page": str(path),
        "canonical_url": page_base,
        "image_count": len(soup.find_all("img")),
        "images": collect_images(soup, page_base),
    }


def write_csv(reports: Iterable[Dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "page",
            "canonical_url",
            "hubspot_path",
            "hubspot_folder",
            "src",
            "raw_src",
            "alt",
            "title",
            "width",
            "height",
            "loading",
            "nearest_heading",
            "parent_chain",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for report in reports:
            page = report.get("page")
            canonical = report.get("canonical_url")
            for image in report.get("images", []):
                writer.writerow(
                    {
                        "page": page,
                        "canonical_url": canonical,
                        "hubspot_path": image.get("hubspot_path"),
                        "hubspot_folder": image.get("hubspot_folder"),
                        "src": image.get("src"),
                        "raw_src": image.get("raw_src"),
                        "alt": image.get("alt"),
                        "title": image.get("title"),
                        "width": image.get("width"),
                        "height": image.get("height"),
                        "loading": image.get("loading"),
                        "nearest_heading": image.get("nearest_heading"),
                        "parent_chain": format_parent_chain(image.get("parent_chain", [])),
                    }
                )


def gather_reports(
    html_files: Sequence[Path],
    base_url: Optional[str],
    workers: int,
    fail_fast: bool,
) -> Tuple[List[Dict], List[Tuple[Path, Exception]]]:
    reports: List[Optional[Dict]] = [None] * len(html_files)
    errors: List[Tuple[Path, Exception]] = []

    def handle_result(index: int, path: Path, future_result: Dict) -> None:
        reports[index] = future_result
        logging.info("Processed %s (%d images)", path, future_result["image_count"])

    if workers and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(build_report, path, base_url): (idx, path)
                for idx, path in enumerate(html_files)
            }
            for future in as_completed(future_map):
                idx, path = future_map[future]
                try:
                    result = future.result()
                    handle_result(idx, path, result)
                except Exception as exc:
                    logging.exception("Failed to process %s", path)
                    errors.append((path, exc))
                    if fail_fast:
                        raise
    else:
        for idx, path in enumerate(html_files):
            try:
                result = build_report(path, base_url)
                handle_result(idx, path, result)
            except Exception as exc:
                logging.exception("Failed to process %s", path)
                errors.append((path, exc))
                if fail_fast:
                    raise

    filtered_reports = [report for report in reports if report is not None]
    return filtered_reports, errors


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    html_files = resolve_targets(args.targets)
    reports, errors = gather_reports(html_files, args.base_url, args.workers, args.fail_fast)

    if args.csv_out:
        write_csv(reports, args.csv_out)
    else:
        json.dump(reports, indent=2, fp=sys.stdout)

    if errors:
        logging.warning("Completed with %d errors.", len(errors))
        for path, exc in errors:
            logging.warning(" - %s: %s", path, exc)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

