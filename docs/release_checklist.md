# Release checklist - taking the repository public for submission (D-037 Step 9)

The repository is **private** (`gh repo view` -> PRIVATE, board card G-1). Making it public is an owner
action (Arun). This list is what has to be true before that switch, and how to check each item.

## 1. Nothing that must not be published

| check | how | state |
|---|---|---|
| No credentials, tokens or `.env` files tracked | `git ls-files \| grep -iE "\.env\|secret\|token\|credential"` | clean (2026-09-28) |
| No raw dataset files tracked (licence: UNB / CTU distribute them; we do not) | `git ls-files data/raw data/interim data/processed` is empty; `.gitignore` covers `data/raw/`, `data/interim/`, `data/processed/` | clean |
| The demo slices are derived excerpts, attributed | `data/demo/index.json` names the source day; the README cites CIC-IDS2017 (corrected, Engelen et al.) and CTU-13 | check the README's data section |
| No personal data in commit metadata beyond names and emails already public on GitHub | team decision | open |
| History carries no large binaries by accident | `git count-objects -vH`; the largest blobs are the r2 checkpoints and fixtures | check |

## 2. Everything a judge needs is in the repo

| item | where | state |
|---|---|---|
| Setup instructions, cold-tested on a fresh clone | `README.md` (A-README, `c5680e7`) | re-test after Step 8 edits |
| Shipped weights + training config | `models/e4e7-worldmodel-r2/*.pt` (tracked), `configs/cicids2017.yaml` | present |
| Reference weights for the claims made (E22, E20r, E26) | `models/m1v2-e*/` are **untracked** (about 36 MB per three-seed run) | **decide**: track seed 42 of each reference, or publish as a release asset |
| Every number's source | `results.md` + `results/tables` + `results/runs/*/metrics.json` | present |
| Reproduction commands | the command block at the top of every `results.md` entry | present |
| Reference manifest | `results/runs/reference-m1-2026-09-28/manifest.json`, tag `ref-m1-2026-09-28` | present |

## 3. No artefact shows a withdrawn number

| check | how |
|---|---|
| No screenshot, fixture or slide uses the whole-capture threshold | fixtures regenerated at G-9 (`f2bb6de`); grep the deck and video for "0.576" or "2.7 %": allowed only labelled as a non-causal upper bound |
| The LR baseline is quoted like for like | 0.112 at the causal threshold (G-6), not E3's 0.011 at LR's own threshold |
| No "warns before" / "early warning" claim | D-021, D-035, D-037: "ranks pre-attack windows above background" |
| Outputs called risk scores, stages called estimates, attributions called feature contributions | E17, E9, E11 |

## 4. The switch (owner)

1. Settings -> Danger zone -> Change visibility -> Public (Arun).
2. `gh repo view --json visibility` shows `PUBLIC`.
3. Open the README from a logged-out browser and follow it once.
