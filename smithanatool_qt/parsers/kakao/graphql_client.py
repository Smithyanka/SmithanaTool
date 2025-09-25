
# -*- coding: utf-8 -*-
"""
Thin GraphQL client for Kakao Page (listing episodes only).
Uses public bff-page.kakao.com/graphql seen in HAR.
NOTE: This does NOT bypass paywall; it only lists episodes and builds viewer URLs.
"""

import re
import requests

GRAPHQL_URL = "https://bff-page.kakao.com/graphql"

CONTENT_HOME_PRODUCT_LIST = """
query contentHomeProductList(
  $after: String,
  $first: Int,
  $seriesId: Long!,
  $boughtOnly: Boolean,
  $sortType: String
) {
  contentHomeProductList(
    seriesId: $seriesId
    after: $after
    first: $first
    boughtOnly: $boughtOnly
    sortType: $sortType
  ) {
    totalCount
    pageInfo { hasNextPage endCursor hasPreviousPage startCursor }
    edges {
      cursor
      node {
        row1
        scheme
        single { productId isFree title slideType operatorProperty { isTextViewer } }
        isViewed
      }
    }
  }
}
""".strip()


def _cookiejar_from_raw(session: requests.Session, raw_cookie: str, domain=".kakao.com"):
    if not raw_cookie:
        return
    for part in raw_cookie.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            session.cookies.set(k.strip(), v.strip(), domain=domain)


class KakaoGraphQL:
    def __init__(self, cookie_raw: str | None = None,
                 user_agent: str | None = None,
                 lang_cookie: str = "ko"):
        self.s = requests.Session()
        _cookiejar_from_raw(self.s, cookie_raw)

        if lang_cookie:
            try:
                self.s.cookies.set("kd_lang", lang_cookie, domain=".kakao.com")
            except Exception:
                pass

        self.s.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Origin": "https://page.kakao.com",
            "Referer": "https://page.kakao.com/"
        })

    def _post(self, payload: dict) -> dict:
        r = self.s.post(GRAPHQL_URL, json=payload, timeout=15)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"errors": [{"message": "Invalid JSON from GraphQL"}]}

    def list_episodes(self, series_id: int, sort: str = "desc", page_size: int = 50):
        after = None
        while True:
            variables = {
                "seriesId": int(series_id),
                "sortType": sort,
                "boughtOnly": False,
                "first": int(page_size),
            }
            if after:
                variables["after"] = after

            # ВАЖНО: не передаём headers=self.headers — у сессии уже стоят заголовки
            r = self.s.post(
                GRAPHQL_URL,
                json={"query": CONTENT_HOME_PRODUCT_LIST, "variables": variables},
                timeout=30
            )
            r.raise_for_status()
            payload = r.json()
            data = payload["data"]["contentHomeProductList"]

            for edge in data.get("edges") or []:
                node = edge["node"]
                title = (node.get("single") or {}).get("title") or node.get("row1") or ""
                product_id = (node.get("single") or {}).get("productId")
                is_free = (node.get("single") or {}).get("isFree")
                is_viewed = node.get("isViewed", False)
                scheme = node.get("scheme")

                m = re.search(r"(\d+)\s*화", title or "")
                ep_no = int(m.group(1)) if m else None

                yield {
                    "cursor": edge["cursor"],
                    "productId": product_id,
                    "title": title,
                    "episodeNo": ep_no,
                    "isFree": is_free,
                    "isViewed": is_viewed,
                    "scheme": scheme,
                }

            page = data["pageInfo"]
            if page["hasNextPage"]:
                after = page["endCursor"]
            else:
                break

    @staticmethod
    def viewer_url(series_id: int, product_id: int) -> str:
        return f"https://page.kakao.com/viewer?product_id={product_id}&series_id={series_id}"

    # ⬇️ Перенесённый метод
    def ready_to_use_ticket(self, series_id: int, product_id: int) -> dict:
        payload = {
            "operationName": "readyToUseTicket",
            "query": READY_TO_USE_TICKET,
            "variables": {"seriesId": int(series_id), "productId": int(product_id)}
        }
        r = self._post(payload)
        return (r.get("data", {}) or {}).get("readyToUseTicket") or {}



READY_TO_USE_TICKET = """
query readyToUseTicket($seriesId: Long!, $productId: Long!) {
  readyToUseTicket(seriesId: $seriesId, productId: $productId) {
    single { readAccessType title waitfreeBlock isDone }
    my { cashAmount ticketOwnCount ticketRentalCount }
    available { ticketRentalType ticketOwnType }
    rentalPeriodByMinute
  }
}
"""


VIEWER_INFO = """
query viewerInfo($seriesId: Long!, $productId: Long!) {
  viewerInfo(seriesId: $seriesId, productId: $productId) {
    viewerData {
      __typename
      ... on TextViewerData {
        atsServerUrl
        metaSecureUrl
        contentsList { chapterId contentId secureUrl }
      }
    }
    item { title productId }
    seriesItem { title seriesId }
  }
}
"""

def viewer_info_text(self, series_id: int, product_id: int) -> dict:
    payload = {
        "operationName": "viewerInfo",
        "query": VIEWER_INFO,
        "variables": {"seriesId": int(series_id), "productId": int(product_id)}
    }
    r = self._post(payload)
    return (r.get("data", {}) or {}).get("viewerInfo") or {}
