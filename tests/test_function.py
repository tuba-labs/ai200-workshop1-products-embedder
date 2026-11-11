import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

from package import package


def test_event_grid_blob_binding():
    path = Path(__file__).resolve().parents[1] / 'function_app.py'
    spec = importlib.util.spec_from_file_location('workshop_function', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    functions = module.app.get_functions()
    assert len(functions) == 1 and functions[0].get_function_name() == 'IndexManual'
    binding = json.loads(functions[0].get_function_json())['bindings'][0]
    assert binding['source'] == 'EventGrid' and binding['type'] == 'blobTrigger'
    assert binding['connection'] == 'ManualStorage'


def test_package_contains_complete_runtime_and_no_local_state(tmp_path):
    result = package(tmp_path / 'function.zip')
    with ZipFile(result) as archive:
        files = set(archive.namelist())
        assert {'function_app.py','host.json','requirements.txt','constraints.txt','rag_core/embedding.py'} <= files
        assert not any(part.startswith('.') or part in {'tests','__pycache__'} for name in files for part in name.split('/'))
        assert '../../' not in archive.read('requirements.txt').decode()
