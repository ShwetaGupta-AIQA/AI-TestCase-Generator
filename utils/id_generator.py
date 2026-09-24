"""Deterministic identifiers scoped to one generator instance."""


class IDGenerator:
    def __init__(self):
        self.requirement_counter = 0
        self.scenario_counter = 0
        self.test_case_counter = 0

    def next_requirement_id(self):
        self.requirement_counter += 1
        return f"REQ{self.requirement_counter:03d}"

    def next_scenario_id(self):
        self.scenario_counter += 1
        return f"SC{self.scenario_counter:03d}"

    def next_test_case_id(self):
        self.test_case_counter += 1
        return f"TC{self.test_case_counter:03d}"
