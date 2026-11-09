from pathlib import Path
import yaml

# Change 'prompts.py' -> 'prompts.yaml'
PROMPTS_FILE = Path(__file__).parent / "prompts.yaml"


def load_prompt(template_key: str, sub_key: str = "system") -> str:
    """Loads a prompt template from prompts.yaml."""
    with open(PROMPTS_FILE, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return data[template_key][sub_key]