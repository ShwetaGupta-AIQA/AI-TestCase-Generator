"""Boundary analysis for inclusive integer ranges, using a step of one."""


def generate_boundary_values(minimum, maximum):
    if type(minimum) is not int or type(maximum) is not int:
        raise ValueError("Boundary analysis requires two integer limits.")
    if minimum > maximum:
        raise ValueError("Minimum must not exceed maximum.")
    candidates = [
        (minimum - 1, "below_minimum"),
        (minimum, "minimum"),
        (minimum + 1, "above_minimum"),
        (maximum - 1, "below_maximum"),
        (maximum, "maximum"),
        (maximum + 1, "above_maximum"),
    ]
    return [
        {"value": value, "boundary_type": label,
         "expected_valid": minimum <= value <= maximum}
        for value, label in candidates
    ]
