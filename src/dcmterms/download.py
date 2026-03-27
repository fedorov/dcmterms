"""Download CHTML files from the DICOM standard website."""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = (
    "https://dicom.nema.org/medical/dicom/current/output/chtml/part16/"
)


def _discover_urls(
    base_url: str,
    session: requests.Session,
    file_pattern: str,
    label: str,
) -> list[str]:
    """Discover file URLs from the directory listing matching a regex pattern."""
    listing_url = base_url.rstrip("/") + "/"
    logger.info("Fetching directory listing from %s", listing_url)

    resp = session.get(listing_url, timeout=60)
    resp.raise_for_status()

    pattern = re.compile(rf'HREF="[^"]*?({file_pattern})"', re.IGNORECASE)
    filenames = sorted(set(pattern.findall(resp.text)))

    if not filenames:
        raise RuntimeError(
            f"No {label} files found in directory listing at {listing_url}"
        )

    logger.info("Discovered %d %s files", len(filenames), label)
    return [base_url.rstrip("/") + "/" + f for f in filenames]


def _discover_cid_urls(base_url: str, session: requests.Session) -> list[str]:
    return _discover_urls(base_url, session, r"sect_CID_\d+\.html", "CID")


def _discover_tid_urls(base_url: str, session: requests.Session) -> list[str]:
    """Discover all TID-related file URLs: sect_TID_*, sect_*Templates.html, chapter_A.html."""
    listing_url = base_url.rstrip("/") + "/"
    resp = session.get(listing_url, timeout=60)
    resp.raise_for_status()

    text = resp.text
    files: set[str] = set()

    # Individual TID files
    for m in re.finditer(r'HREF="[^"]*?(sect_TID_\w+\.html)"', text, re.IGNORECASE):
        files.add(m.group(1))

    # Section template files (contain parent TIDs)
    for m in re.finditer(r'HREF="[^"]*?(sect_\w+Templates\.html)"', text, re.IGNORECASE):
        files.add(m.group(1))

    # chapter_A.html (contains base templates TID 300-1xxx)
    if "chapter_A.html" in text:
        files.add("chapter_A.html")

    logger.info("Discovered %d TID-related files", len(files))
    return [listing_url + f for f in sorted(files)]


def _download_file(
    url: str,
    dest: Path,
    session: requests.Session,
    throttle_lock: Lock,
    delay: float,
    max_retries: int = 3,
) -> bool:
    """Download a single file with retry logic and throttling. Returns True on success."""
    for attempt in range(max_retries):
        try:
            with throttle_lock:
                time.sleep(delay)
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return True
        except Exception:
            if attempt == max_retries - 1:
                logger.exception("Failed to download %s after %d attempts", url, max_retries)
                return False
            # Back off before retry
            time.sleep(2 ** attempt)
    return False


def _bulk_download(
    urls: list[str],
    cache_dir: Path,
    session: requests.Session,
    max_workers: int = 2,
    delay: float = 0.25,
) -> Path:
    """Throttled parallel download of URLs to cache_dir. Returns cache_dir."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    cached = 0
    to_download: list[tuple[str, Path]] = []
    for url in urls:
        filename = url.rsplit("/", 1)[-1]
        dest = cache_dir / filename
        if dest.exists():
            cached += 1
        else:
            to_download.append((url, dest))

    total_needed = len(to_download)
    if cached:
        logger.info("Skipping %d already-cached files", cached)
    if total_needed == 0:
        logger.info("All files already cached")
        return cache_dir

    logger.info("Downloading %d files", total_needed)

    succeeded = 0
    failed = 0
    throttle_lock = Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _download_file, url, dest, session, throttle_lock, delay
            ): url
            for url, dest in to_download
        }

        for future in as_completed(futures):
            if future.result():
                succeeded += 1
            else:
                failed += 1

            done = succeeded + failed
            if done % 50 == 0 or done == total_needed:
                pct = 100 * done / total_needed
                print(f"\r  [{done}/{total_needed}] {pct:.0f}%", end="", flush=True)

    print()  # newline after progress
    logger.info(
        "Download complete: %d succeeded, %d failed", succeeded, failed
    )
    return cache_dir


def download_chtml(
    base_url: str = DEFAULT_BASE_URL,
    cache_dir: Path | None = None,
    max_workers: int = 2,
    delay: float = 0.25,
) -> Path:
    """Download all CID CHTML files from the DICOM standard website.

    Returns the directory containing downloaded files.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "dcmterms/0.1.0"})

    urls = _discover_cid_urls(base_url, session)

    if cache_dir is None:
        cache_dir = Path("cache/part16")

    return _bulk_download(urls, cache_dir, session, max_workers, delay)


def download_tid_chtml(
    base_url: str = DEFAULT_BASE_URL,
    cache_dir: Path | None = None,
    max_workers: int = 2,
    delay: float = 0.25,
) -> Path:
    """Download all TID-related CHTML files from the DICOM standard website.

    Returns the directory containing downloaded files.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "dcmterms/0.1.0"})

    urls = _discover_tid_urls(base_url, session)

    if cache_dir is None:
        cache_dir = Path("cache/part16")

    return _bulk_download(urls, cache_dir, session, max_workers, delay)
