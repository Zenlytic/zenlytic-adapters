# This repo has moved, and this location is no longer maintained.

It has moved to the main [metrics layer repo](https://github.com/Zenlytic/metrics_layer).


# Zenlytic Adapters

Utilities for converting semantic layer YAML files to Zenlytic's format.

## Steps for usage:
1. Run `pip install metricflow-to-zenlytic`
2. `$ metricflow_to_zenlytic [DIRECTORY]` from the command line, where `[DIRECTORY]` is the directory your `dbt_project.yml` file is in.

## Usage in Python

To run the function in python you can do so like this:

```
from metricflow_to_zenlytic.metricflow_to_zenlytic import (
    load_mf_project,
    convert_mf_project_to_zenlytic_project,
)

# Load the metricflow project
metricflow_project = load_mf_project(metricflow_folder)

# Convert to Zenyltic models and views
models, views = convert_mf_project_to_zenlytic_project(metricflow_project, "my_model", "my_company")

# Save as yaml files
out_directory = '/save/to/here/'
zenlytic_views_to_yaml(models, views, out_directory)

```

## Testing

`$ pytest`
