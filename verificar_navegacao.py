import ast
from pathlib import Path

tree = ast.parse(Path(__file__).resolve().with_name('main.py').read_text(encoding='utf-8-sig'))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FuncoesDoPrograma')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'abrir_novas_abas_pw')

class Timeout(Exception):
    pass

class Locator:
    def __init__(self, page, xpath):
        self.page, self.xpath = page, xpath
    def wait_for(self, **kwargs):
        if self.xpath == self.page.fail:
            raise Timeout()
    def click(self, **kwargs):
        self.page.clicks.append(self.xpath)
    def count(self):
        return 0

class Page:
    url = 'https://example.test/app/sca_historico_escolarCon.asp'
    def __init__(self, fail=None):
        self.clicks, self.visits, self.fail = [], [], fail
    def locator(self, xpath):
        return Locator(self, xpath)
    def wait_for_load_state(self, *args, **kwargs):
        pass
    def goto(self, url, **kwargs):
        self.visits.append(url)

env = dict(PlaywrightTimeoutError=Timeout, GEMUL_HISTORICO_URL=Page.url,
           maximizar_janela_navegador=lambda p: None)
exec(compile(ast.Module(body=[method], type_ignores=[]), '<isolated>', 'exec'), env)
run = env['abrir_novas_abas_pw']
page = Page()
run(page, apos_login=True)
assert page.clicks == [
    "xpath=//div[contains(concat(' ', normalize-space(@class), ' '), ' module-card ') and contains(@onclick, '/app/academico.asp')]",
    'xpath=//*[@id="js-nav-menu"]/li[4]/a/span',
    'xpath=//*[@id="js-nav-menu"]/li[4]/ul/li[6]/a/span']
assert not page.visits
assert env['driver'] is page
recovery = Page()
run(recovery)
assert recovery.visits == [Page.url] and not recovery.clicks
broken = Page(fail='xpath=//*[@id="js-nav-menu"]/li[4]/a/span')
try:
    run(broken, apos_login=True)
except RuntimeError as exc:
    assert 'menu Manutencao' in str(exc)
else:
    raise AssertionError('Esperado erro identificando a etapa que falhou')
assert len(broken.clicks) == 1
print('OK: ordem dos tres cliques, recuperacao de sessao e erro por etapa.')
