"""
HTTP-защита уровня приложения (лабораторная № 5):

  • проверка заголовка Host (TRUSTED_HOSTS) — защита от host header injection;
    пробы Kubernetes и /metrics исключены (kubelet обращается по IP пода);
  • /metrics недоступен запросам, пришедшим через Ingress (есть
    X-Forwarded-For): метрики видит только Prometheus внутри кластера;
  • заголовки безопасности (nosniff, X-Frame-Options, CSP, HSTS, no-store);
  • CORS только для явно перечисленных origin'ов (CORS_ORIGINS).
"""

import fnmatch

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import (
    cors_origins,
    metrics_block_proxied,
    secure_headers_enabled,
    trusted_hosts,
)

HOST_CHECK_EXEMPT = ("/health", "/ready", "/metrics")
# Swagger UI подгружает скрипты с CDN — строгий CSP его сломал бы.
CSP_EXEMPT = ("/docs", "/redoc", "/openapi.json")


def _host_allowed(host: str, patterns: list[str]) -> bool:
    host = host.split(":")[0].lower()
    return any(p == "*" or fnmatch.fnmatch(host, p) for p in patterns)


def setup_security(app: FastAPI) -> None:
    origins = cors_origins()

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # Настройки читаются на каждый запрос (дешёвый os.environ): так их
        # можно менять в тестах, а в кластере они всё равно неизменны.
        patterns = trusted_hosts()
        headers_on = secure_headers_enabled()
        block_metrics = metrics_block_proxied()
        path = request.url.path

        if patterns != ["*"] and not path.startswith(HOST_CHECK_EXEMPT):
            if not _host_allowed(request.headers.get("host", ""), patterns):
                return JSONResponse({"detail": "Invalid host header"}, status_code=400)

        if block_metrics and path == "/metrics" and (
            "x-forwarded-for" in request.headers or "x-real-ip" in request.headers
        ):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        response = await call_next(request)

        if headers_on:
            h = response.headers
            h["X-Content-Type-Options"] = "nosniff"
            h["X-Frame-Options"] = "DENY"
            h["Referrer-Policy"] = "no-referrer"
            h["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
            # Эндпоинт может ослабить политику сам (аватар: same-site, чтобы
            # <img> с фронтенда на соседнем порту/поддомене его загрузил).
            h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            if not path.startswith(CSP_EXEMPT):
                style = " style-src 'unsafe-inline';" if path.startswith("/admin") else ""
                h["Content-Security-Policy"] = (
                    f"default-src 'none';{style} frame-ancestors 'none'"
                )
            if path.startswith("/auth"):
                h["Cache-Control"] = "no-store"
            if request.headers.get("x-forwarded-proto") == "https":
                h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,  # без "*": явный список
            # Лаб. № 8: сессия в httpOnly cookie → браузеру нужно разрешить
            # отправлять cookie на API (withCredentials). С credentials "*"
            # запрещён спецификацией — поэтому список origin'ов явный.
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
            expose_headers=["X-Age-Restricted-Hidden", "X-Error-Code", "Retry-After"],
        )
