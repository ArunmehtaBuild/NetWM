# Technical Presentation - NetWM (SIH PS 26153)

## Slide 1: AI based Network Attack Forecasting
- **Problem:** Traditional classifiers map single flows in isolation, discarding temporal and causal structure.
- **Solution (NetWM):** A world-model-based AI system that learns network state transition dynamics, anticipating attacker progression and supporting proactive cyber defence.

## Slide 2: Input Data & World Model Architecture
- **Input Data:** Ingests both flow-level (NetFlow) and packet-level (PCAP) features to capture aggregate behaviour and sequence patterns.
- **Architecture:** Sequence model learning the transition dynamics P(S_t+1 | S_t).
- **Forward Simulation:** Rolls out K steps ahead in latent space to output an **infiltration probability score** before compromise completes.

## Slide 3: Infiltration Prediction & Explainability
- **Attack Stage Mapping:** Maps predicted behavior to MITRE ATT&CK phases (Reconnaissance, Lateral Movement, etc.) based on predicted future state.
- **Explainability:** Uses **attention weights** and the "why panel" to highlight the driving traffic features (e.g. destination-port spread) contributing to predictions.
- **Offline Interface:** The prediction engine and interactive dashboard run fully offline without cloud API dependencies.

## Slide 4: Real-World Performance vs Baseline
- **Evaluation:** Tested on held-out days the model never saw during training.
- **Results:** F1 0.576 at a 2.7% false-positive rate, precision 0.78 at a 10% alert budget.
- **Benchmark:** Demonstrates measurable improvement; the PS's logistic regression baseline scores 0.011 on the same features.

## Slide 5: What we measured that did not work
What it does not do yet is warn *before* the attacker gets in. We tested that properly: against a
shuffled-time baseline, across four attack days, three seeds. Our early alarms didn't beat chance.
We withdrew our own number when it failed. Then we ruled out five causes, one experiment each - the
scoring statistic, the threshold, the data, the training target, and how each capture is
normalised. What's left is this: trained on one set of attack families, the model's weighting
doesn't carry over to another. A seventy-feature model does no better than one feature. That's
the next experiment.
- **Note:** Onset 602 had a long quiet run-up and a real rise (a precursor's shape), but none of it came from the attack itself (bystander hosts).
