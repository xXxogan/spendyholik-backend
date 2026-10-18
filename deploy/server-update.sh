#!/usr/bin/env bash
# Install or update the SpendyHolik backend on the k3s server.
#
#   deploy/server-update.sh            # deploy the latest origin/main
#   deploy/server-update.sh <git-sha>  # deploy (or roll back to) a specific commit
#
# The image ghcr.io/<owner>/spendyholik-backend:<first 7 chars of the SHA> must
# already exist — the CD workflow builds it on every push to main.
# Server-only files (never committed): deploy/charts/spendyholik-backend/
# values-server.yaml and secrets.yaml — see DEPLOY.md.
set -euo pipefail

main() {
  export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
  local repo_dir chart sha tag
  repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  chart="$repo_dir/deploy/charts/spendyholik-backend"

  for file in values-server.yaml secrets.yaml; do
    if [[ ! -f "$chart/$file" ]]; then
      echo "Missing $chart/$file — see DEPLOY.md" >&2
      exit 1
    fi
  done

  cd "$repo_dir"
  git fetch --quiet origin main
  git checkout --quiet --detach "${1:-origin/main}"
  sha="$(git rev-parse HEAD)"
  tag="${sha:0:7}"
  echo "Deploying commit $tag"

  # --atomic rolls the release back automatically if the upgrade fails.
  helm upgrade --install spendyholik-backend "$chart" \
    --namespace spendyholik --create-namespace \
    -f "$chart/values-prod.yaml" -f "$chart/values-server.yaml" -f "$chart/secrets.yaml" \
    --set image.tag="$tag" \
    --atomic --wait --timeout 10m

  kubectl -n spendyholik get pods
}

# Everything runs inside main(), so bash has parsed the whole script before
# `git checkout` can replace this file on disk.
main "$@"
exit
