import copy
import json
import secrets
from pathlib import Path
from urllib.parse import urlparse
from common import Error, boolean, need, write_json

def render(root, env):
    generated = root / 'generated'
    generated.mkdir(exist_ok=True)
    secure_path = generated / 'config/secure.conf'
    if secure_path.exists():
        secure = json.loads(secure_path.read_text())
    else:
        secure = {'http': {'session_secret': {'apiserver': secrets.token_urlsafe(48)}},
                  'auth': {'token_secret': secrets.token_urlsafe(48)},
                  # Every upstream default credential is replaced so no published secret stays valid.
                  'credentials': {name: {'user_key': secrets.token_hex(16), 'user_secret': secrets.token_urlsafe(48),
                                         'role': 'admin' if name == 'services_agent' else 'system'}
                                  for name in ('apiserver', 'fileserver', 'webserver', 'services_agent')}}
        secure['credentials']['webserver']['revoke_in_fixed_mode'] = True
        secure['credentials']['tests'] = {'role': 'user', 'display_name': 'Default User', 'user_key': secrets.token_hex(16),
                                          'user_secret': secrets.token_urlsafe(48), 'revoke_in_fixed_mode': True}
    agent = secure['credentials']['services_agent']
    key, secret = env.get('CLEARML_AGENT_ACCESS_KEY'), env.get('CLEARML_AGENT_SECRET_KEY')
    if bool(key) != bool(secret):
        raise Error('Configure both agent credential values or leave both empty')
    if key:
        agent.update(user_key=key, user_secret=secret)
    secure['elastic'] = {'user': need(env, 'ELASTICSEARCH_USERNAME'), 'password': need(env, 'ELASTICSEARCH_PASSWORD')}
    secure['redis'] = {name: {'password': need(env, 'REDIS_PASSWORD')} for name in ('apiserver', 'workers', 'fileserver')}
    write_json(secure_path, secure)
    elastic = []
    for url in need(env, 'ELASTICSEARCH_URLS').split(','):
        parsed = urlparse(url.strip())
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
            raise Error('ELASTICSEARCH_URLS requires http(s) URLs without embedded credentials')
        if parsed.query or parsed.fragment:
            raise Error('Elasticsearch URLs must not contain query strings or fragments')
        node = {'host': parsed.hostname, 'port': parsed.port or (443 if parsed.scheme == 'https' else 9200), 'scheme': parsed.scheme}
        if parsed.path.strip('/'):
            node['path_prefix'] = parsed.path.rstrip('/')
        elastic.append(node)
    schemes = {node['scheme'] for node in elastic}
    if len(schemes) > 1:
        raise Error('ELASTICSEARCH_URLS must share one scheme; TLS options apply to the whole cluster')
    # elasticsearch-py 8 accepts only scheme/host/port/path_prefix per node; TLS settings are client arguments.
    es_args = {'timeout': 60, 'max_retries': 3, 'retry_on_timeout': True}
    if schemes == {'https'}:
        es_args.update(verify_certs=True, ca_certs='/etc/pki/tls/certs/ca-bundle.crt')
    hosts = {'mongo': {'backend': {'host': need(env, 'MONGO_BACKEND_URI')}, 'auth': {'host': need(env, 'MONGO_AUTH_URI')}},
             'elastic': {name: {'hosts': elastic, 'args': es_args} for name in ('events', 'workers')},
             # The fileserver shares this directory and reads the fileserver alias plus api_server.
             'redis': {name: {'host': need(env, 'REDIS_HOST'), 'port': int(need(env, 'REDIS_PORT')), 'db': db}
                       for name, db in [('apiserver', 0), ('workers', 4), ('fileserver', 8)]},
             'fileserver': 'http://fileserver:8081', 'api_server': 'http://apiserver:8008'}
    if boolean(env, 'REDIS_TLS'):
        for value in hosts['redis'].values():
            value.update(ssl=True, ssl_ca_certs='/etc/pki/tls/certs/ca-bundle.crt', ssl_cert_reqs='required')
    write_json(generated / 'config/hosts.conf', hosts)
    write_json(generated / 'config/apiserver.conf', {'pre_populate': {'enabled': False}})
    write_json(generated / 'config/services.conf', {'async_urls_delete': {'enabled': True, 'fileserver': {'url_prefixes': [need(env, 'CLEARML_FILES_URL')]}}})
    write_json(generated / 'config/fileserver.conf', {'delete': {'allow_batch': True}})
    # The UI authenticates user creation at login with the webserver system credential; upstream ships a public one.
    web = secure['credentials']['webserver']
    write_json(generated / 'configuration.json', {'apiBaseUrl': '/api', 'fileBaseUrl': need(env, 'CLEARML_FILES_URL'),
                                                     'userKey': web['user_key'], 'userSecret': web['user_secret'], 'displayedServerUrls': {'apiServer': need(env, 'CLEARML_API_URL'), 'filesServer': need(env, 'CLEARML_FILES_URL')}, 'hideUpdateNotice': True, 'showSurvey': False, 'GTM_ID': None, 'displayTips': False,
                                                     # enterpriseServer only hides the GitHub star widget (an api.github.com fetch) and a preferences notice.
                                                     'enterpriseServer': True})
    # Paths are resolved once, so moving the repository requires rerendering.
    config_dir = str((generated / 'config').resolve())
    data_dir = str((root / need(env, 'DATA_DIR')).resolve())
    log_dir = str((root / need(env, 'LOG_DIR')).resolve())
    common = {'image': need(env, 'SERVER_IMAGE'), 'pull_policy': 'never', 'restart': 'unless-stopped',
              'environment': {'CLEARML_CONFIG_DIR': '/opt/clearml/config', 'CLEARML_SERVER_DEPLOYMENT_TYPE': 'linux'},
              'volumes': [f'{config_dir}:/run/clearml-config:ro,z', f'{data_dir}:/mnt/fileserver:z', f'{log_dir}:/var/log/clearml:z']}
    services = {}
    def health(port, endpoint):
        return {'test': ['CMD', 'curl', '--fail', '--silent', f'http://localhost:{port}/{endpoint}'], 'interval': '10s', 'timeout': '5s', 'retries': 30, 'start_period': '60s'}
    def port(key, target):
        return [f'{env.get("BIND_ADDRESS", "0.0.0.0")}:{need(env,key)}:{target}']
    for name in ('apiserver', 'fileserver', 'async_delete'):
        services[name] = copy.deepcopy(common)
        services[name]['command'] = [name]
    services['apiserver'].update(ports=port('API_PORT', 8008), healthcheck=health(8008, 'debug.ping'))
    services['fileserver'].update(ports=port('FILES_PORT', 8081), healthcheck=health(8081, ''))
    services['async_delete']['depends_on'] = {n: {'condition': 'service_healthy'} for n in ('apiserver', 'fileserver')}
    services['webserver'] = {'image': need(env, 'WEB_IMAGE'), 'pull_policy': 'never', 'restart': 'unless-stopped',
                             'ports': port('WEB_PORT', 8080), 'depends_on': {n: {'condition': 'service_healthy'} for n in ('apiserver', 'fileserver')},
                             'volumes': [f'{generated.resolve()}/configuration.json:/run/site-configuration.json:ro,z'],
                             'healthcheck': {'test': ['CMD', 'curl', '-fsS', 'http://localhost:8080/'], 'interval': '10s', 'timeout': '5s', 'retries': 10}}
    if boolean(env, 'ENABLE_AGENT', True):
        work = need(env, 'AGENT_WORK_DIR')
        if not Path(work).is_absolute():
            raise Error('AGENT_WORK_DIR must be an absolute host path for sibling task containers')
        agent_config = {'api': {'api_server': need(env, 'CLEARML_API_URL'), 'web_server': need(env, 'CLEARML_WEB_URL'),
                                'files_server': need(env, 'CLEARML_FILES_URL'), 'credentials': {'access_key': agent['user_key'], 'secret_key': agent['user_secret']}},
                        'agent': {'package_manager': {'type': 'pip', 'pip_version': '==' + (env.get('PIP_VERSION') or '25.2'), 'pytorch_resolve': 'none', 'extra_index_url': []}, 'docker_force_pull': False,
                                  'default_docker': {'image': need(env, 'TASK_IMAGE'), 'match_rules': []}, 'disable_ssh_mount': True, 'docker_install_opencv_libs': False, 'docker_init_bash_script': ['test -x /opt/venv/bin/python'], 'bootstrap': {'use_bootstrap': False, 'check_for_latest': False}, 'extra_docker_arguments': ['--pull=never', '-e', 'PIP_INDEX_URL=' + need(env, 'PIP_INDEX_URL'), '-e', 'PIP_EXTRA_INDEX_URL=', '-e', 'PIP_DISABLE_PIP_VERSION_CHECK=1', '-e', 'CLEARML_AGENT_SKIP_PYTHON_ENV_INSTALL=1']}}
        write_json(generated / 'agent.conf', agent_config)
        services['agent-services'] = {'image': need(env, 'AGENT_IMAGE'), 'pull_policy': 'never', 'restart': 'unless-stopped',
            'command': ['daemon', '--foreground', '--services-mode', '--cpu-only', '--queue', 'services', '--create-queue', '--docker', need(env, 'TASK_IMAGE')],
            'depends_on': {'apiserver': {'condition': 'service_healthy'}},
            # host:container mapping lets sibling task containers mount the agent's work files.
            'environment': {'CLEARML_CONFIG_FILE': '/etc/clearml.conf', 'CLEARML_AGENT_DOCKER_HOST_MOUNT': f'{work}:/root/.clearml',
                            'CLEARML_AGENT_DOCKER_AGENT_REPO': '--no-index --find-links=/opt/wheels clearml-agent',
                            'CLEARML_AGENT_SKIP_PIP_VENV_INSTALL': '/opt/venv/bin/python',
                            'PIP_INDEX_URL': need(env, 'PIP_INDEX_URL'), 'PIP_EXTRA_INDEX_URL': '', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
                            'CLEARML_AGENT_DOCKER_IMAGE': need(env, 'TASK_IMAGE'), 'OFFLINE_TASK_IMAGE': need(env, 'TASK_IMAGE')},
            'volumes': [f'{generated.resolve()}/agent.conf:/etc/clearml.conf:ro,z',
                        f'{need(env, "DOCKER_SOCKET")}:/var/run/docker.sock', f'{work}:/root/.clearml:z']}
    write_json(generated / 'compose.json', {'name': 'clearml', 'services': services})
    return services
