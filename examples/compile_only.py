"""No database, no network, no model required for deterministic compilation."""

from nlquery import NLQuery, QueryIntent
from nlquery.cli.main import offline
from nlquery.core.models import FieldSchema, Filter, SchemaModel, SourceSchema

schema = SchemaModel(
    backend="sqlite",
    sources=[SourceSchema(name="orders", fields=[FieldSchema(name="status", data_type="string")])],
)
client = NLQuery(offline(schema))
compiled = client.compile(
    QueryIntent(sources=["orders"], filters=[Filter(field="status", value="paid")], limit=10)
)
print(compiled.generated_query)
print(compiled.parameters)
assert client.validate(compiled).allowed
