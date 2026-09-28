# CIC-IDS2018, corrected release: what the data holds (M3, D-044)

**Source.** The CSE-CIC-IDS2018 capture (Canadian Institute for Cybersecurity / CSE, AWS deployment),
fully re-extracted and relabelled by Liu, Engelen, Lynar, Essam and Joosen, *Error Prevalence in NIDS
datasets: A Case Study on CIC-IDS-2017 and CSE-CIC-IDS-2018*, IEEE CNS 2022 -
<https://intrusion-detection.distrinet-research.be/CNS2022/>. It is the same group and tool as the
corrected CIC-IDS2017 release this project already uses (D-001), and the CSVs have **exactly the same
91 columns**, including `Attempted Category`.

**Download (approved in chat, 2026-09-28).** `CSECICIDS2018_improved.zip`, 10,426,851,729 bytes,
sha256 `7f7b6f8065a88527bcb6e1579f088e1d0480a49903c5fd7e4e907ab238344f6e`, every member's CRC checked.
Extracted to `D:/CIC-IDS2018-improved/csv/` (36.0 GB, 10 files); log in
`D:/CIC-IDS2018-improved/fetch.log`. Nothing else was downloaded (no PCAPs).

**Inspection** (`python scripts/inspect_cicids2018.py --csv-dir D:/CIC-IDS2018-improved/csv`, one
chunked pass; `results/runs/m3-inspect/inspect.json`): **63,195,145 flows** over ten capture days.

| split | file | flows | first timestamp | last timestamp | benign | attack labels (flows) |
|---|---|---:|---|---|---:|---|
| feb14 | Wednesday-14-02-2018.csv | 5,898,350 | 2018-02-14 12:28 | 2018-02-15 00:47 | 5,610,799 | FTP-BruteForce - Attempted 193,354, SSH-BruteForce 94,197 |
| feb15 | Thursday-15-02-2018.csv | 5,410,102 | 2018-02-15 12:23 | 2018-02-16 01:14 | 5,372,471 | DoS GoldenEye 22,560, DoS Slowloris 8,490, DoS GoldenEye - Attempted 4,301, DoS Slowloris - Attempted 2,280 |
| feb16 | Friday-16-02-2018.csv | 7,390,266 | 2018-02-16 12:26 | 2018-02-16 22:15 | 5,481,500 | DoS Hulk 1,803,160, FTP-BruteForce - Attempted 105,520, DoS Hulk - Attempted 86 |
| feb20 | Tuesday-20-02-2018.csv | 6,054,702 | 2018-02-20 12:28 | 2018-02-21 00:37 | 5,764,497 | DDoS-LOIC-HTTP 289,328, DDoS-LOIC-UDP 797, DDoS-LOIC-UDP - Attempted 80 |
| feb21 | Wednesday-21-02-2018.csv | 6,962,593 | 2018-02-21 12:28 | 2018-02-22 00:36 | 5,878,399 | DDoS-HOIC 1,082,293, DDoS-LOIC-UDP 1,730, DDoS-LOIC-UDP - Attempted 171 |
| feb22 | Thursday-22-02-2018.csv | 6,071,153 | 2018-02-22 12:22 | 2018-02-23 00:36 | 6,070,945 | Web Attack - Brute Force - Attempted 76, Web Attack - Brute Force 69, Web Attack - XSS 40, Web Attack - SQL 16, Web Attack - SQL - Attempted 4, Web Attack - XSS - Attempted 3 |
| feb23 | Friday-23-02-2018.csv | 5,976,481 | 2018-02-21 12:33 | 2018-02-23 23:46 | 5,976,251 | Web Attack - XSS 73, Web Attack - Brute Force 62, Web Attack - Brute Force - Attempted 61, Web Attack - SQL 23, Web Attack - SQL - Attempted 10, Web Attack - XSS - Attempted 1 |
| feb28 | Wednesday-28-02-2018.csv | 6,568,726 | 2018-02-28 12:20 | 2018-03-01 01:05 | 6,518,882 | Infiltration - NMAP Portscan 49,740, Infiltration - Dropbox Download 46, Infiltration - Communication Victim Attacker 43, Infiltration - Dropbox Download - Attempted 15 |
| mar01 | Thursday-01-03-2018.csv | 6,551,401 | 2018-03-01 12:15 | 2018-03-01 23:40 | 6,511,554 | Infiltration - NMAP Portscan 39,634, Infiltration - Communication Victim Attacker 161, Infiltration - Dropbox Download 39, Infiltration - Dropbox Download - Attempted 13 |
| mar02 | Friday-02-03-2018.csv | 6,311,371 | 2018-03-02 12:46 | 2018-03-03 00:39 | 6,168,188 | Botnet Ares 142,921, Botnet Ares - Attempted 262 |

**Attack labels: time span (UTC), most frequent sources, destinations and destination ports.**

| split | label | span | sources | destinations | ports |
|---|---|---|---|---|---|
| feb14 | FTP-BruteForce - Attempted | 14:33-18:01 | 18.221.219.4, 13.58.98.64 | 172.31.69.25 | 21 |
| feb14 | SSH-BruteForce | 18:01-19:32 | 13.58.98.64 | 172.31.69.25 | 22 |
| feb15 | DoS GoldenEye | 13:27-14:02 | 18.219.211.138 | 172.31.69.25 | 80 |
| feb15 | DoS GoldenEye - Attempted | 13:27-13:57 | 18.219.211.138 | 172.31.69.25 | 80 |
| feb15 | DoS Slowloris | 15:00-15:41 | 18.217.165.70 | 172.31.69.25 | 80 |
| feb15 | DoS Slowloris - Attempted | 15:00-15:41 | 18.217.165.70 | 172.31.69.25 | 80 |
| feb16 | DoS Hulk | 17:45-17:58 | 18.219.193.20 | 172.31.69.25 | 80 |
| feb16 | FTP-BruteForce - Attempted | 14:12-15:05 | 13.59.126.31 | 172.31.69.25 | 21 |
| feb16 | DoS Hulk - Attempted | 17:58-17:58 | 18.219.193.20 | 172.31.69.25 | 80 |
| feb20 | DDoS-LOIC-HTTP | 14:13-15:16 | 18.219.9.1, 18.218.229.235, 18.216.200.189 | 172.31.69.25 | 80 |
| feb20 | DDoS-LOIC-UDP | 17:14-17:29 | 18.219.32.43, 18.218.55.126, 18.218.229.235 | 172.31.69.25 | 80 |
| feb20 | DDoS-LOIC-UDP - Attempted | 17:14-17:29 | 172.31.69.25 | 18.218.55.126, 18.219.32.43, 52.14.136.135 | 0 |
| feb21 | DDoS-HOIC | 18:11-19:05 | 18.216.200.189, 18.218.229.235, 18.218.115.60 | 172.31.69.28 | 80 |
| feb21 | DDoS-LOIC-UDP | 14:08-14:43 | 18.218.55.126, 52.14.136.135, 18.219.5.43 | 172.31.69.28 | 80 |
| feb21 | DDoS-LOIC-UDP - Attempted | 14:08-14:43 | 172.31.69.28 | 18.218.55.126, 18.219.5.43, 18.216.200.189 | 0 |
| feb22 | Web Attack - Brute Force | 14:17-15:23 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb22 | Web Attack - Brute Force - Attempted | 14:13-15:23 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb22 | Web Attack - SQL | 20:16-20:27 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb22 | Web Attack - SQL - Attempted | 20:14-20:18 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb22 | Web Attack - XSS | 17:51-18:28 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb22 | Web Attack - XSS - Attempted | 17:51-17:54 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb23 | Web Attack - Brute Force | 14:04-15:02 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb23 | Web Attack - Brute Force - Attempted | 14:04-15:02 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb23 | Web Attack - SQL | 19:06-19:17 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb23 | Web Attack - SQL - Attempted | 19:05-19:17 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb23 | Web Attack - XSS | 17:01-18:10 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb23 | Web Attack - XSS - Attempted | 17:01-17:01 | 18.218.115.60 | 172.31.69.28 | 80 |
| feb28 | -1 | 16:46-16:46 | 172.31.65.67 | 104.16.147.229 | 80 |
| feb28 | Infiltration - NMAP Portscan | 14:46-18:38 | 172.31.69.24 | 172.31.69.7, 172.31.69.22, 172.31.69.15 | 135, 3389, 445 |
| feb28 | Infiltration - Communication Victim Attacker | 14:45-18:39 | 172.31.69.24 | 13.58.225.34 | 31337 |
| feb28 | Infiltration - Dropbox Download | 14:33-17:43 | 172.31.69.24 | 162.125.3.1, 162.125.3.5, 162.125.18.133 | 443 |
| feb28 | Infiltration - Dropbox Download - Attempted | 14:33-17:42 | 172.31.69.24 | 104.16.100.29, 104.16.99.29, 52.85.131.81 | 443 |
| mar01 | Infiltration - NMAP Portscan | 14:10-19:37 | 172.31.69.13 | 172.31.69.7, 172.31.69.15, 172.31.69.18 | 135, 445, 3389 |
| mar01 | Infiltration - Communication Victim Attacker | 13:57-19:36 | 172.31.69.13 | 13.58.225.34 | 31337 |
| mar01 | Infiltration - Dropbox Download | 13:53-14:32 | 172.31.69.13 | 162.125.18.133, 162.125.3.1, 162.125.248.1 | 443 |
| mar01 | Infiltration - Dropbox Download - Attempted | 13:53-13:58 | 172.31.69.13 | 104.16.100.29, 13.32.168.125, 52.85.112.72 | 443 |
| mar02 | Botnet Ares | 14:13-19:53 | 172.31.69.30, 172.31.69.10, 172.31.69.6 | 18.219.211.138 | 8080 |
| mar02 | Botnet Ares - Attempted | 19:53-19:54 | 172.31.69.14, 172.31.69.6, 172.31.69.17 | 18.219.211.138 | 8080 |

**What the design takes from this.**
- **Timestamps are UTC.** Each capture runs from about 12:15 to about 01:15 UTC the next night, and
  the attacks start between 13:27 and 18:11 UTC (office hours in Canada), as in the corrected
  CIC-IDS2017 release.
- **The monitored (victim) network is 172.31.0.0/16** (the AWS VPC). The web servers under attack are
  172.31.69.25 and .28. The attackers are public AWS addresses (18.x, 13.x, 52.x).
- **The infiltration days have compromise stages; so does the botnet day.**
  - Infiltration: 172.31.69.24 (28-02) and .13 (01-03) download from Dropbox, call back to
    13.58.225.34:31337, then NMAP-scan the internal network (ports 135, 445, 3389).
  - Botnet: several internal hosts beacon to 18.219.211.138:8080 (Ares).
  - These three days are the only ones with compromise onsets. The other seven hold attacks only
    (brute force, DoS, DDoS, web).
- **"- Attempted" labels** mark attack traffic that had no effect (D-009 demotes it to benign for the
  stage). All FTP brute force (14-02 and 16-02) is attempted, so 14-02's only counted attack is SSH
  brute force. The "DDoS-LOIC-UDP - Attempted" flows are the victim's replies.
- **The web-attack days are tiny.** 22-02 and 23-02 hold only 208 and 230 attack flows (with the
  attempted ones).
- **Two data questions (D-044):** one real, handled by dropping and counting, and one that was not real.
  - 23-02's file holds 2,609 flows stamped 21-22 February (1,216 and 1,393), none of them attack
    traffic. Left in, they would stretch that day's window grid over three days.
  - **No `-1` flow exists (D-044 amendment).** The first inspection pass read 28-02 with 143 rows missing and one garbled row labelled `-1`: a transient read error on the external D: drive. A second pass with the same settings reads every line (6,568,726), the file matches the zip's CRC32, and no line carries a `-1` label. The first read is kept in `inspect.json` under `corrected`.
