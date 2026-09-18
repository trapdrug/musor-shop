# -*- coding: utf-8 -*-
"""
Прокси floor-цен маркетплейса Tonnel (Telegram NFT-подарки).

Зачем: API Tonnel (gifts2.tonnel.network) закрыт Cloudflare и не отдаёт CORS-заголовки,
поэтому браузер со статичного сайта (GitHub Pages) обратиться к нему напрямую не может
(проверено: OPTIONS/POST -> 403, Access-Control-Allow-Origin отсутствует).
Этот serverless-эндпоинт ходит в Tonnel с сервера (TLS-имперсонация Chrome через
curl_cffi) и возвращает сайту готовый JSON с CORS.

Эндпоинты (Vercel: /api/floor):
  GET /api/floor?gift=Toy%20Bear&model=Wizard&limit=5   -> floor подарка+модели
  GET /api/floor?model=Wizard                           -> поиск модели по всем подаркам
  GET /api/floor?limit=30                               -> самые дешёвые лоты вообще
  Параметры: gift, model, backdrop, symbol, min_price, max_price, limit 1..30, ttl (сек)

Ответ:
  {"ok": true, "asset": "TON", "floor": 180.0, "floor_with_fee": 198.0, "count": 2, "items": [...]}

Только чтение публичных данных: cookies/Telegram-сессия не используются и не передаются
(user_auth всегда пустая строка).
"""

import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from curl_cffi import requests

TONNEL_URL = "https://gifts2.tonnel.network/api/pageGifts"
FEE_MULTIPLIER = 1.1      # Tonnel прибавляет покупателю +10% к цене лота
MAX_LIMIT = 30            # больше 30 API не отдаёт ("limit is too big")
DEFAULT_LIMIT = 5
DEFAULT_TTL = 45          # кэш ответов, секунд
CACHE_MAX = 200

HEADERS = {
    "accept": "*/*",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://market.tonnel.network",
    "referer": "https://market.tonnel.network/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"),
}

_cache = {}


def attr_filter(value):
    """Tonnel принимает атрибут как 'Wizard (1.5%)' либо как regex '^Wizard \\('."""
    value = value.strip()
    if "(" in value:
        return value
    return {"$regex": "^" + value + " \\("}


def build_filter(params):
    f = {
        "price": {"$exists": True},
        "refunded": {"$ne": True},
        "buyer": {"$exists": False},
        "export_at": {"$exists": True},
        "asset": "TON",
    }
    gift = (params.get("gift") or [""])[0].strip()
    if gift:
        f["gift_name"] = gift
    for key in ("model", "backdrop", "symbol"):
        val = (params.get(key) or [""])[0].strip()
        if val:
            f[key] = attr_filter(val)
    return f


def fetch_floor(params):
    limit = DEFAULT_LIMIT
    if params.get("limit"):
        try:
            limit = max(1, min(MAX_LIMIT, int(params["limit"][0])))
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT

    price_range = None
    mn = (params.get("min_price") or [""])[0]
    mx = (params.get("max_price") or [""])[0]
    if mn or mx:
        try:
            price_range = [float(mn) if mn else 0, float(mx) if mx else 1000000]
        except ValueError:
            price_range = None

    payload = {
        "page": 1,
        "limit": limit,
        "sort": json.dumps({"price": 1}),   # дешёвые вперёд -> первый лот и есть floor
        "filter": json.dumps(build_filter(params), ensure_ascii=False),
        "price_range": price_range,
        "user_auth": "",                    # публичный просмотр, без авторизации
    }
    resp = requests.post(TONNEL_URL, json=payload, headers=HEADERS,
                         impersonate="chrome", timeout=20)
    if resp.status_code != 200:
        raise RuntimeError("tonnel http %s: %s" % (resp.status_code, resp.text[:200]))
    data = resp.json()
    if isinstance(data, dict):
        raise RuntimeError("tonnel error: %s" % (data.get("error") or str(data)[:200]))
    return data


def normalize(items):
    out = []
    for g in items:
        price = g.get("price")
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        gid = g.get("gift_id")
        out.append({
            "gift_id": gid,
            "name": g.get("name"),
            "number": g.get("gift_num"),
            "model": g.get("model"),
            "backdrop": g.get("backdrop"),
            "symbol": g.get("symbol"),
            "price": float(price),
            "price_with_fee": round(float(price) * FEE_MULTIPLIER, 4),
            "asset": g.get("asset") or "TON",
            "status": g.get("status"),
            "link": ("https://market.tonnel.network/gift/%s" % gid) if gid else None,
        })
    return out


class handler(BaseHTTPRequestHandler):
    server_version = "tonnel-floor-proxy/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Cache-Control", "public, max-age=30")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        started = time.time()
        params = parse_qs(urlparse(self.path).query)

        ttl = DEFAULT_TTL
        if params.get("ttl"):
            try:
                ttl = max(0, min(600, int(params["ttl"][0])))
            except (TypeError, ValueError):
                ttl = DEFAULT_TTL

        key = json.dumps([[k, v[0]] for k, v in sorted(params.items()) if k != "ttl"],
                         ensure_ascii=False, sort_keys=True)
        now = time.time()
        cached = _cache.get(key)
        if cached and now - cached[0] < ttl:
            payload = dict(cached[1])
            payload["cached"] = True
            payload["ms"] = int((time.time() - started) * 1000)
            return self._send(200, payload)

        try:
            items = normalize(fetch_floor(params))
        except Exception as exc:
            return self._send(502, {
                "ok": False,
                "error": str(exc)[:300],
                "hint": "Tonnel недоступен или изменил формат ответа",
                "ms": int((time.time() - started) * 1000),
            })

        payload = {
            "ok": True,
            "source": "tonnel",
            "asset": "TON",
            "gift": (params.get("gift") or [None])[0],
            "model": (params.get("model") or [None])[0],
            "backdrop": (params.get("backdrop") or [None])[0],
            "symbol": (params.get("symbol") or [None])[0],
            "fee_multiplier": FEE_MULTIPLIER,
            "floor": items[0]["price"] if items else None,
            "floor_with_fee": items[0]["price_with_fee"] if items else None,
            "count": len(items),
            "items": items,
            "cached": False,
            "ms": int((time.time() - started) * 1000),
        }
        if items:
            _cache[key] = (time.time(), dict(payload))
            if len(_cache) > CACHE_MAX:
                for old_key, _ in sorted(_cache.items(), key=lambda kv: kv[1][0])[:50]:
                    _cache.pop(old_key, None)
        self._send(200, payload)
