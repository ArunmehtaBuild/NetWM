#!/usr/bin/env bash
# M3 (D-044): the chunking self-check on one day, then the ten-day build, one after the other.
set -u
cd "$(dirname "$0")/../../.."
PY=.venv/Scripts/python.exe
LOG=results/runs/m3-build
echo "$(date -u +%FT%TZ) start check" >> $LOG/build.status
$PY -u scripts/build_cicids2018.py --config configs/cicids2018.yaml --check-chunking feb15 > $LOG/check_chunking.log 2>&1
rc=$?; echo "$(date -u +%FT%TZ) check exit=$rc" >> $LOG/build.status
[ $rc -eq 0 ] || exit 1
echo "$(date -u +%FT%TZ) start build" >> $LOG/build.status
$PY -u scripts/build_cicids2018.py --config configs/cicids2018.yaml > $LOG/build.log 2>&1
echo "$(date -u +%FT%TZ) build exit=$?" >> $LOG/build.status
