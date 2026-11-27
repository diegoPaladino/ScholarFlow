import unittest
from unittest.mock import Mock
from idp_engine import Engine, EngineRegistry

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.registry = EngineRegistry()
        self.local = Mock(return_value={'ok': True})
        self.remote = Mock(return_value={'ok': True})
        self.registry.register(Engine('local', self.local))
        self.registry.register(Engine('openai', self.remote, True))

    def test_local(self):
        self.assertEqual(self.registry.select('local')('historico', b'x'), {'ok': True})
        self.remote.assert_not_called()

    def test_external_denied(self):
        with self.assertRaises(PermissionError):
            self.registry.select('openai')
        self.remote.assert_not_called()

    def test_external_allowed(self):
        self.registry.select('openai', allow_external=True)('boletim', b'x')
        self.remote.assert_called_once_with('boletim', b'x')

    def test_no_fallback(self):
        self.local.side_effect = RuntimeError('failure')
        with self.assertRaises(RuntimeError):
            self.registry.select('local')('historico', b'x')
        self.remote.assert_not_called()

    def test_invalid_input(self):
        for kind, data in [('unknown', b'x'), ('historico', b''), ('historico', 'x')]:
            with self.assertRaises(ValueError):
                self.registry.select('local')(kind, data)
        self.local.assert_not_called()

    def test_invalid_output(self):
        self.local.return_value = []
        with self.assertRaises(TypeError):
            self.registry.select('local')('documento_civil', b'x')

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            self.registry.register(Engine('local', self.local))

    def test_unknown(self):
        with self.assertRaises(KeyError):
            self.registry.select('missing')
