def create_scenario_prompt(requirement_analysis):

    prompt = f"""
You are a Senior QA Engineer.

Generate high-level test scenarios using ONLY the
following analyzed requirement.

REQUIREMENT ID:
{requirement_analysis.requirement_id}

ACTOR:
{requirement_analysis.actor}

FUNCTIONALITY:
{requirement_analysis.functionality}

BUSINESS RULES:
{requirement_analysis.business_rules}

CONSTRAINTS:
{requirement_analysis.constraints}

MISSING INFORMATION:
{requirement_analysis.missing_information}

Generate scenarios in these categories where applicable:

- Functional
- Negative
- Boundary

Return ONLY valid JSON using this structure:

{{
    "scenarios": [
        {{
            "scenario_id": "SC001",
            "requirement_id": "{requirement_analysis.requirement_id}",
            "title": "Scenario title",
            "scenario_type": "Functional",
            "description": "What should be tested"
        }}
    ]
}}

RULES:

1. Use only information supported by the requirement.
2. Do not convert missing information into business rules.
3. Do not invent credentials, limits, error messages,
   security rules or workflows.
4. Every scenario must reference:
   {requirement_analysis.requirement_id}
5. Generate boundary scenarios only when an explicit
   boundary or constraint exists.
6. Return JSON only.
7. Do not return Markdown.
"""

    return prompt