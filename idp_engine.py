"""Explicit engine selection; no implicit external fallback."""
from dataclasses import dataclass
from typing import Callable

KINDS = frozenset(('historico', 'boletim', 'documento_civil'))

@dataclass(frozen=True)
class Engine:
    name: str
    extract: Callable[[str, bytes], dict]
    external: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip() or not callable(self.extract):
            raise ValueError('Invalid engine')
        if type(self.external) is not bool:
            raise ValueError('Invalid external flag')

class EngineRegistry:
    def __init__(self):
        self._engines = {}

    def register(self, engine):
        if not isinstance(engine, Engine) or engine.name in self._engines:
            raise ValueError('Invalid or duplicate engine')
        self._engines[engine.name] = engine

    def select(self, name, *, allow_external=False):
        engine = self._engines[name]
        if engine.external and allow_external is not True:
            raise PermissionError('External engine requires explicit authorization')

        def extract(kind, document):
            if kind not in KINDS or not isinstance(document, bytes) or not document:
                raise ValueError('Invalid document input')
            result = engine.extract(kind, document)
            if not isinstance(result, dict):
                raise TypeError('Expected structured dictionary')
            return result
        return extract
