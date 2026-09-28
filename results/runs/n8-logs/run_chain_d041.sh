#!/usr/bin/env bash
# D-041's remaining runs, then its gate evaluation, one job at a time. Takes over from run_chain.sh,
# which was stopped between steps so that D-041's gates are scored before D-042 starts (D-042 runs
# afterwards from its own chain). The run in progress at the hand-over was left running: this chain
# waits for it, then checks its outputs like any other run.
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
running() {  # number of python processes training <run> (python.exe only, so this query never counts itself)
  powershell.exe -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match '--run $1 ' }).Count" | tr -d '\r'
}
check() {  # check <run> <n_folds> <train.py args...>: repeat once with --resume if not done
  local run=$1 n=$2; shift 2
  if done_train "$run" "$n"; then note "$run OK"; return; fi
  note "$run NOT DONE - repeating once with --resume"
  step "$run-resume" $PY -u scripts/train.py --run "$run" "$@" --resume
  if done_train "$run" "$n"; then note "$run OK after resume"; else note "$run FAILED"; fi
}
train() {  # train <run> <n_folds> <train.py args...>
  local run=$1 n=$2; shift 2
  if done_train "$run" "$n"; then note "$run already done"; return; fi
  if [ "$(running "$run")" != "0" ]; then
    note "$run in progress (started by run_chain.sh) - waiting for it"
    while [ "$(running "$run")" != "0" ]; do sleep 30; done
    note "$run process ended"
  else
    step "$run" $PY -u scripts/train.py --run "$run" "$@"
  fi
  check "$run" "$n" "$@"
}

note "hand-over: run_chain.sh stopped between steps; run_chain_d041.sh continues D-041, then its gates"
for S in 42 43 44; do
  train m1v2-n8-e20rw-s$S 5 --data data/processed/cicids2017_m1v2p --model-config configs/n8/e20r_pcap_window.yaml \
    --test-days monday tuesday wednesday thursday friday --epochs 25 --seed $S --no-figures
done
for S in 42 43 44; do
  train n8-r2w-s$S 2 --config configs/cicids2017.yaml --model-config configs/n8/r2_window.yaml \
    --test-days thursday friday --epochs 25 --samples 16 --seed $S --no-figures
done
train n8-r2i-s42 2 --config configs/cicids2017.yaml --test-days thursday friday --epochs 25 --samples 16 \
  --seed 42 --no-figures

# ---- D-041's gates (scripts/n8_eval.py), then the unit-test part of G1
step n8-eval $PY -u scripts/n8_eval.py
step n8-unit-tests $PY -m pytest -q tests/test_positional_window.py tests/test_world_model.py -p no:cacheprovider
note "d041 chain done"
