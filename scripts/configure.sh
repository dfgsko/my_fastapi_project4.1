#!/usr/bin/env bash
# Подставляет ваш GitHub-аккаунт и репозиторий в конфиги GitOps.
#   ./scripts/configure.sh my-github-user my-repo
set -euo pipefail
USER_NAME="${1:?usage: $0 <github-user> <repo-name>}"
REPO_NAME="${2:?usage: $0 <github-user> <repo-name>}"
cd "$(dirname "$0")/.."
grep -rl --exclude-dir=.git -e YOUR_GITHUB_USER -e YOUR_REPO \
  argocd environments helm .github | while read -r f; do
  sed -i "s/YOUR_GITHUB_USER/${USER_NAME}/g; s/YOUR_REPO/${REPO_NAME}/g" "$f"
  echo "обновлён: $f"
done
