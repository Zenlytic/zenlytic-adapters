import click

from .metricflow_to_zenlytic import (
    convert_mf_project_to_zenlytic_project,
    load_mf_project,
    zenlytic_views_to_yaml,
)


def echo(text: str, color: str = None, bold: bool = True):
    if color:
        click.secho(text, fg=color, bold=bold)
    else:
        click.echo(text)


@click.group()
@click.version_option()
def cli_group():
    pass


@cli_group.command()
@click.option("--out-directory", default=None, help="Where to save the Zenlytic project to")
@click.argument("metricflow_folder")
def convert(metricflow_folder, out_directory):
    """Convert a MetricFlow project to a Zenlytic project"""
    metricflow_project = load_mf_project(metricflow_folder)
    models, views = convert_mf_project_to_zenlytic_project(metricflow_project, "my_model", "my_company")
    zenlytic_views_to_yaml(models, views, out_directory)
