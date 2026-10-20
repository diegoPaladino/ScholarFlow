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

## Daily student register refresh

At every startup, before the GEMUL credentials prompt, the application asks the user to click the screen location used to access the browser with WhatsApp open. After confirming the instructions, the next left click is saved locally in `whatsapp_posicao.json` as `x` and `y` screen coordinates, replacing the previous position. Escape or 120 seconds without a click cancels startup. The position is available through `whatsapp_posicao.carregar_posicao(base_dir)` for a future feature. No additional package is required on Windows.

Before the initial student lookup, ScholarFlow signs in and generates the current school year's student report. It includes all schooling courses, classes and student situations (including transferred students). AEE is not included. The report table is converted locally into UTF-8 CSV in `lista_alunos.csv` and `rel_aluno.csv`.

The selected columns include enrollment number, name, enrollment date, departure date, birth date, sex, birthplace, parents, situation, class, and cellular, commercial, residential and guardian phone numbers. Phone values are preserved as text, including multiple numbers in the same field; unavailable numbers remain empty. Older registers without these columns are refreshed on the next initial lookup even if already generated that day. Previous registers are backed up under `student_sync_backups/`. Invalid reports preserve the existing registers. A successful refresh is recorded for the current date in America/Sao_Paulo; a failed refresh can be retried using **ATUALIZAR ALUNOS**. Historical school years are not fetched by this routine.

Set `GEMUL_USERNAME` and `GEMUL_PASSWORD` in your local environment, or enter them in the login dialog. The live generated report layout still requires validation in an authenticated GEMUL session.

Additional isolated checks: `python -m unittest test_student_sync.py`.

## Opções de operação e desenvolvimento

- **Duplicação:** antes de incluir, o programa consulta a lista atual do GEMUL. Se já existir registro para o mesmo ano, série e escola, informa que o lançamento já está cadastrado e encerra a operação sem incluir disciplinas ou outro cabeçalho. Não retoma automaticamente registros parcialmente preenchidos.
- **Deve histórico:** o status é salvo por matrícula e bloqueia novos lançamentos enquanto estiver marcado. Após a regularização do documento, desmarque essa opção.
- **Gerar cobrança de histórico:** abre um texto curto, com palavras simples, nome, matrícula e escola. O texto é copiado automaticamente para a área de transferência; a janela confirma a cópia. Use **Ctrl+V** para colar. Após editar, use **Copiar texto** novamente. Também é possível **Salvar texto...**. Nenhuma mensagem é enviada automaticamente.
- **Carga horária:** conta os dias letivos desde o primeiro dia do calendário escolar até a transferência, incluindo essa data quando for letiva. A data de entrada do aluno não altera a contagem. Multiplica por 4 horas para agrupamentos ou 5 horas para o ensino fundamental. O calendário de 2026 foi transcrito do PDF da SME de Aparecida de Goiânia fornecido pelo usuário; o de 2024 foi preservado para registros daquele ano. Transferências em anos sem calendário cadastrado exigem carga horária manual, sem reaproveitar datas de outro ano.
- **Lembrar credenciais neste Windows:** opção na janela de login. Após o acesso, memoriza usuário e senha em `gemul_credenciais.dpapi`, protegidos pela DPAPI do Windows para o usuário atual. Nos próximos testes, os campos vêm preenchidos. Desmarque a opção e confirme o diálogo para apagar as credenciais memorizadas. Credenciais e cobranças locais são ignoradas pelo Git.
- **Log:** `HistoricoAutomatizado.log` contém etapas, horários, URLs, seleção de registros e erros. As credenciais não são registradas. O log pode conter dados de alunos.

Verificação: `python -m unittest test_student_sync test_interface_fixes test_workflow_guards -q`.

### Calendário de 2026

Fonte: `C:\Users\Public\Calendario Escolar 2026.pdf`, calendário da Secretaria de Educação de Aparecida de Goiânia, aprovado em 17/11/2025 pela Resolução CME nº 109/2025. Os dias estão incorporados ao programa; não é necessário manter o PDF nesse caminho para executar.

Totais de janeiro a dezembro: **10, 18, 22, 18, 19, 21, 1, 21, 21, 17, 19 e 14**, somando **201 dias** (108 no primeiro semestre e 93 no segundo). A contagem começa em **19/01**, início do ano letivo e planejamento coletivo. Inclui os dias de planejamento, acolhimento, conselhos e avaliação institucional que compõem esses totais oficiais; inclui os sábados 07/02 e 13/06. Exclui feriados, recessos e férias conforme as marcações do documento.

Exemplo: até **09/10/2026**, são **158 dias**, ou **790 horas** no ensino fundamental e **632 horas** nos agrupamentos. Para o ano completo de 2026 em Aparecida de Goiânia, o cálculo resulta em **1.005 horas** e **804 horas**, respectivamente. Cargas salvas no formulário são recalculadas ao carregar esses dados.
