#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/juhwan7/stock-autoresearch}"
RUNNER_TOKEN="${RUNNER_TOKEN:-}"
RUNNER_LABEL="${RUNNER_LABEL:-stock-autoresearch-fixed-ip}"
RUNNER_DIR="${RUNNER_DIR:-/opt/actions-runner}"
RUNNER_USER="${RUNNER_USER:-actions}"

if [[ -z "$RUNNER_TOKEN" ]]; then
  echo "RUNNER_TOKEN is required."
  echo "GitHub repo > Settings > Actions > Runners > New self-hosted runner에서 임시 등록 토큰을 복사하세요."
  exit 2
fi

sudo apt-get update
sudo apt-get install -y curl git tar ca-certificates python3 python3-venv

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash "$RUNNER_USER"
fi

sudo mkdir -p "$RUNNER_DIR"
sudo chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ASSET_ARCH="x64" ;;
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH"; exit 3 ;;
esac

RUNNER_VERSION="$(
  curl -fsSL https://api.github.com/repos/actions/runner/releases/latest     | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))'
)"
ASSET="actions-runner-linux-${ASSET_ARCH}-${RUNNER_VERSION}.tar.gz"
URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ASSET}"

sudo -u "$RUNNER_USER" bash -lc "
  cd '$RUNNER_DIR'
  if [[ ! -x ./run.sh ]]; then
    curl -fsSL '$URL' -o '$ASSET'
    tar xzf '$ASSET'
    rm -f '$ASSET'
  fi
  ./config.sh remove --token '$RUNNER_TOKEN' >/dev/null 2>&1 || true
  ./config.sh \
    --url '$REPO_URL' \
    --token '$RUNNER_TOKEN' \
    --name 'stock-autoresearch-ec2' \
    --labels '$RUNNER_LABEL' \
    --work '_work' \
    --unattended \
    --replace
"

cd "$RUNNER_DIR"
sudo ./svc.sh install "$RUNNER_USER" || true
sudo ./svc.sh start
sudo ./svc.sh status

echo
echo "Runner installed."
echo "Next:"
echo "1) GitHub Actions variable TOSS_FIXED_IP_RUNNER_ENABLED=true"
echo "2) EC2 Elastic IP를 Toss WTS > 설정 > Open API > 허용 IP에 등록"
echo "3) GitHub Actions > '고정 IP 토스 6분 시장 데이터' > Run workflow"
