from __future__ import annotations

import json
import threading
import uuid
from typing import Any, Callable, Optional
from urllib.parse import urlencode

import requests

from smithanatool_qt.tabs.parsers.kakao.shared.utils.kakao_common import apply_raw_cookie, parse_json_response

GRAPHQL_URL = 'https://bff-page.kakao.com/graphql'
VIEWER_DATA_URL = 'https://bff-page.kakao.com/api/gateway/api/v1/viewer/data'
TICKET_READY_URL = 'https://bff-page.kakao.com/api/gateway/api/v1/ticket/ready_to_use'
TICKET_LIST_URL = 'https://bff-page.kakao.com/api/gateway/api/v1/ticket/list'
TICKET_BUY_URL = 'https://bff-page.kakao.com/api/gateway/api/v1/ticket/buy'
TICKET_USE_URL = 'https://bff-page.kakao.com/api/gateway/api/v1/ticket/use'
OPEN_PAGE_URL = 'https://bff-page.kakao.com/api/gateway/api/v5/inven/open_page'

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


class KakaoPageApi:
    def __init__(
        self,
        cookie_raw: Optional[str] = None,
        user_agent: Optional[str] = None,
        lang_cookie: str = 'ko',
        log: Optional[Callable[[str], None]] = None,
    ):
        self.log = log or (lambda *_: None)
        self._cookie_raw = cookie_raw
        self._lang_cookie = lang_cookie
        self._thread_local = threading.local()
        self._headers = {
            'User-Agent': user_agent or (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/123.0.0.0 Safari/537.36'
            ),
            'Content-Type': 'application/json',
            'Origin': 'https://page.kakao.com',
            'Referer': 'https://page.kakao.com/',
            'Accept': 'application/json, text/plain, */*',
        }

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        apply_raw_cookie(session, self._cookie_raw)
        if self._lang_cookie:
            try:
                session.cookies.set('kd_lang', self._lang_cookie, domain='.kakao.com')
            except Exception:
                pass
        session.headers.update(self._headers)
        return session

    def _get_session(self) -> requests.Session:
        session = getattr(self._thread_local, 'session', None)
        if session is None:
            session = self._make_session()
            self._thread_local.session = session
        return session

    def request_json(self, method: str, url: str, *, retries: int = 2, timeout: int = 30, **kwargs) -> dict:
        last_error = None
        for attempt in range(retries + 1):
            try:
                session = self._get_session()
                response = session.request(method, url, timeout=timeout, **kwargs)
                response.raise_for_status()
                return parse_json_response(response)
            except Exception as e:
                last_error = e
                try:
                    self._thread_local.session = self._make_session()
                except Exception:
                    pass
                if attempt >= retries:
                    raise
        raise RuntimeError(str(last_error) if last_error else 'Неизвестная ошибка запроса JSON')

    def post_graphql(
        self,
        operation_name: str,
        query: str,
        variables: dict,
        *,
        timeout: int = 30,
        operation_type: str = 'query',
    ) -> dict:
        payload = {
            'operationName': operation_name,
            'query': query,
            'variables': variables,
        }
        headers = {
            'x-apollo-operation-name': operation_name,
            'x-apollo-operation-type': operation_type,
        }
        data = self.request_json('POST', GRAPHQL_URL, json=payload, headers=headers, timeout=timeout)
        if data.get('errors'):
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data

    @staticmethod
    def _unwrap_rest_result(data: dict, *, op: str) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise RuntimeError(f'{op}: пустой ответ')
        result_code = data.get('result_code')
        try:
            if result_code is not None and int(result_code) != 0:
                message = data.get('message') or data.get('message_key') or f'result_code={result_code}'
                raise RuntimeError(f'{op}: {message}')
        except ValueError:
            pass
        result = data.get('result')
        return result if isinstance(result, dict) else {}

    def _post_form_json(self, url: str, form: dict[str, Any], *, op: str, timeout: int = 30) -> dict:
        session = self._get_session()
        body = urlencode([(k, '' if v is None else str(v)) for k, v in form.items()])
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://page.kakao.com',
            'Referer': 'https://page.kakao.com/',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        response = session.post(url, data=body, headers=headers, timeout=timeout)
        try:
            data = parse_json_response(response)
        except Exception:
            data = {}

        if response.status_code >= 400:
            message = ''
            if isinstance(data, dict):
                try:
                    message = (
                        str(((data.get('result') or {}).get('message') or '')).strip()
                        or str(data.get('message') or '').strip()
                        or str(data.get('message_key') or '').strip()
                    )
                except Exception:
                    message = ''
            if not message:
                try:
                    message = (response.text or '').strip()
                except Exception:
                    message = ''
            message = message[:400]
            raise RuntimeError(f'{op}: HTTP {response.status_code}' + (f' | {message}' if message else ''))

        return data if isinstance(data, dict) else {}

    def list_episodes(self, series_id: int, sort: str = 'desc', page_size: int = 200):
        after = None
        while True:
            variables = {
                'seriesId': int(series_id),
                'sortType': sort,
                'boughtOnly': False,
                'first': int(page_size),
            }
            if after:
                variables['after'] = after

            payload = self.post_graphql('contentHomeProductList', CONTENT_HOME_PRODUCT_LIST, variables, timeout=15)
            data = ((payload.get('data') or {}).get('contentHomeProductList') or {})
            for edge in data.get('edges') or []:
                if isinstance(edge, dict):
                    yield edge

            page = data.get('pageInfo') or {}
            if page.get('hasNextPage'):
                after = page.get('endCursor')
            else:
                break

    def ready_to_use_ticket(self, series_id: int, product_id: int) -> dict:
        del series_id
        data = self.request_json(
            'GET',
            TICKET_READY_URL,
            params={'product_id': int(product_id), 'include_series': 'true'},
            timeout=30,
        )
        return self._unwrap_rest_result(data, op='ticket/ready_to_use')

    def get_ticket_catalog(self, series_id: int) -> dict[str, Any]:
        data = self.request_json(
            'GET',
            TICKET_LIST_URL,
            params={'series_id': int(series_id), 'include_banner': 'true'},
            timeout=30,
        )
        return self._unwrap_rest_result(data, op='ticket/list')

    @staticmethod
    def _choose_single_ticket(tickets: Any) -> dict[str, Any]:
        if not isinstance(tickets, list):
            return {}
        items = [x for x in tickets if isinstance(x, dict)]
        if not items:
            return {}
        for item in items:
            try:
                if int(item.get('paid_num') or 0) == 1:
                    return item
            except Exception:
                continue
        return items[0]

    def get_ticket_offer(self, series_id: int, kind: str) -> dict[str, Any]:
        ticket_info = self.get_ticket_catalog(series_id)
        if kind == 'own':
            offer = self._choose_single_ticket(ticket_info.get('own_ticket_list') or [])
        elif kind == 'rental':
            offer = self._choose_single_ticket(ticket_info.get('rental_ticket_list') or [])
        else:
            offer = {}
        if not isinstance(offer, dict):
            return {}
        return offer

    def get_rental_ticket_offer(self, series_id: int) -> dict[str, Any]:
        return self.get_ticket_offer(series_id, 'rental')

    def buy_ticket(
        self,
        series_id: int,
        ticket_id: Any,
        *,
        buy_type: int,
        quantity: int = 1,
    ) -> dict[str, Any]:
        ticket_id_value = str(ticket_id or '').strip()
        if not ticket_id_value:
            raise RuntimeError('ticket/buy: пустой ticket_id')

        data = self._post_form_json(
            TICKET_BUY_URL,
            {
                'series_id': str(int(series_id)),
                'ticket_list': f'{{{ticket_id_value}:{int(quantity)}}}',
                'type': str(int(buy_type)),
            },
            op='ticket/buy',
            timeout=30,
        )
        return self._unwrap_rest_result(data, op='ticket/buy')

    def use_ticket(self, product_id: int, ticket_type: str) -> dict[str, Any]:
        data = self._post_form_json(
            TICKET_USE_URL,
            {
                'product_id': str(int(product_id)),
                'ticket_type': str(ticket_type or '').strip(),
            },
            op='ticket/use',
            timeout=30,
        )
        return self._unwrap_rest_result(data, op='ticket/use')

    def use_rental_ticket(self, product_id: int) -> dict[str, Any]:
        return self.use_ticket(product_id, 'RT01')

    def open_page(self, series_id: int, product_id: int, ticket_uid: str) -> bool:
        data = self._post_form_json(
            OPEN_PAGE_URL,
            {
                'seriesId': str(int(series_id)),
                'productId': str(int(product_id)),
                'transactionId': uuid.uuid4().hex,
                'ticket_uid': str(ticket_uid),
            },
            op='inven/open_page',
            timeout=30,
        )
        return int((data or {}).get('result_code') or 0) == 0

    def buy_and_use_ticket(
        self,
        series_id: int,
        product_id: int,
        *,
        kind: str,
        offer: Optional[dict[str, Any]] = None,
        ticket_type: Optional[str] = None,
    ) -> dict[str, Any]:
        offer_dict = offer if isinstance(offer, dict) else self.get_ticket_offer(series_id, kind)
        if not offer_dict:
            return {'purchased': False, 'reason': f'no_{kind}_offer'}

        chosen_ticket_type = str(
            ticket_type
            or offer_dict.get('ticket_type')
            or offer_dict.get('ticketType')
            or ('TT01' if kind == 'own' else 'RT01')
        ).strip()
        buy_type = 1 if kind == 'own' else 2

        try:
            buy = self.buy_ticket(
                series_id,
                ticket_id=offer_dict.get('ticket_id') or offer_dict.get('ticketId'),
                buy_type=buy_type,
                quantity=1,
            )
        except Exception as e:
            return {'purchased': False, 'reason': 'buy_failed', 'error': str(e), 'offer': offer_dict}

        try:
            used = self.use_ticket(product_id, chosen_ticket_type)
        except Exception as e:
            return {
                'purchased': False,
                'reason': 'use_failed',
                'error': str(e),
                'remainCash': buy.get('remain_cash'),
                'offer': offer_dict,
            }

        ticket_uid = str((used or {}).get('ticket_uid') or (used or {}).get('ticketUid') or '').strip()
        if ticket_uid:
            try:
                self.open_page(series_id, product_id, ticket_uid)
            except Exception:
                pass

        return {
            'purchased': True,
            'remainCash': buy.get('remain_cash'),
            'ticketUid': ticket_uid or None,
            'offer': offer_dict,
            'ticketType': chosen_ticket_type,
            'kind': kind,
        }

    def buy_and_use_rental_ticket(self, series_id: int, product_id: int) -> dict[str, Any]:
        return self.buy_and_use_ticket(series_id, product_id, kind='rental')

    def viewer_data(self, series_id: int, product_id: int) -> dict:
        return self.request_json(
            'GET',
            VIEWER_DATA_URL,
            params={'series_id': int(series_id), 'product_id': int(product_id)},
            timeout=30,
        ) or {}

    def fetch_json(self, url: str) -> dict:
        return self.request_json('GET', url, timeout=45)

    @staticmethod
    def viewer_url(series_id: int, product_id: int) -> str:
        return f'https://page.kakao.com/viewer?product_id={product_id}&series_id={series_id}'
