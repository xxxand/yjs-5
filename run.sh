#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# 凭证文件路径；代码会自动把 C:\... 转成 WSL 的 /mnt/c/...
if [ -z "${OSS_ACCESS_KEY_CSV:-}" ]; then
  export OSS_ACCESS_KEY_CSV='C:\Users\14898\Downloads\AccessKey.csv'
fi
export OSS_ENDPOINT="${OSS_ENDPOINT:-https://oss-cn-beijing.aliyuncs.com}"
export OSS_BUCKET="${OSS_BUCKET:-jxxyyy}"
export OSS_REGION="${OSS_REGION:-cn-beijing}"

exec python3 app.py
