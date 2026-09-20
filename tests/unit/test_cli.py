import json
import runpy
import sqlite3
from pathlib import Path

import pytest

from nlquery.cli.main import main
from nlquery.config import QueryConfig, load_catalog
from nlquery.exceptions import ConfigurationError


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "data.db"
    with sqlite3.connect(path) as c:
        c.executescript("CREATE TABLE items (name TEXT);INSERT INTO items VALUES ('A');")
    return path


def test_cli_compile_execute_validate(db, tmp_path, capsys):
    intent = tmp_path / "intent.json"
    intent.write_text('{"sources":["items"]}')
    args = ["--database", str(db), "--intent", str(intent), "--format", "json"]
    assert main(["compile", *args]) == 0
    proposal = json.loads(capsys.readouterr().out)
    assert proposal["backend"] == "sqlite"
    compiled = tmp_path / "compiled.json"
    compiled.write_text(json.dumps(proposal))
    assert main(["validate", "--database", str(db), "--compiled", str(compiled)]) == 0
    capsys.readouterr()
    assert main(["ask", *args, "--execute"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == [{"name": "A"}]
    assert main(["inspect", "--database", str(db)]) == 0
    assert "items" in capsys.readouterr().out
    assert main(["explain", *args]) == 0
    assert json.loads(capsys.readouterr().out)["validation"]["allowed"]


def test_cli_error_safe(capsys):
    assert main(["compile", "secret=do-not-print"]) == 2
    assert "do-not-print" not in capsys.readouterr().err


def test_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"policy":{"max_rows":5}}')
    assert QueryConfig.load(path).policy.max_rows == 5
    monkeypatch.setenv("NLQUERY_MAX_ROWS", "7")
    assert QueryConfig.load(path).policy.max_rows == 7
    monkeypatch.setenv("NLQUERY_MAX_ROWS", "bad")
    with pytest.raises(ConfigurationError):
        QueryConfig.load(path)


def test_catalog(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text('{"concepts":{"revenue":{"candidates":["items.amount"]}}}')
    assert load_catalog(path).concepts["revenue"].candidates == ["items.amount"]


def test_examples():
    root = Path(__file__).parents[2]
    result = runpy.run_path(str(root / "examples" / "ecommerce.py"))["run"]()
    assert result["result"]["row_count"] == 2
    runpy.run_path(str(root / "examples" / "compile_only.py"))
