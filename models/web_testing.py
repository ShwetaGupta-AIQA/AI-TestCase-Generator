from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WebPageElement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    locator_strategy: Literal["role", "label", "placeholder", "text"] = "role"


class WebPageSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str
    title: str = ""
    description: str = ""
    headings: list[str] = Field(default_factory=list, max_length=30)
    elements: list[WebPageElement] = Field(default_factory=list, max_length=50)


class WebUITestGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=1, max_length=2048)
    user_goal: str = Field(min_length=5, max_length=1000)
    inspection_mode: Literal["static", "rendered"] = "static"

    @model_validator(mode="after")
    def public_https_url_shape(self):
        parsed = urlparse(self.url)
        try:
            valid_port = parsed.port in (None, 443)
        except ValueError:
            valid_port = False
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or not valid_port):
            raise ValueError("Use a public HTTPS page URL on port 443 without credentials.")
        return self


class WebLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    strategy: Literal["role", "label", "placeholder", "text"]
    value: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=30)

    @model_validator(mode="after")
    def role_locator_has_role(self):
        if self.strategy == "role" and not self.role:
            raise ValueError("Role locators must include a role.")
        if self.strategy != "role" and self.role:
            raise ValueError("Only role locators may specify a role.")
        return self


class WebUIAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["click", "fill", "check", "uncheck", "select_option"]
    locator: WebLocator
    value: str = Field(default="", max_length=300)


class WebUIAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["visible", "hidden", "contains_text", "url_contains"]
    value: str = Field(min_length=1, max_length=300)
    locator: WebLocator | None = None

    @model_validator(mode="after")
    def locator_matches_assertion(self):
        if self.kind == "url_contains" and self.locator is not None:
            raise ValueError("URL assertions do not use an element locator.")
        if self.kind != "url_contains" and self.locator is None:
            raise ValueError("Element assertions require a locator.")
        return self


class WebUITestCase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    test_case_id: str = ""
    title: str = Field(min_length=5, max_length=160)
    test_type: Literal["Functional", "Negative", "Navigation", "Form Validation"] = "Functional"
    priority: Literal["High", "Medium", "Low"] = "Medium"
    objective: str = Field(min_length=5, max_length=400)
    preconditions: list[str] = Field(default_factory=list, max_length=5)
    actions: list[WebUIAction] = Field(default_factory=list, max_length=10)
    assertions: list[WebUIAssertion] = Field(min_length=1, max_length=5)


class WebUITestDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_cases: list[WebUITestCase] = Field(min_length=1, max_length=8)


class WebUITestPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str
    page_title: str = ""
    user_goal: str
    snapshot: WebPageSnapshot
    test_cases: list[WebUITestCase] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def snapshot_matches_plan(self):
        parsed = urlparse(self.url)
        try:
            valid_port = parsed.port in (None, 443)
        except ValueError:
            valid_port = False
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or not valid_port or self.snapshot.url != self.url):
            raise ValueError("Plan URL must be a public HTTPS URL matching its inspected page.")
        return self