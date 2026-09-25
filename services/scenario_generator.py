from services.json_response import request_json_object

from models.test_scenario import TestScenarioResponse
from prompts.scenario_prompt import create_scenario_prompt
from services.llm_service import call_llm
from services.generation_errors import validate_model
from services import demo_limits


def generate_scenarios(requirement_analysis):

    prompt = create_scenario_prompt(
        requirement_analysis
    )
    if demo_limits.active():
        prompt += "\nDemo limit: return at most three scenarios, covering Functional, Negative and Boundary where supported by the requirement."

    data = request_json_object(call_llm, prompt, "Scenario generation")

    validated_scenarios = (
        validate_model(TestScenarioResponse, data, "Scenario generation")
    )

    if demo_limits.active() and len(validated_scenarios.scenarios) > demo_limits.MAX_SCENARIOS:
        raise demo_limits.DemoLimitError("AI returned too many scenarios for the demo. Try a simpler requirement.")
    return validated_scenarios
