"""M3: the CIC-IDS2018 adapter reads the corrected release into the canonical schema."""

import numpy as np
import pandas as pd

from netwm.data.cicids2017 import COLUMN_MAP, PACKET_STAT_MAP
from netwm.data.cicids2018 import DAY_FILES, CICIDS2018Adapter
from netwm.labels.mitre_map import Stage

HEADER = ["id", "Flow ID", *COLUMN_MAP, *PACKET_STAT_MAP, "Attempted Category"]


def _day(tmp_path, rows):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({c: rng.integers(0, 100, len(rows)) for c in HEADER})
    df["Timestamp"] = [r[0] for r in rows]
    df["Label"] = [r[1] for r in rows]
    df["Src IP"] = [r[2] for r in rows]
    df["Dst IP"] = "172.31.69.25"
    path = tmp_path / DAY_FILES["feb28"]
    df.to_csv(path, index=False)
    return CICIDS2018Adapter(tmp_path)


ROWS = [
    ("2018-02-28 14:00:05.5", "BENIGN", "172.31.64.10"),
    ("2018-02-28 14:00:01.25", "Infiltration - NMAP Portscan", "172.31.69.13"),   # from a victim: discovery
    ("2018-02-28 14:00:03", "Infiltration - NMAP Portscan", "13.58.225.34"),      # from outside: recon
    ("2018-02-28 14:00:02", "SSH-BruteForce", "18.221.219.4"),
    ("2018-02-28 14:00:04", "FTP-BruteForce - Attempted", "18.221.219.4"),
]


def test_load_maps_stages_and_sorts(tmp_path):
    ad = _day(tmp_path, ROWS)
    assert ad.splits() == ["feb28"]
    df = ad.load("feb28")
    assert df["ts"].is_monotonic_increasing
    by = df.set_index(df["ts"].dt.strftime("%S.%f"))
    assert by.loc["01.250000", "stage"] == Stage.LATERAL_MOVEMENT      # D-012 split by source address
    assert by.loc["03.000000", "stage"] == Stage.RECONNAISSANCE
    assert by.loc["02.000000", "stage"] == Stage.INITIAL_ACCESS
    assert bool(by.loc["04.000000", "attempted"]) and not bool(by.loc["02.000000", "attempted"])


def test_chunks_carry_the_same_rows(tmp_path):
    ad = _day(tmp_path, ROWS)
    whole = ad.load("feb28")
    parts = pd.concat(list(ad.iter_chunks("feb28", chunk=2))).sort_values("ts", kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(parts, whole)


def test_flows_before_the_capture_date_and_the_unlabelled_flow_are_dropped_and_counted(tmp_path):
    rows = [*ROWS, ("2018-02-26 09:00:00", "BENIGN", "172.31.64.10"), ("2018-02-28 14:00:06", "-1", "172.31.65.67")]
    ad = _day(tmp_path, rows)
    df = ad.load("feb28")
    assert len(df) == len(ROWS)
    assert ad.dropped["feb28"] == {"before_capture_date": 1, "label_-1": 1}


def test_the_infiltration_callback_is_c2_and_the_2017_rules_are_unchanged():
    from netwm.labels.mitre_map import stage_of

    assert stage_of("Infiltration - Communication Victim Attacker") == Stage.COMMAND_AND_CONTROL
    assert stage_of("Infiltration - Dropbox Download") == Stage.LATERAL_MOVEMENT
    assert stage_of("Infiltration") == Stage.LATERAL_MOVEMENT              # CIC-IDS2017's label
    assert stage_of("Infiltration - Portscan") == Stage.LATERAL_MOVEMENT
