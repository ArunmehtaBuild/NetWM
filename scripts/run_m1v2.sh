#!/usr/bin/env bash
# D-035 sweep runner: one experiment (config) x seeds 42/43/44, three processes in parallel,
# 5 folds each. Usage: bash scripts/run_m1v2.sh <exp-id> <model-config> [processed-dir]
#   bash scripts/run_m1v2.sh e19 configs/m1v2/e19_base.yaml
set -u
EXP=$1; CFG=$2; DATA=${3:-data/processed/cicids2017_m1v2}
LOG=results/runs/m1v2-sweep-logs
mkdir -p "$LOG"
for SEED in 42 43 44; do
  (
    OMP_NUM_THREADS=4 .venv/Scripts/python.exe -u scripts/train.py --data "$DATA" \
      --model-config "$CFG" --test-days monday tuesday wednesday thursday friday \
      --run "m1v2-$EXP-s$SEED" --epochs 25 --seed "$SEED" --no-figures \
      > "$LOG/m1v2-$EXP-s$SEED.log" 2>&1
    echo "m1v2-$EXP-s$SEED exit=$?" >> "$LOG/$EXP.status"
  ) &
done
wait
cat "$LOG/$EXP.status"
