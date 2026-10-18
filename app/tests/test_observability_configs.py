"""
Проверки конфигурации наблюдаемости и S3 (лаб. № 4) без кластера:

  • все YAML/JSON в k8s/, monitoring/, argocd/ синтаксически корректны;
  • каждый PromQL-запрос (дашборды, алерты) разбирается парсером Prometheus;
  • метрики, на которые ссылаются дашборды/алерты, действительно
    экспортируются приложением (иначе панель была бы пустой);
  • ключи S3 в Secret приложения совпадают с identities сервера SeaweedFS.
"""

import json
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
promql = pytest.importorskip("promql_parser")


def _load(rel_path):
    return yaml.safe_load((ROOT / rel_path).read_text("utf-8"))


def _yaml_files():
    for folder in ("k8s", "monitoring", "argocd", "environments"):
        yield from (ROOT / folder).rglob("*.yaml")


def _dashboards():
    return sorted((ROOT / "monitoring" / "grafana-dashboards").glob("*.json"))


@pytest.mark.parametrize("path", sorted(_yaml_files()), ids=lambda p: str(p.relative_to(ROOT)))
def test_yaml_parses(path):
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))


def test_dashboards_exist_and_are_valid_json():
    files = _dashboards()
    assert {f.name for f in files} >= {"fastapi-dashboard.json", "celery-dashboard.json"}
    for f in files:
        dash = json.loads(f.read_text(encoding="utf-8"))
        assert dash["uid"] and dash["panels"]


def _dashboard_exprs():
    for f in _dashboards():
        for panel in json.loads(f.read_text(encoding="utf-8"))["panels"]:
            for t in panel.get("targets", []):
                if panel["datasource"]["type"] == "prometheus":
                    yield f.name, panel["title"], t["expr"]


def _alert_rules():
    values = yaml.safe_load((ROOT / "monitoring" / "prometheus-values.yaml").read_text("utf-8"))
    for group_set in values["additionalPrometheusRulesMap"].values():
        for group in group_set["groups"]:
            yield from group["rules"]


@pytest.mark.parametrize("name,title,expr", list(_dashboard_exprs()))
def test_dashboard_promql_valid(name, title, expr):
    promql.parse(expr)


def test_alert_rules_are_valid_promql():
    rules = list(_alert_rules())
    assert {r["alert"] for r in rules} >= {"HighErrorRate", "HighLatency", "CeleryQueueBacklog"}
    for rule in rules:
        promql.parse(rule["expr"])
        assert rule["labels"]["severity"] in ("warning", "critical")
        assert rule["annotations"]["summary"]


def test_alerts_and_dashboards_use_exported_metrics():
    """Метрики приложения из запросов должны экспортироваться кодом app/."""
    source = "\n".join(p.read_text("utf-8") for p in (ROOT / "app").rglob("*.py")
                       if "tests" not in p.parts)
    app_metrics = ["celery_queue_length", "files_operations_total", "files_bytes_total",
                   "http_requests_in_progress"]
    for metric in app_metrics:
        assert metric in source, f"{metric} не экспортируется приложением"
    exprs = [e for _, _, e in _dashboard_exprs()] + [r["expr"] for r in _alert_rules()]
    used = {m for m in app_metrics if any(m in e for e in exprs)}
    assert used == set(app_metrics)


def test_s3_keys_match_between_app_secret_and_server_identities():
    text = (ROOT / "k8s" / "02-secrets.yaml").read_text("utf-8")
    secrets = [d for d in yaml.safe_load_all(text)
               if d and d["metadata"]["name"] == "app-s3-secrets"][0]["stringData"]
    server = _load("k8s/seaweedfs/s3-credentials.yaml")
    identities = {i["name"]: i for i in json.loads(server["stringData"]["s3.json"])["identities"]}
    admin = identities["admin"]["credentials"][0]
    reader = identities["reader"]["credentials"][0]
    assert (admin["accessKey"], admin["secretKey"]) == (
        secrets["S3_ACCESS_KEY"], secrets["S3_SECRET_KEY"])
    assert (reader["accessKey"], reader["secretKey"]) == (
        secrets["S3_READ_ACCESS_KEY"], secrets["S3_READ_SECRET_KEY"])
    # Принцип наименьших привилегий: reader не может писать.
    assert set(identities["reader"]["actions"]) == {"Read", "List"}


def test_compose_s3_config_matches_k8s():
    compose = json.loads((ROOT / "docker" / "seaweedfs-s3.json").read_text("utf-8"))
    k8s = _load("k8s/seaweedfs/s3-credentials.yaml")
    assert compose == json.loads(k8s["stringData"]["s3.json"])


def test_servicemonitor_matches_service_labels_and_port():
    docs = [d for d in yaml.safe_load_all((ROOT / "k8s/30-fastapi.yaml").read_text("utf-8")) if d]
    service = next(d for d in docs if d["kind"] == "Service")
    sm = _load("k8s/monitoring/fastapi-servicemonitor.yaml")
    for key, value in sm["spec"]["selector"]["matchLabels"].items():
        assert service["metadata"]["labels"][key] == value
    port_names = {p["name"] for p in service["spec"]["ports"]}
    assert sm["spec"]["endpoints"][0]["port"] in port_names
