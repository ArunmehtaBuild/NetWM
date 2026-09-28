#!/usr/bin/env bash
# D-041 + D-042 training, one job at a time (user request; D-041 amendment, 050adaa).
# Same train.py / build / lr_baseline arguments as the pre-registered commands; only the order differs.
# A run counts as done only if its outputs are there (all fold checkpoints + metrics.json complete),
# not because it exited 0; a run that is not done is repeated once with --resume.
set -u
cd "$(dirname "$0")/../../.."
PY=.venv/Scripts/python.exe
LOG=results/runs/n8-logs
ST=$LOG/chain.status
export OMP_NUM_THREADS=4

note() { echo "$(date -u +%FT%TZ) $*" >> "$ST"; }
step() {  # step <logname> <cmd...>
  local name=$1; shift
  note "start $name"
  "$@" > "$LOG/$name.log" 2>&1
  note "$name exit=$?"
}
done_train() {  # done_train <run> <n_folds>
  [ "$(ls models/$1/*.pt 2>/dev/null | wc -l)" -eq "$2" ] || return 1
  $PY -c "import json,sys; sys.exit(0 if json.load(open('results/runs/$1/metrics.json'))['metrics'].get('complete') else 1)" 2>/dev/null
}
train() {  # train <run> <n_folds> <train.py args...>
  local run=$1 n=$2; shift 2
  step "$run" $PY -u scripts/train.py --run "$run" "$@"
  if done_train "$run" "$n"; then note "$run OK"; return; fi
  note "$run NOT DONE - repeating once with --resume"
  step "$run-resume" $PY -u scripts/train.py --run "$run" "$@" --resume
  if done_train "$run" "$n"; then note "$run OK after resume"; else note "$run FAILED"; fi
}

# ---- D-041: E20r with window positions (E20r's 105 inputs), 5 folds per seed
for S in 42 43 44; do
  train m1v2-n8-e20rw-s$S 5 --data data/processed/cicids2017_m1v2p --model-config configs/n8/e20r_pcap_window.yaml \
    --test-days monday tuesday wednesday thursday friday --epochs 25 --seed $S --no-figures
done
# ---- D-041: r2's setup with window positions, then the r2i control (today's code, interp)
for S in 42 43 44; do
  train n8-r2w-s$S 2 --config configs/cicids2017.yaml --model-config configs/n8/r2_window.yaml \
    --test-days thursday friday --epochs 25 --samples 16 --seed $S --no-figures
done
train n8-r2i-s42 2 --config configs/cicids2017.yaml --test-days thursday friday --epochs 25 --samples 16 \
  --seed 42 --no-figures

# ---- D-042: the host-relative CTU-13 matrix, then arms G and H seed by seed, then LR on both input sets
step d042-build $PY -u scripts/build_ctu13_hostrel.py --config configs/ctu13_hostrel.yaml
if $PY -c "import json,sys; sys.exit(0 if len(json.load(open('data/processed/ctu13_hostrel/meta.json'))['splits']) == 13 else 1)"; then
  note "d042-build OK (13 splits)"
  for S in 42 43 44; do
    train d042-g-s$S 7 --data data/processed/ctu13_hostrel --model-config configs/d042/ctu_global_window.yaml \
      --group-folds configs/ctu13_folds.yaml --seed $S --no-figures
    train d042-h-s$S 7 --data data/processed/ctu13_hostrel --model-config configs/d042/ctu_hostrel_window.yaml \
      --group-folds configs/ctu13_folds.yaml --seed $S --no-figures
  done
  for A in g h; do
    [ $A = g ] && CFG=configs/d042/ctu_global_window.yaml || CFG=configs/d042/ctu_hostrel_window.yaml
    step lr-d042-$A $PY -u scripts/lr_baseline.py --data data/processed/ctu13_hostrel --model-config $CFG \
      --group-folds configs/ctu13_folds.yaml --run lr-d042-$A
  done
else
  note "d042-build FAILED - D-042 training skipped"
fi
note "chain done"
