#!/usr/bin/env bash
# D-042, two training runs at a time (the user allowed two parallel jobs at 15:5x UTC). Takes over from
# run_chain_d042.sh between steps; d042-g-s42, in progress at the hand-over, was left running. One worker
# per arm, seeds in order; then LR, the uncertainty tables and D-042's rule, one at a time.
# A run counts as done only if all fold checkpoints are there and metrics.json says complete; a run that
# is not is repeated once with --resume.
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
running() {  # python processes training <run> (python.exe only, so the query never counts itself)
  powershell.exe -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match '--run $1 ' }).Count" | tr -d '\r'
}
train() {  # train <run> <n_folds> <train.py args...>
  local run=$1 n=$2; shift 2
  if done_train "$run" "$n"; then note "$run already done"; return; fi
  if [ "$(running "$run")" != "0" ]; then
    note "$run in progress (started by run_chain_d042.sh) - waiting for it"
    while [ "$(running "$run")" != "0" ]; do sleep 30; done
    note "$run process ended"
  else
    step "$run" $PY -u scripts/train.py --run "$run" "$@"
  fi
  if done_train "$run" "$n"; then note "$run OK"; return; fi
  note "$run NOT DONE - repeating once with --resume"
  step "$run-resume" $PY -u scripts/train.py --run "$run" "$@" --resume
  if done_train "$run" "$n"; then note "$run OK after resume"; else note "$run FAILED"; fi
}
arm() {  # arm <g|h>: that arm's three seeds, in order
  local a=$1 cfg
  [ "$a" = g ] && cfg=configs/d042/ctu_global_window.yaml || cfg=configs/d042/ctu_hostrel_window.yaml
  for S in 42 43 44; do
    train d042-$a-s$S 7 --data data/processed/ctu13_hostrel --model-config $cfg \
      --group-folds configs/ctu13_folds.yaml --seed $S --no-figures
  done
}

note "hand-over: run_chain_d042.sh stopped between steps; run_chain_d042_par.sh runs arms G and H in parallel"
arm g &
arm h &
wait
note "both arms finished"
for A in g h; do
  [ $A = g ] && CFG=configs/d042/ctu_global_window.yaml || CFG=configs/d042/ctu_hostrel_window.yaml
  step lr-d042-$A $PY -u scripts/lr_baseline.py --data data/processed/ctu13_hostrel --model-config $CFG \
    --group-folds configs/ctu13_folds.yaml --run lr-d042-$A
done
step ci-e25b $PY -u scripts/ctu_bootstrap_ci.py --tag e25b --data data/processed/ctu13 \
  --wm s42=e25-ctu13-s42 s43=e25-ctu13-s43 s44=e25-ctu13-s44 --lr LR=lr-ctu13-s42
step ci-d042-g $PY -u scripts/ctu_bootstrap_ci.py --tag d042-g --data data/processed/ctu13_hostrel \
  --wm s42=d042-g-s42 s43=d042-g-s43 s44=d042-g-s44 --lr LR=lr-d042-g
step ci-d042-h $PY -u scripts/ctu_bootstrap_ci.py --tag d042-h --data data/processed/ctu13_hostrel \
  --wm s42=d042-h-s42 s43=d042-h-s43 s44=d042-h-s44 --lr LR=lr-d042-h
step d042-compare $PY -u scripts/d042_compare.py
note "d042 chain done"
