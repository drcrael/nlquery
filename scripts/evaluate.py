"""Run real provider inference against the version-controlled corpus, outside normal CI."""

import argparse
import json
from pathlib import Path

from nlquery import NLQuery
from nlquery.cli.main import offline
from nlquery.core.models import SchemaModel
from nlquery.evaluation import evaluate

parser = argparse.ArgumentParser()
parser.add_argument("--provider", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
schema = SchemaModel.model_validate_json((root / "tests/golden/schema.json").read_text())
cases = [
    c
    for c in json.loads((root / "tests/golden/cases.json").read_text())
    if c["outcome"] == "compile"
]
report = evaluate(NLQuery(offline(schema), llm=args.provider), cases)
report["provider"] = args.provider
args.output.write_text(json.dumps(report, indent=2) + "\n")
