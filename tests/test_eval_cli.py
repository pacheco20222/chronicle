import re

from mnemo import eval_cli


def _patch_runtime(monkeypatch, service):
    monkeypatch.setattr(eval_cli, "get_runtime", lambda: service)
    monkeypatch.setattr(eval_cli, "embed_text", lambda content: [1.0, 0.0])


def _metric_line(output, label):
    return next(line for line in output.splitlines() if label in line)


def test_eval_runs_all_metrics_for_seeded_project(service, monkeypatch, capsys):
    _patch_runtime(monkeypatch, service)
    service.add_memory([1.0, 0.0], "alpha memory", "eval-project", "note")
    service.add_memory([0.8, 0.2], "beta memory", "eval-project", "note")
    service.add_memory([0.2, 1.0], "gamma memory", "eval-project", "note")

    eval_cli.main(["--project", "eval-project"])

    output = capsys.readouterr().out
    for label in (
        "self-retrieval recall (proxy)",
        "stale-memory rate",
        "near-duplicate proxy",
        "duplicate rate",
        "avg tokens per memory",
        "avg tokens per k=5 search result set",
        "search latency",
        "provenance coverage",
    ):
        assert re.search(rf"{re.escape(label)}.*\d", output)


def test_eval_empty_project_reports_no_memories(service, monkeypatch, capsys):
    _patch_runtime(monkeypatch, service)

    eval_cli.main(["--project", "empty-eval-project"])

    assert "no memories to evaluate" in capsys.readouterr().out.lower()


def test_eval_stale_rate_and_provenance_coverage(service, monkeypatch, capsys):
    _patch_runtime(monkeypatch, service)
    service.add_memory([1.0, 0.0], "active one", "rate-project", "note")
    service.add_memory([1.0, 0.0], "active two", "rate-project", "note", source="notes.md")
    service.add_memory([1.0, 0.0], "active three", "rate-project", "note")
    superseded_id = service.add_memory([1.0, 0.0], "old memory", "rate-project", "note")
    service.set_status(superseded_id, "superseded")

    eval_cli.main(["--project", "rate-project"])

    output = capsys.readouterr().out
    assert "stale-memory rate:" in output
    assert "0.250" in _metric_line(output, "stale-memory rate")
    assert "provenance coverage:" in output
    assert "0.333" in _metric_line(output, "provenance coverage")


def test_eval_dispatches_from_cli(service, monkeypatch, capsys):
    _patch_runtime(monkeypatch, service)
    service.add_memory([1.0, 0.0], "dispatch memory", "dispatch-project", "note")

    monkeypatch.setattr("sys.argv", ["mnemo", "eval", "--project", "dispatch-project"])
    from mnemo import cli

    cli.main()

    assert "Evaluation report for project 'dispatch-project'" in capsys.readouterr().out
