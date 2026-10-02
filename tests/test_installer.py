import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from common import Error, env_file, fetch_ca_bundle, local_image, output_tag, proxy_args
import sources
from render import render

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def clearml_env(self):
        env = env_file(ROOT/'.env.example')
        return {k:v.replace('CHANGE_ME','test-password-0123456789') for k,v in env.items()}
    def source(self):
        (self.root/'sources.json').write_text(json.dumps({'clearml-web': {'repository':'clearml/clearml-web','ref':'test'}}))
        return self.root/'clearml-web-abcdef0.zip'
    def test_dotenv_is_literal(self):
        path = self.root/'.env'; path.write_text("VALUE='$(touch /tmp/never-run-this)'\n")
        self.assertEqual(env_file(path)['VALUE'],'$(touch /tmp/never-run-this)')
    def test_duplicate_env_rejected(self):
        path=self.root/'.env';path.write_text('A=1\nA=2\n')
        with self.assertRaises(Error):env_file(path)
    def test_missing_source_never_downloads_offline(self):
        self.source()
        with patch('urllib.request.urlopen') as network:
            with self.assertRaises(Error): sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'})
            network.assert_not_called()
    def test_zip_reused_and_tree_locked(self):
        path=self.source()
        with zipfile.ZipFile(path,'w') as archive: archive.writestr('web-abcdef0/pnpm-lock.yaml','lockfileVersion: 9')
        with patch('urllib.request.urlopen') as network:
            sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'true'})
            sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'true'})
            sources.verify(self.root)
            network.assert_not_called()
        (self.root/'clearml-web/pnpm-lock.yaml').write_text('tampered')
        with self.assertRaises(Error): sources.verify(self.root)
        with self.assertRaises(Error): sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'true','STRICT_SOURCES':'true'})
    def test_path_traversal_zip_rejected(self):
        archive=self.source()
        with zipfile.ZipFile(archive,'w') as bundle: bundle.writestr('../escape','bad')
        with self.assertRaises(Error):sources.extract(archive,self.root/'out')
        self.assertFalse((self.root.parent/'escape').exists())
    def test_symlink_inside_root_kept_and_escaping_symlink_rejected(self):
        archive=self.source()
        link=zipfile.ZipInfo('web-abcdef0/docs/example.py');link.external_attr=(0o120777<<16)
        with zipfile.ZipFile(archive,'w') as bundle:
            bundle.writestr('web-abcdef0/pnpm-lock.yaml','lockfileVersion: 9');bundle.writestr(link,'../pnpm-lock.yaml')
        sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'});sources.verify(self.root)
        self.assertEqual(os.readlink(self.root/'clearml-web/docs/example.py'),'../pnpm-lock.yaml')
        shutil.rmtree(self.root/'clearml-web');archive.unlink();(self.root/'sources.lock.json').unlink()
        link=zipfile.ZipInfo('web-abcdef0/escape');link.external_attr=(0o120777<<16)
        with zipfile.ZipFile(archive,'w') as bundle: bundle.writestr(link,'../../etc/passwd')
        with self.assertRaises(Error):sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'})
    def test_release_zip_accepted_when_tree_matches_lock(self):
        archive=self.source()
        with zipfile.ZipFile(archive,'w') as a: a.writestr('clearml-web-abcdef0/pnpm-lock.yaml','lockfileVersion: 9')
        sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'})
        shutil.rmtree(self.root/'clearml-web');archive.unlink()
        release=self.root/'clearml-web-2.5.zip'
        with zipfile.ZipFile(release,'w',compression=zipfile.ZIP_DEFLATED) as a: a.writestr('clearml-web-2.5/pnpm-lock.yaml','lockfileVersion: 9')
        sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'})
        self.assertEqual(json.loads((self.root/'sources.lock.json').read_text())['clearml-web']['origin'],'clearml-web-2.5.zip')
        shutil.rmtree(self.root/'clearml-web')
        with zipfile.ZipFile(release,'w') as a: a.writestr('clearml-web-2.5/pnpm-lock.yaml','different')
        with self.assertRaises(Error):sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false','STRICT_SOURCES':'true'})
        sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'})  # default: accepted, lock updated
        self.assertEqual((self.root/'clearml-web/pnpm-lock.yaml').read_text(),'different');sources.verify(self.root)
    def test_multiple_archives_rejected(self):
        self.source().touch();(self.root/'clearml-web-0123abc.zip').touch()
        with self.assertRaises(Error):sources.prepare(self.root,{})
    def test_archive_prefix_does_not_match_sibling_sources(self):
        (self.root/'sources.json').write_text(json.dumps({'clearml': {'repository':'clearml/clearml','ref':'test'}}))
        with zipfile.ZipFile(self.root/'clearml-0123abc.zip','w') as a: a.writestr('clearml/setup.py','')
        (self.root/'clearml-server-0123abc.zip').touch();(self.root/'clearml-web-0123abc.zip').touch()
        sources.prepare(self.root,{'ALLOW_SOURCE_DOWNLOADS':'false'})
        self.assertTrue((self.root/'clearml/setup.py').is_file())
    def test_blank_allowlist_disables_registry_check(self):
        local_image('almalinux:9',{'ALLOWED_HOSTS':''}); local_image('registry.example/base:9',{})
        with self.assertRaises(Error):local_image('registry.example/base:latest',{'ALLOWED_HOSTS':''})
    def test_ca_bundle_blank_means_no_certs(self):
        self.assertEqual(fetch_ca_bundle(self.root,{'TLS_CA_BUNDLE_URL':''}),[])
        for name in ('tls-ca-bundle.zip','tls-ca-bundle.pem'): self.assertEqual((self.root/'generated/trust'/name).stat().st_size,0)
        (self.root/'config').mkdir()
        with zipfile.ZipFile(self.root/'config/tls-ca-bundle.zip','w') as z: z.writestr('readme.txt','no certs')
        with self.assertRaises(Error):fetch_ca_bundle(self.root,{})
        with zipfile.ZipFile(self.root/'config/tls-ca-bundle.zip','w') as z: z.writestr('certs/root-ca.pem','-----BEGIN CERTIFICATE-----')
        (self.root/'config/tls-ca-bundle.pem').write_text('-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n')
        self.assertEqual(fetch_ca_bundle(self.root,{}),['zip','pem'])
        self.assertTrue((self.root/'generated/trust/tls-ca-bundle.pem').stat().st_size)
        with self.assertRaises(Error):fetch_ca_bundle(self.root,{'TLS_CA_BUNDLE_URL':'ftp://x/y.zip'})
    def test_ca_bundle_download_failure_is_explicit(self):
        unreachable='http://127.0.0.1:9/tls-ca-bundle.zip'
        with self.assertRaises(Error):fetch_ca_bundle(self.root,{'TLS_CA_BUNDLE_URL':unreachable})
        (self.root/'config').mkdir(exist_ok=True)
        with zipfile.ZipFile(self.root/'config/tls-ca-bundle.zip','w') as z: z.writestr('ca.crt','-----BEGIN CERTIFICATE-----')
        self.assertEqual(fetch_ca_bundle(self.root,{'TLS_CA_BUNDLE_URL':unreachable}),['zip'])
    def test_output_tags_need_no_registry(self):
        output_tag('clearml/server:local-1'); output_tag('server:1')
        with self.assertRaises(Error):output_tag('clearml/server')
        with self.assertRaises(Error):output_tag('clearml/server:latest')
    def test_proxy_blank_means_none(self):
        self.assertEqual(proxy_args({'HTTP_PROXY':'','HTTPS_PROXY':''}),{})
        self.assertEqual(proxy_args({'HTTPS_PROXY':'http://proxy.example:3128','NO_PROXY':'localhost'}),
                         {'HTTPS_PROXY':'http://proxy.example:3128','https_proxy':'http://proxy.example:3128','NO_PROXY':'localhost','no_proxy':'localhost'})
    def test_unlisted_image_registry_rejected(self):
        with self.assertRaises(Error):local_image('almalinux:9',{'ALLOWED_HOSTS':'registry.example'})
        with self.assertRaises(Error):local_image('registry.example/base:latest',{'ALLOWED_HOSTS':'registry.example'})
        local_image('registry.example/base:9',{'ALLOWED_HOSTS':'registry.example'})
    def test_clearml_has_no_database_services(self):
        services=render(self.root,self.clearml_env())
        self.assertEqual(set(services),{'apiserver','fileserver','webserver','async_delete','agent-services'})
        self.assertTrue(all(s['pull_policy']=='never' for s in services.values()))
    def test_secrets_preserved_and_private(self):
        env=self.clearml_env();render(self.root,env)
        path=self.root/'generated/config/secure.conf';first=path.read_bytes()
        render(self.root,env);self.assertEqual(first,path.read_bytes());self.assertEqual(path.stat().st_mode & 0o777,0o600)
    def test_shared_config_covers_fileserver_and_replaces_default_credentials(self):
        env=self.clearml_env();render(self.root,env)
        hosts=json.loads((self.root/'generated/config/hosts.conf').read_text())
        secure=json.loads((self.root/'generated/config/secure.conf').read_text())
        self.assertEqual(hosts['redis']['fileserver']['db'],8);self.assertEqual(hosts['api_server'],'http://apiserver:8008')
        self.assertEqual(secure['redis']['fileserver']['password'],env['REDIS_PASSWORD'])
        self.assertEqual(set(secure['credentials']),{'apiserver','fileserver','webserver','services_agent','tests'})
        self.assertNotIn('62T8CP7HGBC6647XF9314C2VY67RJO',json.dumps(secure))
    def test_web_configuration_disables_external_calls(self):
        render(self.root,self.clearml_env());c=json.loads((self.root/'generated/web/configuration.json').read_text())
        self.assertTrue(c['enterpriseServer']);self.assertTrue(c['hideUpdateNotice']);self.assertIsNone(c['GTM_ID'])
        for n in ('configuration.json','credentials.json'): self.assertEqual((self.root/'generated/web'/n).stat().st_mode & 0o777, 0o644)
        secure=json.loads((self.root/'generated/config/secure.conf').read_text())
        creds=json.loads((self.root/'generated/web/credentials.json').read_text())
        self.assertEqual(creds['userKey'],secure['credentials']['webserver']['user_key']);self.assertNotIn('userKey',c)
    def test_pre_populate_only_with_archives(self):
        env=self.clearml_env();services=render(self.root,env)
        self.assertFalse(json.loads((self.root/'generated/config/apiserver.conf').read_text())['pre_populate']['enabled'])
        (self.root/'config/pre-populate').mkdir(parents=True);(self.root/'config/pre-populate/examples.zip').write_bytes(b'PK')
        services=render(self.root,env)
        self.assertTrue(json.loads((self.root/'generated/config/apiserver.conf').read_text())['pre_populate']['enabled'])
        self.assertTrue(any(v.endswith('/opt/clearml/db-pre-populate:ro,z') for v in services['apiserver']['volumes']))
    def test_agent_service_stays_offline(self):
        env=self.clearml_env();services=render(self.root,env);agent=services['agent-services']
        self.assertIn('--cpu-only',agent['command']);self.assertIn('--create-queue',agent['command'])
        self.assertEqual(agent['environment']['CLEARML_AGENT_DOCKER_HOST_MOUNT'],env['AGENT_WORK_DIR']+':/root/.clearml')
        self.assertTrue(agent['environment']['CLEARML_AGENT_DOCKER_AGENT_REPO'].startswith('--no-index'))
        conf=json.loads((self.root/'generated/agent/clearml.conf').read_text())
        self.assertEqual(conf['agent']['package_manager']['pip_version'],'=='+env['PIP_VERSION'])
        self.assertIn('--pull=never',conf['agent']['extra_docker_arguments'])
    def test_configuration_escapes_password(self):
        env=self.clearml_env();env['REDIS_PASSWORD']='x"\\${hello}'
        render(self.root,env)
        secure=json.loads((self.root/'generated/config/secure.conf').read_text())
        self.assertEqual(secure['redis']['workers']['password'],env['REDIS_PASSWORD'])
    def test_partial_agent_credentials_rejected(self):
        env=self.clearml_env();env['CLEARML_AGENT_ACCESS_KEY']='key'
        with self.assertRaises(Error):render(self.root,env)
    def test_elastic_tls_options_are_client_arguments(self):
        env = self.clearml_env()
        env['ELASTICSEARCH_URLS'] = 'https://secure:9243/elastic,https://second:9243/elastic'
        render(self.root, env)
        cluster = json.loads((self.root/'generated/config/hosts.conf').read_text())['elastic']['events']
        self.assertEqual(cluster['args']['ca_certs'], '/etc/pki/tls/certs/ca-bundle.crt')
        self.assertTrue(cluster['args']['verify_certs'])
        self.assertEqual(set(cluster['hosts'][0]), {'host', 'port', 'scheme', 'path_prefix'})
        self.assertEqual(cluster['hosts'][0]['path_prefix'], '/elastic')
        env['ELASTICSEARCH_URLS'] = 'http://plain:9200'
        render(self.root, env)
        cluster = json.loads((self.root/'generated/config/hosts.conf').read_text())['elastic']['events']
        self.assertNotIn('ca_certs', cluster['args'])
        env['ELASTICSEARCH_URLS'] = 'http://plain:9200,https://secure:9243'
        with self.assertRaises(Error): render(self.root, env)
    def test_elastic_query_string_rejected(self):
        env = self.clearml_env()
        env['ELASTICSEARCH_URLS'] = 'https://secure:9243/?token=secret'
        with self.assertRaises(Error): render(self.root, env)
    @unittest.skipUnless(shutil.which('docker'),'Docker CLI required (daemon not needed)')
    def test_compose_models_valid(self):
        render(self.root,self.clearml_env())
        subprocess.run(['docker','compose','-f',str(self.root/'generated/compose.json'),'config','--quiet'],check=True)

class DockerPolicyTests(unittest.TestCase):
    def setUp(self):
        loader=importlib.machinery.SourceFileLoader('docker_policy',str(ROOT/'scripts/docker-policy.py'))
        spec=importlib.util.spec_from_loader(loader.name,loader)
        self.module=importlib.util.module_from_spec(spec);loader.exec_module(self.module)
    def test_only_approved_task_image(self):
        result=self.module.validate(['run','--rm','-e','A=B','registry/task:1','python','job.py'],'registry/task:1')
        self.assertEqual(result[1],'--pull=never')
    def test_public_task_rejected(self):
        with self.assertRaises(ValueError):self.module.validate(['run','ubuntu:latest'],'registry/task:1')
    def test_pull_rejected(self):
        with self.assertRaises(ValueError):self.module.validate(['pull','registry/task:1'],'registry/task:1')
    def test_pull_option_rejected(self):
        with self.assertRaises(ValueError):self.module.validate(['run','--pull=always','registry/task:1'],'registry/task:1')
    def test_unknown_flag_fails_closed(self):
        with self.assertRaises(ValueError):self.module.validate(['run','--unrecognized','registry/task:1'],'registry/task:1')

if __name__=='__main__':unittest.main()
