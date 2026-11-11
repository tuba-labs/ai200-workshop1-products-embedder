"""Package source only; Azure remotely installs Linux dependencies."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def package(destination):
    root = Path(__file__).resolve().parent
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for name in ['function_app.py', 'host.json', 'requirements.txt', 'constraints.txt']:
            archive.write(root / name, name)
        for path in sorted((root / 'rag_core').glob('*.py')):
            archive.write(path, 'rag_core/' + path.name)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='dist/function.zip')
    args = parser.parse_args()
    print(package(args.output))
