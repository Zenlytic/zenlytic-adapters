import pytest
from metricflow_to_zenlytic.metricflow_to_zenlytic import (
    convert_yml_to_dict,
    load_mf_project,
    mf_dict_to_zen_views,
    zen_views_to_yaml,
)
import os

BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")


@pytest.mark.e2e
def test_e2e_read_project():
    metricflow_folder = os.path.join(BASE_PATH, "metricflow")

    metricflow_project = load_mf_project(metricflow_folder)
    print(metricflow_project)

    assert set(metricflow_project.keys()) == {"customers", "orders", "order_item"}
    assert metricflow_project["customers"]["metrics"] == []
    assert any("customers_with_orders" in m["name"] for m in metricflow_project["orders"]["metrics"])


# @pytest.mark.e2e
# @pytest.mark.parametrize(
#     "metricflow_file, zenlytic_file",
#     [
#         ("metricflow/customers.yml", "zenlytic/views/customers.yml"),
#         # ("metricflow/orders.yml", "zenlytic/views/orders.yml"),
#         # ("metricflow/order_items.yml", "zenlytic/views/order_items.yml"),
#     ],
# )
# def test_e2e_conversions(metricflow_file, zenlytic_file):
#     metricflow_path = os.path.join(BASE_PATH, metricflow_file)
#     zenlytic_path = os.path.join(BASE_PATH, zenlytic_file)

#     # convert the yaml to a dictionary
#     mf_yml = convert_yml_to_dict(metricflow_path)
#     # convert the dictionary to zenlytic views
#     zen_views = mf_dict_to_zen_views(mf_yml)
#     # convert the zenlytic views to yaml
#     views = zen_views_to_yaml(zen_views, os.path.join(BASE_PATH, "zenlytic"), write_to_file=False)

#     # read test_zen_yml
#     with open(zenlytic_path, "r") as f:
#         zen_yml = f.read()

#     # assert that zen_yml equals one of the views
#     print(zen_yml)
#     print("---")
#     print(views[-1])
#     assert zen_yml in views
