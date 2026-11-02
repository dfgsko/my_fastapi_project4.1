#!/usr/bin/env bash
# Настраивает Vault (dev-режим) для приложения — идемпотентно:
#   1. включает метод аутентификации kubernetes и указывает адрес API-сервера;
#   2. создаёт политику fastapi-policy (чтение secret/data/fastapi/*);
#   3. создаёт роль fastapi-role (только SA fastapi-sa из namespace fastapi-app);
#   4. кладёт секреты приложения в secret/fastapi/config (kv-v2).
#
#   ./scripts/vault-setup.sh
#   RABBITMQ_HOST=fastapi-dev-rabbitmq NS=fastapi-dev VAULT_PATH=fastapi/dev ./scripts/vault-setup.sh   # Helm-релиз
#
# В методичке шаги 1–2 отсутствуют, а без них VaultAuth получает 403:
# Vault не знает, как проверять токены Kubernetes.
set -euo pipefail
NS="${NS:-fastapi-app}"
VAULT_NS="${VAULT_NS:-vault}"
VAULT_PATH="${VAULT_PATH:-fastapi/config}"
RABBITMQ_HOST="${RABBITMQ_HOST:-rabbitmq}"

# Секреты генерируются на лету и в Git не попадают. Переменные можно
# переопределить окружением (например, чтобы пароль БД совпал с уже
# инициализированным PostgreSQL).
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
DATABASE_USER="${DATABASE_USER:-appuser}"
DATABASE_PASSWORD="${DATABASE_PASSWORD:-securePassword123}"
RABBITMQ_DEFAULT_USER="${RABBITMQ_DEFAULT_USER:-guest}"
RABBITMQ_DEFAULT_PASS="${RABBITMQ_DEFAULT_PASS:-guest}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-app-admin-key}"
S3_SECRET_KEY="${S3_SECRET_KEY:-app-admin-secret-change-me}"
S3_READ_ACCESS_KEY="${S3_READ_ACCESS_KEY:-app-reader-key}"
S3_READ_SECRET_KEY="${S3_READ_SECRET_KEY:-app-reader-secret-change-me}"

kubectl wait --for=condition=Ready pod/vault-0 -n "$VAULT_NS" --timeout=120s

kubectl exec -i -n "$VAULT_NS" vault-0 -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root sh -s <<EOF
set -e
vault auth list | grep -q '^kubernetes/' || vault auth enable kubernetes
vault write auth/kubernetes/config kubernetes_host="https://\$KUBERNETES_PORT_443_TCP_ADDR:443"

vault policy write fastapi-policy - <<'POLICY'
path "secret/data/fastapi/*" {
  capabilities = ["read"]
}
POLICY

vault write auth/kubernetes/role/fastapi-role \\
  bound_service_account_names=fastapi-sa \\
  bound_service_account_namespaces=${NS} \\
  policies=fastapi-policy \\
  audience=vault \\
  ttl=1h

vault kv put secret/${VAULT_PATH} \\
  SECRET_KEY='${SECRET_KEY}' \\
  DATABASE_USER='${DATABASE_USER}' \\
  DATABASE_PASSWORD='${DATABASE_PASSWORD}' \\
  RABBITMQ_DEFAULT_USER='${RABBITMQ_DEFAULT_USER}' \\
  RABBITMQ_DEFAULT_PASS='${RABBITMQ_DEFAULT_PASS}' \\
  RABBITMQ_URL='amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@${RABBITMQ_HOST}:5672//' \\
  S3_ACCESS_KEY='${S3_ACCESS_KEY}' \\
  S3_SECRET_KEY='${S3_SECRET_KEY}' \\
  S3_READ_ACCESS_KEY='${S3_READ_ACCESS_KEY}' \\
  S3_READ_SECRET_KEY='${S3_READ_SECRET_KEY}'
EOF

echo "Готово: Vault настроен. Дальше: kubectl apply -f k8s/vault/"
echo "Проверка: kubectl get secret app-secrets -n ${NS} -o jsonpath='{.data}' | head -c 200"
