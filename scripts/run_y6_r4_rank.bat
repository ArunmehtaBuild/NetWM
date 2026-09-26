@echo off
echo Starting Round 4 (rank-normalisation) Training (Y-6)
echo ===================================

echo Seed 42...
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_r4_rank.yaml --test-days tuesday wednesday thursday friday monday --run r4-rank-s42 --epochs 25 --seed 42

echo Seed 43...
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_r4_rank.yaml --test-days tuesday wednesday thursday friday monday --run r4-rank-s43 --epochs 25 --seed 43

echo Seed 44...
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_r4_rank.yaml --test-days tuesday wednesday thursday friday monday --run r4-rank-s44 --epochs 25 --seed 44

echo Evaluating against D-023 bar...
python scripts/precursor_eval.py --run r4-rank-s42 r4-rank-s43 r4-rank-s44 --deterministic --n-shifts 2000

echo ===================================
echo Done! Please review the results and update results.md (E16 table).
