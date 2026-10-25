"""Report generator synthesizing verified Markdown and HTML documents."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2

from satellite_analyst import __version__
from satellite_analyst.planner.schema import AnalysisPlan
from satellite_analyst.report.grounding import GroundingVerifier


class ReportGenerator:
    """Generates scientifically grounded Markdown and HTML reports."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(templates_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        self.grounding_verifier = GroundingVerifier()

    def generate_markdown(
        self,
        plan: AnalysisPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        narrative: str,
        verify_grounding: bool = True,
    ) -> str:
        """Render Markdown report with optional grounding verification."""
        if verify_grounding:
            self.grounding_verifier.verify(narrative, stats, provenance, strict=True)

        template = self.env.get_template("report.md.j2")
        return template.render(
            plan=plan,
            stats=stats,
            provenance=provenance,
            narrative=narrative,
            software_version=__version__,
            execution_time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def generate_html(
        self,
        plan: AnalysisPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        narrative: str,
        verify_grounding: bool = True,
    ) -> str:
        """Render HTML report with optional grounding verification."""
        if verify_grounding:
            self.grounding_verifier.verify(narrative, stats, provenance, strict=True)

        template = self.env.get_template("report.html.j2")
        return template.render(
            plan=plan,
            stats=stats,
            provenance=provenance,
            narrative=narrative,
            software_version=__version__,
            execution_time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
