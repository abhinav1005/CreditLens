"""Load versioned prompt assets and compute their content hash.

A "prompt bundle" is the system prompt template plus the tool definitions sent to the model.
Its `content_hash` changes whenever any byte of what the model sees changes, so it's used in
eval cache keys alongside the human-readable version label.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from credit.tools.contracts import TOOL_CONTRACTS

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROFILE_PLACEHOLDER = "{{profile_id}}"


@dataclass(frozen=True)
class PromptBundle:
    system_version: str
    tools_version: str
    system_template: str
    tools: list[dict]  # [{name, description, input_schema}]

    @property
    def version(self) -> str:
        return f"system:{self.system_version}+tools:{self.tools_version}"

    @property
    def content_hash(self) -> str:
        payload = json.dumps({"system": self.system_template, "tools": self.tools}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def render_system(self, profile_id: str) -> str:
        return self.system_template.replace(PROFILE_PLACEHOLDER, profile_id)


def load_tools(version: str = "v1") -> list[dict]:
    spec = yaml.safe_load((PROMPTS_DIR / "tools" / f"{version}.yaml").read_text())
    if spec["tools"].keys() != TOOL_CONTRACTS.keys():
        raise ValueError(f"tools/{version}.yaml must describe exactly: {sorted(TOOL_CONTRACTS)}")
    return [
        {
            "name": name,
            "description": spec["tools"][name]["description"],
            "input_schema": TOOL_CONTRACTS[name][0].model_json_schema(),
        }
        for name in TOOL_CONTRACTS
    ]


def load_bundle(system_version: str = "v1", tools_version: str = "v1") -> PromptBundle:
    template = (PROMPTS_DIR / "system" / f"{system_version}.md").read_text()
    if PROFILE_PLACEHOLDER not in template:
        raise ValueError(f"system/{system_version}.md must contain {PROFILE_PLACEHOLDER}")
    return PromptBundle(system_version, tools_version, template, load_tools(tools_version))
