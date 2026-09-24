# CIC-IDS2017 labels -> MITRE ATT&CK, and the ordered stage scale

## Stage scale used by the model

Ordinal progression (the "how far along is the attacker" axis):

| id | stage | ATT&CK tactic | meaning in our data |
|---|---|---|---|
| 0 | Benign | - | nothing of interest |
| 1 | Reconnaissance | TA0043 Reconnaissance / TA0007 Discovery | external or internal scanning, service enumeration |
| 2 | Initial Access | TA0001 Initial Access | credential brute force, web exploitation, vuln exploitation |
| 3 | Lateral Movement | TA0008 Lateral Movement (+ TA0002 Execution) | code running on a victim, movement/discovery from inside |
| 4 | Command & Control | TA0011 Command and Control | established C2 channel, beaconing |
| 5 | Exfiltration | TA0010 Exfiltration | sustained outbound data transfer from a compromised host |
| 6 | Impact (off-scale) | TA0040 Impact | DoS/DDoS - availability attack, not part of the infiltration chain |

`Impact` is deliberately **not** on the ordinal scale (see decisions.md D-003): DoS in CIC-IDS2017
is a standalone event, and forcing it onto the progression axis would make "more advanced than
Lateral Movement" meaningless.

## Label -> stage/technique mapping

| CIC-IDS2017 label | stage | ATT&CK technique |
|---|---|---|
| `BENIGN` | Benign | - |
| `PortScan` (external, Fri) | Reconnaissance | T1595.001/.002 Active Scanning; T1046 Network Service Discovery |
| `FTP-Patator` | Initial Access | T1110.001 Password Guessing (+ T1078 Valid Accounts) |
| `SSH-Patator` | Initial Access | T1110.001 Password Guessing |
| `Web Attack - Brute Force` | Initial Access | T1110 + T1190 Exploit Public-Facing Application |
| `Web Attack - XSS` | Initial Access | T1189 / T1190 web exploitation |
| `Web Attack - Sql Injection` | Initial Access | T1190 Exploit Public-Facing Application |
| `Heartbleed` | Initial Access (memory/credential disclosure) | T1190 |
| `Infiltration` (Dropbox -> Meterpreter) | Lateral Movement | T1204 User Execution; T1105 Ingress Tool Transfer |
| `Infiltration - Cool Disk - MAC` | Lateral Movement | T1204; T1059.006 Python |
| `Infiltration -> internal NMAP scan` | Lateral Movement (internal discovery) | T1046; T1018 Remote System Discovery |
| `Bot` (ARES) | Command & Control | T1071.001 Web Protocols; T1571 Non-Standard Port |
| `DoS Hulk` / `GoldenEye` / `slowloris` / `Slowhttptest` | Impact | T1499 Endpoint DoS |
| `DDoS` (LOIC) | Impact | T1498 Network DoS |
| `* - Attempted` (improved release) | same stage, flag `attempted=1` | attack traffic with no observed effect |

## Exfiltration in M1

CIC-IDS2017 contains no annotated exfiltration. We derive a **heuristic** exfil stage: a host already
at stage >= Lateral Movement showing sustained outbound/inbound byte asymmetry above a percentile
threshold across consecutive windows (T1041 Exfiltration Over C2 Channel). It is reported separately
in results and never counted as ground truth. CTU-13 (M2) supplies real C2 + data-theft scenarios
and replaces it.

## Why map to stages at all

The PS requires ATT&CK stage output, but there is a second reason: the stage scale is what makes the
forecast actionable. "P(compromise) = 0.7" tells a defender to worry; "moving from Reconnaissance to
Initial Access on 192.168.10.50:80, driven by SYN-without-ACK ratio and dst-port entropy" tells them
what to do.

## Reference

- MITRE ATT&CK Enterprise: https://attack.mitre.org/ (tactic IDs are v14+ enterprise tactics)
