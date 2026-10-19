#!/usr/bin/env bash
# runner/setup_runner.sh
# Registers the self-hosted GitHub Actions runner on the GPU machine (RTX 3050).
# Idempotent: checks for existing runner installation and skips redundant registrations.

set -e

RUNNER_DIR="${HOME}/actions-runner"
RUNNER_VERSION="2.319.1"
RUNNER_LABEL="self-hosted,gpu,rtx3050"

echo "=== AutoMLOps Self-Hosted GPU Runner Setup ==="

# 1. Verify NVIDIA GPU & CUDA Drivers
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU Detected:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
    echo "WARNING: nvidia-smi not found. Ensure NVIDIA CUDA drivers are installed for GPU acceleration."
fi

# 2. Check if runner is already configured
if [ -f "${RUNNER_DIR}/.runner" ]; then
    echo "Runner is already configured at ${RUNNER_DIR}."
    echo "Checking service status..."
    if [ -f "${RUNNER_DIR}/svc.sh" ]; then
        cd "${RUNNER_DIR}" && sudo ./svc.sh status || true
    fi
    echo "Setup already completed. To reconfigure, remove ${RUNNER_DIR} and re-run."
    exit 0
fi

# 3. Create runner directory & download binary
mkdir -p "${RUNNER_DIR}" && cd "${RUNNER_DIR}"

if [ ! -f "actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" ]; then
    echo "Downloading GitHub Actions runner v${RUNNER_VERSION}..."
    curl -o "actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" -L \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
    tar xzf "./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
fi

# 4. Check for configuration token
if [ -z "${RUNNER_TOKEN}" ] || [ -z "${REPO_URL}" ]; then
    echo "ERROR: Missing environment variables."
    echo "Please export REPO_URL (e.g. https://github.com/owner/repo) and RUNNER_TOKEN."
    exit 1
fi

# 5. Configure runner
echo "Configuring runner against ${REPO_URL} with labels: ${RUNNER_LABEL}..."
./config.sh --url "${REPO_URL}" \
            --token "${RUNNER_TOKEN}" \
            --labels "${RUNNER_LABEL}" \
            --unattended \
            --replace

# 6. Install as systemd service
echo "Installing runner as a systemd background service..."
sudo ./svc.sh install
sudo ./svc.sh start

echo "=== Runner setup successfully completed and active! ==="
