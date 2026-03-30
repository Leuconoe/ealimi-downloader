# 릴리스 노트

## 2026-03-30 - eAlimi Downloader 최초 공개

### 주요 내용

- e알리미 사진 공지를 백업할 수 있는 Python CLI를 추가했습니다.
- 직접 공지 URL 입력과 `receivednoti` 키워드 검색 수집을 모두 지원합니다.
- 공지별 폴더와 `manifest.json`, `notice.txt`, `download_index.json`, `run_summary.json`을 생성합니다.

### 구현 사항

- 현재 로그인 흐름에 맞는 SSR 로그인 form 파싱과 AJAX JSON 로그인 성공 처리
- `/ReceivedNoti/Content/?l_id=********&addrid=********` 형태의 마스킹된 직접 공지 URL 처리
- 실제 서비스에서 사용하는 `/ReceivedNoti/IndexThumnailJson` 기반 키워드 검색 결과 수집
- 로컬 fixture 기반 오프라인 파서/워크플로 테스트 추가
- `.env`, `.agents`, 다운로드 결과물을 제외하는 로컬 전용 ignore 규칙 추가

### 검증

- `python -m unittest discover -s tests -p "test_*.py"` 통과
- `python -m ealimi_downloader --help` 정상 동작 확인
- 실서비스 검증 결과:
  - 직접 공지 URL 1건 다운로드 성공
  - 키워드 검색 1회 실행 성공
  - 테스트한 키워드 실행에서 공지 4건 수집 확인

### 개인정보 보호

- 릴리스 노트와 저장소 문서에는 모두 마스킹된 예시만 사용했습니다.
- 실제 계정 ID, 비밀번호, 공지 ID, 주소 ID, 아동 이름, 반 이름은 포함하지 않았습니다.

### 운영 메모

- 현재 크롤러는 개발 시점의 실제 e알리미 웹 계약에 맞춰져 있습니다. 로그인 성공 판정은 AJAX JSON 응답 기준이며, 키워드 검색은 JSON 기반 페이지네이션으로 처리합니다.
- e알리미가 해당 엔드포인트나 필드 이름을 바꾸면 소규모 호환성 수정이 필요할 수 있습니다.
