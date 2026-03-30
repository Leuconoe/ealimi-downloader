# eAlimi Downloader

Python CLI for backing up photo-based notices from `https://www.ealimi.com/`.

It supports two workflows:

- crawl one or more direct notice URLs like `/ReceivedNoti/Content/?l_id=12345678&addrid=87654321`
- search the authenticated `receivednoti` inbox by keyword and crawl every matching notice

## Features

- logs in with a normal eAlimi web account using the current SSR + AJAX sign-in flow
- accepts direct notice URLs from CLI arguments or text files
- crawls keyword results through the live `/ReceivedNoti/IndexThumnailJson` endpoint used by the site
- downloads notice photos into per-notice folders
- writes `manifest.json`, `notice.txt`, `download_index.json`, and `run_summary.json`
- keeps local-only state and agent notes out of git with `.gitignore`

## Project Layout

```text
ealimi_downloader/
  __main__.py
  cli.py
  crawler.py
tests/
  fixtures/
  test_ealimi_downloader.py
```

## Requirements

- Python 3.10+
- `requests`

Install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Configuration

Create a local `.env` file from `.env.example`.

```env
EALIMI_USERNAME=your-login-id
EALIMI_PASSWORD=your-password
EALIMI_OUTPUT=downloads
```

Do not commit `.env`.

## Usage

Direct notice crawl:

```bash
python -m ealimi_downloader \
  --username YOUR_ID \
  --password YOUR_PASSWORD \
  "https://www.ealimi.com/ReceivedNoti/Content/?l_id=12345678&addrid=87654321"
```

Multiple direct URLs from file:

```bash
python -m ealimi_downloader \
  --urls-file notice_urls.txt \
  --output downloads_direct
```

Keyword search crawl:

```bash
python -m ealimi_downloader \
  --search-keyword 사진 \
  --output downloads_keyword
```

You can also combine direct URLs and keyword search in one run.

## Output

```text
downloads/
  notices/
    20260327_12345678_sample_notice/
      manifest.json
      notice.txt
      photo_001_sample.jpg
  download_index.json
  run_summary.json
```

- `manifest.json`: notice metadata and downloaded attachment list
- `notice.txt`: simplified text summary
- `download_index.json`: dedupe index for notices and assets
- `run_summary.json`: per-run result summary

## Testing

Run the offline test suite:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

CLI smoke check:

```bash
python -m ealimi_downloader --help
```

## Notes

- The current implementation follows the live eAlimi web contract observed during development: AJAX JSON login handling and `/ReceivedNoti/IndexThumnailJson` for keyword result paging.
- If eAlimi changes those endpoints or field names, the crawler will need to be updated.
- Examples in this README use masked placeholder IDs and addresses only.
