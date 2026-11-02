"""
Проверки безопасности Kubernetes-манифестов без кластера (лаб. № 5):

  1. Pod Security Standards «restricted»: каждый под из k8s/ и из рендера Helm
     проходит проверки (non-root, drop ALL, seccomp, без privilege escalation,
     без hostPath/hostNetwork, разрешённые типы томов);
  2. симулятор NetworkPolicy: нужные потоки (API → БД, воркер → S3, Prometheus →
     API ...) разрешены, а лишние (воркер → API, API → внешний мир, любой под →
     Redis кроме API/воркера ...) запрещены;
  3. согласованность политик Kyverno, Vault, TLS и CI.
"""

import json
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
NS = "fastapi-app"


def _docs(path: pathlib.Path):
    return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]


def _k8s_docs():
    for path in sorted((ROOT / "k8s").glob("*.yaml")) + [ROOT / "k8s/monitoring/flower.yaml"]:
        yield from ((path.name, d) for d in _docs(path))


# ===================================================== 1. Pod Security Standards
ALLOWED_VOLUMES = {
    "configMap",
    "csi",
    "downwardAPI",
    "emptyDir",
    "ephemeral",
    "persistentVolumeClaim",
    "projected",
    "secret",
    "name",
}


def pod_spec(doc):
    """Возвращает (pod spec, метка) для workload-ресурса или None."""
    kind = doc.get("kind")
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "ReplicaSet"):
        return doc["spec"]["template"]["spec"]
    if kind == "Pod":
        return doc["spec"]
    return None


def restricted_violations(spec: dict) -> list[str]:
    """Реализация профиля Restricted из Pod Security Standards (Kubernetes ≥ 1.25)."""
    problems = []
    pod_ctx = spec.get("securityContext") or {}
    if spec.get("hostNetwork") or spec.get("hostPID") or spec.get("hostIPC"):
        problems.append("host namespaces")
    for vol in spec.get("volumes", []):
        kinds = set(vol) - {"name"}
        if not kinds <= ALLOWED_VOLUMES:
            problems.append(f"volume type {kinds - ALLOWED_VOLUMES}")
    for c in spec.get("initContainers", []) + spec.get("containers", []):
        ctx = c.get("securityContext") or {}
        cname = c["name"]
        if ctx.get("privileged"):
            problems.append(f"{cname}: privileged")
        if ctx.get("allowPrivilegeEscalation") is not False:
            problems.append(f"{cname}: allowPrivilegeEscalation != false")
        if ctx.get("runAsNonRoot", pod_ctx.get("runAsNonRoot")) is not True:
            problems.append(f"{cname}: runAsNonRoot != true")
        if ctx.get("runAsUser", pod_ctx.get("runAsUser")) == 0:
            problems.append(f"{cname}: runAsUser 0")
        seccomp = (ctx.get("seccompProfile") or pod_ctx.get("seccompProfile") or {}).get("type")
        if seccomp not in ("RuntimeDefault", "Localhost"):
            problems.append(f"{cname}: seccompProfile {seccomp}")
        caps = ctx.get("capabilities") or {}
        if "ALL" not in [x.upper() for x in caps.get("drop", [])]:
            problems.append(f"{cname}: capabilities.drop != ALL")
        if set(caps.get("add", [])) - {"NET_BIND_SERVICE"}:
            problems.append(f"{cname}: недопустимые capabilities.add")
        for port in c.get("ports", []):
            if port.get("hostPort"):
                problems.append(f"{cname}: hostPort")
    return problems


def test_static_manifests_pass_restricted_profile():
    checked = 0
    for fname, doc in _k8s_docs():
        spec = pod_spec(doc)
        if spec is None:
            continue
        checked += 1
        assert restricted_violations(spec) == [], f"{fname}/{doc['metadata']['name']}"
    assert checked == 7  # api, worker, migrate, postgres, redis, rabbitmq, flower


def test_restricted_checker_detects_violations():
    """Негативный контроль: проверка действительно ловит небезопасные поды."""
    bad = {
        "containers": [{"name": "c", "securityContext": {"privileged": True}}],
        "hostNetwork": True,
        "volumes": [{"name": "v", "hostPath": {"path": "/"}}],
    }
    found = " ".join(restricted_violations(bad))
    for marker in (
        "privileged",
        "runAsNonRoot",
        "seccomp",
        "capabilities.drop",
        "hostPath",
        "host namespaces",
    ):
        assert marker in found, marker


def test_app_workloads_have_read_only_root_filesystem():
    """Образы приложения (API, воркер, миграции, Flower) пишут только в emptyDir."""
    expected = {"fastapi", "celery-worker", "db-migrate", "flower", "redis", "postgres"}
    seen = set()
    for _, doc in _k8s_docs():
        spec = pod_spec(doc)
        if spec is None or doc["metadata"]["name"] not in expected:
            continue
        seen.add(doc["metadata"]["name"])
        for c in spec["containers"]:
            assert c["securityContext"]["readOnlyRootFilesystem"] is True, doc["metadata"]["name"]
    assert seen == expected


def test_namespace_enforces_restricted_pss():
    ns = _docs(ROOT / "k8s/00-namespace.yaml")[0]
    labels = ns["metadata"]["labels"]
    for mode in ("enforce", "audit", "warn"):
        assert labels[f"pod-security.kubernetes.io/{mode}"] == "restricted"


def test_seaweedfs_cr_runs_non_root():
    cr = _docs(ROOT / "k8s/seaweedfs/seaweedfs-cluster.yaml")[0]["spec"]
    for comp in ("master", "volume", "filer", "s3"):
        assert cr[comp]["podSecurityContext"]["runAsNonRoot"] is True, comp
        assert cr[comp]["containerSecurityContext"]["capabilities"]["drop"] == ["ALL"], comp


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm не установлен")
@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_helm_render_passes_restricted_profile(env):
    out = subprocess.run(
        [
            "helm",
            "template",
            f"fastapi-{env}",
            "helm/fastapi-platform",
            "-n",
            f"fastapi-{env}",
            "-f",
            "helm/fastapi-platform/values.yaml",
            "-f",
            f"environments/{env}/values.yaml",
            "--set",
            "vault.enabled=true",
        ],  # staging/prod берут секреты из Vault
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    checked = 0
    for doc in yaml.safe_load_all(out):
        spec = doc and pod_spec(doc)
        if spec:
            checked += 1
            assert restricted_violations(spec) == [], f"{env}: {doc['metadata']['name']}"
    assert checked >= 6


# ============================================================ 2. NetworkPolicy
class Pod:
    def __init__(self, name, ns=NS, **labels):
        self.name, self.ns, self.labels = name, ns, labels


NAMESPACES = {
    NS: {"kubernetes.io/metadata.name": NS},
    **{
        n: {"kubernetes.io/metadata.name": n}
        for n in (
            "kube-system",
            "ingress-nginx",
            "monitoring",
            "keda",
            "cnpg-system",
            "seaweedfs-system",
            "vault",
            "default",
        )
    },
}


def _match(selector, labels):
    return all(labels.get(k) == v for k, v in (selector or {}).get("matchLabels", {}).items())


def _peer_matches(peer, other: Pod, policy_ns: str) -> bool:
    if "ipBlock" in peer:
        return True  # CIDR 0.0.0.0/0 в наших политиках = «любой адрес»
    ns_ok = (
        _match(peer["namespaceSelector"], NAMESPACES[other.ns])
        if "namespaceSelector" in peer
        else other.ns == policy_ns
    )
    pod_ok = _match(peer["podSelector"], other.labels) if "podSelector" in peer else True
    return ns_ok and pod_ok


def _rule_allows(rules, direction, other: Pod, port, policy_ns):
    for rule in rules or []:
        peers = rule.get("from" if direction == "ingress" else "to")
        if peers is not None and not any(_peer_matches(p, other, policy_ns) for p in peers):
            continue
        ports = rule.get("ports")
        if ports is None or any(
            p["port"] == port and p.get("protocol", "TCP") == "TCP" for p in ports
        ):
            return True
        if ports and port == 53 and any(p["port"] == 53 for p in ports):
            return True
    return False


def allowed(policies, src: Pod, dst: Pod, port: int) -> bool:
    """Разрешено ли соединение src → dst:port (семантика NetworkPolicy: allowlist)."""
    checks = (("egress", src, dst), ("ingress", dst, src))
    for direction, subject, other in checks:
        selecting = [
            p
            for p in policies
            if p["metadata"]["namespace"] == subject.ns
            and direction.capitalize() in p["spec"]["policyTypes"]
            and _match(p["spec"]["podSelector"], subject.labels)
        ]
        if not selecting:
            continue  # под не затронут политиками этого направления → разрешено
        if not any(
            _rule_allows(
                p["spec"].get(direction), direction, other, port, p["metadata"]["namespace"]
            )
            for p in selecting
        ):
            return False
    return True


@pytest.fixture(scope="module")
def policies():
    return _docs(ROOT / "k8s/network-policies/network-policies.yaml")


API = Pod("api", app="fastapi")
WORKER = Pod("worker", app="celery-worker")
FLOWER = Pod("flower", app="flower")
MIGRATE = Pod("migrate", app="db-migrate")
PG = Pod("pg", app="postgres")
CNPG = Pod("cnpg", **{"cnpg.io/cluster": "postgres-cluster"})
REDIS = Pod("redis", app="redis")
RABBIT = Pod("rabbit", app="rabbitmq")
SW_S3 = Pod("sw-s3", **{"app.kubernetes.io/name": "seaweedfs"})
SW_MASTER = Pod("sw-master", **{"app.kubernetes.io/name": "seaweedfs"})
KUBE_DNS = Pod("dns", ns="kube-system", **{"k8s-app": "kube-dns"})
INGRESS = Pod("nginx", ns="ingress-nginx")
PROM = Pod("prometheus", ns="monitoring")
KEDA = Pod("keda", ns="keda")
ATTACKER = Pod("attacker", ns=NS, run="attacker")  # произвольный под в namespace
OUTSIDER = Pod("outsider", ns="default")

ALLOWED_FLOWS = [
    (INGRESS, API, 8000),
    (PROM, API, 8000),
    (PROM, FLOWER, 5555),
    (API, PG, 5432),
    (API, CNPG, 5432),
    (API, REDIS, 6379),
    (API, RABBIT, 5672),
    (API, SW_S3, 8333),
    (WORKER, RABBIT, 5672),
    (WORKER, REDIS, 6379),
    (WORKER, PG, 5432),
    (WORKER, SW_S3, 8333),
    (FLOWER, RABBIT, 5672),
    (MIGRATE, PG, 5432),
    (MIGRATE, CNPG, 5432),
    (KEDA, RABBIT, 5672),
    (SW_MASTER, SW_S3, 9333),
    (API, KUBE_DNS, 53),
    (WORKER, KUBE_DNS, 53),
    (Pod("op", ns="seaweedfs-system"), SW_MASTER, 18888),
    (Pod("cnpg-op", ns="cnpg-system"), CNPG, 8000),
    (Pod("vault", ns="vault"), PG, 5432),
]

DENIED_FLOWS = [
    (WORKER, API, 8000),  # воркер не ходит в API
    (API, WORKER, 8080),  # и наоборот
    (ATTACKER, PG, 5432),  # скомпрометированный чужой под → БД
    (ATTACKER, REDIS, 6379),
    (ATTACKER, RABBIT, 5672),
    (ATTACKER, API, 8000),
    (ATTACKER, SW_S3, 8333),
    (OUTSIDER, API, 8000),  # другой namespace
    (OUTSIDER, PG, 5432),
    (FLOWER, PG, 5432),  # Flower ходит только в RabbitMQ
    (FLOWER, REDIS, 6379),
    (API, PG, 22),  # неразрешённый порт
    (API, RABBIT, 15672),  # management-порт API не нужен
    (WORKER, RABBIT, 15672),
    (REDIS, API, 8000),  # БД/кэш не инициируют соединения
    (PG, REDIS, 6379),
    (API, Pod("internet", ns="default"), 443),  # API не выходит наружу
    (WORKER, Pod("internet", ns="default"), 443),
    (INGRESS, REDIS, 6379),  # внешний трафик только в API
    (INGRESS, API, 5432),
    (PROM, PG, 5432),
]


@pytest.mark.parametrize("src,dst,port", ALLOWED_FLOWS, ids=lambda x: getattr(x, "name", x))
def test_required_flows_allowed(policies, src, dst, port):
    assert allowed(policies, src, dst, port), f"{src.name} → {dst.name}:{port} заблокирован"


@pytest.mark.parametrize("src,dst,port", DENIED_FLOWS, ids=lambda x: getattr(x, "name", x))
def test_unneeded_flows_denied(policies, src, dst, port):
    assert not allowed(policies, src, dst, port), f"{src.name} → {dst.name}:{port} разрешён"


def test_simulator_allows_everything_without_policies():
    """Контроль симулятора: без политик трафик не ограничен (как в Kubernetes по умолчанию)."""
    assert allowed([], ATTACKER, PG, 5432)


def test_default_deny_policy_is_present(policies):
    deny = next(p for p in policies if p["metadata"]["name"] == "default-deny-all")
    assert deny["spec"]["podSelector"] == {}
    assert set(deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}


def test_dns_allowed_over_udp_and_tcp(policies):
    dns = next(p for p in policies if p["metadata"]["name"] == "allow-dns-egress")
    protocols = {p["protocol"] for p in dns["spec"]["egress"][0]["ports"]}
    assert protocols == {"UDP", "TCP"}


def test_generated_policies_match_helm_template():
    if shutil.which("helm") is None:
        pytest.skip("helm не установлен")
    result = subprocess.run(
        ["bash", "scripts/gen-network-policies.sh", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ================================================================ 3. Прочее
def test_kyverno_policies_are_scoped_and_enforcing():
    docs = _docs(ROOT / "security/kyverno-policies.yaml")
    names = {d["metadata"]["name"]: d for d in docs}
    assert {
        "disallow-privileged-containers",
        "require-run-as-nonroot",
        "disallow-latest-tag",
    } <= set(names)
    for d in docs:
        for rule in d["spec"]["rules"]:
            resources = rule["match"]["any"][0]["resources"]
            # Политики не должны ломать системные namespace (kube-system, ingress-nginx ...).
            assert resources["namespaces"] == ["fastapi-*"], d["metadata"]["name"]
    assert (
        names["disallow-privileged-containers"]["spec"]["rules"][0]["validate"]["failureAction"]
        == "Enforce"
    )
    assert (
        names["require-run-as-nonroot"]["spec"]["rules"][0]["validate"]["failureAction"]
        == "Enforce"
    )
    assert names["disallow-latest-tag"]["spec"]["rules"][0]["validate"]["failureAction"] == "Audit"


def test_vault_static_secret_targets_app_secrets():
    docs = {d["kind"]: d for d in _docs(ROOT / "k8s/vault/vault-auth.yaml")}
    assert docs["VaultAuth"]["spec"]["kubernetes"]["serviceAccount"] == "fastapi-sa"
    assert docs["ServiceAccount"]["metadata"]["name"] == "fastapi-sa"
    static = _docs(ROOT / "k8s/vault/vault-static-secret.yaml")[0]
    assert static["spec"]["destination"]["name"] == "app-secrets"
    # app-secrets не должен создаваться вручную (конфликт с VSO).
    manual = [d["metadata"]["name"] for _, d in _k8s_docs() if d.get("kind") == "Secret"]
    assert "app-secrets" not in manual


def test_ingress_uses_tls_via_cert_manager():
    ing = _docs(ROOT / "k8s/ingress/ingress.yaml")[0]
    assert "cert-manager.io/cluster-issuer" in ing["metadata"]["annotations"]
    assert ing["spec"]["tls"][0]["secretName"] == "fastapi-tls"
    assert ing["metadata"]["annotations"]["nginx.ingress.kubernetes.io/ssl-redirect"] == "true"


def test_ci_pins_actions_to_commit_sha_and_runs_trivy():
    import re

    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses
    for ref in uses:
        assert re.search(r"@[0-9a-f]{40}$", ref), f"действие не закреплено по SHA: {ref}"
    assert "aquasecurity/trivy-action@" in text
    assert "exit-code: '1'" in text and "CRITICAL,HIGH" in text


def test_secret_not_in_json_logs_of_config():
    """В ConfigMap не должно быть секретов (ключи JWT, пароли)."""
    cm = next(
        d
        for n, d in _k8s_docs()
        if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "app-config"
    )
    # Настройки политик (длина, сроки жизни) — не секреты, их суффиксы допустимы.
    settings_suffixes = ("_LENGTH", "_MINUTES", "_DAYS")
    for key in cm["data"]:
        if key.endswith(settings_suffixes):
            continue
        assert not any(w in key for w in ("SECRET", "PASSWORD", "TOKEN")), key
    json.dumps(cm)  # сериализуется
