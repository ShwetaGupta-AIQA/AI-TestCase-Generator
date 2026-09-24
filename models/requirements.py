{
    "requirement_id": "REQ001",

    "actor": "Registered user",

    "functionality": "Create password",

    "business_rules": [
        "Password must contain between 8 and 20 characters"
    ],

    "constraints": [
        "Minimum password length is 8",
        "Maximum password length is 20"
    ],

    "boundary_constraints": [
        {"field": "password_length", "minimum": 8, "maximum": 20, "unit": "characters"}
    ],

    "missing_information": [
        "Allowed character types are not specified"
    ],

    "assumptions": [],

    "clarification_questions": [
        "Are uppercase letters required?",
        "Are special characters required?"
    ]
}
