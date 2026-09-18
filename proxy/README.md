# tonnel-proxy — floor-цены Tonnel для сайта

Прокси нужен потому, что API Tonnel (`gifts2.tonnel.network`) закрыт Cloudflare и **не отдаёт
CORS-заголовки** — браузер со статичного сайта (GitHub Pages) обратиться к нему напрямую не может.
Прокси делает запрос со сервера (TLS-имперсонация Chrome через `curl_cffi`) и отдаёт сайту JSON.

## Эндпоинт

```
GET /api/floor?gift=Toy%20Bear&model=Wizard&limit=5
GET /api/floor?model=Wizard          сквозной поиск модели по всем подаркам
GET /api/floor?limit=30              самые дешёвые лоты на маркете
GET /api/floor?gift=Desk%20Calendar&model=Deadline%20(0.2%)&min_price=5&max_price=100
```

Параметры: `gift`, `model`, `backdrop`, `symbol`, `min_price`, `max_price`, `limit` (1..30), `ttl` (кэш, сек).

Ответ:

```json
{
  "ok": true,
  "source": "tonnel",
  "asset": "TON",
  "floor": 180,
  "floor_with_fee": 198,
  "count": 2,
  "items": [
    { "gift_id": 9493504, "name": "Toy Bear", "number": 4532, "model": "Wizard (1.5%)",
      "backdrop": "Mystic Pearl (1.5%)", "symbol": "Tulip (0.5%)", "price": 180,
      "price_with_fee": 198, "asset": "TON", "link": "https://market.tonnel.network/gift/9493504" }
  ],
  "cached": false,
  "ms": 260
}
```

`floor` — самый дешёвый лот (цена продавца). `price_with_fee` — столько реально заплатит покупатель
(Tonnel добавляет 10%).

## Локальный запуск

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python local_server.py
# проверка:
# http://127.0.0.1:8787/api/floor?gift=Toy%20Bear&model=Wizard
```

## Деплой на Vercel (вариант А — через сайт, ~3 минуты, без установки)

1. Откройте https://vercel.com и войдите (можно через GitHub).
2. **Add New… → Project → Import** — выберите свой форк этого репозитория
   (или залейте туда только папку `proxy` как отдельный репозиторий, root directory = `proxy`).
3. На шаге **Configure Project** ничего менять не нужно: Vercel сам определит
   Python-функцию `api/floor.py` и поставит зависимости из `requirements.txt`.
   Настройки функции (`vercel.json`): runtime `python3.12`, timeout 30 сек, память 1024 МБ.
4. Нажмите **Deploy**. После деплоя получите домен вида `https://<project>.vercel.app`.
5. Проверка: `https://<project>.vercel.app/api/floor?gift=Toy%20Bear&model=Wizard`
   → должен прийти JSON с `"ok": true, "floor": ...`.
6. Прокси-URL вставляется в сайт (`https://<project>.vercel.app/api/floor`) —
   скажите мне этот адрес, и я подключу к нему `gifts-calculator.html`.

## Деплой на Vercel (вариант Б — через терминал)

```bash
npm i -g vercel
vercel login
cd proxy
vercel --prod
```

Vercel сам определит Python-функцию `api/floor.py`, поставит зависимости из `requirements.txt`
и выдаст домен вида `https://<project>.vercel.app`. Прокси-URL вставляется в сайт
(`https://<project>.vercel.app/api/floor`).

Альтернатива — Cloudflare Workers: там нет `curl_cffi`, TLS-отпечаток не подделать,
поэтому защита Tonnel может вернуть 403 (у Vercel с Python такого ограничения нет).

## Важно знать

- **Только чтение публичных данных.** Никакие Telegram-сессии (`initData`) не используются:
  в запросах всегда `user_auth: ""`. Не добавляйте сюда передачу своего токена — прокси публичный.
- Сводный эндпоинт Tonnel `filterStats` (floor сразу по всем моделям) требует авторизации —
  без Telegram-логина отдаёт `Invalid auth data`, поэтому floor берётся по конкретной модели.
- Лимит страницы Tonnel — **30** (`limit > 30` → `limit is too big`).
- В ответе Tonnel имена полей: `name` (название подарка), `model`, `backdrop`, `symbol`, `price`,
  `asset`, `gift_id`, `gift_num`, `status`. Фильтр по атрибуту принимает либо `"Wizard (1.5%)"`,
  либо regex `"^Wizard \\("`.
- Кэш: 45 секунд по умолчанию (`ttl`), чтобы не долбить маркетплейс.
- API неофициальный: может измениться в любой момент, возможны блокировки по IP.
  Используйте умеренно и на свой риск (см. правила Tonnel).
