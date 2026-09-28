"""D-042: the whole-capture host-relative block equals what window_features appends in one pass."""

import numpy as np
import pandas as pd

from netwm.features.flow_features import HOST_RELATIVE_FEATURES, host_relative_block, window_features
from netwm.features.windowing import WindowSpec, expand_to_windows

from test_flow_features import EXT, INTERNAL, T0, flows, host


def _capture(seed=0):
    rng = np.random.default_rng(seed)
    hosts = [f"192.168.10.{i}" for i in range(2, 9)]
    rows = []
    for w in range(60):
        for h in hosts:
            for _ in range(int(rng.integers(0, 4))):
                rows.append(host(h, f"10.0.0.{int(rng.integers(1, 30))}", 30 * w + float(rng.uniform(0, 29)),
                                 port=int(rng.integers(1, 200))))
        if w > 40:  # one host starts scanning late: the case the block exists for
            rows += [host(hosts[0], "192.168.10.99", 30 * w + 1, port=p) for p in range(20 * (w - 40))]
        rows.append(host(EXT, hosts[1], 30 * w + 2))
    return sorted(rows, key=lambda r: r["t"])


def test_block_equals_window_features_in_one_pass():
    ex, _ = expand_to_windows(flows(_capture()), WindowSpec(60, 30), t0=T0)
    n = int(ex["w"].max()) + 1
    ref = window_features(ex, 60.0, INTERNAL, n_windows=n, use_host_relative=True)[list(HOST_RELATIVE_FEATURES)]
    got = host_relative_block(ex, n, INTERNAL).astype(np.float32)
    pd.testing.assert_frame_equal(got.reset_index(drop=True), ref.reset_index(drop=True), check_names=False)
    assert got["hostrel_ports_z_max"].iloc[45:].max() > 3      # the late scan stands out against its own past


def test_integer_codes_with_explicit_internal_flags_give_the_same_block():
    ex, _ = expand_to_windows(flows(_capture(1)), WindowSpec(60, 30), t0=T0)
    n = int(ex["w"].max()) + 1
    ref = host_relative_block(ex, n, INTERNAL)
    coded = ex.assign(src_internal=ex["src_ip"].str.startswith(INTERNAL),
                      dst_internal=ex["dst_ip"].str.startswith(INTERNAL),
                      src_ip=ex["src_ip"].astype("category").cat.codes,
                      dst_ip=ex["dst_ip"].astype("category").cat.codes)
    pd.testing.assert_frame_equal(host_relative_block(coded, n, INTERNAL), ref)
