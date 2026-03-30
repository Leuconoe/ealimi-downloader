# eAlimi Downloader

eAlimi의 직접 알림장 URL과 `/receivednoti` 검색 결과를 로컬로 백업하는 작은 Python CLI입니다.

## 요구사항

- Python 3.10+
- `requests`

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행

직접 알림장 URL:

```bash
python -m ealimi_downloader \
  --username YOUR_ID \
  --password YOUR_PASSWORD \
  "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1001&addrid=2001"
```

URL 파일 + 검색 키워드 동시 사용:

```bash
python -m ealimi_downloader \
  --username YOUR_ID \
  --password YOUR_PASSWORD \
  --urls-file notice_urls.txt \
  --search-keyword 사진 \
  -o output
```

## 동작 방식

- 로그인 페이지를 먼저 가져와서 `__RequestVerificationToken`과 hidden field를 보존합니다.
- 로그인 POST는 `id`, `pw` 필드를 사용합니다.
- 직접 URL 모드와 검색 모드는 같은 notice 처리 파이프라인을 공유합니다.
- 검색은 인증 후 `/receivednoti`의 실제 검색 form을 읽어 keyword 요청을 만들고, 페이지 내부 pagination 링크를 끝까지 따라갑니다.

## 출력 구조

```text
downloads/
  notices/
    20260330_1001_봄_소풍_사진/
      manifest.json
      notice.txt
      photo_001_photo1.jpg
      photo_002_photo2.jpg
  download_index.json
  run_summary.json
```

- `manifest.json`: notice 메타데이터와 첨부 사진 목록
- `notice.txt`: 읽기 쉬운 본문 요약
- `download_index.json`: notice/asset dedupe index
- `run_summary.json`: 실행 단위 요약

## 환경 변수

- `EALIMI_USERNAME`
- `EALIMI_PASSWORD`
- `EALIMI_OUTPUT`

`.env`를 지원하며, 셸 환경 변수가 있으면 우선 적용됩니다.

## 테스트

```bash
python -m unittest discover -s tests -p "test_*.py"
```
