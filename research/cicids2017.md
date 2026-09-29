# CIC-IDS2017 — capture, schedule, flaws, corrected release

## Capture setup

- Canadian Institute for Cybersecurity (UNB), 5 days: **Mon 3 July – Fri 7 July 2017, 09:00–17:00**
  local time (Atlantic, UTC−3).
- Victim network `192.168.10.0/24` (Windows 7/8.1/10, Ubuntu 12/16, Mac), firewall `205.174.165.80`
  / `172.16.0.1`; attacker Kali box **205.174.165.73** (plus `205.174.165.74` for botnet/infiltration
  stages).
- Benign traffic is *generated* by a B-Profile agent (HTTP/HTTPS/FTP/SSH/email) — it is synthetic,
  not real user traffic. Relevant caveat: benign inter-arrival patterns are more regular than in a
  real enterprise, so anomaly-style scores can look better here than they would in production.
- Releases: raw **PCAPs** (~50 GB total), **GeneratedLabelledFlows** (CSV *with* timestamps + IPs),
  **MachineLearningCSV** (CSV *without* IP/timestamp columns — unusable for our windowing).

## Attack schedule (official, local time UTC−3)

| Day | Attack | Time |
|---|---|---|
| Mon 3 Jul | benign only | all day |
| Tue 4 Jul | FTP-Patator | 09:20–10:20 |
| Tue 4 Jul | SSH-Patator | 14:00–15:00 |
| Wed 5 Jul | DoS slowloris | 09:47–10:10 |
| Wed 5 Jul | DoS Slowhttptest | 10:14–10:35 |
| Wed 5 Jul | DoS Hulk | 10:43–11:00 |
| Wed 5 Jul | DoS GoldenEye | 11:10–11:23 |
| Wed 5 Jul | Heartbleed (port 444) | 15:12–15:32 |
| Thu 6 Jul | Web: Brute Force | 09:20–10:00 |
| Thu 6 Jul | Web: XSS | 10:15–10:35 |
| Thu 6 Jul | Web: SQL Injection | 10:40–10:42 |
| Thu 6 Jul | **Infiltration** (Dropbox → Meterpreter, Win Vista) | 14:19–14:21, 14:33–14:35 |
| Thu 6 Jul | Infiltration → Cool Disk (MAC) | 14:53–15:00 |
| Thu 6 Jul | Infiltration → internal NMAP portscan from victim | 15:04–15:45 |
| Fri 7 Jul | Botnet ARES | 10:02–11:02 |
| Fri 7 Jul | Port Scan (all variants) | 13:55–15:27 |
| Fri 7 Jul | DDoS LOIC | 15:56–16:16 |

> **Timezone trap.** CSV `Timestamp` values are local (UTC−3) while PCAP packet times are UTC, and
> the CSVs use 12-hour times without AM/PM in some day files — e.g. a flow at "3:15" may be 15:15.
> Any pipeline that joins CSV and PCAP must normalise both to UTC first. This is a known source of
> silently-shifted labels in published work.

## The infiltration day, in detail (this is our headline scenario)

1. Victim `192.168.10.8` (Win Vista) downloads a malicious file from **Dropbox** — traffic is TLS to
   Dropbox CDN, so the payload itself is *not* visible, and the dataset authors left those flows
   labelled Benign.
2. A Meterpreter/Metasploit backdoor is executed; **the victim initiates the connection outward** to
   the attacker `205.174.165.73` — a single long-lived TCP connection over which the attacker types
   commands and receives output (first packet 2017-07-06 17:19:02 UTC, last 18:46:09 UTC).
3. From the compromised host the attacker runs an **internal NMAP portscan** across
   `192.168.10.0/24` — the lateral-movement / discovery phase.

Why this matters for a forecaster: the observable signal *before* compromise is weak (an outbound
TLS download), while the signal *after* is loud (reverse shell + internal scan). A model that only
sees the loud part is a detector. The forecasting question is whether the pre-compromise window
(long outbound session, unusual destination, reverse-direction initiation) shifts the predicted
state distribution toward Lateral Movement before the scan starts.

## Documented flaws in the original release

Catalogued by Engelen et al. (WTMC'21) and the CNS'22 follow-up:

**Flow construction / features (CICFlowMeter bugs)**
- TCP sessions terminated incorrectly because of a timing flaw → flows split or merged wrongly;
  flows exceeding a 120 s threshold split mid-session.
- Duplicated features, miscalculated features, wrong protocol detection.

**Labelling (time-window based, no payload validation)**
- *FTP-Patator*: a successful login (port 52108) labelled as brute force.
- *SSH-Patator*: flows containing only a TLS handshake (no credential attempt) labelled attack.
- *DoS Hulk*: 8 of 545 438 "attack" flows are ordinary web browsing; the tool's `Connection: close`
  header means many flows are not the intended attack at all.
- *DoS Slowloris / Slowhttptest*: accidental early tool launch, plus the authors' own manual
  browsing (source ports 33372, 37670) labelled as attack.
- *Web SQL Injection*: first malicious packet occurs ~5 min earlier than documented; ~1 s overlap
  with XSS traffic makes labels ambiguous.
- *Web XSS / Brute Force*: setup and teardown flows included; benign GETs interleaved with attack.
- *Infiltration*: the Dropbox payload flows cannot be identified with certainty and stay Benign;
  the **Cool Disk – MAC** Python-Meterpreter step was missed entirely.
- *NMAP portscan*: official window 18:04–18:45 UTC misses an earlier scan at **17:33 UTC**;
  benign background traffic between `192.168.10.8` and `192.168.10.50` labelled as scan.
- *Botnet ARES*: C2 attempts continuing after the botnet was shut down labelled identically.
- *DDoS LOIC*: byte-identical packets occur outside the attack window (generated background
  traffic) — genuinely ambiguous.

**Consequence for us.** Both the features and the attack *onset times* are unreliable in the
original CSVs. Since our target is "how many windows before onset did we fire", a shifted onset
directly corrupts the headline metric → **D-001**.

## Corrected release we use

- `CICIDS2017_improved.zip` — **327.6 MB**, from
  <https://intrusion-detection.distrinet-research.be/CNS2022/Datasets/>
  (code: <https://github.com/GintsEngelen/CNS2022_Code>).
- Re-extracted with the fixed flow meter, per-flow `Timestamp`, `Src IP/Port`, `Dst IP/Port`
  retained, and labels validated against payloads, including `... - Attempted` variants for attack
  traffic that produced no effect.
- LYCOS-IDS2017 (Rocher et al.) is an independent corrected re-extraction using LycoSTand — a useful
  cross-check if we want a second opinion on labels.

## Open questions / to verify during implementation

- Exact column set and dtypes of the improved CSVs (verify against `GintsEngelen/CNS2022_Code`).
- Whether the improved release ships per-day files (needed for leave-one-day-out) — expected yes.
- PCAP access: `cicresearch.ca` direct links now redirect to the UNB dataset index; need a working
  mirror or the UNB download form for packet-level features. Fallback: derive packet-level-style
  features from our own flow aggregator over any PCAP the user supplies, and synthesise demo PCAPs.

---

## Audit findings from our own copy (E1, 2026-09-24)

The corrected release ships **5 per-day CSVs** (`monday.csv` ... `friday.csv`, 1.1 GB extracted,
2.10 M flows) with 90 columns: `Flow ID`, `Src/Dst IP`, `Src/Dst Port`, `Protocol`, `Timestamp`,
the CICFlowMeter feature set, plus `FWD/Bwd Init Win Bytes`, `Fwd Seg Size Min`, `ICMP Code/Type`,
`Total TCP Flow Time`, `Label` and `Attempted Category`.

**Timestamps are UTC** in this release: each day runs 11:5x - 20:0x UTC, i.e. the documented
09:00-17:00 local (UTC-3). The original CIC CSVs are local time - do not mix them.

**Labels present** (after the corrected relabelling):

- Tuesday: `FTP-Patator` (3 972), `SSH-Patator` (2 961) + 39 attempted
- Wednesday: `DoS Hulk` (158 468), `DoS GoldenEye` (7 567), `DoS Slowloris` (3 859),
  `DoS Slowhttptest` (1 740), `Heartbleed` (11) + 5 876 attempted
- Thursday: `Infiltration - Portscan` (71 767), `Web Attack - Brute Force` (73), `Web Attack - XSS`
  (18), `Web Attack - SQL Injection` (13), **`Infiltration` (36)** + 1 997 attempted
- Friday: `Portscan` (159 066), `DDoS` (95 144), `Botnet` (736) + 4 067 `Botnet - Attempted`

**Three things that changed the design:**

1. `Botnet - Attempted` runs 14:03 - 20:01 UTC - six hours of post-shutdown C2 retries, 5.5x more
   flows than the real botnet window. Treating attempted traffic as a real stage swamped Friday
   (727/968 windows labelled C2) and hid the port scan and the DDoS. -> decisions.md **D-009**
2. `Infiltration - Portscan` begins **17:00:31 UTC**, ~19 min before the officially documented
   infiltration start (17:19). Our onsets come from the labels, with the schedule used only as a
   visual overlay. -> **D-011**
3. The compromise itself is **36 flows**; everything else on Thursday is aftermath. Flow-level
   averages are therefore a bad headline metric for this problem.

### Open question

Is the 17:00 portscan the *unscripted* scan Engelen et al. mention (in which case episode 1 is not a
post-compromise event and its lead time is meaningless), or genuine post-compromise discovery? To
resolve: check whether those flows originate from the victim `192.168.10.8` (post-compromise) or
from the attacker `205.174.165.73` (external, unscripted).

---

## The day captures against the corrected CSVs (E27 check 4, D-040, 2026-09-28)

Measured by running our own `pcap_to_flows` over the UNB day captures and comparing the window state
with the matrix built from the corrected CSVs
([CNS2022 release](https://intrusion-detection.distrinet-research.be/CNS2022/CICIDS2017.html)).

- **Format.** The five `*-WorkingHours.pcap` files are pcapng, written by `mergecap`, despite the
  name. Tuesday (11.0 GB) and Thursday (8.3 GB) match the md5s shipped beside them.
- **Mirrored duplicates, and the CSVs count them.** Many frames appear twice, about 2 us apart, byte
  identical from the IP header on. On Tuesday 13:00-14:00, 54,158 of 916,574 frames are copies by
  `read_packets`' rule. The corrected CSVs' per-flow packet and flag counts *include* the copies. Our
  flow counts match them only with the copies kept (`pkts_total` median ratio 0.999 kept, 0.939
  removed). So a converter meant to reproduce the corrected flows must not deduplicate. Our packet-level
  `pcap_` features were built deduplicated, and stay that way.
- **A day has more quiet flows than a converter can keep open.** UDP and unclosed TCP flows never see
  the packet that would end them under a "timeout on the next packet" rule. On a full day they passed
  a 100,000-session cap, and 2.87 M packets were dropped silently. Timed-out flows have to be swept out
  by capture time (D-040). A slice below the cap does not show the problem: always compare a full day.
- **What the corrected extraction does, read flow by flow (D-043, 2026-09-29).** These were traced by
  pairing our flows with the CSV rows on one hour of Tuesday (`scripts/check4_flow_match.py`), not by
  reading the CNS2022 code. Each is consistent with CICFlowMeter's own behaviour:
  - an RST does not end a flow, though a following SYN starts a new one;
  - no flow of a single packet is ever written (none on Tuesday or Thursday);
  - `Active Mean` leaves out the final active period, so a flow with no 5 s idle gap reads 0;
  - `Fwd Act Data Pkts` does not count the flow's first packet;
  - `Bwd Init Win Bytes` is the *last* backward packet's window, overwritten on each one (0 after an RST);
  - a flow continuing a timed-out one keeps that flow's direction;
  - a later IP fragment is not read as a transport packet, and IATs are never negative.
- **What still differs after that** (full Tuesday): `active_mean` (9 %), the host fan-out and the
  distinct-source count (5 %); everything else is within 5 % and 56 of 67 flow features within 1 %. At
  the model, the difference is small: the served PCAP ensemble's live scores follow its training-state
  scores at 0.991 on the Thursday 16:40 slice. The CNS2022 code
  ([GintsEngelen/CNS2022_Code](https://github.com/GintsEngelen/CNS2022_Code)) is where to look next.
