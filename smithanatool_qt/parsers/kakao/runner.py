from __future__ import annotations
from typing import Optional, Iterable, Callable, Dict, List
from pathlib import Path

from .utils import ensure_dir, _viewer_url
from .auth import _load_cookie_raw_from_session
from .episodes import parse_chapter_spec, parse_index_spec, _safe_list_all
from .download import _download_images_from_list
from .stitch import _auto_stitch_chapter

from .graphql_client import KakaoGraphQL
from .dom import _try_use_rental_ticket, _collect_dom_urls


def _make_pre_action_buy_and_use(series_id: int, product_id: int, log=None):
    """
    Returns pre_action(page) that purchases a RentSingle ticket via GraphQL
    and then tries to use the ticket to open the chapter. Runs inside the page
    so cookies/CSRF/session are reused.
    """

    def _pre_action(page):
        try:
            result = page.evaluate(
                """async ({seriesId, productId}) => {
                    async function gql(q, variables, name="unknown", type="query") {
                      const res = await fetch("https://bff-page.kakao.com/graphql", {
                        method: "POST",
                        credentials: "include",
                        headers: {
                          "content-type": "application/json",
                          "x-apollo-operation-name": name,
                          "x-apollo-operation-type": type
                        },
                        body: JSON.stringify({ operationName: name, query: q, variables })
                      });
                      const json = await res.json();
                      if (json.errors) throw new Error("GraphQL errors: " + JSON.stringify(json.errors));
                      return json.data;
                    }

                    const qInfo = `
                      query contentBuyTicketPage($seriesId: Long!) {
                        contentBuyTicketPage(seriesId: $seriesId) {
                          ticketInfo {
                            purchasableRentalTicketList {
                              ticketType
                              price
                              ticketId
                              ticketKind
                            }
                          }
                        }
                      }
                    `;
                    const info = await gql(qInfo, { seriesId }, "contentBuyTicketPage", "query");
                    const list = info?.contentBuyTicketPage?.ticketInfo?.purchasableRentalTicketList || [];
                    const rent = list.find(t => t.ticketType === "RentSingle");
                    if (!rent) {
                      return { purchased: false, reason: "no_rent_single" };
                    }

                    // 1) купить тикет аренды
                    const mBuy = `
                      mutation buyTicket($input: TicketBuyMutationInput!) {
                        buyTicket(input: $input) {
                          remainCash
                          purchasedTicketCount
                        }
                      }
                    `;
                    const vars = { input: {
                      seriesId,
                      ticketKind: rent.ticketKind || "Rent",
                      ticketList: [{ ticketId: rent.ticketId, quantity: 1 }]
                    }};
                    const buy = await gql(mBuy, vars, "buyTicket", "mutation");
                    const purchased = !!(buy?.buyTicket?.purchasedTicketCount > 0);
                    if (!purchased) return { purchased:false, remainCash: buy?.buyTicket?.remainCash ?? null };

                    const mUse = `mutation UseTicket($input: TicketUseMutationInput!){
                      useTicket(input:$input){ waitfreeChargedAt ticketUid }
                    }`;
                    const use = await gql(mUse, { input: { ticketType: "RentSingle", productId } }, "UseTicket", "mutation");
                    const ticketUid = use?.useTicket?.ticketUid;

                    if (ticketUid) {
                      const mOpen = `mutation OpenPage($input: ViewerOpenPageMutationInput!){
                        viewerOpenPage(input:$input)
                      }`;
                      await gql(mOpen, { input: { seriesId, productId, ticketUid } }, "OpenPage", "mutation");
                    }

                    // НИКАКИХ page.reload здесь — это вне evaluate
                    return { purchased: true, remainCash: buy?.buyTicket?.remainCash ?? null };
                }""",
                {"seriesId": int(series_id), "productId": int(product_id)}
            )
            if result and result.get("purchased"):
                if log: log(f"[OK] Куплен тикет аренды. Остаток: {result.get('remainCash')}")

                # 1) гарантированно уходим с purchase-страницы во viewer
                viewer_url = _viewer_url(int(series_id), int(product_id))
                try:
                    page.goto(viewer_url, wait_until="domcontentloaded")
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                except Exception as e:
                    if log: log(f"[WARN] Переход к viewer после покупки не удался: {e}")

                # 2) (опционально) страховка, если бэкенд ещё не «подложил» доступ:
                try:
                    _try_use_rental_ticket(page, log=log)
                except Exception as e:
                    if log: log(f"[WARN] Страховочный use_ticket не удался: {e}")

                return True
            else:
                if log: log(f"[WARN] Не удалось купить тикет: {result}")
                return False
        except Exception as e:
            if log: log(f"[WARN] Ошибка покупки тикета: {e}")
            return False

    return _pre_action


import re, json, time


def run_parser(
        title_id: str,
        chapter_spec: Optional[str] = None,
        chapters: Optional[Iterable[str]] = None,
        out_dir: str = "",
        on_log: Optional[Callable[[str], None]] = None,
        on_need_login: Optional[Callable[[], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
        min_width: int = 720,
        auto_concat: Optional[dict] = None,
        on_confirm_purchase: Optional[Callable[[int, Optional[int]], bool]] = None,
        on_confirm_use_rental: Optional[Callable[[int, int, Optional[int], str], bool]] = None,
        by_index: Optional[int] = None,
        by_index_spec: Optional[str] = None,
        viewer_ids: Optional[Iterable[int]] = None,
        save_har: bool = True,  # для совместимости, не используется
        use_cache_map: bool = False,
        delete_cache_after: bool = True,
        scroll_ms: int = 30000,
        auth_only: bool = False,
        on_after_auth: Optional[Callable[[str], None]] = None,
        wait_continue: Optional[Callable[[], bool]] = None,
) -> None:
    log = on_log or (lambda s: None)
    sid = int(title_id)

    session_dir = str(Path(out_dir or "."))  # где хранится kakao_auth.json
    series_dir = str(Path(out_dir or ".") / str(sid))  # куда кладём главы и urls.json
    ensure_dir(series_dir)

    cache_dir = str(Path(series_dir) / "cache")
    ensure_dir(cache_dir)

    if stop_flag and stop_flag():
        raise RuntimeError("[CANCEL] Остановлено пользователем.")

    cookie_raw, attempted_login, login_aborted = _load_cookie_raw_from_session(
        session_dir, on_need_login=on_need_login, stop_flag=stop_flag, log=log, wait_continue=wait_continue,
    )
    gql = KakaoGraphQL(cookie_raw=cookie_raw)

    if login_aborted:
        raise RuntimeError("[CANCEL] Авторизация отменена пользователем.")

    if on_after_auth:
        try:
            on_after_auth(cookie_raw)
        except Exception:
            pass
    if auth_only:
        if login_aborted:
            raise RuntimeError("[CANCEL] Авторизация отменена пользователем.")
        return

    all_rows = []
    epmap_path = Path(cache_dir) / "episode_map.json"
    epmap_created_now = False

    if use_cache_map and epmap_path.exists():
        try:
            with open(epmap_path, "r", encoding="utf-8") as f:
                all_rows = json.load(f)
            if log: log(f"[CACHE] Загружена карта эпизодов из {epmap_path}")
        except Exception as e:
            if log: log(f"[WARN] Не удалось прочитать кэш {epmap_path}: {e}")
            all_rows = []

    if not all_rows:
        all_rows = _safe_list_all(sid, sort="desc", cookie_raw=cookie_raw, log=log, stop_flag=stop_flag, retries=2)
        if use_cache_map and all_rows:
            try:
                with open(epmap_path, "w", encoding="utf-8") as f:
                    json.dump(all_rows, f, ensure_ascii=False, indent=0)
                epmap_created_now = True
                if log: log(f"[CACHE] Сохранена карта эпизодов в {epmap_path}")
            except Exception as e:
                if log: log(f"[WARN] Не удалось сохранить кэш {epmap_path}: {e}")

    if stop_flag and stop_flag():
        raise RuntimeError("[CANCEL] Остановлено пользователем.")

    # карты productId <-> episodeNo
    num_to_id: Dict[int, str] = {}
    id_to_num: Dict[str, int] = {}
    for ep in all_rows:
        pid, ep_no = ep.get("productId"), ep.get("episodeNo")
        if not pid or not isinstance(ep_no, int): continue
        pid_s = str(pid)
        num_to_id.setdefault(ep_no, pid_s)
        id_to_num.setdefault(pid_s, ep_no)
    if log: log(f"[DEBUG] epNo-карта: nums={len(num_to_id)}, ids={len(id_to_num)}")

    # определяем таргеты
    targets: List[str] = []
    if chapters:
        targets = [str(x) for x in chapters]
    elif chapter_spec:
        for n in parse_chapter_spec(chapter_spec):
            pid = num_to_id.get(int(n))
            if pid:
                targets.append(pid)
            else:
                log(f"[DEBUG] Нет номера {n} (возможно, пролог/трейлер)")
    elif by_index or by_index_spec:
        rows = list(reversed(all_rows))  # chronological
        pids = [str(_ep["productId"]) for _ep in rows if _ep.get("productId")]
        if by_index_spec:
            idx_list = parse_index_spec(by_index_spec)
        elif by_index:
            idx_list = [int(by_index)]
        else:
            idx_list = []
        seen = set();
        idx_uniq = []
        for x in idx_list:
            if x not in seen: idx_uniq.append(x); seen.add(x)
        for x in idx_uniq:
            if 1 <= x <= len(pids):
                targets.append(pids[x - 1])
                if log: log(f"[DEBUG] by_index {x} → productId={pids[x - 1]}")
            else:
                log(f"[WARN] by_index {x} вне диапазона (1..{len(pids)})")
    else:
        targets = [pid for _, pid in sorted(num_to_id.items(), key=lambda kv: kv[0])]

    if stop_flag and stop_flag():
        raise RuntimeError("[CANCEL] Остановлено пользователем.")
    if not targets:
        raise RuntimeError("[ERROR] Нет ни одной главы для скачивания (проверьте ввод).")

    for i, pid in enumerate(targets, 1):
        if stop_flag and stop_flag():
            raise RuntimeError("[CANCEL] Остановлено пользователем.")

        url = _viewer_url(sid, pid)
        log(f"[VIEWER {i:03d}] {url}")

        ep_no = id_to_num.get(str(pid))
        label = f"{ep_no:03d}" if isinstance(ep_no, int) else f"id_{pid}"

        # ВАЖНО: именно так задаём series_id / product_id для GraphQL
        series_id = int(sid)
        product_id = int(pid)

        # --- Проверяем доступность и собираем данные для модалки
        rtu = {}
        try:
            rtu = gql.ready_to_use_ticket(series_id, product_id) or {}
        except Exception as e:
            if log: log(f"[WARN] readyToUseTicket не удалось: {e}")

        single = (rtu.get("single") or {})
        my = (rtu.get("my") or {})
        available = (rtu.get("available") or {})

        read_access = (single.get("readAccessType") or "").lower()  # notpurchased/expired/purchased/...
        chapter_label = single.get("title") or label

        need_ticket = read_access in ("notpurchased", "expired")

        # --- Если глава недоступна: спрашиваем об использовании 대여권 / или предложим купить
        if need_ticket:
            rental_count = int(my.get("ticketRentalCount") or 0)
            own_count = int(my.get("ticketOwnCount") or 0)
            balance = int(my.get("cashAmount")) if my.get("cashAmount") is not None else None
            if log: log("[DEBUG] access=%s rental=%s own=%s balance=%s available=%s" % (
            read_access, rental_count, own_count, balance, available))

            if rental_count > 0:
                use_it = on_confirm_use_rental(rental_count, own_count, balance,
                                               chapter_label) if on_confirm_use_rental else False
                if not use_it:
                    continue

                def _pre_action(page):
                    return _try_use_rental_ticket(page, log=log)
            else:
                # Нет доступных тикетов аренды: предложим купить
                try:
                    available = rtu.get("available") or {}
                    price = int((available.get("rental") or {}).get("price") or 200)
                except Exception:
                    price = 200
                if log: log(f"[ASK] Отсутствуют тикеты: цена={price}, баланс={balance}.")
                want_buy = on_confirm_purchase(price, balance) if on_confirm_purchase else False
                if not want_buy:
                    if log: log("[SKIP] Нет доступных тикетов. Пользователь отказался покупать. Пропускаем главу.")
                    continue
                if balance is not None and balance < price:
                    if log: log(f"[SKIP] Недостаточно средств: баланс {balance}, цена {price}. Пропускаем главу.")
                    continue
                if log: log(f"[OK] Покупаю тикет аренды за {price} и открываю главу…")
                _pre_action = _make_pre_action_buy_and_use(series_id, product_id, log=log)

        else:
            _pre_action = None

        # --- 1) собираем URL из DOM (с pre_action, если был нужен тикет)
        try:
            if _pre_action:
                urls_json_path = _collect_dom_urls(
                    series_id, product_id,
                    out_dir=series_dir, auth_dir=session_dir,
                    log=log, stop_flag=stop_flag,
                    episode_no=ep_no,
                    pre_action=_pre_action,
                    scroll_ms=int(scroll_ms)
                )
            else:
                urls_json_path = _collect_dom_urls(
                    series_id, product_id,
                    out_dir=series_dir, auth_dir=session_dir,
                    log=log, stop_flag=stop_flag,
                    episode_no=ep_no,
                    scroll_ms=int(scroll_ms)
                )
            if urls_json_path:
                log(f"[OK] URLS {label}: {urls_json_path}")
        except Exception as e:
            log(f"[WARN] URLS {label} не получены: {e}")
            urls_json_path = None

        # --- 2) качаем страницы + 3) склейка (как у тебя было)
        chapter_dir = str(Path(series_dir) / label)
        referer = url
        try:
            if stop_flag and stop_flag():
                raise RuntimeError("[CANCEL] Остановлено пользователем.")
            if urls_json_path and Path(urls_json_path).exists():
                with open(urls_json_path, "r", encoding="utf-8") as f:
                    urls = json.load(f)

                _download_images_from_list(
                    urls, chapter_dir,
                    referer=referer, cookie_raw=cookie_raw,
                    min_width=int(min_width) if min_width else 0,
                    log=log, stop_flag=stop_flag,
                    auto_threads=bool((auto_concat or {}).get("auto_threads", True)),
                    threads=int((auto_concat or {}).get("threads", 4)),
                )

                if auto_concat and auto_concat.get("enable"):
                    _auto_stitch_chapter(
                        chapter_dir, auto_cfg=auto_concat, log=log, stop_flag=stop_flag
                    )
                    if delete_cache_after and urls_json_path:
                        try:
                            p = Path(urls_json_path)
                            # удаляем только то, что лежит в нашем cache текущей серии
                            if p.exists() and str(p.parent) == cache_dir:
                                p.unlink()
                                if log: log(f"[CACHE] Удалён кэш URL: {p}")
                        except Exception as e:
                            if log: log(f"[WARN] Не удалось удалить кэш {urls_json_path}: {e}")
            else:
                log(f"[WARN] Нет DOM-URL для {label} (или файл отсутствует)")
        except Exception as e:
            log(f"[WARN] Ошибка докачки DOM-URL для {label}: {e}")

    if delete_cache_after and epmap_created_now:
        try:
            if epmap_path.exists():
                epmap_path.unlink()
                if log: log(f"[CACHE] Удалён кэш карты эпизодов: {epmap_path}")
        except Exception as e:
            if log: log(f"[WARN] Не удалось удалить кэш карты эпизодов {epmap_path}: {e}")