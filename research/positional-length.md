# A window's score depends on the capture's length (E27 finding)

**What.** `CausalContext` (`src/netwm/models/world_model.py`) learns `context_len` positional vectors
(16 in every shipped config). When the input is longer than that, they are *linearly interpolated to
the input's length*:

```python
pos = self.pos[:, :t] if t <= self.cfg.context_len else F.interpolate(
    self.pos.transpose(1, 2), size=t, mode="linear", align_corners=False).transpose(1, 2)
```

The attention mask is causal and limited to the last `context_len` windows, so no future *content*
reaches window t. But the positional vector added at t is a function of the whole input length T, so
the score at t changes when windows are appended.

**Why it matters.**
- *Train/inference mismatch.* Training sequences are `seq_len` = 96 windows (a 6x stretch);
  evaluation and the dashboard pass a whole capture of about 970 windows (about 60x). Inference runs
  at positional encodings training never produced.
- *Offline ≠ live.* D-034's causal threshold was designed so "a sensor can run it on a live stream".
  The threshold is causal; the score it thresholds is not length-invariant. A streaming sensor (T grows
  window by window) would produce different scores from the offline analysis of the same capture.
- *Size of the effect* (E27, real E20r ensemble, first half of a day scored alone against the whole
  day):

  | | Thursday | Friday |
  |---|---:|---:|
  | score correlation | 0.995 | 0.948 |
  | largest score change | 0.139 | 0.199 |
  | alarm windows that change | 0 of 38 | 16 of 36 |

**What it does not invalidate.** Every stored score was computed on whole days, so the benchmark rows
are internally consistent with each other. Leave-one-day-out, the causal threshold and the nulls are
unaffected.

**Fix options** (each changes the model, so each needs retraining under its own pre-registration):
1. *Index positions within the attention window*, not over the sequence: the key at distance d from
   the query gets `pos[context_len - 1 - d]`. This is length-invariant by construction, and matches
   what the mask already assumes.
2. *Relative-position bias in the attention scores* instead of added absolute embeddings: ALiBi (Press
   et al., 2021, <https://arxiv.org/abs/2108.12409>) or learned relative biases (Shaw et al., 2018,
   <https://arxiv.org/abs/1803.02155>). Both are length-extrapolating by design.
3. *Drop positional embeddings.* The GRU already orders the sequence. Worth an ablation, not a default.

A strict-xfail test, `backend/tests/test_pcap_route.py::test_forecast_is_prefix_invariant`, turns
green when the model is fixed.

**On CTU-13 (results.md "N-8 x E25b").** Scoring each held-out capture as the start of a 96- or an
8,019-window recording moves E25b's ROC-AUC by at most 0.023 on captures of >= 208 windows, and by up
to 0.11 on the three captures of <= 61 windows. No scenario crosses 0.50 or 0.70, and the two short
inversions (Rbot s11, Sogou s07) stay below 0.05. Restarting the recurrent state in fixed-length
slices costs far more (up to 0.25 on Neris s01), so a streaming sensor must carry the state across the
feed whatever positional fix is chosen.
