#!/usr/bin/env bash
# D-042 (pre-registered in 1c78e49), one job at a time, after D-041's gates: the host-relative CTU-13
# matrix, arms G and H seed by seed, LR on both input sets, then the uncertainty tables (E25b's final
# table and both arms) and D-042's rule. A training run counts as done only if all fold checkpoints are
# there and metrics.json says complete; a run that is not is repeated once with --resume.
set -u
cd "$(dirname "$0")/../../.."
PY=.venv/Scripts/python.exe
LOG=results/runs/n8-logs
ST=$LOG/chain_d042.status
export OMP_NUM_THREADS=4

note() { echo "$(date -u +%FT%TZ) $*" >> "$ST"; }
step() {  # step <logname> <cmd...>
  local name=$1; shift
  note "start $name"
  "$@" > "$LOG/$name.log" 2>&1
  note "$name exit=$?"
}
done_train() {
  [ "$(ls models/$1/*.pt 2>/dev/null | wc -l)" -eq "$2" ] || return 1
  $PY -c "import json,sys; sys.exit(0 if json.load(open('results/runs/$1/metrics.json'))['metrics'].get('complete') else 1)" 2>/dev/null
}
train() {  # train <run> <n_folds> <train.py args...>
  local run=$1 n=$2; shift 2
  if done_train "$run" "$n"; then note "$run already done"; return; fi
  step "$run" $PY -u scripts/train.py --run "$run" "$@"
  if done_train "$run" "$n"; then note "$run OK"; return; fi
  note "$run NOT DONE - repeating once with --resume"
  step "$run-resume" $PY -u scripts/train.py --run "$run" "$@" --resume
  if done_train "$run" "$n"; then note "$run OK after resume"; else note "$run FAILED"; fi
}

step d042-build $PY -u scripts/build_ctu13_hostrel.py --config configs/ctu13_hostrel.yaml
if ! $PY -c "import json,sys; sys.exit(0 if len(json.load(open('data/processed/ctu13_hostrel/meta.json'))['splits']) == 13 else 1)"; then
  note "d042-build FAILED - stopping"; exit 1
fi
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
# ---- item 3 (D-042's uncertainty method) on E25b's final table, then on both arms; then D-042's rule
step ci-e25b $PY -u scripts/ctu_bootstrap_ci.py --tag e25b --data data/processed/ctu13 \
  --wm s42=e25-ctu13-s42 s43=e25-ctu13-s43 s44=e25-ctu13-s44 --lr LR=lr-ctu13-s42
step ci-d042-g $PY -u scripts/ctu_bootstrap_ci.py --tag d042-g --data data/processed/ctu13_hostrel \
  --wm s42=d042-g-s42 s43=d042-g-s43 s44=d042-g-s44 --lr LR=lr-d042-g
step ci-d042-h $PY -u scripts/ctu_bootstrap_ci.py --tag d042-h --data data/processed/ctu13_hostrel \
  --wm s42=d042-h-s42 s43=d042-h-s43 s44=d042-h-s44 --lr LR=lr-d042-h
step d042-compare $PY -u scripts/d042_compare.py
note "d042 chain done"
