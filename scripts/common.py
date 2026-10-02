"""Shared, standard-library-only installer utilities. Never executes .env as shell."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

class Error(Exception):
    pass

def env_file(path):
    values = {}
    if not path.is_file():
        raise Error(f"Missing {path}; copy .env.example to .env and configure it")
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise Error(f"Invalid .env key at line {n}")
        if key in values:
            raise Error(f"Duplicate .env key: {key}")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise Error(f"Unclosed quote at line {n}")
            value = value[1:-1]
        values[key] = value
    return values

def need(env, key):
    value = env.get(key, '')
    if not value or 'CHANGE_ME' in value:
        raise Error(f"Configure {key} in .env")
    return value

def boolean(env, key, default=False):
    value = env.get(key, str(default)).lower()
    if value not in ('true', 'false'):
        raise Error(f"{key} must be true or false")
    return value == 'true'

def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    temporary.replace(path)

def write_json(path, value):
    if path.name == 'compose.json':
        def escape(item):
            if isinstance(item, str): return item.replace('$', '$$')
            if isinstance(item, list): return [escape(v) for v in item]
            if isinstance(item, dict): return {k: escape(v) for k,v in item.items()}
            return item
        value = escape(value)
    private_write(path, json.dumps(value, indent=2) + '\n')

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def allowed_hosts(env):
    """Empty ALLOWED_HOSTS disables the host allowlist."""
    return {x.strip() for x in env.get('ALLOWED_HOSTS', '').split(',') if x.strip()}

def allowed_url(url, env):
    parsed = urlparse(url)
    hosts = allowed_hosts(env)
    if parsed.scheme not in ('http', 'https') or (hosts and parsed.hostname not in hosts):
        raise Error(f'Repository host is not in ALLOWED_HOSTS: {parsed.hostname}')
    if parsed.username or parsed.password:
        raise Error('Use secret configuration files for repository credentials')
    return url

def local_image(image, env):
    hosts = allowed_hosts(env)
    if hosts and ('/' not in image or urlparse('https://' + image.split('/')[0]).hostname not in hosts):
        raise Error(f"Image registry is not in ALLOWED_HOSTS: {image}")
    if ':latest' in image or (':' not in image.rsplit('/', 1)[-1] and '@sha256:' not in image):
        raise Error('Use a versioned image tag or digest')

def fetch_ca_bundle(root, env):
    """Stage generated/trust/{tls-ca-bundle.zip,tls-ca-bundle.pem} for image builds.
    Blank URL and no local files means no private CA (empty placeholders). A manually placed
    config/tls-ca-bundle.pem bootstraps the download when the download host uses the private CA."""
    import ssl
    import urllib.error
    import urllib.request
    import zipfile
    config = root / 'config'
    zip_path, pem_path = config / 'tls-ca-bundle.zip', config / 'tls-ca-bundle.pem'
    staged = root / 'generated/trust'
    staged.mkdir(parents=True, exist_ok=True)
    url = env.get('TLS_CA_BUNDLE_URL', '')
    if url:
        if urlparse(url).scheme not in ('http', 'https'):
            raise Error('TLS_CA_BUNDLE_URL must be an http(s) URL')
        proxies = {k[:-6]: v for k, v in proxy_args(env).items() if k.islower() and k != 'no_proxy'}
        context = ssl.create_default_context()
        if pem_path.is_file() and pem_path.stat().st_size:
            context.load_verify_locations(cafile=str(pem_path))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies), urllib.request.HTTPSHandler(context=context))
        temporary = zip_path.with_suffix('.zip.part')
        config.mkdir(parents=True, exist_ok=True)
        try:
            with opener.open(url, timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            temporary.replace(zip_path)
        except (urllib.error.URLError, OSError, ValueError) as error:
            temporary.unlink(missing_ok=True)
            reason = getattr(error, 'reason', error)
            if zip_path.is_file() and zip_path.stat().st_size:
                print(f'WARNING: could not download the CA bundle ({type(reason).__name__ if not isinstance(reason, str) else reason}); using the existing config/tls-ca-bundle.zip')
            else:
                raise Error('Could not download TLS_CA_BUNDLE_URL. If that host uses the private CA, place the CA as '
                            'config/tls-ca-bundle.pem (it is inside the zip) and retry, or copy the zip to config/tls-ca-bundle.zip')
    have = []
    if zip_path.is_file() and zip_path.stat().st_size:
        try:
            names = zipfile.ZipFile(zip_path).namelist()
        except zipfile.BadZipFile:
            raise Error('config/tls-ca-bundle.zip is not a zip archive')
        if not any(n.lower().endswith(('.pem', '.crt', '.cer')) for n in names):
            raise Error('CA bundle contains no .pem/.crt/.cer certificates')
        shutil.copyfile(zip_path, staged / 'tls-ca-bundle.zip')
        have.append('zip')
    else:
        (staged / 'tls-ca-bundle.zip').write_bytes(b'')
    if pem_path.is_file() and pem_path.stat().st_size:
        if 'BEGIN CERTIFICATE' not in pem_path.read_text(errors='replace'):
            raise Error('config/tls-ca-bundle.pem holds no PEM certificate')
        shutil.copyfile(pem_path, staged / 'tls-ca-bundle.pem')
        have.append('pem')
    else:
        (staged / 'tls-ca-bundle.pem').write_bytes(b'')
    print('CA material staged: ' + (', '.join(have) if have else 'none (system trust)'))
    return have

def proxy_args(env):
    """Blank proxy settings mean no proxy. Both cases are passed; dnf, pip, curl and npm differ."""
    result = {}
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY'):
        value = env.get(key, '')
        if value:
            result[key] = value
            result[key.lower()] = value
    return result

def docker_build(root, env, file, tag, args=None, secrets=None, target=None):
    local_image(need(env, 'RUNTIME_BASE_IMAGE'), env)
    command = ['docker', 'build', '--pull=false', '--network', env.get('BUILD_NETWORK', 'default'),
               '-f', str(root / file), '-t', tag]
    for key, value in (args or {}).items():
        command += ['--build-arg', f'{key}={value}']
    for key, value in proxy_args(env).items():
        command += ['--build-arg', f'{key}={value}']
    for key, path in (secrets or {}).items():
        if path:
            command += ['--secret', f'id={key},src={path}']
    if target:
        command += ['--target', target]
    run(*command, root)

def compose(root, *args):
    run('docker', 'compose', '--project-directory', root, '-f', root / 'generated/compose.json', *args)
