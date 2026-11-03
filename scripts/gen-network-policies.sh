#!/usr/bin/env bash
# Генерирует k8s/network-policies/network-policies.yaml из Helm-шаблона
# (единый источник политик для «сырых» манифестов и Helm).
#   ./scripts/gen-network-policies.sh          — записать файл
#   ./scripts/gen-network-policies.sh --check  — проверить, что файл актуален (CI)
#
# --check сравнивает манифесты по СОДЕРЖИМОМУ (разобранный YAML), а не построчно:
# разные версии Helm по-разному печатают разделители «---» и комментарии,
# и текстовый diff падал бы в CI при той же самой конфигурации.
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
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT
  render > "$tmp"
  python3 - "$tmp" "$OUT" <<'PY'
import sys
import yaml

def load(path):
    with open(path, encoding="utf-8") as f:
        docs = [d for d in yaml.safe_load_all(f) if d]
    return {(d["kind"], d["metadata"]["name"]): d for d in docs}

rendered, committed = load(sys.argv[1]), load(sys.argv[2])
if rendered == committed:
    print(f"network-policies.yaml актуален ({len(rendered)} политик)")
    sys.exit(0)
print("network-policies.yaml устарел: запустите scripts/gen-network-policies.sh")
for key in sorted(rendered.keys() | committed.keys()):
    if rendered.get(key) != committed.get(key):
        state = ("нет в файле" if key not in committed
                 else "лишняя в файле" if key not in rendered else "отличается")
        print(f"  {key[0]}/{key[1]}: {state}")
sys.exit(1)
PY
else
  render > "$OUT"; echo "записан $OUT"
fi
