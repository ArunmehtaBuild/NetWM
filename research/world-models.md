# World models — what they are, and what that means for network telemetry

## The idea

A **world model** learns an internal simulator of an environment: given the current state and
(optionally) an action, it predicts the distribution over the next state. Its defining capability is
**imagination** — rolling the model forward many steps *without* new observations.

Lineage relevant to us:

- **Ha & Schmidhuber (2018), "World Models"** — V (VAE encoder) + M (MDN-RNN predicting the next
  latent) + C (controller). Established the compress-then-predict-in-latent-space recipe.
- **PlaNet / RSSM (Hafner et al., 2018)** — *Recurrent State Space Model*: the state is split into a
  **deterministic** path `h_t` (a GRU carrying long-range context) and a **stochastic** path `z_t`
  (a Gaussian capturing what cannot be predicted). Trained as a sequential VAE: posterior
  `q(z_t | h_t, o_t)` sees the observation, prior `p(z_t | h_t)` does not, and the KL between them
  is what forces the prior to become a usable predictor. Planning happens entirely in latent space.
- **Dreamer (2019) and successors** — learn behaviours purely from imagined rollouts; also
  introduced the practical tricks we borrow: **KL free bits** (stop the KL from collapsing the
  stochastic path) and **multi-step open-loop training** (train the prior to survive being rolled
  forward, not just one step).

## Why this is not "just an LSTM classifier"

| | sequence classifier | world model |
|---|---|---|
| learns | `P(y_t | o_{≤t})` | `P(s_{t+1} | s_t)`, plus heads on top |
| horizon | now | K steps ahead, open-loop |
| output | a label | a distribution → uncertainty bands |
| novelty | out-of-distribution input → confident nonsense | prediction error ("surprise") is itself a signal |
| evaluation | accuracy/F1 at t | rollout fidelity at t+k, lead time |

The practical consequence for this project: **one-step accuracy is not evidence that we built a
world model.** The evidence is (a) open-loop K-step rollouts that stay close to the observed future
state, (b) forecasts that fire before onset (lead time > 0), (c) usable surprise on attack families
never seen in training.

## Mapping RSSM onto network traffic

| RSSM concept | Our instantiation |
|---|---|
| observation `o_t` | window feature vector `S_t` (~80 dims: flag ratios, port entropy, IAT stats, TTL variance, …) |
| encoder | temporal Transformer over the last `L` windows → `h_t` (attention weights reused for explanation) |
| deterministic state | GRU cell carrying `h_t` through imagined steps |
| stochastic state `z_t` | diagonal Gaussian; posterior sees `S_t`, prior does not |
| transition `p(z_{t+1}|z_t,h_t)` | the learned dynamics — **the deliverable** |
| decoder | reconstructs `Ŝ_{t+1}` (Gaussian NLL) → gives us the surprise score |
| reward head (Dreamer) | **hazard head**: `P(compromise at step k)` + stage logits |
| action | none — the network is an uncontrolled environment in M1. (Future: defender actions such as *block host* become the action input, turning the model into a what-if simulator.) |

**No actions in M1** is a deliberate simplification: we are forecasting an autonomous environment,
so the model is a pure dynamics model. The action slot is left in the interface so a later milestone
can ask "what happens if I isolate this host?" without an architecture change.

## Failure modes to watch for (and how we'll check)

1. **Posterior collapse** — KL → 0, the stochastic path is ignored, rollouts become deterministic.
   *Check:* log KL per epoch; use free bits; compare MC rollout variance against a deterministic
   ablation.
2. **Latent shortcut** — the model predicts the next state by copying the current one (traffic is
   autocorrelated, so this scores well). *Check:* benchmark against a **persistence baseline**
   (`Ŝ_{t+1} = S_t`); report the improvement over persistence, not the raw NLL.
3. **Onset leakage via overlapping windows** — 50 % stride means window *t* shares traffic with
   *t+1*; if labels are assigned sloppily, "prediction" is retrospective. *Check:* label a window
   only from traffic strictly inside it, and measure lead time against the ground-truth onset.
4. **Class imbalance** — attack windows are a small fraction of the week. *Check:* PR-AUC, not
   ROC-AUC; class-weighted losses; report FPR at the operating threshold.

## References

- Ha & Schmidhuber, *World Models*, arXiv:1803.10122
- Hafner et al., *Learning Latent Dynamics for Planning from Pixels* (PlaNet/RSSM), arXiv:1811.04551
- Hafner et al., *Dream to Control* (Dreamer), arXiv:1912.01603
- Hafner et al., *Mastering Diverse Domains through World Models* (DreamerV3), arXiv:2301.04104
