from utils.id_generator import IDGenerator


if __name__ == "__main__":
    generator = IDGenerator()
    print(generator.next_requirement_id())
    for _ in range(3):
        print(generator.next_scenario_id())
    for _ in range(4):
        print(generator.next_test_case_id())
