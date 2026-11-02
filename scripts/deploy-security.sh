#!/usr/bin/env bash
# Компоненты безопасности лабораторной № 5 (Minikube) одной командой:
#   minikube start --cpus=4 --memory=8192 --cni=calico     # calico нужен для NetworkPolicy!
#   minikube addons enable ingress
#   ./scripts/deploy-security.sh
# Порядок: cert-manager → Kyverno → Vault + VSO → настройка Vault → Falco → политики.
set -euo pipefail
cd "$(dirname "$0")/.."

helm repo add jetstack https://charts.jetstack.io >/dev/null
helm repo add kyverno https://kyverno.github.io/kyverno/ >/dev/null
helm repo add hashicorp https://helm.releases.hashicorp.com >/dev/null
helm repo add falcosecurity https://falcosecurity.github.io/charts >/dev/null
helm repo update >/dev/null

echo "==> 1/6 cert-manager"
helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
  --set crds.enabled=true --wait

echo "==> 2/6 Kyverno"
helm upgrade --install kyverno kyverno/kyverno -n kyverno --create-namespace --wait

echo "==> 3/6 Vault (dev) и Vault Secrets Operator"
helm upgrade --install vault hashicorp/vault -n vault --create-namespace \
  -f security/vault-values.yaml
kubectl wait --for=condition=Ready pod/vault-0 -n vault --timeout=180s
helm upgrade --install vault-secrets-operator hashicorp/vault-secrets-operator \
  -n vault-secrets-operator-system --create-namespace --wait

echo "==> 4/6 Настройка Vault: метод kubernetes, политика, роль, секреты"
./scripts/vault-setup.sh

echo "==> 5/6 Falco"
helm upgrade --install falco falcosecurity/falco -n falco --create-namespace \
  -f security/falco-values.yaml

echo "==> 6/6 Политики Kyverno и издатели сертификатов"
kubectl apply -f security/cert-manager-issuers.yaml
kubectl apply -f security/kyverno-policies.yaml

echo
echo "Дальше (приложение): kubectl apply -f k8s/00-namespace.yaml ... см. README, «Лабораторная № 5»."
