import yaml
from glob import glob
import os
import re

from .metricflow_types import MetricflowMetricTypes


def convert_mf_project_to_zenlytic_project(
    mf_project: dict, project_name: str = "mf_project_name", connection_name: str = "mf_connection_name"
):
    """mf_project is a dict with keys for each semantic model
    and the dims, measures, and metrics associated with it
    """
    all_measures = []
    for semantic_model in mf_project.values():
        all_measures.extend(semantic_model.get("measures", []))

    model = {"version": 1, "type": "model", "name": project_name, "connection": connection_name}
    views = []
    for _, semantic_model in mf_project.items():
        views.append(convert_mf_view_to_zenlytic_view(semantic_model, all_measures))

    return [model], views


def load_mf_project(models_folder: str):
    semantic_models, metrics = {}, []
    for fn in read_mf_project_files(models_folder):
        mf_model_dict = convert_yml_to_dict(fn)

        metrics.extend(mf_model_dict.get("metrics", []))
        for semantic_model in mf_model_dict.get("semantic_models", []):
            semantic_models[semantic_model["name"]] = semantic_model
            # Empty list of metrics to be filled below
            semantic_models[semantic_model["name"]]["metrics"] = []

    # Assign metrics to the view they should logically live in
    for metric in metrics:
        type_params = metric["type_params"]
        if metric["type"] in {MetricflowMetricTypes.simple, MetricflowMetricTypes.cumulative}:
            metric_measure = type_params["measure"]
        elif metric["type"] == MetricflowMetricTypes.ratio:
            metric_measure = type_params["numerator"]
        elif metric["type"] == MetricflowMetricTypes.derived:
            metric_measure = type_params["metrics"][0]["name"]

        for model_name, semantic_model in semantic_models.items():
            for measure in semantic_model.get("measures", []):
                if metric_measure == measure["name"]:
                    semantic_models[model_name]["metrics"].append(metric)
                    break

    return semantic_models


def convert_mf_view_to_zenlytic_view(
    mf_semantic_model: dict, all_measures: list, original_file_path: str = None
):
    zenlytic_data = {"version": 1, "type": "view", "fields": [], "identifiers": []}

    mf_metrics = mf_semantic_model.get("metrics", [])

    if original_file_path:
        zenlytic_data["original_file_path"] = original_file_path

    # Get view-level values
    zenlytic_data["name"] = mf_semantic_model["name"]
    zenlytic_data["model_name"] = extract_inner_text(mf_semantic_model["model"])
    zenlytic_data["description"] = mf_semantic_model.get("description", None)
    default_date = mf_semantic_model.get("defaults", {}).get("agg_time_dimension")

    if default_date:
        zenlytic_data["default_date"] = default_date

    # dimensions to fields.dimensions
    for dimension in mf_semantic_model.get("dimensions", []):
        field_dict = convert_mf_dimension_to_zenlytic_dimension(dimension)
        zenlytic_data["fields"].append(field_dict)

    # measures to measures
    for measure in mf_semantic_model.get("measures", []):
        field_dict = convert_mf_measure_to_zenlytic_measure(measure)
        zenlytic_data["fields"].append(field_dict)

    for metric in mf_metrics:
        metric_dict, added_measures = convert_mf_metric_to_zenlytic_measure(metric, all_measures)
        zenlytic_data["fields"].append(metric_dict)
        zenlytic_data["fields"].extend(added_measures)

    # entities to identifiers
    for entity in mf_semantic_model["entities"]:
        if "name" in entity:
            identifier = convert_mf_entity_to_zenlytic_identifier(entity)
            zenlytic_data["identifiers"].append(identifier)

    return zenlytic_data


def convert_mf_dimension_to_zenlytic_dimension(mf_dimension: dict):
    field_dict = {
        "name": mf_dimension["name"],
        "sql": mf_dimension["expr"] if "expr" in mf_dimension else mf_dimension["name"],
    }

    if mf_dimension["type"] == "time":
        field_dict["field_type"] = "dimension_group"
        field_dict["type"] = "time"
        field_dict["timeframes"] = ["raw", "date", "week", "month", "quarter", "year", "month_of_year"]

    elif mf_dimension["type"] == "categorical":
        field_dict["field_type"] = "dimension"
        field_dict["type"] = "string"

    if description := mf_dimension.get("description"):
        field_dict["description"] = description

    if label := mf_dimension.get("label"):
        field_dict["label"] = label

    return field_dict


def convert_mf_measure_to_zenlytic_measure(mf_measure: dict):
    field_dict = {
        "name": mf_measure["name"],
        "sql": mf_measure["expr"] if "expr" in mf_measure else mf_measure["name"],
        "type": mf_measure["agg"],
        "field_type": "measure",
    }

    if not mf_measure.get("create_metric", False):
        field_dict["hidden"] = True
        # If we are not creating this metric directly, we need to set an underscore
        # in front of the metric name to stop collisions with metrics that have
        # the exact same name
        field_dict["name"] = "_" + field_dict["name"]

    if field_dict["type"] == "sum_boolean":
        field_dict["type"] = "sum"
        field_dict["sql"] = f"CAST({field_dict['sql']} AS INT)"

    if canon_date := mf_measure.get("agg_time_dimension"):
        field_dict["canon_date"] = canon_date

    if description := mf_measure.get("description"):
        field_dict["description"] = description

    if label := mf_measure.get("label"):
        field_dict["label"] = label

    return field_dict


def convert_mf_entity_to_zenlytic_identifier(mf_entity: dict):
    # if expr is a simple string, use it as the sql otherwise use it as given as a sql snippet
    if "expr" in mf_entity:
        if any(char in mf_entity["expr"] for char in [" ", "(", ")"]):
            sql = mf_entity["expr"]
        else:
            sql = "${" + mf_entity["expr"] + "}"
    else:
        sql = "${" + mf_entity["name"] + "}"

    return {
        "name": mf_entity["name"],
        "type": mf_entity["type"] if mf_entity["type"] != "unique" else "primary",
        "sql": sql,
    }


def convert_mf_metric_to_zenlytic_measure(mf_metric: dict, measures: list) -> list:
    """This returns a list because metrics with filters applied can
    result in an additional measure(s) being created
    """
    metric_dict = {
        "name": mf_metric["name"],
        "label": mf_metric.get("label", mf_metric["name"].replace("_", " ").title()),
        "field_type": "measure",
    }

    additional_measures = []
    if mf_metric["type"].lower() == "cumulative":
        metric_dict["type"] = "cumulative"
        metric_dict["measure"] = "_" + mf_metric["type_params"]["measure"]

    elif mf_metric["type"].lower() == "simple":
        associated_measure = _get_measure(mf_metric["type_params"]["measure"], measures)
        metric_dict, _ = apply_filter_to_metric(
            associated_measure, mf_metric, extra_metric_params=metric_dict
        )

    elif mf_metric["type"].lower() == "ratio":
        metric_dict["type"] = "ratio"
        numerator = mf_metric["type_params"]["numerator"]
        denominator = mf_metric["type_params"]["denominator"]
        if isinstance(numerator, str):
            numerator_sql = "${_" + numerator + "}"
        else:
            # If there's a filter, re-write the sql to include the filter
            if "filter" in numerator:
                associated_numerator = _get_measure(numerator["name"], measures)
                numerator_dict, numerator_measures = apply_filter_to_metric(
                    associated_numerator, numerator, new_measure_name=mf_metric["name"] + "_numerator"
                )
                numerator_sql = "${" + numerator_dict["name"] + "}"
                additional_measures.extend(numerator_measures)
            else:
                numerator_sql = "${_" + numerator["name"] + "}"

        if isinstance(denominator, str):
            denominator_sql = "${_" + denominator + "}"
        else:
            # If there's a filter, re-write the sql to include the filter
            if "filter" in denominator:
                associated_denominator = _get_measure(denominator["name"], measures)
                denominator_dict, denominator_measures = apply_filter_to_metric(
                    associated_denominator, denominator, new_measure_name=mf_metric["name"] + "_denominator"
                )
                denominator_sql = "${" + denominator_dict["name"] + "}"
                additional_measures.extend(denominator_measures)
            else:
                denominator_sql = "${_" + denominator["name"] + "}"

        metric_dict["sql"] = numerator_sql + " / " + denominator_sql
        metric_dict["type"] = "number"

    elif mf_metric["type"].lower() == "derived":
        metric_dict["type"] = "number"
        expr = mf_metric["type_params"]["expr"]
        referenced_metrics = mf_metric["type_params"]["metrics"]
        for metric in referenced_metrics:
            if "alias" in metric and "filter" not in metric:
                expr = expr.replace(metric["alias"], "${_" + metric["name"] + "}")
            elif "alias" in metric and "filter" in metric:
                associated_measure = _get_measure(metric["name"], measures)
                measure_dict, added_measures = apply_filter_to_metric(
                    associated_measure, metric, new_measure_name=mf_metric["name"] + f"_{metric['alias']}"
                )
                additional_measures.extend(added_measures)
                expr = expr.replace(metric["alias"], "${" + measure_dict["name"] + "}")
            else:
                # If there is no alias and no filters we just need to add reference syntax
                expr = expr.replace(metric["name"], "${_" + metric["name"] + "}")
        metric_dict["sql"] = expr

    else:
        raise TypeError(f"Metric type {mf_metric['type']} not supported")

    if description := mf_metric.get("description"):
        metric_dict["description"] = description

    if "agg_time_dimension" in mf_metric:
        metric_dict["canon_date"] = mf_metric["agg_time_dimension"]

    if "meta" in mf_metric:
        metric_dict["extra"] = mf_metric["meta"]

    return metric_dict, additional_measures


def _get_measure(measure_name: str, measures: list):
    try:
        return next((m for m in measures if m["name"] == measure_name))
    except StopIteration:
        raise ValueError(f"Could not find associated measure {measure_name}")


def apply_filter_to_metric(
    mf_measure: dict, mf_metric: dict, extra_metric_params: dict = {}, new_measure_name: str = None
):
    measure_dict = convert_mf_measure_to_zenlytic_measure(mf_measure)
    metric_dict = {**measure_dict, **extra_metric_params, "hidden": False}

    # If there's a filter, re-write the sql to include the filter
    additional_measures = []
    if "filter" in mf_metric:
        metric_dict["sql"] = apply_filter_to_sql(metric_dict["sql"], mf_metric["filter"])
        if new_measure_name:
            metric_dict["name"] = new_measure_name
            additional_measures.append(metric_dict)
    return metric_dict, additional_measures


def apply_filter_to_sql(sql, filter):
    filter_sql = _extract_filter_sql(filter)
    return f"case when {filter_sql} then {sql} else null end"


def _extract_filter_sql(filter_string):
    """A filter will look like
    "{{ Dimension('order__is_food_order') }} = True
    We want to turn it into a valid filter statement like ${order.is_food_order} = True
    """
    matches = re.findall(r"{{\s*Dimension\('(.+?)'\)\s*}}\s*([=><!]+)\s*(.+?)\s*(and|or|$)", filter_string)
    for match in matches:
        column_name = match[0].replace("__", ".")
        # operator = match[1]
        # value = match[2]
        replacement = "${" + column_name + "}"
        filter_string = filter_string.replace(f"Dimension('{match[0]}')", replacement)
        filter_string = filter_string.replace("{{", "").replace("}}", "")
    return filter_string


def convert_yml_to_dict(yml_path):
    with open(yml_path, "r") as stream:
        try:
            yaml_data = yaml.safe_load(stream)
            return yaml_data
        except yaml.YAMLError as exc:
            print(exc)
    return None


def extract_inner_text(s):
    match = re.search(r"ref\('(.*)'\)", s)
    if match:
        return match.group(1)
    return None


def zenlytic_views_to_yaml(zenlytic_models, zenlytic_views, directory: str = None, write_to_file=True):
    view_directory = os.path.join(directory, "views") if directory else "./views"
    model_directory = os.path.join(directory, "models") if directory else "./models"

    if not os.path.exists(view_directory) and write_to_file:
        os.makedirs(view_directory)

    if not os.path.exists(model_directory) and write_to_file:
        os.makedirs(model_directory)

    zenlytic_yaml = []
    for zenlytic_file in zenlytic_models + zenlytic_views:
        # write the yaml to views/model_name.yml
        if write_to_file:
            if "original_file_path" in zenlytic_file:
                file_path = zenlytic_file["original_file_path"]
            else:
                file_path = f"{zenlytic_file['name']}_{zenlytic_file['type']}.yml"

            if zenlytic_file["type"] == "model":
                write_to_path = os.path.join(model_directory, file_path)
            else:
                write_to_path = os.path.join(view_directory, file_path)
            # write the yaml to views/model_name.yml
            with open(write_to_path, "w") as outfile:
                yaml.dump(zenlytic_file, outfile, default_flow_style=False)

        # add the yaml string to views_yaml
        zenlytic_yaml.append(yaml.dump(zenlytic_file, default_flow_style=False))

    return zenlytic_yaml


def read_mf_project_files(models_folder: str):
    """Returns a list of all the yml files in the Metricflow project.
    Args:
        models_folder (str): The path to the models folder (usually project_name/models)
    """
    yml_files = glob(f"{models_folder}**/*.yml", recursive=True)
    yaml_files = glob(f"{models_folder}**/*.yaml", recursive=True)
    return yml_files + yaml_files
