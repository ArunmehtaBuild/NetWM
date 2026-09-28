import hashlib

from netwm.freeze import brace_expand, check_references, quoted_paths, sha256_file


def test_brace_expansion_and_quoted_paths():
    assert brace_expand("results/runs/e25-ctu13-s{42,43}/x{a,b}") == [
        "results/runs/e25-ctu13-s42/xa", "results/runs/e25-ctu13-s42/xb",
        "results/runs/e25-ctu13-s43/xa", "results/runs/e25-ctu13-s43/xb"]
    md = ("Artefacts: `results/tables/a.csv`, (`results/runs/r-{1,2}/`), and results/tables/<run>_x.csv.\n"
          "See `results/tables/a.csv` again.")
    assert quoted_paths(md) == ["results/tables/a.csv", "results/runs/r-1/", "results/runs/r-2/",
                                "results/tables/<run>_x.csv"]


def test_references_are_checked_and_hashed(tmp_path):
    (tmp_path / "results/tables").mkdir(parents=True)
    (tmp_path / "results/runs/r1").mkdir(parents=True)
    (tmp_path / "results/tables/a.csv").write_text("x,y\n1,2\n")
    (tmp_path / "results/runs/r1/metrics.json").write_text("{}")
    rows = {r["path"]: r for r in check_references(
        "`results/tables/a.csv` `results/runs/r1/` `results/tables/gone.csv` `results/runs/<run>/`", tmp_path)}
    assert rows["results/tables/a.csv"]["sha256"] == hashlib.sha256(b"x,y\n1,2\n").hexdigest() or \
        rows["results/tables/a.csv"]["sha256"] == sha256_file(tmp_path / "results/tables/a.csv")
    assert rows["results/runs/r1/"]["status"] == "folder" and rows["results/runs/r1/"]["files"] == 1
    assert rows["results/tables/gone.csv"]["status"] == "MISSING"
    assert rows["results/runs/<run>/"]["status"] == "pattern (not checked)"


def test_range_shorthand_expands():
    from netwm.freeze import range_expand

    assert range_expand("results/tables/scorecard_e19..e21.csv") == [
        "results/tables/scorecard_e19.csv", "results/tables/scorecard_e20.csv", "results/tables/scorecard_e21.csv"]
    assert range_expand("results/figures/e1_wednesday..friday_timeline.png") == [
        "results/figures/e1_wednesday_timeline.png", "results/figures/e1_thursday_timeline.png",
        "results/figures/e1_friday_timeline.png"]
