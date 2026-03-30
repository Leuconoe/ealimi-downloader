import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import requests

from ealimi_downloader.cli import build_parser
from ealimi_downloader.crawler import (
    EalimiClient,
    SEARCH_API_URL,
    load_index,
    normalize_notice_url_inputs,
    parse_login_form,
    parse_notice_page,
    parse_search_page_state,
    parse_search_form,
    parse_search_results_page,
    process_notice_refs,
    response_requires_login,
    save_index,
    save_run_summary,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(
        self,
        url: str,
        text: str = "",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        history: list["FakeResponse"] | None = None,
        body: bytes = b"",
    ) -> None:
        self.url: str = url
        self.text: str = text
        self.status_code: int = status_code
        self.headers: dict[str, str] = headers or {
            "content-type": "text/html; charset=utf-8"
        }
        self.history: list[FakeResponse] = history or []
        self._body: bytes = body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 65536):
        _ = chunk_size
        if self._body:
            yield self._body

    def json(self) -> object:
        return json.loads(self.text)


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.notice_html: dict[str, str] = {
            "1001": read_fixture("notice_page.html"),
            "1002": read_fixture("notice_page.html").replace(
                "봄 소풍 사진", "교실 사진"
            ),
            "1003": read_fixture("notice_page.html").replace(
                "봄 소풍 사진", "행사 사진"
            ),
        }
        self.binary_payloads: dict[str, bytes] = {
            "https://www.ealimi.com/Files3/6203/Board/attach/202603/photo1.jpg": b"image-one",
            "https://www.ealimi.com/Files3/6203/Board/attach/202603/photo2.jpg": b"image-two",
        }

    def request(
        self, method: str, url: str, timeout: int = 30, **kwargs: Any
    ) -> FakeResponse:
        _ = timeout
        params = cast(dict[str, str] | None, kwargs.get("params"))
        effective_url = url
        if params:
            effective_url = f"{url}?{urlencode(params)}"
        self.requests.append((method, effective_url, kwargs))

        if method == "GET" and effective_url == "https://www.ealimi.com/Member/SignIn":
            return FakeResponse(url=effective_url, text=read_fixture("login_page.html"))

        if method == "POST" and effective_url.startswith(
            "https://www.ealimi.com/Member/SignIn"
        ):
            return FakeResponse(
                url="https://www.ealimi.com/receivednoti",
                text="<html><body>ok</body></html>",
            )

        if method == "GET" and effective_url == "https://www.ealimi.com/receivednoti":
            return FakeResponse(
                url=effective_url, text=read_fixture("search_landing.html")
            )

        if (
            method == "GET"
            and effective_url.startswith("https://www.ealimi.com/receivednoti?")
            and "searchString=" in effective_url
        ):
            if "page=2" in effective_url:
                return FakeResponse(
                    url=effective_url, text=read_fixture("search_page_2.html")
                )
            return FakeResponse(
                url=effective_url, text=read_fixture("search_page_1.html")
            )

        if method == "GET" and "ReceivedNoti/Content" in effective_url:
            notice_id = effective_url.split("l_id=")[-1].split("&")[0]
            return FakeResponse(url=effective_url, text=self.notice_html[notice_id])

        if method == "POST" and effective_url == SEARCH_API_URL:
            form_data = cast(dict[str, str], kwargs.get("data") or {})
            page = form_data.get("page", "1")
            search_text = form_data.get("searchText", "")
            if search_text != "사진":
                return FakeResponse(
                    url=effective_url,
                    text=json.dumps({"IsSuccess": True, "Data": []}),
                    headers={"content-type": "application/json; charset=utf-8"},
                )
            if page == "1":
                rows = [
                    {"L_ID": 1001, "AddrID": 2001},
                    {"L_ID": 1002, "AddrID": 2001},
                ]
            elif page == "2":
                rows = [{"L_ID": 1003, "AddrID": 2001}]
            else:
                rows = []
            return FakeResponse(
                url=effective_url,
                text=json.dumps({"IsSuccess": True, "Data": rows}),
                headers={"content-type": "application/json; charset=utf-8"},
            )

        if method == "GET" and effective_url in self.binary_payloads:
            return FakeResponse(
                url=effective_url,
                headers={"content-type": "image/jpeg"},
                body=self.binary_payloads[effective_url],
            )

        raise AssertionError(f"Unexpected request: {method} {effective_url}")


class ParserTests(unittest.TestCase):
    def test_parse_login_form_preserves_hidden_fields(self) -> None:
        form = parse_login_form(
            read_fixture("login_page.html"), "https://www.ealimi.com/Member/SignIn"
        )
        self.assertEqual(
            form.action_url,
            "https://www.ealimi.com/Member/SignIn?returnURL=%2Freceivednoti",
        )
        self.assertEqual(
            form.hidden_fields["__RequestVerificationToken"], "token-12345"
        )
        self.assertEqual(form.hidden_fields["deviceType"], "desktop")
        self.assertEqual(form.hidden_fields["deviceToken"], "device-token-abc")

    def test_parse_notice_page_extracts_metadata_and_attachments(self) -> None:
        notice = parse_notice_page(
            read_fixture("notice_page.html"),
            "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1001&addrid=2001",
        )
        self.assertEqual(notice.notice_id, "1001")
        self.assertEqual(notice.addrid, "2001")
        self.assertEqual(notice.title, "봄 소풍 사진")
        self.assertEqual(notice.author, "김선생님")
        self.assertEqual(notice.class_name, "햇살반")
        self.assertIn("아이들이 신나게 뛰어놀았습니다.", notice.body_text)
        self.assertEqual(len(notice.attachments), 2)
        self.assertEqual(
            notice.attachments[0].url,
            "https://www.ealimi.com/Files3/6203/Board/attach/202603/photo1.jpg",
        )

    def test_parse_search_results_page_extracts_notice_links_and_pagination(
        self,
    ) -> None:
        page = parse_search_results_page(
            read_fixture("search_page_1.html"),
            "https://www.ealimi.com/receivednoti?searchString=%EC%82%AC%EC%A7%84",
        )
        self.assertEqual(
            page.notice_urls,
            [
                "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1001&addrid=2001",
                "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1002&addrid=2001",
            ],
        )
        self.assertEqual(
            page.pagination_urls,
            [
                "https://www.ealimi.com/receivednoti?searchString=%EC%82%AC%EC%A7%84&page=2"
            ],
        )

    def test_parse_search_form_discovers_keyword_field(self) -> None:
        form = parse_search_form(
            read_fixture("search_landing.html"),
            "https://www.ealimi.com/receivednoti",
        )
        self.assertEqual(form.action_url, "https://www.ealimi.com/receivednoti")
        self.assertEqual(form.method, "get")
        self.assertEqual(form.keyword_field, "searchText")
        self.assertEqual(form.hidden_fields["category"], "received")

    def test_parse_search_page_state_reads_hidden_defaults(self) -> None:
        state = parse_search_page_state(
            read_fixture("search_landing.html"),
            "https://www.ealimi.com/receivednoti",
        )
        self.assertEqual(state.keyword_field, "searchText")
        self.assertEqual(state.is_all, "0")
        self.assertEqual(state.list_date, "90")
        self.assertEqual(state.is_api, "1")

    def test_response_requires_login_detects_signin_redirect_or_fallback(self) -> None:
        redirect = FakeResponse(
            url="https://www.ealimi.com/Member/SignIn",
            text=read_fixture("login_page.html"),
        )
        self.assertTrue(
            response_requires_login(cast(requests.Response, cast(object, redirect)))
        )


class WorkflowTests(unittest.TestCase):
    def test_client_login_posts_hidden_fields_and_creds(self) -> None:
        session = FakeSession()
        client = EalimiClient(session=cast(requests.Session, cast(object, session)))
        client.login(username="demo-user", password="demo-pass")

        post_requests = [item for item in session.requests if item[0] == "POST"]
        self.assertEqual(len(post_requests), 1)
        _, _, kwargs = post_requests[0]
        payload = cast(dict[str, str], kwargs["data"])
        self.assertEqual(payload["id"], "demo-user")
        self.assertEqual(payload["pw"], "demo-pass")
        self.assertEqual(payload["__RequestVerificationToken"], "token-12345")

    def test_search_collects_all_notice_urls_across_pagination(self) -> None:
        client = EalimiClient(
            session=cast(requests.Session, cast(object, FakeSession()))
        )
        urls = client.collect_notice_urls_for_keyword("사진")
        self.assertEqual(
            urls,
            [
                "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1001&addrid=2001",
                "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1002&addrid=2001",
                "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1003&addrid=2001",
            ],
        )

    def test_process_notice_refs_writes_notice_outputs_and_indices(self) -> None:
        client = EalimiClient(
            session=cast(requests.Session, cast(object, FakeSession()))
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            index = load_index(output_root / "download_index.json")
            results = process_notice_refs(
                client=client,
                notice_urls=normalize_notice_url_inputs(
                    [
                        "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1001&addrid=2001"
                    ]
                ),
                output_root=output_root,
                index=index,
            )
            save_index(output_root / "download_index.json", index)
            summary_path = save_run_summary(output_root, results)

            self.assertEqual(results[0]["status"], "downloaded")
            manifest_path = output_root / cast(str, results[0]["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["title"], "봄 소풍 사진")
            self.assertEqual(len(manifest["attachments"]), 2)
            self.assertTrue((output_root / "download_index.json").exists())
            self.assertTrue(summary_path.exists())

    def test_parser_accepts_urls_and_search_keyword(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "https://www.ealimi.com/ReceivedNoti/Content/?l_id=1001&addrid=2001",
                "--urls-file",
                "urls.txt",
                "--search-keyword",
                "사진",
            ]
        )
        self.assertEqual(args.search_keyword, "사진")
        self.assertEqual(args.urls_file, ["urls.txt"])
        self.assertEqual(len(args.urls), 1)


if __name__ == "__main__":
    _ = unittest.main()
