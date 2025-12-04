#!/bin/bash

set -e

# Variáveis
REGISTRY="quay.io/fcalomen"
IMAGE_NAME="vm-expirer-b3"
VERSION="1.0.0"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
PYTHON_VERSION="312"  # ou 311

echo "=== Building Docker Image with UBI9 Python ${PYTHON_VERSION} ==="
podman build -t ${FULL_IMAGE} .
podman tag ${FULL_IMAGE} ${REGISTRY}/${IMAGE_NAME}:latest

echo "=== Testing Image ==="
podman run --rm ${FULL_IMAGE} python --version

echo "=== Pushing to Registry ==="
podman push ${FULL_IMAGE}
podman push ${REGISTRY}/${IMAGE_NAME}:latest

echo "=== Deployment complete! ==="
echo "Base Image: registry.access.redhat.com/ubi9/python-${PYTHON_VERSION}"
echo "Final Image: ${FULL_IMAGE}"
