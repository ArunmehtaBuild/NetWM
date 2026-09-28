#!/usr/bin/env bash
# D-041 training chain (pre-registered in 1c78e49): E20rw x 3 seeds, then r2w x 3 seeds + the r2i control.
set -u
cd "$(dirname "$0")/../../.."
bash scripts/run_m1v2.sh n8-e20rw configs/n8/e20r_pcap_window.yaml data/processed/cicids2017_m1v2p
LOG=results/runs/n8-logs
for SEED in 42 43 44; do
  ( OMP_NUM_THREADS=3 .venv/Scripts/python.exe -u scripts/train.py --config configs/cicids2017.yaml \
      --model-config configs/n8/r2_window.yaml --test-days thursday friday --epochs 25 --samples 16 \
      --run n8-r2w-s$SEED --seed $SEED --no-figures > "$LOG/n8-r2w-s$SEED.log" 2>&1
    echo "n8-r2w-s$SEED exit=$?" >> "$LOG/d041.status" ) &
done
( OMP_NUM_THREADS=3 .venv/Scripts/python.exe -u scripts/train.py --config configs/cicids2017.yaml \
    --test-days thursday friday --epochs 25 --samples 16 --run n8-r2i-s42 --seed 42 --no-figures \
    > "$LOG/n8-r2i-s42.log" 2>&1
  echo "n8-r2i-s42 exit=$?" >> "$LOG/d041.status" ) &
wait
echo "chain done" >> "$LOG/d041.status"
