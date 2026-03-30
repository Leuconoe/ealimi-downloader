import argparse
import getpass
import logging
import sys
from pathlib import Path
from typing import cast

from .crawler import (
    DEFAULT_OUTPUT_DIR,
    EalimiClient,
    extract_urls_from_file,
    load_index,
    load_settings,
    normalize_notice_url_inputs,
    process_notice_refs,
    save_index,
    save_run_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download photos from direct eAlimi notice URLs and/or crawl all notice "
            "results for a keyword on /receivednoti."
        )
    )
    _ = parser.add_argument("urls", nargs="*", help="Direct eAlimi notice content URLs")
    _ = parser.add_argument(
        "--urls-file",
        action="append",
        help="Text file with notice URLs, one per line (# comments allowed)",
    )
    _ = parser.add_argument(
        "--search-keyword",
        help="Keyword to search on /receivednoti before downloading every matching notice",
    )
    _ = parser.add_argument("--username", help="eAlimi login id (or EALIMI_USERNAME)")
    _ = parser.add_argument(
        "--password", help="eAlimi login password (or EALIMI_PASSWORD)"
    )
    _ = parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output root directory (default: downloads)",
    )
    _ = parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    _ = parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def resolve_credentials(
    args: argparse.Namespace, settings: dict[str, str]
) -> tuple[str, str]:
    username_arg = cast(str | None, args.username)
    password_arg = cast(str | None, args.password)
    username = (username_arg or settings.get("EALIMI_USERNAME") or "").strip()
    password = (password_arg or settings.get("EALIMI_PASSWORD") or "").strip()
    if not username:
        username = input("eAlimi id: ").strip()
    if not password:
        password = getpass.getpass("eAlimi password: ").strip()
    if not username or not password:
        raise RuntimeError("Username and password are required.")
    return username, password


def collect_direct_urls(args: argparse.Namespace) -> list[str]:
    merged = list(cast(list[str], args.urls))
    for file_name in cast(list[str] | None, args.urls_file) or []:
        merged.extend(extract_urls_from_file(Path(file_name).expanduser().resolve()))
    return normalize_notice_url_inputs(merged)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    search_keyword = cast(str | None, args.search_keyword)
    urls = cast(list[str], args.urls)
    urls_file = cast(list[str] | None, args.urls_file)
    verbose = cast(bool, args.verbose)
    output_arg = cast(str | None, args.output)
    timeout = cast(int, args.timeout)

    if not search_keyword and not urls and not urls_file:
        parser.error(
            "Provide at least one notice URL, --urls-file, or --search-keyword"
        )

    configure_logging(verbose)
    settings = load_settings()
    username, password = resolve_credentials(args, settings)

    output_value = (
        output_arg or settings.get("EALIMI_OUTPUT") or str(DEFAULT_OUTPUT_DIR)
    )
    output_root = Path(output_value).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    client = EalimiClient(timeout=timeout)
    logging.info("Logging in to eAlimi")
    client.login(username=username, password=password)

    notice_urls = collect_direct_urls(args)
    if search_keyword:
        logging.info("Searching /receivednoti for keyword: %s", search_keyword)
        search_urls = client.collect_notice_urls_for_keyword(search_keyword)
        notice_urls.extend(search_urls)

    normalized_notice_urls = normalize_notice_url_inputs(notice_urls)
    if not normalized_notice_urls:
        raise RuntimeError("No valid notice URLs found after input normalization.")

    logging.info("Processing %s notice URL(s)", len(normalized_notice_urls))
    index = load_index(output_root / "download_index.json")
    results = process_notice_refs(
        client=client,
        notice_urls=normalized_notice_urls,
        output_root=output_root,
        index=index,
    )
    save_index(output_root / "download_index.json", index)
    summary_path = save_run_summary(output_root=output_root, results=results)

    downloaded = sum(1 for result in results if result["status"] == "downloaded")
    skipped = sum(
        1 for result in results if str(result.get("status", "")).startswith("skipped")
    )
    failed = sum(1 for result in results if result["status"] == "failed")

    logging.info("Done")
    logging.info("Downloaded: %s, skipped: %s, failed: %s", downloaded, skipped, failed)
    logging.info("Run summary: %s", summary_path)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
