from models.test_case import TestCase
from evaluation.evaluator import evaluate_test_suite


if __name__ == "__main__":
    cases = [TestCase(test_case_id=f"TC{i:03d}", requirement_id="REQ001",
                     scenario_id=f"SC{i:03d}", title="Verify valid password",
                     test_type="Functional", priority="High", preconditions=[],
                     steps=["Enter an 8-character password"], test_data={"password": "abcdefgh"},
                     expected_result="Password length is accepted") for i in (1, 2)]
    print(evaluate_test_suite(cases).model_dump_json(indent=2))
