#!/usr/bin/env python3
"""
One-time respectful crawler to mirror a website locally for image extraction.

Usage:
    python scripts/crawl_site.py https://automation.broadcom.com/ --output site_mirror/
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_robots_txt(base_url: str) -> RobotFileParser:
    """Check and parse robots.txt for crawl permissions."""
    robots_url = urljoin(base_url, "/robots.txt")
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        logger.info(f"Loaded robots.txt from {robots_url}")
    except Exception as e:
        logger.warning(f"Could not load robots.txt: {e}. Proceeding with caution.")
    return rp


def fetch_page(url: str, delay: float = 1.0) -> tuple[str, bytes] | None:
    """Fetch a single page with rate limiting."""
    try:
        time.sleep(delay)  # Rate limiting
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ImageInventoryBot/1.0; +https://github.com/saran-io/hubbmOS)"
        }
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
        return response.text, response.content
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def extract_links(soup: BeautifulSoup, base_url: str, domain: str) -> set[str]:
    """Extract all internal links from a page."""
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == domain or (not parsed.netloc and href.startswith("/")):
            links.add(full_url)
    return links


def save_page(url: str, content: bytes, output_dir: Path) -> Path:
    """Save page content to local file, preserving directory structure."""
    parsed = urlparse(url)
    path = parsed.path.strip("/") or "index.html"
    if not path.endswith((".html", ".htm")):
        path += ".html"
    file_path = output_dir / parsed.netloc / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    return file_path


def crawl_site(
    start_url: str,
    output_dir: Path,
    max_pages: int = 100,
    delay: float = 1.0,
    respect_robots: bool = True,
) -> None:
    """Crawl a website and save pages locally."""
    parsed_start = urlparse(start_url)
    domain = parsed_start.netloc
    base_url = f"{parsed_start.scheme}://{domain}"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check robots.txt
    rp = check_robots_txt(base_url) if respect_robots else None

    visited = set()
    to_visit = {start_url}
    pages_saved = 0

    logger.info(f"Starting crawl of {start_url} (max {max_pages} pages, delay {delay}s)")

    while to_visit and pages_saved < max_pages:
        url = to_visit.pop()
        if url in visited:
            continue

        # Check robots.txt
        if rp and not rp.can_fetch("ImageInventoryBot", url):
            logger.info(f"Skipping {url} (disallowed by robots.txt)")
            continue

        visited.add(url)
        logger.info(f"Fetching {url} ({pages_saved + 1}/{max_pages})")

        result = fetch_page(url, delay)
        if not result:
            continue

        html, content = result
        file_path = save_page(url, content, output_dir)
        pages_saved += 1
        logger.info(f"Saved to {file_path}")

        # Extract links for next pages
        try:
            soup = BeautifulSoup(html, "html.parser")
            new_links = extract_links(soup, url, domain)
            to_visit.update(new_links - visited)
        except Exception as e:
            logger.warning(f"Failed to parse links from {url}: {e}")

    logger.info(f"Crawl complete: {pages_saved} pages saved to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-time respectful website crawler for image extraction."
    )
    parser.add_argument(
        "url",
        type=str,
        help="Starting URL to crawl (e.g., https://automation.broadcom.com/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("site_mirror"),
        help="Output directory for mirrored pages (default: site_mirror/)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum number of pages to crawl (default: 100)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--no-robots",
        action="store_true",
        help="Ignore robots.txt (not recommended)",
    )
    args = parser.parse_args()

    crawl_site(
        args.url,
        args.output,
        max_pages=args.max_pages,
        delay=args.delay,
        respect_robots=not args.no_robots,
    )


if __name__ == "__main__":
    main()

