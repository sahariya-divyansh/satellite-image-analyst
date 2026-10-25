"""Command Line Interface for satellite-analyst."""

import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import click
import pandas as pd  # type: ignore[import-untyped]
from affine import Affine

from satellite_analyst import __version__
from satellite_analyst.analysis.change import detect_water_change, save_change_raster_to_geotiff
from satellite_analyst.analysis.indices import compute_mndwi
from satellite_analyst.analysis.stats import (
    compute_summary_stats,
    compute_threshold_sensitivity,
)
from satellite_analyst.analysis.vectorize import (
    estimate_utm_epsg,
    extract_waterbody_records,
    vectorize_change_classes,
)
from satellite_analyst.analysis.water import segment_dual_period_water
from satellite_analyst.data.composites import CompositeBuilder, save_composite_to_geotiff
from satellite_analyst.errors import SatelliteAnalystError
from satellite_analyst.logging import setup_logging
from satellite_analyst.planner.geocode import GeocodeService
from satellite_analyst.planner.llm_base import BaseLLMProvider, LLMPlanner
from satellite_analyst.planner.providers.gemini import GeminiProvider
from satellite_analyst.planner.providers.openai import OpenAIProvider
from satellite_analyst.planner.rule_based import RuleBasedPlanner
from satellite_analyst.planner.schema import TimeInterval
from satellite_analyst.report.generator import ReportGenerator


@click.group()
@click.version_option(version=__version__, prog_name="satellite-analyst")
@click.option("--debug", is_flag=True, help="Enable verbose debug logging.")
def main(debug: bool) -> None:
    """Natural-Language Satellite Image Analyst CLI."""
    setup_logging(level="DEBUG" if debug else "INFO")


def _resolve_seasonal_dates(season_str: str, year: int) -> tuple[date, date, str]:
    """Map human seasonal string into exact temporal date boundary."""
    season_norm = season_str.lower().strip().replace("-", "_")
    if season_norm in ("post_monsoon", "postmonsoon"):
        return (
            date(year, 10, 1),
            date(year, 11, 30),
            f"Post-Monsoon Oct-Nov {year}",
        )
    if season_norm in ("pre_monsoon", "premonsoon", "summer"):
        return (
            date(year, 3, 1),
            date(year, 5, 31),
            f"Pre-Monsoon Mar-May {year}",
        )
    if season_norm in ("monsoon", "kharif"):
        return (
            date(year, 6, 1),
            date(year, 9, 30),
            f"Monsoon Jun-Sep {year}",
        )
    return (
        date(year, 10, 1),
        date(year, 11, 30),
        f"Post-Monsoon Oct-Nov {year}",
    )


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
    help="Radial buffering distance around centroid in km (default: 15.0 km).",
)
@click.option(
    "--max-cloud",
    type=float,
    default=40.0,
    help="Maximum allowed scene cloud cover percentage (default: 40.0%).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("outputs/"),
    help="Output directory for generated GeoTIFF composites and provenance.",
)
def composite(
    place: str,
    year: int,
    season: str,
    radius_km: float,
    max_cloud: float,
    out: Path,
) -> None:
    """Generate a cloud-masked seasonal median composite from Sentinel-2 L2A."""
    try:
        start_d, end_d, season_label = _resolve_seasonal_dates(season, year)
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

        out.mkdir(parents=True, exist_ok=True)
        season_norm = season.lower().strip().replace("-", "_")
        prefix = f"{place.lower()}_{year}_{season_norm}"
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


@main.command(name="water-change")
@click.option("--place", required=True, help="Target location (e.g. 'Raipur').")
@click.option("--year-a", type=int, default=2023, help="Baseline period year (e.g. 2023).")
@click.option("--year-b", type=int, default=2025, help="Comparison period year (e.g. 2025).")
@click.option(
    "--season",
    type=str,
    default="post_monsoon",
    help="Seasonal window: 'post_monsoon', 'pre_monsoon', or 'monsoon'.",
)
@click.option(
    "--radius-km",
    type=float,
    default=15.0,
    help="Radial buffering distance in km (default: 15.0 km).",
)
@click.option(
    "--max-cloud",
    type=float,
    default=40.0,
    help="Maximum allowed scene cloud cover percentage (default: 40.0%).",
)
@click.option(
    "--threshold-policy",
    type=click.Choice(["shared", "per_period"]),
    default="shared",
    help="Threshold policy ('shared' pools data to prevent false change).",
)
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Manual MNDWI threshold override (disables Otsu).",
)
@click.option(
    "--min-area-ha",
    type=float,
    default=0.1,
    help="Minimum waterbody area filter in hectares (default: 0.1 ha = 10 px).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("outputs/"),
    help="Directory to save output GeoTIFFs, GeoJSONs, CSVs, and provenance.",
)
def water_change(
    place: str,
    year_a: int,
    year_b: int,
    season: str,
    radius_km: float,
    max_cloud: float,
    threshold_policy: str,
    threshold: float | None,
    min_area_ha: float,
    out: Path,
) -> None:
    """Run 3-class surface water change detection between two temporal periods."""
    try:
        out.mkdir(parents=True, exist_ok=True)
        season_norm = season.lower().strip().replace("-", "_")

        # 1. Geocode place bounds
        click.echo(f"==> Resolving spatial bounds for '{place}' (radius: {radius_km} km)...")
        geocoder = GeocodeService()
        geo_res = geocoder.geocode(place, radius_km=radius_km)
        utm_zone = estimate_utm_epsg(geo_res.lon, geo_res.lat)
        click.echo(
            f"    Location: {geo_res.display_name}\n"
            f"    Centroid: ({geo_res.lat:.4f}, {geo_res.lon:.4f}) | Source: {geo_res.source}\n"
            f"    Planar Area: {geo_res.area_km2:.1f} km² | Equal-Area CRS: EPSG:{utm_zone}"
        )

        builder = CompositeBuilder()

        # 2. Ingest / load Baseline Composite (Period A)
        start_a, end_a, label_a = _resolve_seasonal_dates(season, year_a)
        interval_a = TimeInterval(start_date=start_a, end_date=end_a, label=label_a)
        click.echo(f"==> Ingesting / loading Baseline Composite ({label_a})...")
        comp_a = builder.build_composite(
            bbox=geo_res.bbox,
            time_range=interval_a,
            max_cloud_cover=max_cloud,
            min_valid_obs=2,
        )

        # 3. Ingest / load Comparison Composite (Period B)
        start_b, end_b, label_b = _resolve_seasonal_dates(season, year_b)
        interval_b = TimeInterval(start_date=start_b, end_date=end_b, label=label_b)
        click.echo(f"==> Ingesting / loading Comparison Composite ({label_b})...")
        comp_b = builder.build_composite(
            bbox=geo_res.bbox,
            time_range=interval_b,
            max_cloud_cover=max_cloud,
            min_valid_obs=2,
        )

        # 4. Compute MNDWI index
        click.echo("==> Computing MNDWI index rasters...")
        mndwi_a = compute_mndwi(comp_a.green.values, comp_a.swir1.values)
        mndwi_b = compute_mndwi(comp_b.green.values, comp_b.swir1.values)

        # 5. Segment water masks under consistent threshold policy
        click.echo(f"==> Segmenting water masks (policy: {threshold_policy})...")
        policy_lit: Literal["shared", "per_period"] = (
            "shared" if threshold_policy == "shared" else "per_period"
        )
        mask_a, mask_b = segment_dual_period_water(
            mndwi_a=mndwi_a,
            mndwi_b=mndwi_b,
            policy=policy_lit,
            override_threshold=threshold,
            min_area_ha=min_area_ha,
            pixel_size_m=10.0,
        )

        # 6. Detect 3-class transitions
        click.echo("==> Performing 3-class change classification & confidence masking...")
        change_raster = detect_water_change(
            mask_a=mask_a,
            mask_b=mask_b,
            valid_count_a=comp_a.valid_count.values,
            valid_count_b=comp_b.valid_count.values,
            min_valid_obs=2,
        )

        # 7. Derive Affine Transform from coordinate dimensions
        xs = comp_a.green["x"].values
        ys = comp_a.green["y"].values
        res_x = float(abs(xs[1] - xs[0])) if len(xs) > 1 else 10.0
        res_y = float(abs(ys[1] - ys[0])) if len(ys) > 1 else 10.0
        top_left_x = float(xs[0] - res_x / 2.0)
        top_left_y = float(ys[0] + res_y / 2.0)
        transform = Affine.translation(top_left_x, top_left_y) @ Affine.scale(res_x, -res_y)

        # 8. Vectorize and extract per-waterbody records
        click.echo("==> Vectorizing change classes and tabulating waterbody dynamics...")
        change_gdf = vectorize_change_classes(
            change_raster=change_raster,
            transform=transform,
            crs=comp_a.crs,
            min_area_ha=min_area_ha,
        )

        wb_records, wb_gdf = extract_waterbody_records(
            mask_a=mask_a.mask,
            mask_b=mask_b.mask,
            transform=transform,
            crs=comp_a.crs,
            min_area_ha=min_area_ha,
            pixel_size_m=10.0,
        )

        # 9. Compute regional aggregate statistics and sensitivity
        stats = compute_summary_stats(
            change_raster=change_raster,
            waterbodies=wb_records,
            pixel_size_m=10.0,
        )

        valid_common = (comp_a.valid_count.values >= 2) & (comp_b.valid_count.values >= 2)
        sensitivity = compute_threshold_sensitivity(
            mndwi_a=mndwi_a,
            mndwi_b=mndwi_b,
            valid_mask=valid_common,
            mid_threshold=float(mask_a.threshold),
            offset=0.1,
            pixel_size_m=10.0,
        )

        # 10. Export artifacts
        slug = f"{place.lower()}_{year_a}_{year_b}_{season_norm}"
        p_change_tif = out / f"{slug}_change_classes.tif"
        p_change_geojson = out / f"{slug}_change_vectors.geojson"
        p_wb_geojson = out / f"{slug}_waterbodies.geojson"
        p_wb_csv = out / f"{slug}_waterbodies.csv"
        p_provenance = out / f"{slug}_provenance.json"

        save_change_raster_to_geotiff(change_raster, p_change_tif, transform, comp_a.crs)
        change_gdf.to_file(p_change_geojson, driver="GeoJSON")
        wb_gdf.to_file(p_wb_geojson, driver="GeoJSON")
        pd.DataFrame([r.to_dict() for r in wb_records]).to_csv(p_wb_csv, index=False)

        prov_meta = {
            "place": place,
            "centroid": [geo_res.lat, geo_res.lon],
            "radius_km": radius_km,
            "bbox": geo_res.bbox.as_list(),
            "crs": comp_a.crs,
            "year_a": year_a,
            "year_b": year_b,
            "season": season_norm,
            "threshold_policy": threshold_policy,
            "period_a": {
                "window": label_a,
                "scenes_count": len(comp_a.scene_ids),
                "scene_ids": comp_a.scene_ids,
                "threshold": round(mask_a.threshold, 4),
                "method": mask_a.method,
                "water_fraction": round(mask_a.water_fraction, 4),
                "bimodality_metric": round(mask_a.bimodality_metric, 4),
            },
            "period_b": {
                "window": label_b,
                "scenes_count": len(comp_b.scene_ids),
                "scene_ids": comp_b.scene_ids,
                "threshold": round(mask_b.threshold, 4),
                "method": mask_b.method,
                "water_fraction": round(mask_b.water_fraction, 4),
                "bimodality_metric": round(mask_b.bimodality_metric, 4),
            },
            "summary_statistics": stats.to_dict(),
            "threshold_sensitivity": sensitivity.to_dict(),
            "software_version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with open(p_provenance, "w", encoding="utf-8") as f:
            json.dump(prov_meta, f, indent=2)

        # 11. Print comprehensive summary table
        delta_sign = "+" if stats.net_change_ha >= 0 else ""
        click.echo("\n====================== WATER CHANGE DETECTION SUMMARY ======================")
        click.echo(
            f" Location:                {place} (Centroid: {geo_res.lat:.4f}, {geo_res.lon:.4f})"
        )
        click.echo(
            f" Analysis Period:         {season.replace('_', ' ').title()} {year_a} vs {year_b} (Shared Window)"
        )
        click.echo(
            f" Coordinate Reference:    {comp_a.crs} (10m Resolution, Area: {stats.total_aoi_ha:,.0f} ha)"
        )
        click.echo(
            f" Threshold Policy:        {threshold_policy} (Thresh: {mask_a.threshold:.4f}, Method: {mask_a.method})"
        )
        click.echo("----------------------------------------------------------------------------")
        click.echo(" Surface Water Dynamics:")
        click.echo(
            f"   Baseline Water ({year_a}):       {stats.total_water_period_a_ha:>10,.2f} ha"
        )
        click.echo(
            f"   Comparison Water ({year_b}):     {stats.total_water_period_b_ha:>10,.2f} ha"
        )
        click.echo(
            f"   Net Water Change:            {delta_sign}{stats.net_change_ha:>9,.2f} ha ({delta_sign}{stats.percent_change:.2f}%)"
        )
        click.echo(f"   Gained Water (New):          {stats.gained_water_ha:>10,.2f} ha")
        click.echo(f"   Lost Water (Receded):        {stats.lost_water_ha:>10,.2f} ha")
        click.echo(f"   Persistent Water (Stable):   {stats.persistent_water_ha:>10,.2f} ha")
        click.echo(f"   Churn Ratio:                 {stats.churn_ratio * 100:>10.2f}%")
        click.echo(f"   Scientific Significance:     {stats.significance.upper():>10}")
        click.echo(" Headline Features (>= 1.0 ha):")
        click.echo(
            f"   Count: {stats.headline_1ha['count']} | Period A: {stats.headline_1ha['total_water_period_a_ha']:.2f} ha | Period B: {stats.headline_1ha['total_water_period_b_ha']:.2f} ha | Net: {stats.headline_1ha['net_change_ha']:+.2f} ha"
        )
        click.echo(" Threshold Sensitivity (+-0.1 MNDWI):")
        click.echo(
            f"   Range: [{sensitivity.net_change_range_ha[0]:+.2f}, {sensitivity.net_change_range_ha[1]:+.2f}] ha | Sign Flips: {sensitivity.sign_flips} | Stable: {sensitivity.is_stable}"
        )
        click.echo("----------------------------------------------------------------------------")
        click.echo(f"   Tracked Waterbodies (All):   {stats.waterbody_count:>10} features")
        click.echo(f"   Valid AOI Area Fraction:     {stats.valid_area_fraction * 100:>10.2f}%")
        click.echo("----------------------------------------------------------------------------")
        click.echo(" Exported Artifacts:")
        click.echo(f"   [CHANGE RASTER]:   {p_change_tif}")
        click.echo(f"   [VECTOR CLASSES]:  {p_change_geojson}")
        click.echo(f"   [WATERBODIES]:     {p_wb_geojson}")
        click.echo(f"   [ATTRIBUTES CSV]:  {p_wb_csv}")
        click.echo(f"   [PROVENANCE JSON]: {p_provenance}")
        click.echo("============================================================================\n")

    except SatelliteAnalystError as sae:
        click.secho(f"\nError: [{sae.code}] {sae.message}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nExecution Failed: {e}", fg="red", err=True)
        sys.exit(1)


@main.command()
@click.option("--query", required=True, help="Natural language query string.")
@click.option(
    "--planner",
    type=click.Choice(["rule", "llm", "auto"]),
    default="auto",
    help="Planner engine ('rule', 'llm', or 'auto' detection).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Emit the validated JSON execution plan only and exit.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("outputs/"),
    help="Directory to save generated outputs and scientific report.",
)
def analyze(query: str, planner: str, dry_run: bool, out: Path) -> None:
    """Execute end-to-end surface water analysis from a natural language query."""
    try:
        out.mkdir(parents=True, exist_ok=True)
        click.echo(f"==> Interpreting query: '{query}'")

        # 1. Resolve planner provider
        llm_provider: BaseLLMProvider | None = None
        if planner in ("llm", "auto"):
            if os.environ.get("GEMINI_API_KEY"):
                llm_provider = GeminiProvider()
            elif os.environ.get("OPENAI_API_KEY"):
                llm_provider = OpenAIProvider()
            elif planner == "llm":
                click.secho(
                    "Warning: --planner llm requested but no API key configured. Falling back to rule-based.",
                    fg="yellow",
                )

        if planner == "rule" or (planner == "auto" and llm_provider is None):
            plan_engine: Any = RuleBasedPlanner()
            plan = plan_engine.parse_query(query)
        else:
            plan_engine = LLMPlanner(provider=llm_provider, fallback_planner=RuleBasedPlanner())
            plan = plan_engine.parse_query(query)

        # 2. Check for clarification requirement
        if plan.needs_clarification:
            click.secho(
                f"\nClarification Required: {plan.clarification_question}\n",
                fg="yellow",
                err=True,
            )
            sys.exit(2)

        # 3. Dry-run mode: output validated plan JSON and exit
        if dry_run:
            click.echo("\n================ VALIDATED EXECUTION PLAN ================")
            click.echo(plan.model_dump_json(indent=2))
            click.echo("==========================================================\n")
            return

        click.echo(
            f"==> Generated Plan: {plan.task_type} for {plan.aoi.place} ({plan.season_policy})"
        )
        click.echo(f"    Baseline period:   {plan.time_range_a.label}")
        if plan.time_range_b:
            click.echo(f"    Comparison period: {plan.time_range_b.label}")
        if plan.assumptions:
            click.echo(f"    Assumptions applied: {len(plan.assumptions)}")
            for asm in plan.assumptions:
                click.echo(f"      - {asm}")

        # 4. Geocode target spatial bounds
        geocoder = GeocodeService()
        geo_res = geocoder.geocode(plan.aoi.place, radius_km=plan.aoi.radius_km)

        # 5. Build composites
        builder = CompositeBuilder()
        interval_a = plan.time_range_a
        label_a = interval_a.label
        click.echo(f"==> Ingesting / loading Baseline Composite ({label_a})...")
        comp_a = builder.build_composite(
            bbox=geo_res.bbox,
            time_range=interval_a,
            max_cloud_cover=40.0,
            min_valid_obs=2,
        )

        year_b = plan.period_b.year if plan.period_b else plan.period_a.year + 2
        label_b = plan.time_range_b.label if plan.time_range_b else f"Period B {year_b}"
        interval_b = (
            plan.time_range_b
            if plan.time_range_b
            else TimeInterval(
                start_date=date(year_b, 10, 1),
                end_date=date(year_b, 11, 30),
                label=label_b,
            )
        )
        click.echo(f"==> Ingesting / loading Comparison Composite ({label_b})...")
        comp_b = builder.build_composite(
            bbox=geo_res.bbox,
            time_range=interval_b,
            max_cloud_cover=40.0,
            min_valid_obs=2,
        )

        # 6. Compute spectral indices
        click.echo("==> Computing Modified Normalized Difference Water Index (MNDWI)...")
        mndwi_a = compute_mndwi(comp_a.green.values, comp_a.swir1.values)
        mndwi_b = compute_mndwi(comp_b.green.values, comp_b.swir1.values)

        # 7. Segment water masks
        click.echo("==> Segmenting surface water masks...")
        policy_lit: Literal["shared", "per_period"] = "shared"
        mask_a, mask_b = segment_dual_period_water(
            mndwi_a=mndwi_a,
            mndwi_b=mndwi_b,
            policy=policy_lit,
            min_area_ha=plan.min_area_ha,
            pixel_size_m=10.0,
        )

        # 8. Detect change raster and vectorize
        click.echo("==> Classifying 3-class surface water dynamics...")
        change_raster = detect_water_change(
            mask_a=mask_a,
            mask_b=mask_b,
            valid_count_a=comp_a.valid_count.values,
            valid_count_b=comp_b.valid_count.values,
            min_valid_obs=2,
        )

        # Derive Affine Transform from coordinate dimensions
        xs = comp_a.green["x"].values
        ys = comp_a.green["y"].values
        res_x = float(abs(xs[1] - xs[0])) if len(xs) > 1 else 10.0
        res_y = float(abs(ys[1] - ys[0])) if len(ys) > 1 else 10.0
        top_left_x = float(xs[0] - res_x / 2.0)
        top_left_y = float(ys[0] + res_y / 2.0)
        transform = Affine.translation(top_left_x, top_left_y) @ Affine.scale(res_x, -res_y)

        change_gdf = vectorize_change_classes(
            change_raster,
            transform=transform,
            crs=comp_a.crs,
            min_area_ha=plan.min_area_ha,
        )
        wb_records, wb_gdf = extract_waterbody_records(
            mask_a=mask_a.mask,
            mask_b=mask_b.mask,
            transform=transform,
            crs=comp_a.crs,
            min_area_ha=plan.min_area_ha,
            pixel_size_m=10.0,
        )

        # 9. Compute summary stats & threshold sensitivity
        stats = compute_summary_stats(
            change_raster=change_raster,
            waterbodies=wb_records,
            pixel_size_m=10.0,
        )
        valid_common = (comp_a.valid_count.values >= 2) & (comp_b.valid_count.values >= 2)
        sensitivity = compute_threshold_sensitivity(
            mndwi_a=mndwi_a,
            mndwi_b=mndwi_b,
            valid_mask=valid_common,
            mid_threshold=float(mask_a.threshold),
            offset=0.1,
            pixel_size_m=10.0,
        )

        # 10. Export geospatial artifacts
        slug = f"{plan.aoi.place.lower().replace(' ', '_')}_{plan.period_a.year}_{year_b}_{plan.season_policy}"
        p_change_tif = out / f"{slug}_change_classes.tif"
        p_change_geojson = out / f"{slug}_change_vectors.geojson"
        p_wb_geojson = out / f"{slug}_waterbodies.geojson"
        p_wb_csv = out / f"{slug}_waterbodies.csv"
        p_provenance = out / f"{slug}_provenance.json"
        p_report_md = out / f"{slug}_report.md"
        p_report_html = out / f"{slug}_report.html"

        save_change_raster_to_geotiff(change_raster, p_change_tif, transform, comp_a.crs)
        change_gdf.to_file(p_change_geojson, driver="GeoJSON")
        wb_gdf.to_file(p_wb_geojson, driver="GeoJSON")
        pd.DataFrame([r.to_dict() for r in wb_records]).to_csv(p_wb_csv, index=False)

        prov_meta = {
            "query": query,
            "place": plan.aoi.place,
            "centroid": [geo_res.lat, geo_res.lon],
            "radius_km": plan.aoi.radius_km,
            "bbox": geo_res.bbox.as_list(),
            "crs": comp_a.crs,
            "year_a": plan.period_a.year,
            "year_b": year_b,
            "season": plan.season_policy,
            "threshold_policy": plan.season_policy,
            "period_a": {
                "window": label_a,
                "scenes_count": len(comp_a.scene_ids),
                "threshold": round(mask_a.threshold, 4),
                "method": mask_a.method,
                "water_fraction": round(mask_a.water_fraction, 4),
                "bimodality_metric": round(mask_a.bimodality_metric, 4),
            },
            "period_b": {
                "window": label_b,
                "scenes_count": len(comp_b.scene_ids),
                "threshold": round(mask_b.threshold, 4),
                "method": mask_b.method,
                "water_fraction": round(mask_b.water_fraction, 4),
                "bimodality_metric": round(mask_b.bimodality_metric, 4),
            },
            "summary_statistics": stats.to_dict(),
            "threshold_sensitivity": sensitivity.to_dict(),
            "software_version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with open(p_provenance, "w", encoding="utf-8") as f:
            json.dump(prov_meta, f, indent=2)

        # 11. Generate grounded scientific report
        click.echo("==> Synthesizing grounded report...")
        report_gen = ReportGenerator()
        narrative, md_report, html_report = report_gen.generate_report_bundle(
            plan=plan,
            stats=stats.to_dict(),
            provenance=prov_meta,
            provider=llm_provider,
            user_query=query,
        )
        p_report_md.write_text(md_report, encoding="utf-8")
        p_report_html.write_text(html_report, encoding="utf-8")

        # 12. Print terminal summary
        delta_sign = "+" if stats.net_change_ha >= 0 else ""
        click.echo("\n====================== SATELLITE ANALYST REPORT ======================")
        click.echo(f" Target Location:        {plan.aoi.place} (Radius: {plan.aoi.radius_km} km)")
        click.echo(f" Analysis Period:        {label_a} vs {label_b}")
        click.echo(
            f" Scientific Assessment:  {stats.significance.upper()} (Churn: {stats.churn_ratio * 100:.2f}%)"
        )
        click.echo("----------------------------------------------------------------------")
        click.echo(f" Baseline Water:         {stats.total_water_period_a_ha:>10,.2f} ha")
        click.echo(f" Comparison Water:       {stats.total_water_period_b_ha:>10,.2f} ha")
        click.echo(
            f" Net Change:         {delta_sign}{stats.net_change_ha:>9,.2f} ha ({delta_sign}{stats.percent_change:.2f}%)"
        )
        click.echo(f" Gained Surface Water:   {stats.gained_water_ha:>10,.2f} ha")
        click.echo(f" Lost Surface Water:     {stats.lost_water_ha:>10,.2f} ha")
        click.echo(f" Persistent Water:       {stats.persistent_water_ha:>10,.2f} ha")
        click.echo(
            f" Headline Bodies (>=1ha): {stats.headline_1ha['count']} bodies (Net: {stats.headline_1ha['net_change_ha']:+.2f} ha)"
        )
        click.echo(
            f" Sensitivity Range:      [{sensitivity.net_change_range_ha[0]:+.2f}, {sensitivity.net_change_range_ha[1]:+.2f}] ha (Sign flips: {sensitivity.sign_flips})"
        )
        click.echo("----------------------------------------------------------------------")
        click.echo(f" Generated Narrative:\n {narrative}")
        click.echo("----------------------------------------------------------------------")
        click.echo(" Exported Artifacts:")
        click.echo(f"   [MARKDOWN REPORT]:  {p_report_md}")
        click.echo(f"   [HTML REPORT]:      {p_report_html}")
        click.echo(f"   [PROVENANCE JSON]:  {p_provenance}")
        click.echo(f"   [VECTOR CLASSES]:   {p_change_geojson}")
        click.echo(f"   [WATERBODIES]:      {p_wb_geojson}")
        click.echo(f"   [CHANGE RASTER]:    {p_change_tif}")
        click.echo("======================================================================\n")

    except SatelliteAnalystError as sae:
        click.secho(f"\nError: [{sae.code}] {sae.message}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nExecution Failed: {e}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
