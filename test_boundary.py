from qa_engine.boundary_analyzer import generate_boundary_values


if __name__ == "__main__":
    for boundary in generate_boundary_values(8, 20):
        print("Value:", boundary["value"])
        print("Boundary:", boundary["boundary_type"])
        print("Expected Valid:", boundary["expected_valid"])
        print("-" * 40)
