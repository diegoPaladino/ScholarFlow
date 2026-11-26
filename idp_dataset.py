"""Offline, local dataset registry. Only explicitly reviewed references are accepted."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from idp_benchmark import evaluate

ROOT = Path(__file__).resolve().parent / 'idp_dataset_local'
TYPES = {'historico', 'boletim', 'documento_civil'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Dataset:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'registry.sqlite3'
        with closing(self.connect()) as db, db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported dataset version')
            db.execute('''CREATE TABLE IF NOT EXISTS samples (
                sha TEXT PRIMARY KEY, group_id TEXT NOT NULL, split TEXT NOT NULL,
                kind TEXT NOT NULL, reference TEXT NOT NULL, document BLOB NOT NULL)''')
            db.execute('PRAGMA user_version=1')

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def register(self, document, *, kind, split, group_id, reference, reviewed=False):
        if reviewed is not True or kind not in TYPES or split not in ('learning', 'evaluation'):
            raise ValueError('Invalid metadata or missing human review')
        if not isinstance(group_id, str) or not re.fullmatch(r'[a-f0-9]{32}', group_id):
            raise ValueError('Use an opaque group identifier')
        if not isinstance(document, bytes) or not document:
            raise ValueError('Empty or invalid document')
        validate_reference(kind, reference)
        encoded = canonical(reference)
        sha = digest(document)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM samples WHERE group_id=? AND split<>?', (group_id, split)).fetchone():
                raise ValueError('Group crosses dataset partitions')
            old = db.execute('SELECT group_id,split,kind,reference FROM samples WHERE sha=?', (sha,)).fetchone()
            if old is not None:
                if old != (group_id, split, kind, encoded):
                    raise ValueError('Conflicting duplicate document')
                return sha
            db.execute('INSERT INTO samples VALUES (?,?,?,?,?,?)', (sha, group_id, split, kind, encoded, document))
        return sha

    def manifest(self, split):
        if split not in ('learning', 'evaluation'):
            raise ValueError('Invalid partition')
        with closing(self.connect()) as db:
            rows = db.execute('SELECT sha,group_id,kind,reference FROM samples WHERE split=? ORDER BY sha', (split,)).fetchall()
        # No reference values or group identifiers are returned.
        return {'split': split, 'count': len(rows), 'version': digest(canonical([1, split, rows]).encode())}


def validate_reference(kind, reference):
    def check(schema, value):
        if schema['type'] == 'string':
            if type(value) is not str:
                raise ValueError('Invalid reference string')
        elif schema['type'] == 'array':
            if type(value) is not list:
                raise ValueError('Invalid reference array')
            for item in value:
                check(schema['items'], item)
        elif schema['type'] == 'object':
            if type(value) is not dict or set(value) != set(schema['required']):
                raise ValueError('Invalid reference fields')
            for key, item in value.items():
                check(schema['properties'][key], item)
    check(SCHEMAS[kind], reference)
    if not evaluate(reference, reference)['expected_fields']:
        raise ValueError('Empty reference')


SCHEMAS = {'boletim': {'additionalProperties': False,
             'properties': {'ano': {'type': 'string'},
                            'nome_aluno': {'type': 'string'},
                            'notas': {'items': {'additionalProperties': False,
                                                'properties': {'bimestre': {'type': 'string'},
                                                               'disciplina': {'type': 'string'},
                                                               'nota': {'type': 'string'}},
                                                'required': ['disciplina', 'bimestre', 'nota'],
                                                'type': 'object'},
                                      'type': 'array'},
                            'numero_matricula': {'type': 'string'},
                            'turma': {'type': 'string'}},
             'required': ['numero_matricula', 'nome_aluno', 'ano', 'turma', 'notas'],
             'type': 'object'},
 'documento_civil': {'additionalProperties': False,
                     'properties': {'data_nascimento': {'type': 'string'},
                                    'mae': {'type': 'string'},
                                    'naturalidade': {'type': 'string'},
                                    'nome_aluno': {'type': 'string'},
                                    'numero_documento': {'type': 'string'},
                                    'pai': {'type': 'string'},
                                    'sexo': {'type': 'string'},
                                    'tipo_documento': {'type': 'string'}},
                     'required': ['tipo_documento',
                                  'nome_aluno',
                                  'sexo',
                                  'data_nascimento',
                                  'naturalidade',
                                  'pai',
                                  'mae',
                                  'numero_documento'],
                     'type': 'object'},
 'historico': {'additionalProperties': False,
               'properties': {'ano': {'type': 'string'},
                              'carga_horaria': {'type': 'string'},
                              'cidade': {'type': 'string'},
                              'disciplinas_extra': {'items': {'additionalProperties': False,
                                                              'properties': {'disciplina': {'type': 'string'},
                                                                             'nota': {'type': 'string'}},
                                                              'required': ['disciplina', 'nota'],
                                                              'type': 'object'},
                                                    'type': 'array'},
                              'historicos': {'items': {'additionalProperties': False,
                                                       'properties': {'ano': {'type': 'string'},
                                                                      'carga_horaria': {'type': 'string'},
                                                                      'cidade': {'type': 'string'},
                                                                      'cursando': {'type': 'string'},
                                                                      'disciplinas_extra': {'items': {'additionalProperties': False,
                                                                                                      'properties': {'disciplina': {'type': 'string'},
                                                                                                                     'nota': {'type': 'string'}},
                                                                                                      'required': ['disciplina',
                                                                                                                   'nota'],
                                                                                                      'type': 'object'},
                                                                                            'type': 'array'},
                                                                      'nome_escola': {'type': 'string'},
                                                                      'nota_arte': {'type': 'string'},
                                                                      'nota_ciencias': {'type': 'string'},
                                                                      'nota_cultura': {'type': 'string'},
                                                                      'nota_educacao_fisica': {'type': 'string'},
                                                                      'nota_ensino_religioso': {'type': 'string'},
                                                                      'nota_geografia': {'type': 'string'},
                                                                      'nota_historia': {'type': 'string'},
                                                                      'nota_lingua_portuguesa': {'type': 'string'},
                                                                      'nota_matematica': {'type': 'string'},
                                                                      'serie': {'type': 'string'},
                                                                      'txt_observacoes': {'type': 'string'},
                                                                      'txt_observacoes_gerais': {'type': 'string'},
                                                                      'uf': {'type': 'string'}},
                                                       'required': ['ano',
                                                                    'serie',
                                                                    'nome_escola',
                                                                    'cidade',
                                                                    'uf',
                                                                    'carga_horaria',
                                                                    'txt_observacoes',
                                                                    'txt_observacoes_gerais',
                                                                    'cursando',
                                                                    'nota_arte',
                                                                    'nota_ciencias',
                                                                    'nota_cultura',
                                                                    'nota_educacao_fisica',
                                                                    'nota_ensino_religioso',
                                                                    'nota_geografia',
                                                                    'nota_historia',
                                                                    'nota_lingua_portuguesa',
                                                                    'nota_matematica',
                                                                    'disciplinas_extra'],
                                                       'type': 'object'},
                                             'type': 'array'},
                              'nome_aluno': {'type': 'string'},
                              'nome_escola': {'type': 'string'},
                              'nota_arte': {'type': 'string'},
                              'nota_ciencias': {'type': 'string'},
                              'nota_cultura': {'type': 'string'},
                              'nota_educacao_fisica': {'type': 'string'},
                              'nota_ensino_religioso': {'type': 'string'},
                              'nota_geografia': {'type': 'string'},
                              'nota_historia': {'type': 'string'},
                              'nota_lingua_portuguesa': {'type': 'string'},
                              'nota_matematica': {'type': 'string'},
                              'numero_matricula': {'type': 'string'},
                              'serie': {'type': 'string'},
                              'txt_observacoes': {'type': 'string'},
                              'txt_observacoes_gerais': {'type': 'string'},
                              'uf': {'type': 'string'}},
               'required': ['numero_matricula',
                            'nome_aluno',
                            'ano',
                            'nome_escola',
                            'cidade',
                            'uf',
                            'serie',
                            'carga_horaria',
                            'txt_observacoes',
                            'txt_observacoes_gerais',
                            'nota_arte',
                            'nota_ciencias',
                            'nota_cultura',
                            'nota_educacao_fisica',
                            'nota_ensino_religioso',
                            'nota_geografia',
                            'nota_historia',
                            'nota_lingua_portuguesa',
                            'nota_matematica',
                            'disciplinas_extra',
                            'historicos'],
               'type': 'object'}}
