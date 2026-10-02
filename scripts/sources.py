import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from common import Error, boolean, sha, write_json

def inside(root_relative_dir, target):
    """True when a relative symlink target stays inside the source root."""
    if PurePosixPath(target).is_absolute():
        return False
    depth = len(root_relative_dir.parts)
    for part in PurePosixPath(target).parts:
        if part == '..':
            depth -= 1
            if depth < 0:
                return False
        elif part != '.':
            depth += 1
    return True

def tree_hash(root):
    import hashlib
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            target = os.readlink(path)
            if not inside(relative.parent, target):
                raise Error(f'Source symlink escapes the source root: {path}')
            digest.update(relative.as_posix().encode() + b'\0link:' + target.encode() + b'\0')
        elif path.is_file():
            digest.update(relative.as_posix().encode() + b'\0')
            digest.update(bytes.fromhex(sha(path)))
    return digest.hexdigest()

def extract(archive, target):
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        roots = set()
        links = {}
        for item in infos:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename:
                raise Error('Unsafe ZIP member')
            if stat.S_ISLNK(item.external_attr >> 16):
                link_target = bundle.read(item).decode()
                if not inside(PurePosixPath(*path.parts[1:-1]), link_target):
                    raise Error(f'ZIP symlink escapes the repository root: {item.filename}')
                links[item.filename] = link_target
            if path.parts:
                roots.add(path.parts[0])
        if len(roots) != 1:
            raise Error('ZIP must contain one repository root')
        with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
            bundle.extractall(temporary)
            # extractall writes symlink members as files holding the target text.
            for name, link_target in links.items():
                placeholder = Path(temporary) / name
                placeholder.unlink()
                os.symlink(link_target, placeholder)
            source = Path(temporary) / roots.pop()
            if not source.is_dir():
                raise Error('ZIP repository root must be a directory')
            shutil.move(source, target)

def prepare(root, env):
    manifest = json.loads((root / 'sources.json').read_text())
    lock_path = root / 'sources.lock.json'
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    for name, spec in manifest.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise Error('Invalid source name')
        directory = root / name
        previous = lock.get(name, {})
        if directory.exists():
            fingerprint = tree_hash(directory)
            if previous and fingerprint != previous['tree_sha256']:
                raise Error(f'{name}: source differs from lock; review changes explicitly')
            record = previous or {'origin': 'local-directory', 'tree_sha256': fingerprint}
        else:
            # <name>-<hex revision>.zip; a plain glob would let clearml-*.zip match clearml-server-*.zip.
            archives = sorted(p for p in root.glob(name + '-*.zip') if re.fullmatch(r'[0-9a-f]{7,40}', p.stem[len(name) + 1:]))
            if (root / (name + '.zip')).exists():
                archives.append(root / (name + '.zip'))
            if len(archives) > 1:
                raise Error(f'{name}: multiple root ZIPs; retain only the intended version')
            revision = previous.get('revision')
            if not archives:
                if not boolean(env, 'ALLOW_SOURCE_DOWNLOADS'):
                    raise Error(f'{name}: source missing; provide a root ZIP or enable source preparation downloads')
                repo = spec['repository']
                if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', repo):
                    raise Error('Invalid GitHub repository')
                if not revision:
                    ref = urllib.parse.quote(spec['ref'], safe='')
                    request = urllib.request.Request(f'https://api.github.com/repos/{repo}/commits/{ref}',
                                                     headers={'User-Agent': 'clearml-offline-installer'})
                    with urllib.request.urlopen(request, timeout=60) as response:
                        revision = json.load(response)['sha']
                if not re.fullmatch(r'[a-f0-9]{40}', revision):
                    raise Error('Expected immutable GitHub commit')
                archive = root / f'{name}-{revision}.zip'
                temporary = archive.with_suffix('.part')
                try:
                    with urllib.request.urlopen(f'https://github.com/{repo}/archive/{revision}.zip', timeout=60) as response, temporary.open('wb') as output:
                        shutil.copyfileobj(response, output)
                    temporary.replace(archive)
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                archive = archives[0]
                if not revision and re.fullmatch(r'[a-f0-9]{40}', archive.stem[len(name) + 1:]):
                    revision = archive.stem[len(name) + 1:]  # <name>-<commit>.zip supplied by hand
            checksum = sha(archive)
            if previous.get('archive_sha256') and checksum != previous['archive_sha256']:
                raise Error(f'{name}: archive checksum mismatch')
            extract(archive, directory)
            fingerprint = tree_hash(directory)
            if previous and fingerprint != previous['tree_sha256']:
                shutil.rmtree(directory)
                raise Error(f'{name}: extracted source differs from lock')
            record = {'origin': archive.name, 'archive_sha256': checksum, 'tree_sha256': fingerprint}
            if revision:
                record['revision'] = revision
        lock[name] = record
        write_json(lock_path, lock)
        print(f'{name}: source ready, SHA-256 {record["tree_sha256"][:16]}')

def verify(root):
    path = root / 'sources.lock.json'
    if not path.exists():
        raise Error('Run prepare to stage and lock source inputs first')
    lock = json.loads(path.read_text())
    for name in json.loads((root / 'sources.json').read_text()):
        if name not in lock or not (root / name).is_dir() or tree_hash(root / name) != lock[name]['tree_sha256']:
            raise Error(f'{name}: missing or changed source')
    web = root / 'clearml-web'
    if not (web / 'pnpm-lock.yaml').is_file():
        raise Error('Selected web source must include pnpm-lock.yaml (Node 24 / pnpm 10)')
    for name in lock:
        module = root / name / '.gitmodules'
        if module.exists() and module.read_text().strip():
            raise Error(f'{name}: submodules require explicit ZIP staging; cannot run Git')
