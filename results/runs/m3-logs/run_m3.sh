#!/usr/bin/env bash
# M3 (D-044 and its amendment, 986e626): verification build, comparison, then the pre-registered runs,
# one job at a time. A training run counts as done only if all fold checkpoints exist and metrics.json
# says complete; a run that is not is repeated once with --resume.
set -u
cd "$(dirname "$0")/../../.."
PY=.venv/Scripts/python.exe
LOG=results/runs/m3-logs
ST=$LOG/m3.status
export OMP_NUM_THREADS=4
note() { echo "$(date -u +%FT%TZ) $*" >> "$ST"; }
step() { local name=$1; shift; note "start $name"; "$@" > "$LOG/$name.log" 2>&1; note "$name exit=$?"; }
done_train() {
  [ "$(ls models/$1/*.pt 2>/dev/null | wc -l)" -eq "$2" ] || return 1
  $PY -c "import json,sys; sys.exit(0 if json.load(open('results/runs/$1/metrics.json'))['metrics'].get('complete') else 1)" 2>/dev/null
}
train() {
  local run=$1 n=$2; shift 2
  if done_train "$run" "$n"; then note "$run already done"; return; fi
  step "$run" $PY -u scripts/train.py --run "$run" "$@"
  if done_train "$run" "$n"; then note "$run OK"; return; fi
  note "$run NOT DONE - repeating once with --resume"
  step "$run-resume" $PY -u scripts/train.py --run "$run" "$@" --resume
  if done_train "$run" "$n"; then note "$run OK after resume"; else note "$run FAILED"; fi
}

# First attempt: pandas ran out of memory reading feb20's CSV at 1 M-row chunks (verify-build.oom-feb20.log;
# feb14-16 were built). Per the user: retry the missing days at the same 1 M rows, and step down only if
# that crashes again - the chunk size changes how much of a file is in memory at once, not what is read,
# and every day must still come out identical to the first build.
ALL="feb14 feb15 feb16 feb20 feb21 feb22 feb23 feb28 mar01 mar02"
missing() { for s in $ALL; do [ -f data/processed/cicids2018_verify/$s.parquet ] || printf '%s ' "$s"; done; }
for CH in 1000000 500000 250000; do
  M=$(missing); [ -z "$M" ] && break
  step verify-build-$CH $PY -u scripts/build_cicids2018.py --config configs/cicids2018_verify.yaml --chunk-rows $CH --splits $M
done
[ -z "$(missing)" ] || { note "verification build incomplete after 250,000-row chunks: $(missing)- stopping"; exit 1; }
step compare-builds $PY -u scripts/compare_builds.py data/processed/cicids2018 data/processed/cicids2018_verify
if ! grep -q "builds identical: True" "$LOG/compare-builds.log"; then note "builds differ - stopping before any training"; exit 1; fi
note "builds identical - training starts"
for S in 42 43 44; do
  train m3-s$S 6 --data data/processed/cicids2018 --model-config configs/m3/m3_stack.yaml \
    --group-folds configs/cicids2018_folds.yaml --seed $S --no-figures
done
step lr-m3 $PY -u scripts/lr_baseline.py --data data/processed/cicids2018 --model-config configs/m3/m3_stack.yaml \
  --group-folds configs/cicids2018_folds.yaml --run lr-m3
step m3-matrix $PY -u scripts/m3_family_matrix.py
note "m3 chain done"
