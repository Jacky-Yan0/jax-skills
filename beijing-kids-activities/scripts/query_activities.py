#!/usr/bin/env python3
"""
Query parent-child activities at Beijing kindergartens from the 3ren.cn
baby-map-center POI API.

Usage:
    python query_activities.py --keywords "中华女子" --start-time 1783180800000
    python query_activities.py --keywords "亲子" --start-time 1783180800000 --page-size 20
    python query_activities.py --keywords "幼儿园" --start-time 1783180800000 --debug
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from io import BytesIO


API_URL = (
    "https://api.3ren.cn/baby-map-center/poi/getSimplePage"
    "?v=0.011624866969903058"
)

DEFAULT_LATITUDE = 39.992465056392575
DEFAULT_LONGITUDE = 116.41426729298928

BASE_PAYLOAD: dict = {
    "activityType": [],
    "activityStatus": [],
    "activityRegisterStatus": [],
    "activityAge": [],
    "activityArea": [],
    "activityCycles": [],
    "dataType": 6,
    "isMove": 0,
    "latitude": DEFAULT_LATITUDE,
    "longitude": DEFAULT_LONGITUDE,
    "personLatitude": DEFAULT_LATITUDE,
    "personLongitude": DEFAULT_LONGITUDE,
}

HEADERS = {
    "Host": "api.3ren.cn",
    "Connection": "keep-alive",
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def build_payload(*, keywords: str, start_time: int, page_index: int, page_size: int) -> dict:
    """Construct the full request payload from user parameters."""
    payload = dict(BASE_PAYLOAD)
    payload["keywords"] = keywords
    payload["startTime"] = start_time
    payload["pageIndex"] = page_index
    payload["pageSize"] = page_size
    return payload


def _make_ssl_context(no_verify: bool = False) -> ssl.SSLContext:
    """Create an SSL context. On macOS the default cert chain sometimes fails."""
    ctx = ssl.create_default_context()
    if no_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def query_activities(
    *,
    keywords: str,
    start_time: int,
    page_index: int = 1,
    page_size: int = 50,
    debug: bool = False,
    no_verify_ssl: bool = False,
) -> dict:
    """Send the POST request and return the parsed JSON response."""
    payload = build_payload(
        keywords=keywords,
        start_time=start_time,
        page_index=page_index,
        page_size=page_size,
    )

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(API_URL, data=body, headers=HEADERS, method="POST")
    ssl_ctx = _make_ssl_context(no_verify=no_verify_ssl)

    if debug:
        print(f"[DEBUG] Request URL: {API_URL}", file=sys.stderr)
        print(f"[DEBUG] Request headers: {json.dumps(HEADERS, indent=2)}", file=sys.stderr)
        print(f"[DEBUG] Request body: {json.dumps(payload, ensure_ascii=False, indent=2)}", file=sys.stderr)

    try:
        with urllib.request.urlopen(req, context=ssl_ctx) as resp:
            raw_bytes = resp.read()
            # Handle gzip content-encoding
            content_encoding = resp.headers.get("Content-Encoding", "")
            if "gzip" in content_encoding:
                raw_bytes = gzip.GzipFile(fileobj=BytesIO(raw_bytes)).read()
            raw = raw_bytes.decode("utf-8")
            if debug:
                print(f"[DEBUG] Response status: {resp.status}", file=sys.stderr)
            result = json.loads(raw)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        try:
            print(e.read().decode("utf-8"), file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}", file=sys.stderr)
        sys.exit(1)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query parent-child activities at Beijing kindergartens (北京幼儿园亲子活动)"
    )
    parser.add_argument(
        "--keywords",
        type=str,
        required=True,
        help='Search keywords, e.g. "中华女子", "亲子", "幼儿园活动"',
    )
    parser.add_argument(
        "--start-time",
        type=int,
        required=True,
        help="Start time as epoch timestamp in milliseconds, e.g. 1783180800000",
    )
    parser.add_argument(
        "--page-index",
        type=int,
        default=1,
        help="Page number for pagination (default: 1)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        choices=[10, 20, 30, 50],
        help="Results per page (default: 50)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug info (request/response) to stderr",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL certificate verification (useful on macOS with cert issues)",
    )

    args = parser.parse_args()

    result = query_activities(
        keywords=args.keywords,
        start_time=args.start_time,
        page_index=args.page_index,
        page_size=args.page_size,
        debug=args.debug,
        no_verify_ssl=args.no_verify_ssl,
    )

    # Pretty-print the JSON result to stdout
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
