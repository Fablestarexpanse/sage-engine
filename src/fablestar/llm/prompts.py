"""PromptManager — renders Jinja2 prompt templates from the prompts/ directory."""

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Manages Jinja2 prompt templates.
    Supports hot-reloading by re-initializing the environment.
    """

    def __init__(self, prompt_dir: str = "prompts"):
        self.prompt_dir = Path(prompt_dir)
        self._env = Environment(
            loader=FileSystemLoader(str(self.prompt_dir)), autoescape=select_autoescape()
        )

    def render(self, template_name: str, **kwargs) -> str:
        """Render a specific prompt template."""
        try:
            template = self._env.get_template(f"{template_name}.j2")
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"Error rendering prompt {template_name}: {e}")
            return f"Error: Could not render prompt {template_name}"

    def reload(self):
        """Clear the Jinja2 cache to pick up file changes."""
        # Jinja2 FileSystemLoader generally picks up changes,
        # but we can force it by clearing the internal cache if needed.
        self._env.cache.clear()
        logger.info("Prompt template cache cleared.")
