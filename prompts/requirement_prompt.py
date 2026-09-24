def create_requirement_analysis_prompt(requirement):

    prompt = f"""
You are a Senior QA Requirement Analyst.

Analyze ONLY the information explicitly present
in the following requirement.

REQUIREMENT:

{requirement}

Return ONLY valid JSON using exactly this structure:

{{
    "requirement_id": "REQ001",
    "actor": "",
    "functionality": "",
    "business_rules": [],
    "constraints": [],
    "boundary_constraints": [],
    "missing_information": [],
    "assumptions": [],
    "clarification_questions": []
}}

IMPORTANT RULES:

1. Do not invent business requirements.

2. business_rules must contain only rules explicitly
   supported by the provided requirement.

3. constraints must contain only explicit restrictions,
   limits or conditions from the requirement.

4. If information necessary for testing is not provided,
   add it to missing_information.

5. Do not silently convert missing information into
   an assumption.

6. If you make an assumption, clearly put it in assumptions.

7. Generate clarification questions for important
   missing information.

8. Do not return Markdown.

9. Do not use ```json.

10. Return JSON only.

11. Extract explicit inclusive integer limits into boundary_constraints as
    objects with field, minimum, maximum and unit. For example, a password
    length between 8 and 20 characters becomes:
    {{"field": "password_length", "minimum": 8, "maximum": 20, "unit": "characters"}}.
12. Never invent minimum or maximum values.
13. If no supported numeric boundary exists, return an empty boundary_constraints list.
14. Use null when only one side of the boundary is known; a maximum does not
    imply a minimum of zero.
15. This version supports inclusive integer limits only. Keep fractional,
    exclusive or ambiguous limits in constraints and flag any clarification
    needed; do not round them or silently change their meaning.
"""

    return prompt
