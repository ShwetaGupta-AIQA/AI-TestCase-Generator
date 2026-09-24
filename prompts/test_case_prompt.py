def create_test_case_prompt(
    requirement_analysis,
    scenario
):

    prompt = f"""
You are a Senior QA Engineer.

Generate detailed test cases for the following
test scenario.

REQUIREMENT ID:
{requirement_analysis.requirement_id}

BUSINESS RULES:
{requirement_analysis.business_rules}

CONSTRAINTS:
{requirement_analysis.constraints}

FUNCTIONALITY:
{requirement_analysis.functionality}

MISSING INFORMATION (unconfirmed):
{requirement_analysis.missing_information}

SCENARIO ID:
{scenario.scenario_id}

SCENARIO TYPE:
{scenario.scenario_type}

SCENARIO:
{scenario.title}

DESCRIPTION:
{scenario.description}

Return ONLY valid JSON:

{{
    "test_cases": [
        {{
            "test_case_id": "TC001",
            "requirement_id":
                "{requirement_analysis.requirement_id}",
            "scenario_id":
                "{scenario.scenario_id}",
            "title": "Test case title",
            "test_type": "{scenario.scenario_type}",
            "priority": "High",
            "preconditions": [],
            "steps": ["Concrete action to perform"],
            "test_data": {{}},
            "expected_result": "Observable result supported by the requirement"
        }}
    ]
}}

RULES:

1. Generate test cases only for the supplied scenario.

2. Do not invent unsupported business rules.

3. Every test case must reference requirement:
   {requirement_analysis.requirement_id}

4. Every test case must reference scenario:
   {scenario.scenario_id}

5. Test steps must be clear and executable.

6. Expected results must be derived from the provided
   requirement and scenario.

7. Return JSON only.

8. Do not return Markdown.

9. Use unique test_case_id values within this response.
10. Generate at least one case, with nonempty steps and expected_result.
11. test_data values must be strings; use an empty object if no data is needed.
12. priority must be High, Medium or Low. Match test_type to the scenario type.
13. Do not treat missing information as confirmed requirements.
"""

    return prompt
