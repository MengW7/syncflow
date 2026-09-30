#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
SQL_FILE="$SCRIPT_DIR/init_db.sql"

usage() {
  echo "Usage: $0 [--test] [DB_NAME]"
  echo "  不传参数     迁移 .env 里的 MYSQL_DATABASE"
  echo "  --test       创建并迁移 MYSQL_TEST_DATABASE"
  echo "  DB_NAME      迁移指定库（不要和 --test 一起用）"
  exit 1
}

TEST=0
DB_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --test|-test|-t)
      TEST=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      DB_NAME="$1"
      shift
      ;;
  esac
done

[ -f "$ENV_FILE" ] || { echo "找不到 $ENV_FILE" >&2; exit 1; }
[ -f "$SQL_FILE" ] || { echo "找不到 $SQL_FILE" >&2; exit 1; }

set -a
# 兼容 Windows 检出的 CRLF
source <(sed 's/\r$//' "$ENV_FILE")
set +a

: "${MYSQL_USER:?缺少 MYSQL_USER}"
: "${MYSQL_PASSWORD:?缺少 MYSQL_PASSWORD}"
: "${MYSQL_DATABASE:?缺少 MYSQL_DATABASE}"

cd "$ROOT_DIR"

if [[ "$TEST" -eq 1 ]]; then
  : "${MYSQL_TEST_DATABASE:?缺少 MYSQL_TEST_DATABASE}"
  : "${MYSQL_ROOT_PASSWORD:?缺少 MYSQL_ROOT_PASSWORD}"
  TARGET_DB="$MYSQL_TEST_DATABASE"

  docker compose exec -T mysql \
    mysql --user=root --password="${MYSQL_ROOT_PASSWORD}" \
    -e "CREATE DATABASE IF NOT EXISTS \`${TARGET_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON \`${TARGET_DB}\`.* TO '${MYSQL_USER}'@'%'; FLUSH PRIVILEGES;"
else
  TARGET_DB="${DB_NAME:-$MYSQL_DATABASE}"
fi

docker compose exec -T mysql \
  mysql --user="${MYSQL_USER}" --password="${MYSQL_PASSWORD}" \
  --default-character-set=utf8mb4 "$TARGET_DB" < "$SQL_FILE"

echo "migrated: $TARGET_DB"