"""Daily student register refresh using the authenticated GEMUL browser session."""
import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPORT_URL = "https://gemul-aparecida.com.br/app/sca_rel_alunoCon.asp"
FIELDS = {
    "matricula": {"MATRICULA", "NUMERO MATRICULA", "RA"},
    "nome": {"NOME", "ALUNO", "NOME ALUNO", "NOME DO ALUNO"},
    "data_matricula": {"DATA MATRICULA", "DATA DA MATRICULA", "DATA DE MATRICULA"},
    "data_afastamento": {"DATA AFASTAMENTO", "DATA DE AFASTAMENTO", "DATA DO AFASTAMENTO"},
    "data_nascimento": {"DATA NASCIMENTO", "DATA DE NASCIMENTO", "DATA NASCIMENTO DO ALUNO", "NASCIMENTO"},
    "sexo": {"SEXO", "SEXO DO ALUNO"},
    "naturalidade": {"NATURALIDADE"},
    "pai": {"PAI", "NOME DO PAI", "NOME PAI"},
    "mae": {"MAE", "NOME DA MAE", "NOME MAE"},
    "situacao": {"SITUACAO", "SITUACAO ALUNO", "SITUACAO DO ALUNO"},
    "turma": {"TURMA"},
    "telefone_celular": {"TELEFONE CELULAR"},
    "telefone_comercial": {"TELEFONE COMERCIAL"},
    "telefone_residencial": {"TELEFONE RESIDENCIAL"},
    "telefone_responsavel": {"TELEFONE RESPONSAVEL", "TELEFONE DO RESPONSAVEL"},
}
CHECKBOXES = ("datamatricula", "dataafastamento", "datanascimento", "sexo",
              "naturalidade", "nomepai", "nomemae", "situacaoaluno", "turma",
              "telefonecelular", "telefonecomercial", "telefoneresidencial", "telefoneresponsavel")


def hoje():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()


def verificar_espaco(base_dir, minimo=512 * 1024 * 1024):
    for local in {str(Path(base_dir).resolve()), tempfile.gettempdir()}:
        livre = shutil.disk_usage(local).free
        if livre < minimo:
            raise OSError(
                f"Espaco insuficiente no disco: {livre / (1024 * 1024):.1f} MB livres. "
                f"Libere pelo menos {minimo / (1024 * 1024):.0f} MB antes de tentar novamente."
            )


def normalizar(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def base_atualizada_hoje(base_dir):
    base = Path(base_dir)
    try:
        state = json.loads((base / "student_sync_state.json").read_text(encoding="utf-8"))
        return state.get("campos") == list(FIELDS) and state["data"] == hoje() and all(
            hashlib.sha256((base / name).read_bytes()).hexdigest() == state["arquivos"][name]
            for name in ("lista_alunos.csv", "rel_aluno.csv")
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def extrair_registros(tabelas):
    """Accept only tables with all requested headers; never interpret a login/error as data."""
    registros = []
    for rows in tabelas:
        mapping = None
        for row in rows:
            found = {}
            for index, cell in enumerate(row):
                label = normalizar(cell)
                for field, aliases in FIELDS.items():
                    if label in aliases:
                        if field in found:
                            raise ValueError("Colunas duplicadas no relatorio.")
                        found[field] = index
            if set(FIELDS).issubset(found):
                mapping = found
                continue
            if mapping is None or len(row) <= max(mapping.values()):
                continue
            record = {key: str(row[index]).strip() for key, index in mapping.items()}
            if not re.fullmatch(r"\d{9}", record["matricula"]):
                continue
            if not record["nome"]:
                raise ValueError("Registro de aluno sem nome.")
            registros.append(record)
    if not registros:
        raise ValueError("Relatorio sem tabela valida com as colunas solicitadas. A base anterior nao foi alterada.")
    unique = {}
    for record in registros:
        key = tuple(record.items())
        unique[key] = record
    return list(unique.values())


def _csv_bytes(records):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(FIELDS), delimiter=";")
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8-sig")


def salvar_base(base_dir, records):
    """Keep a backup and roll back both registers if replacement fails."""
    base = Path(base_dir)
    payload = _csv_bytes(records)
    targets = [base / "lista_alunos.csv", base / "rel_aluno.csv"]
    original = {path: path.read_bytes() if path.exists() else None for path in targets}
    backup = base / "student_sync_backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True)
    for path, data in original.items():
        if data is not None:
            (backup / path.name).write_bytes(data)
    changed = []
    temps = []
    state = {"data": hoje(), "registros": len(records), "ano_letivo": hoje()[:4],
             "campos": list(FIELDS),
             "arquivos": {p.name: hashlib.sha256(payload).hexdigest() for p in targets}}
    state_path = base / "student_sync_state.json"
    writes = [(path, payload) for path in targets]
    writes.append((state_path, (json.dumps(state, indent=2) + "\n").encode("utf-8")))
    try:
        for path, data in writes:
            with tempfile.NamedTemporaryFile(dir=base, delete=False, suffix=".tmp") as file:
                temps.append(Path(file.name))
                file.write(data)
        for (path, _data), staged in zip(writes, temps):
            os.replace(staged, path)
            if path in original:
                changed.append(path)
    except Exception:
        for path in changed:
            if original[path] is None:
                path.unlink(missing_ok=True)
            else:
                # Restore via rename; no new disk allocation is needed.
                os.replace(backup / path.name, path)
        raise
    finally:
        for path in temps:
            path.unlink(missing_ok=True)


def _selecionar(page, selector, value):
    locator = page.locator(selector)
    if locator.input_value() != value:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            locator.select_option(value=value)


def atualizar_base_diaria(pagina, base_dir, forcar=False):
    if not forcar and base_atualizada_hoje(base_dir):
        return json.loads((Path(base_dir) / "student_sync_state.json").read_text())["registros"]
    verificar_espaco(base_dir)
    if pagina.is_closed() or not pagina.context.browser.is_connected():
        raise RuntimeError("Navegador fechado. Use RECUPERAR GEMUL e tente atualizar novamente.")
    page = pagina.context.new_page()
    try:
        page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=60000)
        page.locator("#frm #txtAnoLetivo").wait_for(state="visible", timeout=15000)
        # The page's year field submits on blur; reload using the actual form.
        year = hoje()[:4]
        if page.locator("#txtAnoLetivo").input_value() != year:
            page.locator("#txtAnoLetivo").fill(year)
            with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                page.locator("#txtAnoLetivo").press("Tab")
        _selecionar(page, "#cmbTipoTurma", "ESC")
        _selecionar(page, "#cmbSemestre", "3")
        # Include every course, class and student situation, including transferred students.
        for selector in ("#cmbCurso", "#cmbPeriodo", "#cmbTurno", "#cmbTurma", "#cmbSituacaoAluno"):
            _selecionar(page, selector, "0")
        for selector in ("#cmbTipoNacionalidade", "#cmbSexo", "#cmbMes", "#cmbIdade", "#cmbNecessidadeEspecialSN", "#cmbAtendimentoEspecial", "#cmbSalaAEE"):
            page.locator(selector).select_option(value="0")
        for name in ("txtDataMatriculaI", "txtDataMatriculaF", "txtDataAfastamentoI", "txtDataAfastamentoF"):
            page.locator(f"#{name}").fill("")
        page.locator("#cmbOrdem").select_option(value="matricula")
        page.locator("#cmbQuebraPagina").select_option(value="NORMAL")
        page.locator("#cmblpp").select_option(value="0")
        boxes = page.locator('#frm input[type="checkbox"]:not([disabled])')
        for index in range(boxes.count()):
            box = boxes.nth(index)
            box.set_checked(box.get_attribute("name") in CHECKBOXES)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            page.get_by_role("button", name="Gerar Relatório", exact=True).click()
        page.locator("table").first.wait_for(state="attached", timeout=15000)
        tables = page.locator("table").evaluate_all("""tables => tables.map(table =>
            Array.from(table.rows).map(row => Array.from(row.cells).map(cell => cell.innerText.trim())))""")
        records = extrair_registros(tables)
        salvar_base(base_dir, records)
        return len(records)
    finally:
        # Cleanup must not hide the original report/storage error.
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
