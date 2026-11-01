"""Validate public roadmap and build an exact allowlisted Pages artifact."""
import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
FILES = ('index.html', 'roadmap.css', 'roadmap.js', 'roadmap-data.js')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = ROOT / 'roadmap'
    for name in FILES:
        path = source / name
        assert path.is_file() and not path.is_symlink(), name
        text = path.read_text(encoding='utf-8')
        assert not re.search(r'https?://|tailscale|\.ts\.net|(?:100\.)\d+\.\d+\.\d+|-----BEGIN .*PRIVATE KEY', text, re.I), 'Unexpected public endpoint or credential marker: ' + name
    raw = (source / 'roadmap-data.js').read_text(encoding='utf-8')
    data = json.loads(raw.split('window.SMARTINI_ROADMAP = ', 1)[1].rstrip().removesuffix(';'))
    tasks = {t['id']: t for t in data['tasks']}
    assert len(tasks) == len(data['tasks']), 'Duplicate task IDs'
    phases = {p['id'] for p in data['phases']}
    visited, active = set(), set()

    def visit(key):
        assert key not in active, 'Dependency cycle'
        if key in visited:
            return
        active.add(key)
        for dep in tasks[key]['dependsOn']:
            assert dep in tasks, 'Unknown dependency: ' + dep
            visit(dep)
        active.remove(key)
        visited.add(key)

    for task in tasks.values():
        assert task['phase'] in phases
        assert task['status'] in ('delivered', 'provisional', 'optional', 'tbd')
        assert 'start' not in task and 'end' not in task, 'Roadmap must remain undated'
        step = task['step']
        if step is not None:
            assert isinstance(step, int) and 0 <= step < len(data['steps'])
            for dep in task['dependsOn']:
                previous = tasks[dep]['step']
                assert previous is None or previous <= step, 'Dependency follows workstream: ' + task['id']
        else:
            assert task['status'] in ('delivered', 'tbd')
        visit(task['id'])
    if args.output:
        destination = args.output.resolve()
        assert not destination.exists(), 'Choose a fresh output directory'
        destination.mkdir(parents=True)
        for name in FILES:
            shutil.copyfile(source / name, destination / name)
        (destination / '.nojekyll').touch()
    print(f'Validated {len(tasks)} public workstreams; dependencies acyclic; Pages allowlist: {len(FILES)} files.')


if __name__ == '__main__':
    main()
