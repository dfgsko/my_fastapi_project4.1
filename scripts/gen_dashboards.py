#!/usr/bin/env python3
"""
Генератор дашбордов Grafana (monitoring/grafana-dashboards/*.json).

JSON дашборда на 1000+ строк неудобно править руками, поэтому структура
описана кодом: `python scripts/gen_dashboards.py` пересоздаёт файлы.
Источники данных — переменные ${ds_prom} и ${ds_loki} (тип datasource),
поэтому дашборды не зависят от uid источников в конкретном кластере.
"""

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "monitoring" / "grafana-dashboards"
PROM = {"type": "prometheus", "uid": "${ds_prom}"}
LOKI = {"type": "loki", "uid": "${ds_loki}"}

_id = 0


def _next() -> int:
    global _id
    _id += 1
    return _id


def target(expr, legend="", ref="A", ds=PROM):
    return {"datasource": ds, "expr": expr, "legendFormat": legend, "refId": ref}


def stat(title, expr, x, y, w=4, h=4, unit="short", thresholds=None, desc=""):
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "id": _next(), "type": "stat", "title": title, "description": desc,
        "datasource": PROM, "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr)],
        "fieldConfig": {"defaults": {
            "unit": unit, "decimals": 2,
            "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "area",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }


def timeseries(title, targets, x, y, w=12, h=8, unit="short", desc="", stack=False):
    return {
        "id": _next(), "type": "timeseries", "title": title, "description": desc,
        "datasource": PROM, "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "fieldConfig": {"defaults": {
            "unit": unit,
            "custom": {"lineWidth": 2, "fillOpacity": 15,
                       "stacking": {"mode": "normal" if stack else "none"}}},
            "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi"}},
    }


def logs(title, expr, x, y, w=24, h=9):
    return {
        "id": _next(), "type": "logs", "title": title, "datasource": LOKI,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr, ds=LOKI)],
        "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                    "enableLogDetails": True, "dedupStrategy": "none"},
    }


def row(title, y):
    return {"id": _next(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


def dashboard(uid, title, panels, tags):
    return {
        "uid": uid, "title": title, "tags": tags, "timezone": "browser",
        "schemaVersion": 39, "version": 1, "editable": True, "refresh": "15s",
        "time": {"from": "now-30m", "to": "now"},
        "templating": {"list": [
            {"name": "ds_prom", "label": "Prometheus", "type": "datasource",
             "query": "prometheus", "current": {}, "hide": 0},
            {"name": "ds_loki", "label": "Loki", "type": "datasource",
             "query": "loki", "current": {}, "hide": 0},
        ]},
        "annotations": {"list": []}, "panels": panels,
    }


RED = [{"color": "green", "value": None}, {"color": "orange", "value": 0.01},
       {"color": "red", "value": 0.05}]
LAT = [{"color": "green", "value": None}, {"color": "orange", "value": 0.5},
       {"color": "red", "value": 1}]
Q = [{"color": "green", "value": None}, {"color": "orange", "value": 20},
     {"color": "red", "value": 100}]


def fastapi():
    global _id
    _id = 0
    p = [row("RED: Rate · Errors · Duration", 0)]
    p += [
        stat("Запросов/с", 'sum(rate(http_requests_total[5m]))', 0, 1, unit="reqps",
             desc="Request rate: rate(http_requests_total[5m])"),
        stat("Ошибки 5xx, %", 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))',
             4, 1, unit="percentunit", thresholds=RED, desc="Порог алерта HighErrorRate — 5%"),
        stat("Latency p95", 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))',
             8, 1, unit="s", thresholds=LAT, desc="Порог алерта HighLatency — 1 с"),
        stat("Запросов в обработке", 'sum(http_requests_in_progress)', 12, 1),
        stat("Реплик API (UP)", 'sum(up{namespace=~"fastapi-.*", service=~"fastapi-service|.*-api"})', 16, 1),
        stat("Длина очереди Celery", 'max(celery_queue_length{queue="celery"})', 20, 1, thresholds=Q),
    ]
    p += [
        timeseries("Request rate по эндпоинтам",
                   [target('sum by (handler) (rate(http_requests_total[5m]))', "{{handler}}")],
                   0, 5, unit="reqps", stack=True),
        timeseries("Коды ответов",
                   [target('sum by (status) (rate(http_requests_total[5m]))', "{{status}}")],
                   12, 5, unit="reqps", stack=True),
        timeseries("Задержка: p50 / p95 / p99",
                   [target('histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))', "p50", "A"),
                    target('histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))', "p95", "B"),
                    target('histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))', "p99", "C")],
                   0, 13, unit="s"),
        timeseries("p95 по эндпоинтам",
                   [target('histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket[5m])))', "{{handler}}")],
                   12, 13, unit="s"),
        timeseries("Ошибки 5xx по эндпоинтам",
                   [target('sum by (handler) (rate(http_requests_total{status=~"5.."}[5m]))', "{{handler}}")],
                   0, 21, unit="reqps"),
        timeseries("Запросы в обработке (по подам)",
                   [target('sum by (pod) (http_requests_in_progress)', "{{pod}}")], 12, 21),
    ]
    p += [row("Файлы (SeaweedFS S3)", 29)]
    p += [
        timeseries("Операции с файлами",
                   [target('sum by (operation, result) (rate(files_operations_total[5m]))', "{{operation}} / {{result}}")],
                   0, 30, unit="ops"),
        timeseries("Трафик в S3 / из S3",
                   [target('sum by (direction) (rate(files_bytes_total[5m]))', "{{direction}}")],
                   12, 30, unit="Bps"),
    ]
    p += [row("Логи FastAPI (Loki)", 38)]
    p += [
        logs("Ошибки и предупреждения",
             '{namespace=~"fastapi-.*", app="fastapi"} |~ "(?i)error|exception|traceback|warning"', 0, 39),
        logs("Все логи API", '{namespace=~"fastapi-.*", app="fastapi"}', 0, 48),
    ]
    return dashboard("fastapi-red", "FastAPI — RED + логи", p, ["fastapi", "lab4"])


def celery():
    global _id
    _id = 0
    p = [row("Очередь и воркеры", 0)]
    p += [
        stat("Сообщений в очереди", 'max(celery_queue_length{queue="celery"})', 0, 1, thresholds=Q,
             desc="Порог алерта CeleryQueueBacklog — 100"),
        stat("Воркеров online", 'sum(flower_worker_online)', 4, 1),
        stat("Задач выполняется", 'sum(flower_worker_number_of_currently_executing_tasks)', 8, 1),
        stat("Реплик воркера (Deployment)", 'sum(kube_deployment_status_replicas{namespace=~"fastapi-.*", deployment=~"celery-worker|.*-worker"})',
             12, 1, desc="Меняется под управлением KEDA (ScaledObject → HPA)"),
        stat("Задач успешно / с", 'sum(rate(flower_events_total{type="task-succeeded"}[5m]))', 16, 1, unit="ops"),
        stat("Задач с ошибкой / с", 'sum(rate(flower_events_total{type="task-failed"}[5m]))', 20, 1, unit="ops",
             thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 0.001}]),
    ]
    p += [
        timeseries("Длина очереди и число воркеров (автомасштабирование KEDA)",
                   [target('max(celery_queue_length{queue="celery"})', "сообщений в очереди", "A"),
                    target('sum(kube_deployment_status_replicas{namespace=~"fastapi-.*", deployment=~"celery-worker|.*-worker"})', "реплик воркера", "B")],
                   0, 5, w=24, desc="Запустите scripts/load_test.py: очередь растёт, KEDA добавляет воркеры, очередь спадает."),
        timeseries("События задач по типам",
                   [target('sum by (type) (rate(flower_events_total[5m]))', "{{type}}")],
                   0, 13, unit="ops", stack=True),
        timeseries("Время выполнения задач: p50 / p95",
                   [target('histogram_quantile(0.50, sum by (le) (rate(flower_task_runtime_seconds_bucket[5m])))', "p50", "A"),
                    target('histogram_quantile(0.95, sum by (le) (rate(flower_task_runtime_seconds_bucket[5m])))', "p95", "B")],
                   12, 13, unit="s"),
        timeseries("Задач выполняется по воркерам",
                   [target('sum by (worker) (flower_worker_number_of_currently_executing_tasks)', "{{worker}}")],
                   0, 21),
        timeseries("CPU воркеров",
                   [target('sum by (pod) (rate(container_cpu_usage_seconds_total{namespace=~"fastapi-.*", pod=~"celery-worker.*|.*-worker-.*", container!=""}[5m]))', "{{pod}}")],
                   12, 21, unit="cores"),
    ]
    p += [row("Логи воркеров (Loki)", 29)]
    p += [
        logs("Генерация сертификатов и ошибки",
             '{namespace=~"fastapi-.*", app="celery-worker"} |~ "(?i)сертификат|error|exception|retry"', 0, 30),
        logs("Все логи воркеров", '{namespace=~"fastapi-.*", app="celery-worker"}', 0, 39),
    ]
    return dashboard("celery-workers", "Celery — очередь, воркеры, KEDA + логи", p, ["celery", "keda", "lab4"])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, d in (("fastapi-dashboard.json", fastapi()), ("celery-dashboard.json", celery())):
        (OUT / name).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written", OUT / name)
