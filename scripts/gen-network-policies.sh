#!/usr/bin/env bash
# Генерирует k8s/network-policies/network-policies.yaml из Helm-шаблона
# (единый источник политик для «сырых» манифестов и Helm).
#   ./scripts/gen-network-policies.sh          — записать файл
#   ./scripts/gen-network-policies.sh --check  — проверить, что файл актуален (CI)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=k8s/network-policies/network-policies.yaml
render() {
  echo "# GENERATED из helm/fastapi-platform/templates/networkpolicies.yaml — не править руками."
  echo "# Перегенерировать: ./scripts/gen-network-policies.sh"
  helm template fastapi helm/fastapi-platform -n fastapi-app \
    -s templates/networkpolicies.yaml | grep -v '^# Source:'
}
if [[ "${1:-}" == "--check" ]]; then
  diff <(render) "$OUT" >/dev/null || { echo "network-policies.yaml устарел: запустите scripts/gen-network-policies.sh"; exit 1; }
  echo "network-policies.yaml актуален"
else
  render > "$OUT"; echo "записан $OUT"
fi
