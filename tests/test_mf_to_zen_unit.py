import pytest
from metricflow_to_zenlytic.metricflow_to_zenlytic import (
    convert_mf_dimension_to_zenlytic_dimension,
    convert_mf_measure_to_zenlytic_measure,
    convert_mf_entity_to_zenlytic_identifier,
    convert_mf_metric_to_zenlytic_measure,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "mf_dimension",
    [
        {"name": "no_sql", "type": "categorical", "label": "No SQL"},
        {
            "name": "is_bulk_transaction",
            "type": "categorical",
            "expr": "case when quantity > 10 then true else false end",
        },
        {
            "name": "deleted_at",
            "type": "time",
            "expr": "date_trunc('day', ts_deleted)",
            "is_partition": True,
            "type_params": {"time_granularity": "day"},
        },
    ],
)
def test_dimension_conversion(mf_dimension):
    converted = convert_mf_dimension_to_zenlytic_dimension(mf_dimension)

    if mf_dimension["name"] == "is_bulk_transaction":
        correct = {
            "name": "is_bulk_transaction",
            "field_type": "dimension",
            "type": "string",
            "sql": "case when quantity > 10 then true else false end",
        }
    elif mf_dimension["name"] == "deleted_at":
        correct = {
            "name": "deleted_at",
            "field_type": "dimension_group",
            "type": "time",
            "sql": "date_trunc('day', ts_deleted)",
            "timeframes": ["raw", "date", "week", "month", "quarter", "year", "month_of_year"],
        }
    elif mf_dimension["name"] == "no_sql":
        correct = {
            "name": "no_sql",
            "label": "No SQL",
            "field_type": "dimension",
            "type": "string",
            "sql": "no_sql",
        }

    assert converted == correct


@pytest.mark.unit
@pytest.mark.parametrize(
    "mf_measure",
    [
        {
            "name": "total_revenue",
            "description": "all gross revenue",
            "agg": "sum",
            "expr": "revenue",
            "agg_time_dimension": "created_at",
            "label": "Total Revenue (USD)",
        },
        {
            "name": "aov",
            "agg": "average",
            "expr": "case when email not ilike '%internal.com' then revenue end",
        },
        {"name": "quick_buy_transactions", "agg": "sum_boolean"},
        {"name": "last_purchase", "agg": "max", "expr": "purchase_date", "create_metric": True},
    ],
)
def test_measure_conversion(mf_measure):
    converted = convert_mf_measure_to_zenlytic_measure(mf_measure)

    if mf_measure["name"] == "total_revenue":
        correct = {
            "name": "_total_revenue",
            "field_type": "measure",
            "sql": "revenue",
            "type": "sum",
            "label": "Total Revenue (USD)",
            "canon_date": "created_at",
            "description": "all gross revenue",
            "hidden": True,
        }
    elif mf_measure["name"] == "aov":
        correct = {
            "name": "_aov",
            "field_type": "measure",
            "sql": "case when email not ilike '%internal.com' then revenue end",
            "type": "average",
            "hidden": True,
        }
    elif mf_measure["name"] == "quick_buy_transactions":
        correct = {
            "name": "_quick_buy_transactions",
            "field_type": "measure",
            "sql": "CAST(quick_buy_transactions AS INT)",
            "type": "sum",
            "hidden": True,
        }
    elif mf_measure["name"] == "last_purchase":
        correct = {"name": "last_purchase", "field_type": "measure", "sql": "purchase_date", "type": "max"}

    assert converted == correct


@pytest.mark.unit
@pytest.mark.parametrize(
    "mf_metric",
    [
        {
            "name": "cumulative_metric",
            "description": "The metric description",
            "type": "cumulative",
            "label": "C Metric",
            "type_params": {
                "measure": "total_revenue",
                "window": "7 days",
                "grain_to_date": "month",
            },  # NOTE: we do not support, window or grain_to_date
        },
        {
            "name": "customers",
            "description": "Count of customers",
            "type": "simple",
            "label": "Count of customers",
            "type_params": {"measure": "customers"},
        },
        {
            "name": "large_orders",
            "description": "Order with order values over 20.",
            "type": "SIMPLE",
            "label": "Large Orders",
            "type_params": {"measure": "orders"},
            "filter": "{{Dimension('customer__order_total_dim')}} >= 20",
        },
        {
            "name": "food_order_pct",
            "description": "The food order count as a ratio of the total order count",
            "label": "Food Order Ratio",
            "type": "ratio",
            "type_params": {"numerator": "food_orders", "denominator": "orders"},
        },
        {
            "name": "frequent_purchaser_ratio",
            "description": "Fraction of active users who qualify as frequent purchasers",
            "owners": ["support@getdbt.com"],
            "type": "ratio",
            "type_params": {
                "numerator": {
                    "name": "distinct_purchasers",
                    "filter": "{{Dimension('customer__is_frequent_purchaser')}}",
                    "alias": "frequent_purchasers",
                },
                "denominator": {"name": "distinct_purchasers"},
            },
        },
        {
            "name": "order_gross_profit",
            "description": "Gross profit from each order.",
            "type": "derived",
            "label": "Order Gross Profit",
            "type_params": {
                "expr": "revenue - cost",
                "metrics": [
                    {"name": "order_total", "alias": "revenue"},
                    {"name": "order_cost", "alias": "cost"},
                ],
            },
        },
        {
            "name": "food_order_gross_profit",
            "label": "Food Order Gross Profit",
            "description": "The gross profit for each food order.",
            "type": "derived",
            "type_params": {
                "expr": "revenue - cost",
                "metrics": [
                    {
                        "name": "order_total",
                        "alias": "revenue",
                        "filter": "{{ Dimension('order__is_food_order') }} = True",
                    },
                    {
                        "name": "order_cost",
                        "alias": "cost",
                        "filter": "{{ Dimension('order__is_food_order') }} = True",
                    },
                ],
            },
        },
    ],
)
def test_metric_conversion(mf_metric):
    measures = [
        {"name": "customers", "agg": "count_distinct", "expr": "id_customer"},
        {"name": "orders", "agg": "count_distinct", "expr": "id_order"},
        {"name": "food_orders", "agg": "count_distinct", "expr": "case when is_food then id_order end"},
        {"name": "distinct_purchasers", "agg": "count_distinct", "expr": "id_customer"},
        {"name": "order_total", "agg": "sum", "expr": "num_order_total"},
        {"name": "order_cost", "agg": "sum", "expr": "num_order_cost"},
    ]
    converted = convert_mf_metric_to_zenlytic_measure(mf_metric, measures)

    if mf_metric["name"] == "cumulative_metric":
        correct = {
            "name": "cumulative_metric",
            "field_type": "measure",
            "measure": "_total_revenue",
            "type": "cumulative",
            "label": "C Metric",
            "description": "The metric description",
        }
    elif mf_metric["name"] == "customers":
        correct = {
            "name": "customers",
            "field_type": "measure",
            "sql": "id_customer",
            "hidden": False,
            "type": "count_distinct",
            "label": "Count of customers",
            "description": "Count of customers",
        }
    elif mf_metric["name"] == "large_orders":
        # Push down the filter to a new filtered measure
        correct = {
            "name": "large_orders",
            "field_type": "measure",
            "hidden": False,
            "sql": "case when ${customer.order_total_dim} >= 20 then id_order else null end",
            "type": "count_distinct",
            "label": "Large Orders",
            "description": "Order with order values over 20.",
        }
    elif mf_metric["name"] == "food_order_pct":
        correct = {
            "name": "food_order_pct",
            "field_type": "measure",
            "sql": "${_food_orders} / ${_orders}",
            "type": "number",
            "label": "Food Order Ratio",
            "description": "The food order count as a ratio of the total order count",
        }
    elif mf_metric["name"] == "frequent_purchaser_ratio":
        correct = {
            "name": "frequent_purchaser_ratio",
            "field_type": "measure",
            "sql": "${frequent_purchaser_ratio_numerator} / ${_distinct_purchasers}",
            "type": "number",
            "label": "Frequent Purchaser Ratio",
            "description": "Fraction of active users who qualify as frequent purchasers",
        }
    elif mf_metric["name"] == "order_gross_profit":
        correct = {
            "name": "order_gross_profit",
            "field_type": "measure",
            "sql": "${_order_total} - ${_order_cost}",
            "type": "number",
            "label": "Order Gross Profit",
            "description": "Gross profit from each order.",
        }
    elif mf_metric["name"] == "food_order_gross_profit":
        correct = {
            "name": "food_order_gross_profit",
            "field_type": "measure",
            "sql": "${food_order_gross_profit_revenue} - ${food_order_gross_profit_cost}",
            "type": "number",
            "label": "Food Order Gross Profit",
            "description": "The gross profit for each food order.",
        }

    assert converted == correct


@pytest.mark.unit
@pytest.mark.parametrize(
    "mf_entity",
    [
        {"name": "transaction", "type": "primary", "expr": "id_transaction"},
        {"name": "order", "type": "foreign", "expr": "id_order"},
        {"name": "order_line", "type": "unique", "expr": "CAST(id_order_line AS STRING)"},
    ],
)
def test_entity_conversion(mf_entity):
    converted = convert_mf_entity_to_zenlytic_identifier(mf_entity)

    if mf_entity["name"] == "transaction":
        correct = {"name": "transaction", "type": "primary", "sql": "${id_transaction}"}
    elif mf_entity["name"] == "order":
        correct = {"name": "order", "type": "foreign", "sql": "${id_order}"}
    elif mf_entity["name"] == "order_line":
        correct = {"name": "order_line", "type": "primary", "sql": "CAST(id_order_line AS STRING)"}

    assert converted == correct
