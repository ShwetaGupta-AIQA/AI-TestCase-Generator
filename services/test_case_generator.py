from services.json_response import request_json_object

from models.test_case import TestCaseResponse
from prompts.test_case_prompt import create_test_case_prompt
from services.llm_service import call_llm
from services.generation_errors import validate_model


def generate_test_cases(
    requirement_analysis,
    scenario
):
    if scenario.requirement_id != requirement_analysis.requirement_id:
        raise ValueError("Scenario references a different requirement.")

    prompt = create_test_case_prompt(
        requirement_analysis,
        scenario
    )

    data = request_json_object(call_llm, prompt, f"Test case generation ({scenario.scenario_id})")

    validated_test_cases = (
        validate_model(TestCaseResponse, data, f"Test case generation ({scenario.scenario_id})")
    )

    return validated_test_cases
