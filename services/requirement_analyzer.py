from services.json_response import request_json_object

from models.requirement import RequirementAnalysis
from prompts.requirement_prompt import (
    create_requirement_analysis_prompt
)
from services.llm_service import call_llm
from services.generation_errors import validate_model
from services import demo_limits


def analyze_requirement(requirement):
    if not requirement or not requirement.strip():
        raise ValueError("Requirement must not be empty.")
    if demo_limits.active() and len(requirement) > demo_limits.MAX_TEXT_CHARS:
        raise demo_limits.DemoLimitError("Each demo requirement must be at most 12,000 characters.")

    prompt = create_requirement_analysis_prompt(
        requirement
    )

    data = request_json_object(call_llm, prompt, "Requirement analysis")

    validated_analysis = (
        validate_model(RequirementAnalysis, data, "Requirement analysis")
    )

    return validated_analysis
