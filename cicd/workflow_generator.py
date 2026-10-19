from typing import Dict, Any


def generate_workflow(mlops_config: Dict[str, Any], backend_url: str = "http://localhost:8000") -> str:
    """
    Generates the GitHub Actions workflow (.github/workflows/mlops.yml)
    customised to the connected repository's framework and entry point.
    """
    project_name = mlops_config.get("project_name", "mlops-pipeline")
    entry_point = mlops_config.get("entry_point", "ml/train.py")
    dependencies = mlops_config.get("dependencies", "requirements.txt")
    task_type = mlops_config.get("task_type", "classification")

    workflow_content = f"""name: AutoMLOps Pipeline - {project_name}

on:
  push:
    branches:
      - main
      - master
  repository_dispatch:
    types:
      - automlops-retrain

jobs:
  train-and-evaluate:
    runs-on: self-hosted
    env:
      BACKEND_CALLBACK_URL: "{backend_url}"
      REPO_ID: "${{{{ github.event.repository.name }}}}"
      COMMIT_SHA: "${{{{ github.sha }}}}"
      TASK_TYPE: "{task_type}"

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Verify GPU Access
        run: |
          if command -v nvidia-smi &> /dev/null; then
            nvidia-smi
          else
            echo "NVIDIA GPU not detected, proceeding with standard execution."
          fi

      - name: Install Project Dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f "{dependencies}" ]; then
            pip install -r {dependencies}
          fi
          pip install requests pyyaml

      - name: Execute Model Training
        run: |
          echo "Starting training script: {entry_point}"
          python {entry_point}

      - name: Run Quality Gate Check
        id: quality_gate
        run: |
          python -c "
          import json, sys
          from ml.quality_gate import check_quality_gate
          passed, details = check_quality_gate('metrics.json', 'mlops.yaml')
          print('Quality Gate Result:', json.dumps(details, indent=2))
          if not passed:
              sys.exit(1)
          "

      - name: Notify AutoMLOps Backend (Success)
        if: success()
        run: |
          python -c "
          import json, os, urllib.request
          callback_url = os.environ.get('BACKEND_CALLBACK_URL') + '/webhook/pipeline-result'
          payload = {{
              'repo_id': os.environ.get('REPO_ID'),
              'commit_sha': os.environ.get('COMMIT_SHA'),
              'status': 'passed',
              'metrics': json.load(open('metrics.json')) if os.path.exists('metrics.json') else {{}}
          }}
          req = urllib.request.Request(callback_url, data=json.dumps(payload).encode('utf-8'), headers={{'Content-Type': 'application/json'}})
          try:
              urllib.request.urlopen(req, timeout=10)
          except Exception as e:
              print('Callback warning:', e)
          "

      - name: Notify AutoMLOps Backend (Failure)
        if: failure()
        run: |
          python -c "
          import json, os, urllib.request
          callback_url = os.environ.get('BACKEND_CALLBACK_URL') + '/webhook/pipeline-result'
          payload = {{
              'repo_id': os.environ.get('REPO_ID'),
              'commit_sha': os.environ.get('COMMIT_SHA'),
              'status': 'failed'
          }}
          req = urllib.request.Request(callback_url, data=json.dumps(payload).encode('utf-8'), headers={{'Content-Type': 'application/json'}})
          try:
              urllib.request.urlopen(req, timeout=10)
          except Exception as e:
              print('Callback warning:', e)
          "
"""
    return workflow_content
