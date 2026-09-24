# Related work - attack forecasting / prediction (and how NetWM differs)

> Status: first pass. Entries marked *(abstract only)* have not been read in full yet; verify before
> citing them in the architecture document or the slides.

## 1. Static flow classification (the thing we are *not* doing)

The dominant CIC-IDS2017 literature: per-flow features -> RF / XGBoost / MLP -> benign vs malicious,
usually with random splits and ~0.99 F1. Two independently documented problems: dataset errors
(Engelen et al.) and split leakage (near-duplicate flows from a single attack burst landing in both
train and test). Neither approach produces lead time, and neither models temporal structure.

## 2. Alert / log-level sequence forecasting

- *Forecasting Network Intrusions from Security Logs Using LSTMs* (Springer, 2020) *(abstract only)* -
  LSTM over security-log event sequences predicting the next event. Closest in spirit to us, but it
  operates on already-detected alerts rather than raw telemetry, so it inherits the detector blind
  spots.
- *Cyber Attacks Against Enterprise Networks: Characterization, Modeling and Forecasting*
  (SciSec 2023) *(abstract only)* - time-series forecasting of aggregate attack *rates*. Forecasts
  volume, not a specific attacker progression.
- DDoS volume forecasting with LSTMs (arXiv:2509.02076) *(abstract only)* - univariate/multivariate
  volume prediction; useful as a sanity reference for sequence-model hyperparameters.

## 3. Attack-stage / kill-chain state modelling

- *Multi-Stage Attack Detection via Kill Chain State Machines* (arXiv:2103.14628) - aggregates IDS
  alerts into per-host kill-chain state machines on CIC-IDS2017-like data. Shares our stage framing,
  but the state machine is hand-built and reactive; ours is learned and predictive.
- *ProAPT: Projection of APT Threats with Deep RL* (arXiv:2209.07215) *(abstract only)* - predicts the
  next APT step in a POMDP via RL over alert states. Conceptually adjacent, but assumes an alert
  pipeline and an action-conditioned MDP.
- Attack graphs / Bayesian attack graphs (classical) - require a hand-built topology and
  vulnerability model; strong interpretability, no learning from telemetry.

## 4. World models outside security

The PlaNet / Dreamer line, see [world-models.md](world-models.md). Applications to security are, as
of now, mostly position papers rather than implemented systems - which is exactly the gap PS-153
points at.

## Where NetWM sits

| | alert-sequence LSTMs | kill-chain state machines | attack graphs | **NetWM** |
|---|---|---|---|---|
| input | detector alerts | detector alerts | topology + CVEs | raw flows / packets |
| dynamics | next event | hand-built transitions | expert-specified | **learned P(S_t+1 given S_t)** |
| horizon | next event | current state | hypothetical paths | **K-step MC rollout with bands** |
| uncertainty | - | - | probabilistic (static) | **stochastic latent, sampled** |
| unseen attacks | no | no | partially | **surprise score + family holdout** |
| explanation | limited | structural | structural | **attention + IG over traffic features** |

## Honest limitations to state up front

- Benign traffic in CIC-IDS2017 is synthetically generated, so dynamics are smoother than in a real
  enterprise; cross-dataset evaluation (M3 / M4) is the mitigation.
- The state is network-global in M1. Per-host attribution comes from the flow table and host
  aggregate features, not yet from a graph; a GNN over the host graph is the natural next step for
  lateral movement.
- The forecast horizon is bounded by how long a pre-compromise signal exists. For the Dropbox
  infiltration that is minutes, not hours, so we report lead-time distributions, not a single number.
