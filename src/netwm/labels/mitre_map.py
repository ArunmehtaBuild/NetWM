"""Map dataset attack labels to MITRE ATT&CK stages.

The mapping is the spec in ``research/mitre-mapping.md``; the rationale for the ordered stage scale
(and for keeping Impact off it) is decision D-003 in ``decisions.md``.

Labels are matched by regex, not by exact string, because every release spells them differently:
CIC-IDS2017 ships ``Web Attack \xef\xbf\xbd Brute Force`` (mojibake dash), the corrected release uses
``Web Attack - Brute Force`` plus ``... - Attempted`` variants, and CIC-IDS2018 renames several
classes. Unmatched labels raise instead of silently becoming benign - a mislabelled attack is worse
than a crash during the dataset audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class Stage(IntEnum):
    """Ordered kill-chain stage. IMPACT is deliberately off the progression axis (D-003)."""

    BENIGN = 0
    RECONNAISSANCE = 1
    INITIAL_ACCESS = 2
    LATERAL_MOVEMENT = 3
    COMMAND_AND_CONTROL = 4
    EXFILTRATION = 5
    IMPACT = 6


#: Stages that form the ordinal "how far has the attacker progressed" axis.
PROGRESSION_STAGES: tuple[Stage, ...] = (
    Stage.BENIGN,
    Stage.RECONNAISSANCE,
    Stage.INITIAL_ACCESS,
    Stage.LATERAL_MOVEMENT,
    Stage.COMMAND_AND_CONTROL,
    Stage.EXFILTRATION,
)

#: Stage at or above which we consider the network "compromised" for the hazard target (D-005).
COMPROMISE_THRESHOLD: Stage = Stage.LATERAL_MOVEMENT

STAGE_LABELS: dict[Stage, str] = {
    Stage.BENIGN: "Benign",
    Stage.RECONNAISSANCE: "Reconnaissance",
    Stage.INITIAL_ACCESS: "Initial Access",
    Stage.LATERAL_MOVEMENT: "Lateral Movement",
    Stage.COMMAND_AND_CONTROL: "Command & Control",
    Stage.EXFILTRATION: "Exfiltration",
    Stage.IMPACT: "Impact",
}

TACTIC_IDS: dict[Stage, str] = {
    Stage.BENIGN: "",
    Stage.RECONNAISSANCE: "TA0043",
    Stage.INITIAL_ACCESS: "TA0001",
    Stage.LATERAL_MOVEMENT: "TA0008",
    Stage.COMMAND_AND_CONTROL: "TA0011",
    Stage.EXFILTRATION: "TA0010",
    Stage.IMPACT: "TA0040",
}


@dataclass(frozen=True)
class StageInfo:
    """What a dataset label means in ATT&CK terms."""

    stage: Stage
    technique: str
    technique_name: str
    attempted: bool = False

    @property
    def tactic(self) -> str:
        return TACTIC_IDS[self.stage]

    @property
    def stage_label(self) -> str:
        return STAGE_LABELS[self.stage]


class UnknownLabelError(ValueError):
    """Raised for a label the mapping does not cover, so it cannot silently become benign."""


# Ordered: the first pattern that matches wins, so put the specific rules first.
# NOTE: the internal-portscan rule must precede the generic portscan rule, because a scan launched
# *from* a compromised host is lateral movement (discovery), not external reconnaissance.
_RULES: tuple[tuple[re.Pattern[str], StageInfo], ...] = (
    (re.compile(r"^benign$|^normal$|^background$"), StageInfo(Stage.BENIGN, "", "")),
    (
        re.compile(r"infiltration.*(portscan|port scan|nmap)|portscan.*infiltration"),
        StageInfo(Stage.LATERAL_MOVEMENT, "T1046", "Network Service Discovery"),
    ),
    (
        re.compile(r"infiltration.*cool ?disk"),
        StageInfo(Stage.LATERAL_MOVEMENT, "T1059.006", "Command and Scripting Interpreter: Python"),
    ),
    (
        # CIC-IDS2018 (D-044): the infected host calling its attacker back (13.58.225.34:31337) is the
        # C2 channel, not the infiltration step itself. No CIC-IDS2017 label contains "communication".
        re.compile(r"infiltration.*communication"),
        StageInfo(Stage.COMMAND_AND_CONTROL, "T1571", "Non-Standard Port"),
    ),
    (
        re.compile(r"infiltration"),
        StageInfo(Stage.LATERAL_MOVEMENT, "T1204", "User Execution"),
    ),
    (
        re.compile(r"\bbot(net)?\b|ares|c ?& ?c|command and control"),
        StageInfo(Stage.COMMAND_AND_CONTROL, "T1071.001", "Application Layer Protocol: Web Protocols"),
    ),
    (
        re.compile(r"exfil"),
        StageInfo(Stage.EXFILTRATION, "T1041", "Exfiltration Over C2 Channel"),
    ),
    (
        re.compile(r"ddos"),
        StageInfo(Stage.IMPACT, "T1498", "Network Denial of Service"),
    ),
    (
        re.compile(r"\bdos\b|hulk|goldeneye|slowloris|slowhttptest|rudy|hoic|loic"),
        StageInfo(Stage.IMPACT, "T1499", "Endpoint Denial of Service"),
    ),
    (
        re.compile(r"port ?scan|\bscan\b|probe|reconnaissance|\brecon\b"),
        StageInfo(Stage.RECONNAISSANCE, "T1595.001", "Active Scanning: Scanning IP Blocks"),
    ),
    (
        re.compile(r"patator|brute ?force|bruteforce|ftp|ssh"),
        StageInfo(Stage.INITIAL_ACCESS, "T1110.001", "Brute Force: Password Guessing"),
    ),
    (
        re.compile(r"sql ?injection|sqli"),
        StageInfo(Stage.INITIAL_ACCESS, "T1190", "Exploit Public-Facing Application"),
    ),
    (
        re.compile(r"\bxss\b|cross ?site"),
        StageInfo(Stage.INITIAL_ACCESS, "T1189", "Drive-by Compromise"),
    ),
    (
        re.compile(r"heartbleed"),
        StageInfo(Stage.INITIAL_ACCESS, "T1190", "Exploit Public-Facing Application"),
    ),
    (
        re.compile(r"web ?attack|shellshock|backdoor|exploit|worms?|shellcode"),
        StageInfo(Stage.INITIAL_ACCESS, "T1190", "Exploit Public-Facing Application"),
    ),
)


_ATTEMPTED = re.compile(r"\battempt(ed)?\b")


def normalise_label(label: str) -> str:
    """Lowercase, strip the ``- Attempted`` suffix and squash punctuation/mojibake dashes."""
    text = str(label).strip().lower()
    text = re.sub(r"[‐-―�]+", "-", text)  # unicode dashes / replacement chars
    text = _ATTEMPTED.sub(" ", text)
    text = re.sub(r"[_\-/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_attempted(label: str) -> bool:
    """True for the corrected release's ``... - Attempted`` labels (attack traffic with no effect)."""
    return bool(_ATTEMPTED.search(str(label).lower()))


def map_label(label: str) -> StageInfo:
    """Map one dataset label to its ATT&CK stage. Raises ``UnknownLabelError`` if unmapped."""
    text = normalise_label(label)
    if not text:
        raise UnknownLabelError("empty label")
    for pattern, info in _RULES:
        if pattern.search(text):
            return StageInfo(info.stage, info.technique, info.technique_name, is_attempted(label))
    raise UnknownLabelError(f"no ATT&CK stage rule for label {label!r} (normalised: {text!r})")


def stage_of(label: str) -> Stage:
    """Convenience wrapper returning just the stage."""
    return map_label(label).stage


def window_stage(labels: "list[str] | tuple[str, ...]") -> Stage:
    """Stage of a time window = the most advanced stage among its flows.

    Impact (DoS/DDoS) is off the progression scale, so it only wins when nothing else is present:
    a window containing both a DDoS and an infiltration is an infiltration window.
    """
    stages = [stage_of(lbl) for lbl in labels] or [Stage.BENIGN]
    # Only a progression stage *above benign* outranks Impact; otherwise a window holding a DDoS and
    # ordinary traffic would come back Benign.
    progression = [s for s in stages if s in PROGRESSION_STAGES and s > Stage.BENIGN]
    if progression:
        return max(progression)
    return max(stages)


def is_compromise(stage: Stage) -> bool:
    """Whether a stage counts as 'infiltration completed' for the hazard target (D-005)."""
    return stage in PROGRESSION_STAGES and stage >= COMPROMISE_THRESHOLD


_SCAN_LABEL = re.compile(r"scan|nmap|probe")


def refine_scan_direction(
    labels: "pd.Series", stages: "pd.Series", src_ips: "pd.Series", internal_prefixes: tuple[str, ...]
) -> "pd.Series":
    """Split scan traffic by direction: outside-in is Reconnaissance, inside-out is discovery.

    The corrected CIC-IDS2017 release labels *both* the external attacker's unscripted port scan and
    the compromised host's internal NMAP sweep as ``Infiltration - Portscan``. They are different
    kill-chain stages: a scan from outside the monitored network is reconnaissance, while the same
    scan launched from a victim host is post-compromise discovery / lateral movement. Getting this
    wrong shifts the compromise onset ~19 minutes earlier and inflates lead time (D-012).
    """
    import pandas as pd  # local import: keeps this module importable without pandas

    is_scan = labels.astype(str).str.lower().str.contains(_SCAN_LABEL, regex=True, na=False)
    internal = src_ips.astype(str).str.startswith(internal_prefixes)
    demote = is_scan & ~internal & (stages == int(Stage.LATERAL_MOVEMENT))
    out = stages.copy()
    out[demote] = int(Stage.RECONNAISSANCE)
    return out
