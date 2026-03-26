from datetime import timedelta

from feast import Entity, FeatureView, Field
from feast.infra.offline_stores.contrib.postgres_offline_store.postgres_source import (
    PostgreSQLSource,
)
from feast.types import Float64
from feast.value_type import ValueType

transaction_entity = Entity(
    name="entity_id",
    join_keys=["entity_id"],
    value_type=ValueType.INT64,
)

fraud_source = PostgreSQLSource(
    name="fraud_transactions_source",
    query="SELECT * FROM fraud_transactions",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

fraud_features = FeatureView(
    name="fraud_features",
    entities=[transaction_entity],
    ttl=timedelta(days=7),
    schema=[
        Field(name="distance_from_home", dtype=Float64),
        Field(name="distance_from_last_transaction", dtype=Float64),
        Field(name="ratio_to_median_purchase_price", dtype=Float64),
        Field(name="repeat_retailer", dtype=Float64),
        Field(name="used_chip", dtype=Float64),
        Field(name="used_pin_number", dtype=Float64),
        Field(name="online_order", dtype=Float64),
        Field(name="fraud", dtype=Float64),
    ],
    source=fraud_source,
)
