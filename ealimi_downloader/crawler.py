from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse, urlunparse

import requests


BASE_URL = "https://www.ealimi.com"
LOGIN_URL = f"{BASE_URL}/Member/SignIn"
SEARCH_URL = f"{BASE_URL}/receivednoti"
SEARCH_API_URL = f"{BASE_URL}/ReceivedNoti/IndexThumnailJson"
DEFAULT_OUTPUT_DIR = Path("downloads")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
INDEX_VERSION = 1
ENV_PATHS = (Path(".env"),)
SUPPORTED_ENV_KEYS = {
    "EALIMI_USERNAME",
    "EALIMI_PASSWORD",
    "EALIMI_OUTPUT",
}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic")


class AuthenticationError(RuntimeError):
    pass


class IndexData(TypedDict):
    version: int
    notices: dict[str, str]
    assets: dict[str, str]
    updated_at: NotRequired[str]


@dataclass(frozen=True)
class LoginFormData:
    action_url: str
    hidden_fields: dict[str, str]


@dataclass(frozen=True)
class SearchResultsPage:
    notice_urls: list[str]
    pagination_urls: list[str]


@dataclass(frozen=True)
class SearchFormData:
    action_url: str
    method: str
    keyword_field: str
    hidden_fields: dict[str, str]


@dataclass(frozen=True)
class SearchPageState:
    keyword_field: str
    is_all: str
    list_date: str
    is_api: str
    search_status: str


@dataclass(frozen=True)
class NoticeAttachment:
    url: str
    suggested_name: str


@dataclass(frozen=True)
class NoticeData:
    source_url: str
    notice_id: str
    addrid: str
    canonical_url: str
    title: str
    body_text: str
    author: str
    published_at: str
    class_name: str
    attachments: list[NoticeAttachment]


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key in SUPPORTED_ENV_KEYS:
            loaded[key] = value
    return loaded


def load_settings() -> dict[str, str]:
    settings: dict[str, str] = {}
    for env_path in ENV_PATHS:
        settings.update(read_env_file(env_path))
    for key in SUPPORTED_ENV_KEYS:
        value = os.getenv(key)
        if value:
            settings[key] = value.strip()
    return settings


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned[:120] if len(cleaned) > 120 else cleaned


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def looks_like_image_url(url: str) -> bool:
    parsed = urlparse(url)
    lowered_path = parsed.path.lower()
    is_known_ealimi_path = (
        lowered_path.startswith("/files")
        or "/upload/" in lowered_path
        or "/uploads/" in lowered_path
        or "/board/attach/" in lowered_path
    )
    if parsed.netloc and parsed.netloc not in {"www.ealimi.com", "ealimi.com"}:
        return lowered_path.endswith(IMAGE_EXTENSIONS)
    return is_known_ealimi_path


def is_notice_content_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.lower().rstrip("/") == "/receivednoti/content"


def normalize_notice_url(url: str) -> str | None:
    text = url.strip()
    if not text:
        return None
    parsed = urlparse(text)
    if not parsed.scheme:
        if text.startswith("/"):
            parsed = urlparse(urljoin(BASE_URL, text))
        else:
            return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if not is_notice_content_url(
        urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))
    ):
        return None
    query = parse_qs(parsed.query)
    notice_id = (query.get("l_id") or [""])[0].strip()
    addrid = (query.get("addrid") or [""])[0].strip()
    if not notice_id or not addrid:
        return None
    normalized_query = f"l_id={quote_plus(notice_id)}&addrid={quote_plus(addrid)}"
    return urlunparse(
        ("https", parsed.netloc, "/ReceivedNoti/Content/", "", normalized_query, "")
    )


def normalize_notice_url_inputs(urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_url in urls:
        value = normalize_notice_url(raw_url)
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def extract_urls_from_file(file_path: Path) -> list[str]:
    urls: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        urls.append(text)
    return urls


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    stream: bool = False,
    allow_redirects: bool = True,
    timeout: int,
    retries: int = 3,
) -> requests.Response:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            response = session.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                data=data,
                stream=stream,
                allow_redirects=allow_redirects,
                timeout=timeout,
            )
            if response.status_code >= 500:
                response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


class LoginFormParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url: str = page_url
        self.active_form: bool = False
        self.found_named_fields: set[str] = set()
        self.action_url: str = page_url
        self.hidden_fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "form":
            form_id = attr_map.get("id", "")
            action = attr_map.get("action", "")
            if form_id == "form_datas" or not self.active_form:
                self.active_form = True
                self.action_url = urljoin(self.page_url, action or self.page_url)
            return

        if not self.active_form or tag != "input":
            return

        name = attr_map.get("name", "").strip()
        value = attr_map.get("value", "")
        input_type = attr_map.get("type", "").lower().strip()
        if name in {"id", "pw"}:
            self.found_named_fields.add(name)
        if name and input_type == "hidden":
            self.hidden_fields[name] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.active_form:
            self.active_form = False


class SearchFormParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.form_depth = 0
        self.current_action_url = page_url
        self.current_method = "get"
        self.current_hidden_fields: dict[str, str] = {}
        self.current_text_inputs: list[tuple[str, int]] = []
        self.selected_form: SearchFormData | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "form":
            self.form_depth += 1
            if self.form_depth == 1:
                action = attr_map.get("action", "")
                self.current_action_url = urljoin(
                    self.page_url, action or self.page_url
                )
                self.current_method = (attr_map.get("method", "get") or "get").lower()
                self.current_hidden_fields = {}
                self.current_text_inputs = []
            return

        if self.form_depth != 1 or tag != "input":
            return

        name = attr_map.get("name", "").strip()
        if not name:
            return

        input_type = (attr_map.get("type", "text") or "text").lower().strip()
        if input_type == "hidden":
            self.current_hidden_fields[name] = attr_map.get("value", "")
            return

        if input_type not in {"text", "search"}:
            return

        marker_text = " ".join(
            [
                name,
                attr_map.get("id", ""),
                attr_map.get("class", ""),
                attr_map.get("placeholder", ""),
            ]
        ).lower()
        score = 0
        if any(
            token in marker_text
            for token in {"search", "keyword", "find", "query", "검색"}
        ):
            score = 1
        self.current_text_inputs.append((name, score))

    def handle_endtag(self, tag: str) -> None:
        if tag != "form" or self.form_depth == 0:
            return

        if (
            self.form_depth == 1
            and self.selected_form is None
            and self.current_text_inputs
        ):
            keyword_field = max(self.current_text_inputs, key=lambda item: item[1])[0]
            self.selected_form = SearchFormData(
                action_url=self.current_action_url,
                method=self.current_method if self.current_method == "post" else "get",
                keyword_field=keyword_field,
                hidden_fields=dict(self.current_hidden_fields),
            )
        self.form_depth -= 1


def parse_search_form(html: str, page_url: str) -> SearchFormData:
    parser = SearchFormParser(page_url)
    parser.feed(html)
    if parser.selected_form is None:
        raise RuntimeError("Search form could not be located on /receivednoti.")
    return parser.selected_form


class SearchPageStateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.is_all = "0"
        self.list_date = "0"
        self.is_api = "1"
        self.search_status = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        attr_map = {key: value or "" for key, value in attrs}
        element_id = attr_map.get("id", "").strip()
        value = attr_map.get("value", "")
        if element_id == "isAll":
            self.is_all = value or "0"
        elif element_id == "listDate":
            self.list_date = value or "0"
        elif element_id == "isApi":
            self.is_api = value or "1"


def parse_search_page_state(html: str, page_url: str) -> SearchPageState:
    form = parse_search_form(html, page_url)
    parser = SearchPageStateParser()
    parser.feed(html)
    return SearchPageState(
        keyword_field=form.keyword_field,
        is_all=parser.is_all,
        list_date=parser.list_date,
        is_api=parser.is_api,
        search_status="",
    )


def parse_login_form(html: str, page_url: str) -> LoginFormData:
    parser = LoginFormParser(page_url)
    parser.feed(html)
    if "id" not in parser.found_named_fields or "pw" not in parser.found_named_fields:
        raise RuntimeError("Login form fields 'id' and 'pw' were not found.")
    token = parser.hidden_fields.get("__RequestVerificationToken", "")
    if not token:
        raise RuntimeError("Login anti-forgery token was not found.")
    return LoginFormData(
        action_url=parser.action_url, hidden_fields=dict(parser.hidden_fields)
    )


def is_login_page_html(html: str) -> bool:
    if "__RequestVerificationToken" not in html:
        return False
    login_markers = ['name="id"', "name='id'", 'name="pw"', "name='pw'"]
    return all(marker in html for marker in login_markers[:2]) or (
        'name="pw"' in html and 'name="id"' in html
    )


def response_requires_login(response: requests.Response) -> bool:
    parsed = urlparse(response.url)
    if parsed.path.lower().startswith("/member/signin"):
        return True
    for history_item in response.history:
        if (
            urlparse(history_item.headers.get("Location", ""))
            .path.lower()
            .startswith("/member/signin")
        ):
            return True
    content_type = response.headers.get("content-type", "")
    if "html" in content_type.lower() and is_login_page_html(response.text):
        return True
    return False


class SearchResultsParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url: str = page_url
        self.notice_urls: list[str] = []
        self.pagination_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {key: value or "" for key, value in attrs}
        href = attr_map.get("href", "").strip()
        if not href:
            return
        absolute_url = urljoin(self.page_url, href)
        normalized_notice = normalize_notice_url(absolute_url)
        if normalized_notice:
            self.notice_urls.append(normalized_notice)
            return

        parsed = urlparse(absolute_url)
        if parsed.path.lower().rstrip("/") == "/receivednoti":
            self.pagination_urls.append(
                urlunparse(
                    (parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, "")
                )
            )


def parse_search_results_page(html: str, page_url: str) -> SearchResultsPage:
    parser = SearchResultsParser(page_url)
    parser.feed(html)
    return SearchResultsPage(
        notice_urls=normalize_notice_url_inputs(parser.notice_urls),
        pagination_urls=sorted(set(parser.pagination_urls)),
    )


class NoticePageParser(HTMLParser):
    IMAGE_CONTAINER_TOKENS = {
        "editorhtml",
        "article_con",
        "notice_body",
        "article_body",
        "notice_photos",
    }
    BODY_TEXT_TOKENS = {
        "editorhtml",
        "article_con",
        "notice_body",
        "article_body",
    }

    FIELD_SELECTORS: dict[str, set[str]] = {
        "title": {"notice_title", "tit", "article_title", "title", "article_tit"},
        "body_text": {
            "notice_body",
            "noti_view_cont",
            "article_body",
            "editorhtml",
        },
        "published_at": {"notice_date", "write_date", "reg_date", "date", "reg_dt"},
        "author": {"author", "teacher_name", "writer", "reg_nm"},
        "class_name": {"class_name", "class", "kind_class", "school_name"},
    }

    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url: str = page_url
        self.field_stack: list[str | None] = []
        self.token_stack: list[set[str]] = []
        self.buffers: dict[str, list[str]] = {key: [] for key in self.FIELD_SELECTORS}
        self.attachments: list[str] = []
        self.page_title: list[str] = []
        self.capture_title_tag: bool = False
        self.ignore_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag in {"script", "style"}:
            self.ignore_depth += 1
            self.field_stack.append(None)
            return

        if tag == "title":
            self.capture_title_tag = True

        classes = set(
            (attr_map.get("class", "") + " " + attr_map.get("id", ""))
            .replace("-", "_")
            .lower()
            .split()
        )
        self.token_stack.append(classes)
        matched_field = None
        for field_name, tokens in self.FIELD_SELECTORS.items():
            if classes & tokens:
                matched_field = field_name
                break
        self.field_stack.append(matched_field)

        if tag == "img" and any(
            token_set & self.IMAGE_CONTAINER_TOKENS for token_set in self.token_stack
        ):
            for key in ("data-full-src", "data-origin-src", "data-src", "src"):
                candidate = attr_map.get(key, "").strip()
                if not candidate:
                    continue
                absolute_url = urljoin(self.page_url, candidate)
                if looks_like_image_url(absolute_url):
                    self.attachments.append(absolute_url)
                    break

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignore_depth > 0:
            self.ignore_depth -= 1
        if tag == "title":
            self.capture_title_tag = False
        if self.field_stack:
            _ = self.field_stack.pop()
        if self.token_stack:
            _ = self.token_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.ignore_depth > 0:
            return
        text = normalize_whitespace(data)
        if not text:
            return
        if self.capture_title_tag:
            self.page_title.append(text)
        for field_name in reversed(self.field_stack):
            if field_name is None:
                continue
            if field_name == "body_text" and not any(
                token_set & self.BODY_TEXT_TOKENS for token_set in self.token_stack
            ):
                continue
            self.buffers[field_name].append(text)
            break


def extract_notice_identity(url: str) -> tuple[str, str]:
    query = parse_qs(urlparse(url).query)
    notice_id = (query.get("l_id") or [""])[0].strip()
    addrid = (query.get("addrid") or [""])[0].strip()
    if not notice_id or not addrid:
        raise RuntimeError(f"Notice URL missing l_id or addrid: {url}")
    return notice_id, addrid


def parse_notice_page(html: str, page_url: str) -> NoticeData:
    parser = NoticePageParser(page_url)
    parser.feed(html)
    notice_id, addrid = extract_notice_identity(page_url)
    title = (
        normalize_whitespace(" ".join(parser.buffers["title"]))
        or normalize_whitespace(" ".join(parser.page_title))
        or f"notice-{notice_id}"
    )
    body_text = "\n".join(
        line
        for line in (normalize_whitespace(part) for part in parser.buffers["body_text"])
        if line
    )
    attachments: list[NoticeAttachment] = []
    for index, asset_url in enumerate(dict.fromkeys(parser.attachments), start=1):
        path_name = Path(urlparse(asset_url).path).name or f"photo_{index:03d}.jpg"
        suggested_name = sanitize_name(path_name) or f"photo_{index:03d}.jpg"
        attachments.append(
            NoticeAttachment(url=asset_url, suggested_name=suggested_name)
        )
    return NoticeData(
        source_url=page_url,
        canonical_url=normalize_notice_url(page_url) or page_url,
        notice_id=notice_id,
        addrid=addrid,
        title=title,
        body_text=body_text,
        author=normalize_whitespace(" ".join(parser.buffers["author"])),
        published_at=normalize_whitespace(" ".join(parser.buffers["published_at"])),
        class_name=normalize_whitespace(" ".join(parser.buffers["class_name"])),
        attachments=attachments,
    )


class EalimiClient:
    def __init__(
        self, *, timeout: int = 30, session: requests.Session | None = None
    ) -> None:
        self.timeout: int = timeout
        self.session: requests.Session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def login(self, *, username: str, password: str) -> None:
        login_page = request_with_retry(
            self.session, "GET", LOGIN_URL, timeout=self.timeout
        )
        login_page.raise_for_status()
        form = parse_login_form(login_page.text, login_page.url)
        payload = dict(form.hidden_fields)
        payload["id"] = username
        payload["pw"] = password
        login_response = request_with_retry(
            self.session,
            "POST",
            form.action_url,
            timeout=self.timeout,
            data=payload,
            headers={"Referer": login_page.url},
            allow_redirects=True,
        )
        login_response.raise_for_status()
        auth_check = request_with_retry(
            self.session, "GET", SEARCH_URL, timeout=self.timeout, allow_redirects=True
        )
        auth_check.raise_for_status()
        if response_requires_login(auth_check):
            raise AuthenticationError(
                "Login failed or eAlimi redirected back to the sign-in page."
            )

    def get_notice(self, notice_url: str) -> NoticeData:
        response = request_with_retry(
            self.session, "GET", notice_url, timeout=self.timeout, allow_redirects=True
        )
        response.raise_for_status()
        if response_requires_login(response):
            raise AuthenticationError(
                f"Authenticated notice fetch redirected to login: {notice_url}"
            )
        return parse_notice_page(response.text, response.url)

    def collect_notice_urls_for_keyword(self, keyword: str) -> list[str]:
        landing_response = request_with_retry(
            self.session,
            "GET",
            SEARCH_URL,
            timeout=self.timeout,
            allow_redirects=True,
        )
        landing_response.raise_for_status()
        if response_requires_login(landing_response):
            raise AuthenticationError("Search landing page redirected to login.")

        state = parse_search_page_state(landing_response.text, landing_response.url)
        notice_urls: list[str] = []
        seen_notices: set[str] = set()
        page_number = 1

        while True:
            payload = {
                "page": str(page_number),
                "pagePart": "4",
                state.keyword_field: keyword,
                "searchStatus": state.search_status,
                "isAll": state.is_all,
                "listDate": state.list_date,
                "isApi": state.is_api,
                "temp": str(int(datetime.now().timestamp() * 1000)),
            }
            response = request_with_retry(
                self.session,
                "POST",
                SEARCH_API_URL,
                timeout=self.timeout,
                allow_redirects=True,
                data=payload,
                headers={"Referer": landing_response.url},
            )
            response.raise_for_status()
            if response_requires_login(response):
                raise AuthenticationError("Search API request redirected to login.")

            payload_json = response.json()
            if not isinstance(payload_json, dict) or not payload_json.get("IsSuccess"):
                raise RuntimeError("Search API request failed.")
            rows = payload_json.get("Data")
            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                if not isinstance(row, dict):
                    continue
                notice_id = str(row.get("L_ID") or "").strip()
                addrid = str(row.get("AddrID") or "").strip()
                if not notice_id or not addrid:
                    continue
                notice_url = normalize_notice_url(
                    f"{BASE_URL}/ReceivedNoti/Content/?l_id={quote_plus(notice_id)}&addrid={quote_plus(addrid)}"
                )
                if not notice_url:
                    continue
                if notice_url not in seen_notices:
                    seen_notices.add(notice_url)
                    notice_urls.append(notice_url)
            page_number += 1

        return notice_urls

    def download_binary(self, url: str, destination: Path) -> int:
        response = request_with_retry(
            self.session, "GET", url, timeout=self.timeout, stream=True
        )
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    _ = handle.write(cast(bytes, chunk))
                    total += len(chunk)
        return total


def normalize_index(data: object) -> IndexData:
    if not isinstance(data, dict):
        return {"version": INDEX_VERSION, "notices": {}, "assets": {}}
    payload = cast(dict[object, object], data)
    notices_raw = payload.get("notices")
    assets_raw = payload.get("assets")
    notices: dict[object, object] = notices_raw if isinstance(notices_raw, dict) else {}
    assets: dict[object, object] = assets_raw if isinstance(assets_raw, dict) else {}
    return {
        "version": INDEX_VERSION,
        "notices": {str(key): str(value) for key, value in notices.items()},
        "assets": {str(key): str(value) for key, value in assets.items()},
    }


def load_index(index_path: Path) -> IndexData:
    if not index_path.exists():
        return normalize_index({})
    return normalize_index(
        cast(object, json.loads(index_path.read_text(encoding="utf-8")))
    )


def save_index(index_path: Path, index: IndexData) -> None:
    payload = normalize_index(index)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _ = index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_notice_folder_name(notice: NoticeData) -> str:
    date_digits = re.sub(r"[^0-9]", "", notice.published_at)[
        :8
    ] or datetime.now().strftime("%Y%m%d")
    title_part = sanitize_name(notice.title).replace(" ", "_") or "notice"
    return f"{date_digits}_{notice.notice_id}_{title_part}"


def write_notice_manifest(
    folder: Path, notice: NoticeData, attachments: list[dict[str, object]]
) -> Path:
    manifest_path = folder / "manifest.json"
    _ = manifest_path.write_text(
        json.dumps(
            {
                "notice_id": notice.notice_id,
                "addrid": notice.addrid,
                "canonical_url": notice.canonical_url,
                "source_url": notice.source_url,
                "title": notice.title,
                "author": notice.author,
                "class_name": notice.class_name,
                "published_at": notice.published_at,
                "body_text": notice.body_text,
                "attachments": attachments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def write_notice_text(folder: Path, notice: NoticeData) -> Path:
    text_path = folder / "notice.txt"
    lines = [
        f"title: {notice.title}",
        f"notice_id: {notice.notice_id}",
        f"addrid: {notice.addrid}",
        f"published_at: {notice.published_at}",
        f"class_name: {notice.class_name}",
        f"author: {notice.author}",
        "",
        notice.body_text,
    ]
    _ = text_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return text_path


def existing_notice_manifest(
    output_root: Path, index: IndexData, notice_url: str
) -> Path | None:
    relative_path = index.get("notices", {}).get(notice_url)
    if not relative_path:
        return None
    manifest_path = output_root / relative_path
    return manifest_path if manifest_path.exists() else None


def make_attachment_file_name(index: int, suggested_name: str) -> str:
    stem = sanitize_name(Path(suggested_name).stem) or f"photo_{index:03d}"
    suffix = Path(suggested_name).suffix or ".jpg"
    return f"photo_{index:03d}_{stem}{suffix}"


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def process_notice_refs(
    *,
    client: EalimiClient,
    notice_urls: list[str],
    output_root: Path,
    index: IndexData,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    notice_root = output_root / "notices"
    notice_root.mkdir(parents=True, exist_ok=True)

    for notice_url in normalize_notice_url_inputs(notice_urls):
        manifest_path = existing_notice_manifest(output_root, index, notice_url)
        if manifest_path is not None:
            results.append(
                {
                    "source_url": notice_url,
                    "status": "skipped_existing_notice",
                    "manifest": relative_posix(manifest_path, output_root),
                }
            )
            continue

        try:
            notice = client.get_notice(notice_url)
            folder = notice_root / build_notice_folder_name(notice)
            folder.mkdir(parents=True, exist_ok=True)
            _ = write_notice_text(folder, notice)

            attachment_results: list[dict[str, object]] = []
            for attachment_index, attachment in enumerate(notice.attachments, start=1):
                file_name = make_attachment_file_name(
                    attachment_index, attachment.suggested_name
                )
                file_path = folder / file_name
                bytes_written = client.download_binary(attachment.url, file_path)
                relative_file = relative_posix(file_path, output_root)
                index["assets"][attachment.url] = relative_file
                attachment_results.append(
                    {
                        "url": attachment.url,
                        "file": relative_file,
                        "bytes": bytes_written,
                    }
                )

            manifest = write_notice_manifest(folder, notice, attachment_results)
            relative_manifest = relative_posix(manifest, output_root)
            index["notices"][notice.canonical_url] = relative_manifest
            results.append(
                {
                    "source_url": notice_url,
                    "status": "downloaded",
                    "manifest": relative_manifest,
                    "attachment_count": len(attachment_results),
                    "folder": relative_posix(folder, output_root),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logging.exception("Failed to process notice: %s", notice_url)
            results.append(
                {
                    "source_url": notice_url,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return results


def save_run_summary(output_root: Path, results: list[dict[str, object]]) -> Path:
    summary_path = output_root / "run_summary.json"
    _ = summary_path.write_text(
        json.dumps(
            {
                "run_at": datetime.now().isoformat(timespec="seconds"),
                "notice_count": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary_path
