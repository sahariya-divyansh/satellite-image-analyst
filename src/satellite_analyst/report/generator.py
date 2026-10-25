"""Report generator synthesizing verified Markdown and HTML documents."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2

from satellite_analyst import __version__
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.llm_base import BaseLLMProvider
from satellite_analyst.planner.rule_based import RuleBasedPlanner
from satellite_analyst.planner.schema import AnalysisPlan, QueryPlan
from satellite_analyst.report.grounding import GroundingVerifier

logger = get_logger(__name__)


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
        self.rule_based_planner = RuleBasedPlanner()

    async def generate_narrative_with_grounding(
        self,
        plan: AnalysisPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        provider: BaseLLMProvider | None = None,
    ) -> str:
        """Produce a grounded narrative summary via LLM or deterministic template fallback.

        If provider is provided:
        1. Calls provider to generate narrative strictly from facts.
        2. Verifies narrative through GroundingVerifier.
        3. On violation: retries once with feedback.
        4. If retry fails: logs and falls back to deterministic template.
        """
        # Default deterministic template narrative
        default_narrative = await self.rule_based_planner.generate_narrative(
            plan=plan,
            stats=stats,
            _provenance=provenance,
        )

        if provider is None:
            return default_narrative

        # Attempt 1: Call LLM provider
        try:
            narrative = await provider.generate_narrative(
                plan=plan,
                stats=stats,
                provenance=provenance,
            )
            ungrounded = self.grounding_verifier.verify(
                narrative=narrative,
                stats=stats,
                provenance=provenance,
                strict=False,
            )
            if not ungrounded:
                return narrative

            logger.warning(
                "LLM narrative failed grounding verification (ungrounded: %s). Retrying once with error feedback...",
                ungrounded,
            )

            # Attempt 2: Retry with feedback
            retry_prompt = (
                f"Your previous narrative contained ungrounded numbers: {ungrounded}.\n"
                f"Facts JSON:\n{stats}\n{provenance}\n"
                "Please output a summary where EVERY number matches the facts exactly."
            )
            retry_narrative = await provider.generate_chat_completion(
                system_prompt="You are a strictly grounded scientific assistant. Every single number you output MUST match the facts provided.",
                user_prompt=retry_prompt,
            )
            ungrounded_2 = self.grounding_verifier.verify(
                narrative=retry_narrative,
                stats=stats,
                provenance=provenance,
                strict=False,
            )
            if not ungrounded_2:
                return retry_narrative

            logger.warning(
                "LLM narrative retry failed grounding (ungrounded: %s). Falling back to deterministic template.",
                ungrounded_2,
            )
            return default_narrative

        except Exception as e:
            logger.warning(
                "LLM narrative generation failed (%s). Falling back to deterministic template.",
                e,
            )
            return default_narrative

    def generate_markdown(
        self,
        plan: AnalysisPlan | QueryPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        narrative: str,
        user_query: str | None = None,
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
            user_query=user_query,
            software_version=__version__,
            execution_time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def generate_html(
        self,
        plan: AnalysisPlan | QueryPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        narrative: str,
        user_query: str | None = None,
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
            user_query=user_query,
            software_version=__version__,
            execution_time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def generate_report_bundle(
        self,
        plan: AnalysisPlan | QueryPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        provider: BaseLLMProvider | None = None,
        user_query: str | None = None,
    ) -> tuple[str, str, str]:
        """Generate narrative, Markdown report, and HTML report synchronously."""
        narrative = asyncio.run(
            self.generate_narrative_with_grounding(
                plan=plan,
                stats=stats,
                provenance=provenance,
                provider=provider,
            )
        )
        md_content = self.generate_markdown(
            plan=plan,
            stats=stats,
            provenance=provenance,
            narrative=narrative,
            user_query=user_query,
            verify_grounding=False,
        )
        html_content = self.generate_html(
            plan=plan,
            stats=stats,
            provenance=provenance,
            narrative=narrative,
            user_query=user_query,
            verify_grounding=False,
        )
        return narrative, md_content, html_content
