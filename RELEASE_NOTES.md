# Release Notes

## 2026-03-30 - Initial eAlimi Downloader Release

### Highlights

- Added a Python CLI for backing up eAlimi notice photos.
- Supports direct notice URLs and authenticated keyword search from `receivednoti`.
- Stores downloads in per-notice folders with `manifest.json`, `notice.txt`, `download_index.json`, and `run_summary.json`.

### Implemented

- SSR login form parsing with current AJAX JSON sign-in handling.
- Direct notice crawling for masked URLs shaped like `/ReceivedNoti/Content/?l_id=********&addrid=********`.
- Keyword crawl support through the live `/ReceivedNoti/IndexThumnailJson` paging endpoint.
- Offline parser and workflow tests using local fixtures.
- Local-only ignore rules for `.env`, `.agents`, and download output folders.

### Validation

- Offline verification passed with `python -m unittest discover -s tests -p "test_*.py"`.
- CLI smoke check passed with `python -m ealimi_downloader --help`.
- Live validation confirmed:
  - 1 direct notice crawl completed successfully
  - 1 keyword search crawl completed successfully
  - 4 notices were collected from the tested keyword run

### Privacy

- Release notes and repository docs use masked examples only.
- No real account ID, password, notice ID, address ID, child name, or classroom identifier is included here.

### Operational Note

- The current crawler matches the live eAlimi web contract observed during development, including AJAX login success handling and JSON-backed keyword result paging.
- If eAlimi changes those endpoints or field names, the crawler may need a small compatibility update.
