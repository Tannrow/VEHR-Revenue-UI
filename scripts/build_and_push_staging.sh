#!/usr/bin/env bash

set -euo pipefail

: "${ACR_NAME:?ACR_NAME is required}"
: "${RG:?RG is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
if ! GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null)"; then
  echo "Unable to derive git SHA from repository at ${REPO_ROOT}" >&2
  exit 1
fi
if [[ -z "${GIT_SHA}" ]]; then
  echo "Unable to derive git SHA" >&2
  exit 1
fi
IMAGE_TAG="vehr-api:${GIT_SHA}"

echo "Using resource group: ${RG}"
echo "Validating ACR existence: ${ACR_NAME}"
if ! az acr show --name "${ACR_NAME}" --resource-group "${RG}" --output none; then
  echo "Failed to validate ACR '${ACR_NAME}' in resource group '${RG}' (check ACR name, resource group, access, and network connectivity)." >&2
  exit 1
fi

echo "Logging into ACR: ${ACR_NAME}"
if ! az acr login --name "${ACR_NAME}"; then
  echo "Failed to log into ACR '${ACR_NAME}'" >&2
  exit 1
fi

echo "Building and pushing image tag: ${IMAGE_TAG}"
if ! az acr build --registry "${ACR_NAME}" --image "${IMAGE_TAG}" --file Dockerfile "${REPO_ROOT}"; then
  echo "Failed to build and push image '${IMAGE_TAG}' to ACR '${ACR_NAME}'" >&2
  exit 1
fi

echo "Done: ${ACR_NAME}.azurecr.io/${IMAGE_TAG}"
