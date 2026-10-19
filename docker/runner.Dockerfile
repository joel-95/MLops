# docker/runner.Dockerfile
# Container that executes a connected repository's training script on self-hosted GPU runner

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-install common ML frameworks and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    numpy \
    pandas \
    scipy \
    scikit-learn \
    pyyaml \
    mlflow \
    evidently \
    requests \
    joblib

# Prepare output artifact volume directory
RUN mkdir -p /output

# Entrypoint script: installs repo-specific requirements if present and executes the declared training script
COPY <<'EOF' /entrypoint.sh
#!/bin/bash
set -e

ENTRY_POINT="${ENTRY_POINT:-ml/train.py}"
REQUIREMENTS="${REQUIREMENTS:-requirements.txt}"

if [ -f "/workspace/${REQUIREMENTS}" ]; then
    echo "Installing repo-specific requirements from ${REQUIREMENTS}..."
    pip install --no-cache-dir -r "/workspace/${REQUIREMENTS}"
fi

echo "Running training entry point: ${ENTRY_POINT}..."
cd /workspace
python "${ENTRY_POINT}"

# Ensure output directory receives metrics.json and artifacts
if [ -f "/workspace/metrics.json" ]; then
    cp /workspace/metrics.json /output/metrics.json
fi
if [ -d "/workspace/artifacts" ]; then
    cp -r /workspace/artifacts/* /output/ || true
fi

echo "Training container execution completed."
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
