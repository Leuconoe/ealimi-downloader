# eAlimi Downloader

`https://www.ealimi.com/`에서 공유되는 사진 중심 공지를 로컬에 백업하기 위한 Python CLI입니다.

다음 두 가지 방식으로 사용할 수 있습니다.

- 직접 공지 URL 입력: `/ReceivedNoti/Content/?l_id=12345678&addrid=87654321` 형태의 URL 1개 이상 처리
- 받은 알리미 검색: 로그인 후 `receivednoti` 화면에서 키워드로 검색된 공지를 일괄 수집

## 주요 기능

- 현재 e알리미 웹 로그인 흐름(SSR + AJAX JSON 응답)에 맞춰 일반 계정으로 로그인
- CLI 인자 또는 텍스트 파일로 직접 공지 URL 여러 개 입력 가능
- 실제 서비스에서 사용하는 `/ReceivedNoti/IndexThumnailJson` 엔드포인트를 통해 키워드 검색 결과 수집
- 공지별 폴더에 사진 다운로드
- `manifest.json`, `notice.txt`, `download_index.json`, `run_summary.json` 생성
- `.gitignore`로 `.env`, 다운로드 결과물, 에이전트 메모 등 로컬 전용 파일 제외

## 프로젝트 구조

```text
ealimi_downloader/
  __main__.py
  cli.py
  crawler.py
tests/
  fixtures/
  test_ealimi_downloader.py
```

## 요구사항

- Python 3.10+
- `requests`

설치:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 설정

`.env.example`을 참고해 로컬 `.env` 파일을 만듭니다.

```env
EALIMI_USERNAME=your-login-id
EALIMI_PASSWORD=your-password
EALIMI_OUTPUT=downloads
```

`.env`는 커밋하지 않도록 되어 있습니다.

## 사용 방법

직접 공지 URL 다운로드:

```bash
python -m ealimi_downloader \
  --username YOUR_ID \
  --password YOUR_PASSWORD \
  "https://www.ealimi.com/ReceivedNoti/Content/?l_id=12345678&addrid=87654321"
```

여러 URL을 파일에서 읽기:

```bash
python -m ealimi_downloader \
  --urls-file notice_urls.txt \
  --output downloads_direct
```

키워드 검색 후 일괄 다운로드:

```bash
python -m ealimi_downloader \
  --search-keyword 사진 \
  --output downloads_keyword
```

직접 URL과 키워드 검색을 한 번에 같이 사용할 수도 있습니다.

## 출력 예시

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

- `manifest.json`: 공지 메타데이터와 다운로드한 첨부 목록
- `notice.txt`: 간단히 읽을 수 있는 본문 요약
- `download_index.json`: 공지/첨부 dedupe 인덱스
- `run_summary.json`: 실행 단위 결과 요약

## 테스트

오프라인 테스트 실행:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

CLI 도움말 확인:

```bash
python -m ealimi_downloader --help
```

## 참고 사항

- 현재 구현은 개발 시점의 실제 e알리미 웹 계약에 맞춰져 있습니다. 로그인 성공 판정은 AJAX JSON 응답 기준으로 처리하고, 키워드 검색은 `/ReceivedNoti/IndexThumnailJson` 기반으로 수집합니다.
- e알리미가 해당 엔드포인트나 필드 이름을 변경하면 작은 호환성 수정이 필요할 수 있습니다.
- 이 README의 예시는 모두 마스킹된 placeholder ID와 주소만 사용합니다.

## 릴리스 노트

- 최초 릴리스 요약과 검증 기록은 `RELEASE_NOTES.md`에서 볼 수 있습니다.
