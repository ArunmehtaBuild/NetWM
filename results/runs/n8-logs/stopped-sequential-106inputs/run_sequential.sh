#!/usr/bin/env bash
# D-041 + D-042 training, one job at a time (the user asked for no parallel runs; a first, parallel
# attempt of the E20rw sweep was stopped in its first fold - logs in stopped-parallel/).
# Same train.py arguments as the pre-registered commands; only the scheduling differs.
set -u
cd "$(dirname "$0")/../../.."
PY=.venv/Scripts/python.exe
LOG=results/runs/n8-logs
ST=$LOG/sequential.status
export OMP_NUM_THREADS=4
step() {  # step <name> <cmd...>
  local name=$1; shift
  echo "$(date -u +%FT%TZ) start $name" >> "$ST"
  "$@" > "$LOG/$name.log" 2>&1
  echo "$(date -u +%FT%TZ) $name exit=$?" >> "$ST"
}
# D-041: E20r with window positions, 5 folds per seed (run_m1v2.sh's arguments)
for S in 42 43 44; do
  step m1v2-n8-e20rw-s$S $PY -u scripts/train.py --data data/processed/cicids2017_m1v2p \
    --model-config configs/n8/e20r_pcap_window.yaml --test-days monday tuesday wednesday thursday friday \
    --run m1v2-n8-e20rw-s$S --epochs 25 --seed $S --no-figures
done
# D-041: r2's setup with window positions, then the r2i control (today's code, interp)
for S in 42 43 44; do
  step n8-r2w-s$S $PY -u scripts/train.py --config configs/cicids2017.yaml --model-config configs/n8/r2_window.yaml \
    --test-days thursday friday --epochs 25 --samples 16 --run n8-r2w-s$S --seed $S --no-figures
done
step n8-r2i-s42 $PY -u scripts/train.py --config configs/cicids2017.yaml \
  --test-days thursday friday --epochs 25 --samples 16 --run n8-r2i-s42 --seed 42 --no-figures
# D-042: the host-relative CTU-13 matrix, then arms G and H seed by seed, then LR on both input sets
step d042-build $PY -u scripts/build_ctu13_hostrel.py --config configs/ctu13_hostrel.yaml
for S in 42 43 44; do
  for A in g h; do
    [ $A = g ] && CFG=configs/d042/ctu_global_window.yaml || CFG=configs/d042/ctu_hostrel_window.yaml
    step d042-$A-s$S $PY -u scripts/train.py --data data/processed/ctu13_hostrel --model-config $CFG \
      --group-folds configs/ctu13_folds.yaml --run d042-$A-s$S --seed $S --no-figures
  done
done
step lr-d042-g $PY -u scripts/lr_baseline.py --data data/processed/ctu13_hostrel \
  --model-config configs/d042/ctu_global_window.yaml --group-folds configs/ctu13_folds.yaml --run lr-d042-g
step lr-d042-h $PY -u scripts/lr_baseline.py --data data/processed/ctu13_hostrel \
  --model-config configs/d042/ctu_hostrel_window.yaml --group-folds configs/ctu13_folds.yaml --run lr-d042-h
echo "$(date -u +%FT%TZ) chain done" >> "$ST"
