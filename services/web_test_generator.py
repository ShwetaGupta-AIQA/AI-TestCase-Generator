import re

from pydantic import ValidationError

from models.web_testing import WebPageSnapshot, WebUITestDraftResponse, WebUITestPlan
from prompts.web_test_prompt import create_web_test_prompt
from services.generation_errors import validate_model
from services.json_response import parse_json_object
from services.llm_service import call_llm


class _DraftValidationError(ValueError):
    pass


def _normalize_nested_actions(data):
    """Repair model output that nests an entire action object under `action`."""
    if not isinstance(data, dict) or not isinstance(data.get("test_cases"), list):
        return data
    normalized = dict(data)
    cases = []
    for case in normalized["test_cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("actions"), list):
            cases.append(case)
            continue
        updated_case = dict(case)
        actions = []
        for item in case["actions"]:
            if (isinstance(item, dict) and isinstance(item.get("action"), dict)
                    and "locator" not in item):
                nested = item["action"]
                if isinstance(nested.get("action"), str) and isinstance(nested.get("locator"), dict):
                    repaired = dict(nested)
                    if "value" in item and "value" not in repaired:
                        repaired["value"] = item["value"]
                    actions.append(repaired)
                    continue
            actions.append(item)
        updated_case["actions"] = actions
        cases.append(updated_case)
    normalized["test_cases"] = cases
    return normalized


def _validation_feedback(error):
    if isinstance(error, ValidationError):
        return "; ".join(
            ".".join(str(part) for part in issue["loc"]) + ": " + issue["type"]
            for issue in error.errors(include_input=False, include_context=False, include_url=False)[:5]
        )
    return str(error)[:500]


def _locator_key(locator):
    return locator.strategy, locator.role, locator.value


def _observed_locators(snapshot: WebPageSnapshot):
    observed = {("role", element.role, element.name) for element in snapshot.elements}
    observed.update((element.locator_strategy, "", element.name)
                    for element in snapshot.elements if element.locator_strategy != "role")
    observed.update(("text", "", heading) for heading in snapshot.headings)
    return observed


def _validate_observed_locators(cases, snapshot):
    observed = _observed_locators(snapshot)

    def observed_role(locator):
        if locator.strategy == "role":
            return locator.role
        return next((element.role for element in snapshot.elements
                     if element.locator_strategy == locator.strategy and element.name == locator.value), "")

    for case in cases:
        for action in case.actions:
            if _locator_key(action.locator) not in observed:
                raise _DraftValidationError("Generated test used a control that was not found on the inspected page. Regenerate or review the page summary.")
            role = observed_role(action.locator)
            valid_action_roles = {
                "click": {"button", "link", "checkbox", "radio", "tab", "menuitem"},
                "fill": {"textbox", "searchbox", "spinbutton"},
                "check": {"checkbox", "radio"},
                "uncheck": {"checkbox", "radio"},
                "select_option": {"combobox"},
            }
            if action.action not in valid_action_roles or role not in valid_action_roles[action.action]:
                allowed = ", ".join(sorted(name for name, roles in valid_action_roles.items() if role in roles)) or "no actions"
                raise _DraftValidationError(
                    f"Generated action '{action.action}' does not fit the observed '{role}' control "
                    f"'{action.locator.value}'. Use one of: {allowed}."
                )
        for assertion in case.assertions:
            if assertion.locator and _locator_key(assertion.locator) not in observed:
                raise _DraftValidationError("Generated assertion used a locator that was not found on the inspected page.")


def generate_web_ui_tests(snapshot: WebPageSnapshot, user_goal: str) -> WebUITestPlan:
    """Draft Playwright-oriented cases and accept only observed, supported locators."""
    if not user_goal or len(user_goal.strip()) < 5:
        raise ValueError("Describe the browser user goal in at least five characters.")
    prompt = create_web_test_prompt(snapshot, user_goal.strip()[:1000])
    for attempt in range(2):
        response = call_llm(prompt)
        try:
            data = _normalize_nested_actions(parse_json_object(response))
            draft = validate_model(WebUITestDraftResponse, data, "Web UI test generation")
            _validate_observed_locators(draft.test_cases, snapshot)
            break
        except (ValueError, ValidationError) as exc:
            feedback = _validation_feedback(exc)
            if attempt == 1:
                raise ValueError(f"Could not produce a valid browser test draft after one correction: {feedback}") from exc
            prompt += (
                "\nCORRECTION REQUIRED: Your previous test draft did not match the required schema or page controls. "
                f"Validation feedback: {feedback} Return a corrected complete JSON object. "
                "Action-role rules: click only button/link/tab/menuitem/checkbox/radio; "
                "fill only textbox/searchbox/spinbutton; check and uncheck only checkbox/radio; "
                "select_option only combobox. Use the exact observed locator and role."
            )

    unique_cases = []
    titles = set()
    for case in draft.test_cases:
        normalized_title = re.sub(r"\s+", " ", case.title.casefold()).strip()
        if normalized_title in titles:
            continue
        titles.add(normalized_title)
        case.test_case_id = f"WEB-TC-{len(unique_cases) + 1:03d}"
        unique_cases.append(case)
    if not unique_cases:
        raise ValueError("No unique web UI tests were generated. Try a more specific goal.")
    return WebUITestPlan(url=snapshot.url, page_title=snapshot.title,
                         user_goal=user_goal.strip()[:1000], snapshot=snapshot,
                         test_cases=unique_cases)