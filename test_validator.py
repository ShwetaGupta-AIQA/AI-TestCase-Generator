from models.test_case import TestCase
from qa_engine.test_case_validator import validate_test_case


if __name__ == "__main__":
    bad_case = TestCase(
        test_case_id="TC999", requirement_id="REQ999", scenario_id="SC999",
        title="", test_type="Functional", priority="High", preconditions=[],
        steps=[], test_data={}, expected_result="",
    )
    print(validate_test_case(bad_case, "REQ001", "SC001"))
