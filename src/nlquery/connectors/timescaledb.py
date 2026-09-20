"""PostgreSQL reuse with explicit hypertable metadata and time_bucket compilation."""

from nlquery.connectors.postgres import PostgresConnector
from nlquery.core.models import ConnectorCapabilities, SchemaModel
from nlquery.exceptions import SchemaDiscoveryError


class TimescaleDBConnector(PostgresConnector):
    backend = "timescaledb"
    capabilities = ConnectorCapabilities(
        joins=True, aggregation=True, calculations=True, distinct=True, time_series=True
    )

    def discover(self) -> SchemaModel:
        base = super().discover()
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SELECT set_config('statement_timeout','10000',true)")
                cur.execute(
                    "SELECT hypertable_name, column_name FROM timescaledb_information.dimensions WHERE hypertable_schema=%s AND dimension_type='Time' LIMIT %s",
                    (self.namespace, self.config.max_sources + 1),
                )
                dimensions = dict(cur.fetchall())
                cur.execute(
                    "SELECT view_name FROM timescaledb_information.continuous_aggregates WHERE view_schema=%s LIMIT %s",
                    (self.namespace, self.config.max_sources + 1),
                )
                continuous = {r[0] for r in cur.fetchall()}
                sources = [
                    s.model_copy(
                        update={
                            "time_field": dimensions.get(s.name),
                            "metadata": {
                                "hypertable": s.name in dimensions,
                                "continuous_aggregate": s.name in continuous,
                            },
                        }
                    )
                    for s in base.sources
                ]
                return base.model_copy(update={"sources": sources})
        except Exception:
            raise SchemaDiscoveryError(
                "Timescale metadata discovery failed; extension required"
            ) from None
