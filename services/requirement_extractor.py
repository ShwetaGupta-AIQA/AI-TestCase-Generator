from models.document_requirement import RequirementExtractionResponse
from prompts.requirement_extraction_prompt import create_requirement_extraction_prompt
from services.json_response import request_json_object
from services.llm_service import call_llm
from services.generation_errors import validate_model


def extract_requirements(document_text):
    if not document_text or not document_text.strip():
        raise ValueError("Document text must not be empty.")
    data = request_json_object(call_llm, create_requirement_extraction_prompt(document_text),
                               "Requirement extraction")
    return validate_model(RequirementExtractionResponse, data, "Requirement extraction")
