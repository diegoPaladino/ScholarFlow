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
- **Iniciar Protocolo de Cobrança de Histórico:** área exclusiva com um botão que abre o texto e a escolha dos telefones da base diária para a matrícula consultada. Reúne celular, comercial, residencial e responsável, trata DDD e código 55 e elimina duplicados. Ao escolher, clica na posição capturada no início, abre uma aba com Ctrl+T, cola o link wa.me e abre o endereço. O texto fica no clipboard para Ctrl+V; o envio é manual. O botão fica cinza após abrir o link, com marca persistida por matrícula e número em `cobranca_contatos_utilizados.json`. Essa marca indica link utilizado, sem confirmar entrega da mensagem. Telefones sem DDD válido ficam fora da seleção. O texto usa sempre a escola solicitante padrão, mesmo que o formulário informe a escola anterior.
- **Carga horária:** conta os dias letivos desde o primeiro dia do calendário escolar até a transferência, incluindo essa data quando for letiva. A data de entrada do aluno não altera a contagem. Multiplica por 4 horas para agrupamentos ou 5 horas para o ensino fundamental. O calendário de 2026 foi transcrito do PDF da SME de Aparecida de Goiânia fornecido pelo usuário; o de 2024 foi preservado para registros daquele ano. Transferências em anos sem calendário cadastrado exigem carga horária manual, sem reaproveitar datas de outro ano.
- **Lembrar credenciais neste Windows:** opção na janela de login. Após o acesso, memoriza usuário e senha em `gemul_credenciais.dpapi`, protegidos pela DPAPI do Windows para o usuário atual. O login também é reconhecido quando o GEMUL abre primeiro a seleção de escola. Nos próximos acessos, as credenciais salvas são reutilizadas sem diálogo; se o GEMUL recusar o acesso, o diálogo reaparece para correção. Use **Esquecer credenciais GEMUL** na interface para apagar o armazenamento local e informar outras credenciais no próximo acesso. Credenciais e cobranças locais são ignoradas pelo Git.
- **Log:** `HistoricoAutomatizado.log` contém etapas, horários, URLs, seleção de registros e erros. As credenciais não são registradas. O log pode conter dados de alunos.

Verificação: `python -m unittest test_student_sync test_interface_fixes test_workflow_guards -q`.

### Calendário de 2026

Fonte: `C:\Users\Public\Calendario Escolar 2026.pdf`, calendário da Secretaria de Educação de Aparecida de Goiânia, aprovado em 17/11/2025 pela Resolução CME nº 109/2025. Os dias estão incorporados ao programa; não é necessário manter o PDF nesse caminho para executar.

Totais de janeiro a dezembro: **10, 18, 22, 18, 19, 21, 1, 21, 21, 17, 19 e 14**, somando **201 dias** (108 no primeiro semestre e 93 no segundo). A contagem começa em **19/01**, início do ano letivo e planejamento coletivo. Inclui os dias de planejamento, acolhimento, conselhos e avaliação institucional que compõem esses totais oficiais; inclui os sábados 07/02 e 13/06. Exclui feriados, recessos e férias conforme as marcações do documento.

Exemplo: até **09/10/2026**, são **158 dias**, ou **790 horas** no ensino fundamental e **632 horas** nos agrupamentos. Para o ano completo de 2026 em Aparecida de Goiânia, o cálculo resulta em **1.005 horas** e **804 horas**, respectivamente. Cargas salvas no formulário são recalculadas ao carregar esses dados.

### Diagnosing student refresh failures

Use **ATUALIZAR ALUNOS** to force a complete report refresh even on a day already marked successful. Registers created before phone collection are automatically treated as outdated; resetting the date or deleting CSVs is unnecessary. Failed refreshes preserve the previous registers and remain eligible for retry. The log records the failing stage, report URL, error type and traceback. Invalid report errors identify missing columns without logging student rows.

Phone report headers accept full, short and abbreviated labels (for example, `Telefone Celular`, `Celular` and `Tel. Celular`). Checkbox selection is verified before submission. If parsing fails, the log includes the recognizable header labels for layout diagnosis, without student rows. Missing phone columns still reject the report and preserve the previous base.

### Student transfer confirmation

For first through fifth grade, the new GEMUL discipline table is filled with Artes, Ciências, Cultura de Inovação e Tecnologias, Educação Física, Ensino Religioso, Geografia, História, Língua Portuguesa and Matemática. New rows use `Cursando`, with CH and Média blank; the annual total remains in `txtCHTotal` on the history header. Existing subjects are preserved. Past-year rows already marked `Cursando` stop the operation with a request for manual correction in GEMUL, without resending saved rows. Repeating a launch for an existing header adds only missing subjects, without creating another header. Each save must return a valid ID, and the application reloads the page to confirm the saved rows before reporting completion.

Only `ATIVO` triggers the student situation check before history entry or request protocol. Other situations, including `TRANSFERENCIA INTERNA`, `CANCELADO`, `DESISTENTE`, `FALECIDO` and `TRANSFERIDO`, proceed normally. For `ATIVO`, the user can continue explicitly, cancel, or open GEMUL to review the situation. **Conferir novamente** refreshes the register; **Continuar mesmo assim** permits proceeding while still active. Confirmation is scoped to the selected enrollment and name. The software does not change the situation itself.

### Literacy cycle observations

Under the rule and text supplied by the user, Aparecida de Goiania histories retain Resolution 011/2019, with its full text on the first citation per student in the session and the short reference thereafter. Other existing historical norms are retained. For first and second grade from 2026 onward, observations also include Resolution CME 16/2026, dated 20 February 2026, on numerical grades in the literacy cycle. For these grades and years, the automatically generated descriptive-assessment and PE-only grade wording is removed. Earlier years and other municipalities keep their previous assessment rules.

Checks: `python -m unittest test_student_transfer test_resolucoes_observacoes test_workflow_guards test_student_sync test_cobranca_historico test_interface_fixes -q`.

The sentence `Aluno(a) apto(a) a dar continuidade aos estudos no (...)` is placed at the end of the year observation, after resolutions and manual complementary notes, with repeated identical copies removed.
