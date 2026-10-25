"""Command Line Interface for satellite-analyst."""

import click

from satellite_analyst import __version__
from satellite_analyst.logging import setup_logging
from satellite_analyst.planner.geocode import GeocodeService
from satellite_analyst.planner.rule_based import RuleBasedPlanner


@click.group()
@click.version_option(version=__version__, prog_name="satellite-analyst")
@click.option("--debug", is_flag=True, help="Enable verbose debug logging.")
def main(debug: bool) -> None:
    """Natural-Language Satellite Image Analyst CLI."""
    setup_logging(level="DEBUG" if debug else "INFO")


@main.command()
@click.option("--place", required=True, help="Target place name (e.g. 'Raipur').")
@click.option("--year", type=int, required=True, help="Target year (e.g. 2023).")
@click.option(
    "--season",
    type=click.Choice(["post-monsoon", "pre-monsoon"], case_sensitive=False),
    default="post-monsoon",
    help="Target season window.",
)
def composite(place: str, year: int, season: str) -> None:
    """Build a cloud-masked seasonal composite for a target region and year."""
    click.echo(f"Geocoding place: {place}...")
    geocoder = GeocodeService()
    bbox = geocoder.geocode(place)
    click.echo(f"Resolved BBox: {bbox.as_list()}")
    click.echo(f"Building {season} composite for {year} (Implementation in Phase 1)...")


@main.command()
@click.option("--query", required=True, help="Natural language query string.")
def analyze(query: str) -> None:
    """Execute end-to-end analysis from a natural language query."""
    click.echo(f"Executing query: '{query}'")
    planner = RuleBasedPlanner()
    plan = planner.parse_query(query)
    click.echo(f"Generated Plan: {plan.task_type} for {plan.aoi.place_name} ({plan.season_policy})")
    click.echo(f"Baseline window: {plan.time_range_a.label}")
    if plan.time_range_b:
        click.echo(f"Comparison window: {plan.time_range_b.label}")


if __name__ == "__main__":
    main()
