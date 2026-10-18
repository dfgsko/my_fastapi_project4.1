#!/usr/bin/env bash
# Весь стек лабораторной № 4 одной командой (Minikube, без Argo CD):
#   ./scripts/deploy-observability.sh
# Что делает: операторы (SeaweedFS) → стек мониторинга → приложение (Helm).
# Требуется: minikube start, образы fastapi-app / fastapi-worker уже собраны.
set -euo pipefail
cd "$(dirname "$0")/.."
NS=${NS:-fastapi-app}

helm repo add seaweedfs-operator https://seaweedfs.github.io/seaweedfs-operator/ >/dev/null
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null
helm repo update >/dev/null

echo "==> 1/4 SeaweedFS Operator"
helm upgrade --install seaweedfs-operator seaweedfs-operator/seaweedfs-operator \
  -n seaweedfs-system --create-namespace --wait

echo "==> 2/4 Namespace, Secret Grafana, datasource Loki, дашборды"
kubectl apply -k monitoring/

echo "==> 3/4 kube-prometheus-stack, Loki, Alloy"
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring -f monitoring/prometheus-values.yaml --wait --timeout 10m
helm upgrade --install loki grafana/loki -n monitoring -f monitoring/loki-values.yaml --wait --timeout 10m
helm upgrade --install alloy grafana/alloy -n monitoring -f monitoring/alloy-values.yaml --wait

echo "==> 4/4 Приложение: API, воркеры, инфраструктура, SeaweedFS, ServiceMonitor, Flower"
helm upgrade --install fastapi-platform helm/fastapi-platform -n "$NS" --create-namespace \
  -f helm/fastapi-platform/values-dev.yaml

echo
echo "Готово. Доступ к сервисам — раздел «Доступ к сервисам» в README."
