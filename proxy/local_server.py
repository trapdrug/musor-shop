# -*- coding: utf-8 -*-
"""Локальный запуск того же кода, что деплоится на Vercel: python local_server.py

Открывает те же эндпоинты на http://127.0.0.1:8787/api/floor
(используется обработчик handler из api/floor.py — проверяется ровно тот код,
который потом уедет в прод).
"""

import importlib.util
import os
import sys
from http.server import HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8787"))


def load_handler():
    path = os.path.join(HERE, "api", "floor.py")
    spec = importlib.util.spec_from_file_location("floor_handler", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["floor_handler"] = mod
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    module = load_handler()
    print("tonnel-proxy локально: http://127.0.0.1:%d/api/floor?gift=Toy%%20Bear&model=Wizard" % PORT)
    HTTPServer(("127.0.0.1", PORT), module.handler).serve_forever()
