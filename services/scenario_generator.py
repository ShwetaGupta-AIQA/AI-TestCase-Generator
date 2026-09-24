from services.json_response import request_json_object

from models.test_scenario import TestScenarioResponse
from prompts.scenario_prompt import create_scenario_prompt
from services.llm_service import call_llm
from services.generation_errors import validate_model


def generate_scenarios(requirement_analysis):

    prompt = create_scenario_prompt(
        requirement_analysis
    )

    data = request_json_object(call_llm, prompt, "Scenario generation")

    validated_scenarios = (
        validate_model(TestScenarioResponse, data, "Scenario generation")
    )

    return validated_scenarios
