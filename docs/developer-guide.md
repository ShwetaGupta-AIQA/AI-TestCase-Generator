# Developer and legacy workflow reference

React is the primary interface. For first-time setup, use the [README](../README.md).

## Command-line workflows

```powershell
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe app.py --requirement "Password must contain 8 to 20 characters" --output output/result.json
.\.venv\Scripts\python.exe app.py --document sample_documents/login_brd.txt --output output/brd.json
.\.venv\Scripts\python.exe document_pipeline.py --document sample_documents/login_brd.txt --output output/TestGen_Output.xlsx
```

`app.py --file` reads a UTF-8 file as one requirement. `app.py --document` extracts
requirements and processes only the first. `document_pipeline.py` processes the
first two with shared IDs and exports Excel. Default Excel filename is
`TestGen_Output.xlsx`. Existing output files are overwritten; close them in Excel
before exporting again. Rejected cases are excluded from Excel and retained in
pipeline reports. CLI QA failures return exit code 1 after reporting results.

## Testing and evaluation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe test_evaluator.py
.\.venv\Scripts\python.exe run_evaluation.py --output output/evaluation.json
```

Regression tests use mocked AI responses and exercise actual document readers,
Excel creation/reopening, API requests and Streamlit interactions. The duplicate
demo is offline. The golden runner makes live model requests for three versioned
examples: password length, login with no limits, and a maximum-only upload size.
It records expected/actual constraints, model, timestamp, failures and scores.
Live accuracy has not been measured as part of packaging.

Suite metrics include accepted and rejected schema-valid cases. Completeness checks
nonblank titles, steps and expected results; traceability checks Python-assigned
scenario/requirement mappings; duplicates are exact normalized titles. Golden
boundary-extraction accuracy checks extracted limits, not boundary coverage in tests.
Three passing examples would mean 3/3 on dataset v1, not general AI accuracy.


## Legacy Streamlit interface

After installing backend dependencies, run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py
```

Open http://localhost:8501. This interface is optional; it is not the React app.
