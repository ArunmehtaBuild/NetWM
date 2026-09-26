# M2: CTU-13 Dataset Transfer Evaluation

## Overview
The CTU-13 dataset is a dataset of botnet traffic captured at CTU University, Czech Republic, in 2011. It provides a robust, multi-family environment to test the model's ability to generalize to unseen attack patterns—a critical gap identified in CIC-IDS2017 where leave-one-day-out is functionally leave-one-family-out (D-006).

## The 13 Scenarios and Botnet Families
The dataset contains 13 distinct capture scenarios, spanning different botnet families with varying attack behaviors (e.g., C2 beaconing, port scanning, spam, DDoS).

| Scenario | Botnet Family | Primary Behavior |
|---|---|---|
| 1 | Neris | IRC, SPAM, ClickFraud |
| 2 | Neris | IRC, SPAM, ClickFraud |
| 3 | Rbot | IRC, PortScan |
| 4 | Rbot | IRC, PortScan |
| 5 | Virut | SPAM, PortScan |
| 6 | Menti | PortScan |
| 7 | Sogou | HTTP, SPAM |
| 8 | Murlo | IRC, PortScan |
| 9 | Neris | IRC, SPAM, ClickFraud |
| 10 | Rbot | IRC, PortScan |
| 11 | Rbot | IRC, PortScan |
| 12 | NSIS.ay | P2P |
| 13 | Virut | SPAM, PortScan |

## Label Scheme
The original label scheme assigns one of three labels per flow:
1. `Background`: Normal, unmonitored traffic.
2. `Normal`: Known benign traffic from monitored victim hosts.
3. `Botnet`: Traffic produced by the infected machines.

For our MITRE ATT&CK progression (D-003):
- Background/Normal mapping to `Benign`.
- `Botnet` flows will be decomposed contextually into `Command & Control` (e.g., IRC, HTTP beaconing), `Reconnaissance` (PortScans), and `Impact` (DDoS/Spam). Since CTU-13 features concurrent attacks (C2 + scanning), the multi-label stage vector (D-010) is fully exercised here.

## Flow Format and Schema Mapping
The dataset is distributed in Argus `binetflow` format, not CICFlowMeter.
We must map `binetflow` columns to our canonical `src/netwm/data/base.py` schema:
- `StartTime` -> `timestamp`
- `SrcAddr`, `Sport`, `DstAddr`, `Dport`, `Proto` -> canonical 5-tuple
- `TotPkts`, `TotBytes`, `SrcBytes` -> basic sizing
- `State`, `Dir` -> flow flags

Features relying strictly on CICFlowMeter internals (like specific standard deviations or packet length histograms not present in `binetflow`) will require a subset/intersection feature space or re-extraction from the original CTU PCAPs (if available) via `pcap_features.py`.

## Sizes
- ~20 million flows total across the 13 scenarios.
- The largest scenario (Scenario 10) is ~5.1M flows, while the smallest (Scenario 6) is ~550K flows.

## Scenario-Held-Out Design (Pre-registered)
To evaluate transferability, we adopt a **leave-one-family-out** cross-validation design:
1. **Train** on a subset of scenarios representing N-1 botnet families.
2. **Test** on a scenario from the held-out Nth botnet family.
3. **Evaluation Bar (D-023)**: Any early-warning or lead-time claim must exceed the 95th percentile of the 2,000-shift circular null at a deployable alert budget on >= 2 of the held-out scenarios (Fisher-combined p < 0.05). Lead times are measured per episode (D-019), and metrics must be reported for each held-out family.

## Adapter Plan for `src/netwm/data/ctu13.py`
1. **Loader**: Implement a `DatasetAdapter` for reading `binetflow` files. 
2. **Harmonization**: Map `binetflow` columns to the canonical schema. We must declare monitored internal prefixes explicitly to satisfy D-012 (refine scan direction), since CTU-13 mixes subnets differently.
3. **Labeling**: Apply a heuristic or signature-based mapper to subdivide the `Botnet` label into specific MITRE stages, leveraging D-010.
4. **Validation**: Test the adapter in `tests/test_flow_features.py` to guarantee windowing correctly handles the mapped schema.
