# Feature Dictionary

This document outlines the metrics (features) our World Model uses to observe the state of the network. It is written in plain English to bridge the gap between network defenders, developers, and the AI model. 

Every minute, the model calculates these numbers to take a "snapshot" of the network.

## 1. Volume & Rate Metrics
*Capturing brute-force and denial-of-service (DoS) attacks.*
- **`n_flows`, `flows_per_s`**: The total number of unique connections per minute. Huge, sudden spikes often indicate a DoS attack or a rapid password-guessing bot.
- **`bytes_total`, `pkts_total`**: The raw amount of data and packets flowing across the network. 

## 2. Spread & Reconnaissance
*Capturing network mapping and lateral movement.*
- **`uniq_dst_port`**: How many different "doors" (ports) were touched. Hackers doing reconnaissance scan thousands of ports looking for an open one.
- **`uniq_dst_ip`**: How many different destination computers were talked to. Spikes here expose lateral movement (a hacker spreading inside the building) or ping sweeps.
- **`fanout_mean`, `fanout_max`**: On average, how many different computers does a single internal host talk to? High fanout is the signature of a worm or a network scanner.

## 3. Flag Behavior
*Capturing silent scans and connection failures.*
- **`syn_no_ack_rate`**: The percentage of connections where someone said "Hello" (SYN) but the other computer never replied (ACK). This is the classic signature of a SYN-flood attack or a hacker scanning a closed, heavily defended port.
- **`has_rst_rate`**: How often connections are aggressively hung up (RST flag). Often caused by failed brute-force login attempts or servers actively rejecting traffic.

## 4. Direction & Shape
*Capturing data theft and command channels.*
- **`byte_asymmetry`**: The ratio of data leaving the network vs entering it. A sudden shift towards "leaving" heavily strongly signals data exfiltration (stealing files).
- **`is_outbound_rate`**: The percentage of traffic crossing from inside the network to the internet, rather than just internal chatter.

## 5. Timing & Beaconing
*Capturing malware phoning home.*
- **`beacon_score`**: Measures how "robotic" and perfectly regular the time gap is between connections. Malware Command & Control (C2) servers "phone home" exactly every X seconds (e.g., exactly every 60 seconds). Normal humans browse the web irregularly.

## 6. Trend (Velocity) Features
*Capturing the acceleration of an attack before it completes.*
Rather than just looking at the absolute numbers above, the model also looks at how fast they are changing.
- **`*_delta`**: The immediate jump from the previous minute to this minute.
- **`*_slope_2`, `*_slope_5`, `*_slope_10`**: The average rate of change over 2, 5, or 10 minutes. Captures the *acceleration* of an attack (e.g. a slow, sneaky port scan escalating into a full breach).
- **`*_zscore`**: How abnormal the current minute is compared to a 2-hour baseline. This automatically accounts for the fact that an office network is naturally busier at 2 PM than at 2 AM.

## 7. Per-Host Channel (Top Talkers)
*Capturing silent, isolated infections.*
- **Top Talkers Sub-vector**: Rather than looking at the whole network as a giant aggregate blob, this tracks the busiest individual computers. If one single computer gets infected and starts silently moving laterally, this channel catches it even if the overall network seems quiet.
