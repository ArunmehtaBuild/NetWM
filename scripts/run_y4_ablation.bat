@echo off
echo Starting Y-4 Ablation Tests (E10)
echo ===================================

echo 1. Full model (with S_t v2 trend features, stochastic latent, multi-step loss)
python scripts/train.py --config configs/features_trend.yaml --run e10-ablation-full --epochs 20

echo 2. Ablation: NO trend features (using v1 levels-only)
python scripts/train.py --config configs/cicids2017.yaml --run e10-ablation-no-trend --epochs 20

echo 3. Ablation: NO stochastic latent (latent_dim = 0)
python scripts/train.py --config configs/features_trend.yaml --model-config configs/model_no_stochastic.yaml --run e10-ablation-no-stochastic --epochs 20

echo 4. Ablation: NO multi-step loss
python scripts/train.py --config configs/features_trend.yaml --model-config configs/model_no_multistep.yaml --run e10-ablation-no-multistep --epochs 20

echo ===================================
echo Done! Please review the results and update results.md with the table.
