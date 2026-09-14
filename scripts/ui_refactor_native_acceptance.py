"""Additional installed UI review followed by every existing exclusive native stage."""
import argparse
from pathlib import Path
from exclusive_native_acceptance import run
from ui_refactor_native import review

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('executable', 'driver', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--kind', choices=('deb', 'appimage', 'nsis'), required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--fixture-root', type=Path)
    run(parser.parse_args(), ui_review=review)
