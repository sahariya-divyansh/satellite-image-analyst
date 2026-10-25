"""Command Line Interface for satellite-analyst."""

import sys
from datetime import date
from pathlib import Path

import click

from satellite_analyst import __version__
from satellite_analyst.data.composites import CompositeBuilder, save_composite_to_geotiff
from satellite_analyst.errors import SatelliteAnalystError
from satellite_analyst.logging import setup_logging
from satellite_analyst.planner.geocode import GeocodeService
from satellite_analyst.planner.rule_based import RuleBasedPlanner
from satellite_analyst.planner.schema import TimeInterval


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
    type=str,
    default="post_monsoon",
    help="Target seasonal window: 'post_monsoon' (Oct-Nov) or 'pre_monsoon' (Mar-May).",
)
@click.option(
    "--radius-km",
    type=float,
    default=15.0,
    help="Buffer radius in kilometers around place centroid (default: 15 km).",
)
@click.option(
    "--max-cloud",
    type=float,
    default=40.0,
    help="Maximum scene cloud cover percentage for STAC filtering (default: 40%).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("outputs"),
    help="Output directory for generated GeoTIFFs and provenance metadata.",
)
def composite(
    place: str,
    year: int,
    season: str,
    radius_km: float,
    max_cloud: float,
    out: Path,
) -> None:
    """Build a cloud-masked seasonal composite for a target region and year."""
    try:
        season_normalized = season.strip().lower().replace("-", "_")
        if season_normalized == "pre_monsoon":
            start_d = date(year, 3, 1)
            end_d = date(year, 5, 31)
            season_label = f"Pre-Monsoon Mar-May {year}"
        else:
            season_normalized = "post_monsoon"
            start_d = date(year, 10, 1)
            end_d = date(year, 11, 30)
            season_label = f"Post-Monsoon Oct-Nov {year}"

        interval = TimeInterval(
            start_date=start_d,
            end_date=end_d,
            label=season_label,
        )

        click.echo(f"==> Resolving spatial bounds for '{place}' (radius: {radius_km} km)...")
        geocoder = GeocodeService()
        geo_res = geocoder.geocode(place, radius_km=radius_km)
        click.echo(
            f"    Location: {geo_res.display_name}\n"
            f"    Centroid: ({geo_res.lat:.4f}, {geo_res.lon:.4f}) | Source: {geo_res.source}\n"
            f"    BBox: {geo_res.bbox.as_list()}\n"
            f"    Planar Area: {geo_res.area_km2:.1f} km²"
        )

        click.echo(f"==> Building {season_label} median composite (max cloud: {max_cloud}%)...")
        builder = CompositeBuilder()
        res = builder.build_composite(
            bbox=geo_res.bbox,
            time_range=interval,
            max_cloud_cover=max_cloud,
            min_valid_obs=2,
        )

        # Save output GeoTIFFs and provenance
        out.mkdir(parents=True, exist_ok=True)
        prefix = f"{place.lower()}_{year}_{season_normalized}"
        saved_paths = save_composite_to_geotiff(res, output_dir=out, prefix=prefix)

        click.echo("\n================ COMPOSITE SUMMARY ================")
        click.echo(f" Place:                  {place}")
        click.echo(f" Seasonal Window:        {season_label}")
        click.echo(f" Scenes Found & Used:    {len(res.scene_ids)}")
        click.echo(f" Clear-Sky Valid Pixels: {res.valid_fraction * 100:.2f}%")
        click.echo(f" Equal-Area CRS:         {res.crs}")
        click.echo(" Generated Artifacts:")
        for name, path in saved_paths.items():
            click.echo(f"   [{name.upper()}]: {path}")
        click.echo("====================================================\n")

    except SatelliteAnalystError as sae:
        click.secho(f"\nError: [{sae.code}] {sae.message}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nExecution Failed: {e}", fg="red", err=True)
        sys.exit(1)


@main.command()
@click.option("--query", required=True, help="Natural language query string.")
def analyze(query: str) -> None:
    """Execute end-to-end analysis from a natural language query."""
    try:
        click.echo(f"Executing query: '{query}'")
        planner = RuleBasedPlanner()
        plan = planner.parse_query(query)
        click.echo(
            f"Generated Plan: {plan.task_type} for {plan.aoi.place_name} ({plan.season_policy})"
        )
        click.echo(f"Baseline window: {plan.time_range_a.label}")
        if plan.time_range_b:
            click.echo(f"Comparison window: {plan.time_range_b.label}")
    except Exception as e:
        click.secho(f"Analysis failed: {e}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
