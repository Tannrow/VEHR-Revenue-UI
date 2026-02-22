#!/usr/bin/env bash

set -euo pipefail

: "${ACR_NAME:?ACR_NAME is required}"
: "${RG:?RG is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
if [[ -z "${GIT_SHA}" ]]; then
  echo "Unable to derive git SHA"
  exit 1
fi
IMAGE_TAG="vehr-api:${GIT_SHA}"

echo "Using resource group: ${RG}"
echo "Validating ACR existence: ${ACR_NAME}"
az acr show --name "${ACR_NAME}" --resource-group "${RG}" --output none

echo "Logging into ACR: ${ACR_NAME}"
az acr login --name "${ACR_NAME}"

echo "Building and pushing image tag: ${IMAGE_TAG}"
az acr build --registry "${ACR_NAME}" --image "${IMAGE_TAG}" --file Dockerfile "${REPO_ROOT}"

echo "Done: ${ACR_NAME}.azurecr.io/${IMAGE_TAG}"
