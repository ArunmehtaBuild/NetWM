@echo off
echo Starting Y-4 Ablation Tests (E10)
echo ===================================

echo 1. Full model (v1 features)
python scripts/train.py --config configs/cicids2017.yaml --run e10-full-s42 --epochs 25 --samples 16 --seed 42 --test-days thursday friday
python scripts/train.py --config configs/cicids2017.yaml --run e10-full-s43 --epochs 25 --samples 16 --seed 43 --test-days thursday friday
python scripts/train.py --config configs/cicids2017.yaml --run e10-full-s44 --epochs 25 --samples 16 --seed 44 --test-days thursday friday

echo 2. Ablation: NO stochastic latent (latent_dim = 0)
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_no_stochastic.yaml --run e10-no-stochastic-s42 --epochs 25 --samples 16 --seed 42 --test-days thursday friday
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_no_stochastic.yaml --run e10-no-stochastic-s43 --epochs 25 --samples 16 --seed 43 --test-days thursday friday
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_no_stochastic.yaml --run e10-no-stochastic-s44 --epochs 25 --samples 16 --seed 44 --test-days thursday friday

echo 3. Ablation: NO multi-step loss
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_no_multistep.yaml --run e10-no-multistep-s42 --epochs 25 --samples 16 --seed 42 --test-days thursday friday
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_no_multistep.yaml --run e10-no-multistep-s43 --epochs 25 --samples 16 --seed 43 --test-days thursday friday
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/model_no_multistep.yaml --run e10-no-multistep-s44 --epochs 25 --samples 16 --seed 44 --test-days thursday friday

echo ===================================
echo Done! Please review the results and update results.md with the table.
