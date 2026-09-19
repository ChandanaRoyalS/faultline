#!/usr/bin/env bash
# T6.7 piece 2 - the nightly snapshot. One `pg_dump --clean --if-exists` of the platform's
# database into ~/snapshots, dated to the minute in UTC, and a seven-day window.
#
# **This is the file that makes README §4's "no backups beyond the manual snapshot" untrue.**
# It is the same command §3.7's drill restored from on 2026-09-19 (979 KB, restored in 0.48 s,
# every table at its count), run by cron instead of by hand. The snapshot directory is the
# deploy user's home, not /tmp: the one snapshot that mattered before this file lived in /tmp
# and would not have survived the reboot the VM has been asking for.
#
# Install (README §3.7): `crontab -e` and one line -
#   17 3 * * * /home/deploy/faultline/deploy/snapshot.sh >> /home/deploy/snapshots/cron.log 2>&1
#
# Not a backup off the machine. A disk that dies takes the snapshots with the database; the
# honest sentence for §4 is "nightly snapshots on the same disk", and off-host copies are a
# decision about where a portfolio system's data may go, which this script does not make.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOT_DIR="${FAULTLINE_SNAPSHOT_DIR:-$HOME/snapshots}"
KEEP_DAYS="${FAULTLINE_SNAPSHOT_KEEP_DAYS:-7}"
STAMP="$(date -u +%Y-%m-%dT%H%MZ)"
TARGET="$SNAPSHOT_DIR/faultline-$STAMP.sql.gz"

mkdir -p "$SNAPSHOT_DIR"
cd "$DEPLOY_DIR"
# `-T`: no pseudo-terminal, because cron has none and compose would otherwise refuse.
docker compose exec -T postgres pg_dump -U faultline --clean --if-exists faultline | gzip > "$TARGET"
# A dump that failed half-way is a small file that restores to nothing. Refuse to keep one.
if [ "$(stat -c %s "$TARGET")" -lt 10240 ]; then
  echo "snapshot $TARGET is $(stat -c %s "$TARGET") bytes - too small to be a database; removed" >&2
  rm -f "$TARGET"
  exit 1
fi
find "$SNAPSHOT_DIR" -name 'faultline-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) snapshot $TARGET $(stat -c %s "$TARGET") bytes; kept: $(ls "$SNAPSHOT_DIR"/faultline-*.sql.gz | wc -l)"
