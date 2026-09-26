# Technical Presentation - NetWM

## Slide 1: NetWM - Intrusion Detection via World Models
- **Project:** NetWM (SIH 2026, PS 26153)
- **Goal:** Real-time network intrusion detection using world models.
- **Approach:** Modeling network state transitions rather than classifying individual flows.

## Slide 2: The World Model Architecture
- **Concept:** Predicts how the network's state moves from one 30-second window to the next.
- **Rollout:** Rolls forward 10 steps in latent space without seeing more traffic.
- **Advantage:** From step 2 onwards, it predicts the next state better than simply repeating the current one. 

## Slide 3: Live Detection and Features
- **Features:** 70+ features including volume, spread (fanout, unique ports/IPs), flags, and per-host channels.
- **Surprise Score:** The model's negative log-likelihood of the next window. High surprise indicates abnormal network movement.
- **Alert Budget:** 10% budget used to avoid false positives and focus alarms on the loudest phase (e.g., lateral movement sweep).

## Slide 4: Real-World Performance
- **Evaluation:** Tested on held-out days the model never saw during training.
- **Results:** F1 0.576 at a 2.7% false-positive rate, precision 0.78.
- **Baseline Comparison:** The problem statement's logistic regression baseline scores 0.011 on the same features.

## Slide 5: What we measured that did not work
What it does not do yet is warn *before* the attacker gets in. We tested that properly: against a
shuffled-time baseline, across four attack days, three seeds. Our early alarms didn't beat chance.
We withdrew our own number when it failed. Then we ruled out five causes, one experiment each - the
scoring statistic, the threshold, the data, the training target, and how each capture is
normalised. What's left is this: trained on one set of attack families, the model's weighting
doesn't carry over to another. A seventy-feature model does no better than one feature. That's
the next experiment.
- **Note:** Onset 602 had a long quiet run-up and a real rise (a precursor's shape), but none of it came from the attack itself (bystander hosts).
