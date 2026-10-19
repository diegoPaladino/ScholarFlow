# ScholarFlow

AI-powered academic records extraction, validation, and browser automation.

ScholarFlow is a Windows desktop application for processing school records. It combines a Tkinter interface, document reading through the OpenAI API, structured JSON extraction, record normalization, and Playwright automation for a school management system.

## Capabilities

- Extract academic and civil document information with AI.
- Normalize academic records and compare them with local student registers.
- Assist with entering academic records through browser automation.
- Cache document processing locally.

The current browser workflow is specific to the GEMUL school system and requires an authorized account. The interface is in Portuguese. This project does not train a machine learning model.

## Run on Windows

Use Python 3.10 or later with Tkinter installed. Dependencies are currently unpinned; validate them in your environment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe main.py
```

For AI features, set `OPENAI_API_KEY` in the environment before starting the application. The code also supports `OPENAI_OCR_MODEL`. Configure secrets locally; do not commit them. AI document reading sends the selected document to the configured API.

Keep local student registers (`lista_alunos.csv` and `rel_aluno.csv`) beside `main.py` when required by the workflow. These files and document caches are excluded from Git.

## Checks

```powershell
python -m py_compile main.py
python verificar_navegacao.py
python verificar_observacoes.py
```

These checks cover isolated navigation and record observation behavior. They do not validate a live school-system session or an API request.

## Version control

Edit `main.py` instead of creating filenames with timestamps or version numbers. Other Python files can hold modules and checks. Use Git commits for change history and Git tags for releases.

Previous script copies are preserved locally in `archive/`, which is excluded from Git. Existing changelog entries retain their original filenames as historical references.

After the repository is connected, save changes with:

```powershell
git add .
git diff --cached --stat
git commit -m "Describe the change"
git push
```

Review staged files before committing. Keep student records, credentials, and local exports out of the repository.
