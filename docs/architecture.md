# AI Test Case Generator — System Architecture

![System Architecture](images/architecture.png)

## 1. Architecture Overview

User
 ↓
Streamlit UI
 ↓
FastAPI
 ↓
Document / Requirement Processing
 ↓
LLM Requirement Analyzer
 ↓
Test Scenario Generator
 ↓
Deterministic QA Engine
 ↓
Validation / BVA
 ↓
Results & Excel Export


## 2. Components

### Streamlit UI
Purpose...

### FastAPI Backend
Purpose...

### LLM Service
Purpose...

### QA Engine
Purpose...

### Run Persistence
Purpose...


## 3. LLM vs Deterministic Logic

LLM:
- Requirement understanding
- Scenario generation
- Test generation

Python:
- Boundary value analysis
- Validation
- IDs
- Metrics
- Export


## 4. Data Flow

Requirement
    ↓
Requirement Analysis
    ↓
Test Scenario Generation
    ↓
Test Case Generation
    ↓
QA Validation
    ↓
Export


## 5. Technology Stack

Python
FastAPI
Streamlit
OpenRouter
Pydantic
Pytest
Docker

