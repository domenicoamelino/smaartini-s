"""Synthetic rollout checks: preserve config, preflight failure and automatic rollback."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('rollout', Path(__file__).resolve().parents[1] / 'deploy/openwebui/apply.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RolloutTests(unittest.TestCase):
    def exercise(self, preflight_fail=False, live_fail=False):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'public').mkdir()
            original = base / 'original.conf'
            text = 'map $http_upgrade $connection_upgrade {default upgrade; "" close;}\nserver {\n    location /meeting-ui/ { proxy_pass http://127.0.0.1:8765; }\n    location / { proxy_pass http://127.0.0.1:8080; }\n}\n'
            original.write_text(text)
            (base / 'proxy-html.conf').write_text('sub_filter_once on;')
            (base / 'proxy-locations.conf').write_text('location /smartinis-ui/ {alias /opt/smartinis-ui/;}')
            (base / 'SHA256SUMS.json').write_text('{}')
            old = {'Id': 'old-id', 'Image': 'sha256:original-image', 'State': {'Running': True},
                   'Config': {'Env': ['PRESERVE=exact'], 'Cmd': ['nginx', '-g', 'daemon off;']},
                   'Mounts': [{'Destination': '/etc/nginx/conf.d/default.conf', 'Source': str(original), 'Type': 'bind', 'RW': False}],
                   'HostConfig': {'NetworkMode': 'host', 'RestartPolicy': {'Name': 'unless-stopped'},
                                  'Binds': [str(original) + ':/etc/nginx/conf.d/default.conf:ro']}}
            calls, configs = [], []

            def docker(*args):
                calls.append(args)
                if args[0] == 'wait':
                    return '1' if preflight_fail else '0'
                return ''

            def create(name, config):
                configs.append((name, config))
                return 'test-id' if name.endswith('-check') else 'new-id'

            def get(path, port=8088):
                if path == '/api/version':
                    return b'{"version":"0.12.3"}', {}
                if port == 8765:
                    return b'{"ok":true}', {}
                return b'<html><head></head></html>', {}

            with patch.multiple(module, BASE=base, STATE=base / 'status.json'), \
                    patch.object(module, 'inspect', side_effect=[old, {'Id': 'new-id'}]), \
                    patch.object(module, 'get', side_effect=get), \
                    patch.object(module, 'create', side_effect=create), \
                    patch.object(module, 'docker', side_effect=docker), \
                    patch.object(module.time, 'sleep'), \
                    patch.object(module, 'verify', side_effect=RuntimeError('synthetic verification failure') if live_fail else None):
                if preflight_fail or live_fail:
                    with self.assertRaises((AssertionError, RuntimeError)):
                        module.apply()
                else:
                    module.apply()
                self.assertEqual(original.read_text(), text)
                self.assertFalse(any('open-webui' in arg for call in calls for arg in call))
                if preflight_fail:
                    self.assertFalse(any(call[0] == 'stop' for call in calls))
                else:
                    live = configs[-1][1]
                    self.assertEqual(live['Image'], 'sha256:original-image')
                    self.assertEqual(live['Env'], ['PRESERVE=exact'])
                    self.assertEqual(live['HostConfig']['NetworkMode'], 'host')
                    status = json.loads((base / 'status.json').read_text())
                    self.assertEqual(status['status'], 'rolled_back' if live_fail else 'deployed_http_verified')

    def test_success(self):
        self.exercise()

    def test_failed_preflight_keeps_proxy_running(self):
        self.exercise(preflight_fail=True)

    def test_failed_health_restores_original_proxy(self):
        self.exercise(live_fail=True)


if __name__ == '__main__':
    unittest.main()
