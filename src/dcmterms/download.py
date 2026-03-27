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


def _discover_cid_urls(base_url: str, session: requests.Session) -> list[str]:
    """Discover all sect_CID_*.html file URLs from the directory listing."""
    listing_url = base_url.rstrip("/") + "/"
    logger.info("Fetching directory listing from %s", listing_url)

    resp = session.get(listing_url, timeout=60)
    resp.raise_for_status()

    # Extract all sect_CID_*.html references from the directory listing
    pattern = re.compile(r'HREF="[^"]*?(sect_CID_\d+\.html)"', re.IGNORECASE)
    filenames = sorted(set(pattern.findall(resp.text)))

    if not filenames:
        raise RuntimeError(
            f"No sect_CID_*.html files found in directory listing at {listing_url}"
        )

    logger.info("Discovered %d CID files", len(filenames))
    return [base_url.rstrip("/") + "/" + f for f in filenames]


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


def download_chtml(
    base_url: str = DEFAULT_BASE_URL,
    cache_dir: Path | None = None,
    max_workers: int = 2,
    delay: float = 0.25,
) -> Path:
    """Download all CID CHTML files from the DICOM standard website.

    Uses throttled parallel downloads to avoid overwhelming the server.
    With default settings (2 workers, 0.25s delay), effective rate is
    ~2 requests/second.

    Returns the directory containing downloaded files.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "dcmterms/0.1.0"})

    urls = _discover_cid_urls(base_url, session)

    # Determine cache directory
    if cache_dir is None:
        cache_dir = Path("cache/part16")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    existing = list(cache_dir.glob("sect_CID_*.html"))
    if len(existing) >= len(urls):
        logger.info(
            "Cache already has %d files (need %d), skipping download",
            len(existing),
            len(urls),
        )
        return cache_dir

    logger.info(
        "Downloading %d CID files to %s (workers=%d)",
        len(urls),
        cache_dir,
        max_workers,
    )

    # Also download chapter_B.html for reference
    dummy_lock = Lock()
    _download_file(
        base_url.rstrip("/") + "/chapter_B.html",
        cache_dir / "chapter_B.html",
        session,
        dummy_lock,
        0,
    )

    # Throttled parallel download
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

    logger.info("Downloading %d files (~%.0f MB estimated)", total_needed, total_needed * 85 / 1024)

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
