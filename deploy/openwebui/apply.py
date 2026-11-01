#!/usr/bin/env python3
"""Apply only the SMARTINI's proxy appearance overlay; retain the old proxy for rollback."""
import argparse
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

PROXY = 'minisforum-meeting-proxy'
BASE = Path(__file__).resolve().parent
STATE = BASE / 'status.json'


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Docker operation failed: ' + args[0] + ' (details retained by Docker)')
    return result.stdout.strip()


class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(40)
        self.sock.connect('/var/run/docker.sock')


def create(name, config):
    connection = DockerConnection('localhost', timeout=40)
    try:
        connection.request('POST', '/containers/create?name=' + name,
                           body=json.dumps(config), headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = json.loads(response.read())
        if response.status != 201:
            raise RuntimeError('Docker refused the candidate configuration; no active proxy changed')
        return data['Id']
    finally:
        connection.close()


def get(path, port=8088):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=15) as response:
        return response.read(), response.headers


def save(state):
    temp = BASE / 'status.json.tmp'
    temp.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    temp.chmod(0o644)
    temp.replace(STATE)


def inspect(name):
    return json.loads(docker('inspect', name))[0]


def verify():
    version, _ = get('/api/version')
    assert json.loads(version)['version'] == '0.12.3', 'Unexpected WebUI version'
    health, _ = get('/meeting-proxy-health')
    assert b'meeting proxy ready' in health, 'Proxy health failed'
    page, headers = get('/')
    assert page.count(b'/smartinis-ui/smartinis-ui.js') == 1, 'Script injection missing/duplicated'
    assert page.count(b'/smartinis-ui/smartinis-ui.css') == 1, 'Stylesheet injection missing/duplicated'
    assert 'text/html' in headers.get('Content-Type', ''), 'Unexpected WebUI content type'
    for name, mime in [('smartinis-ui.js', 'javascript'), ('smartinis-ui.css', 'text/css'),
                       ('smartinis-logo.png', 'image/png')]:
        content, response_headers = get('/smartinis-ui/' + name)
        assert content == (BASE / 'public' / name).read_bytes(), 'Asset bytes differ: ' + name
        assert mime in response_headers.get('Content-Type', ''), 'Incorrect asset MIME: ' + name
    worker, _ = get('/health', 8765)
    assert json.loads(worker).get('ok') is True, 'Worker health failed'


def restore(state):
    current = inspect(PROXY)
    assert current['Id'] == state['new_id'], 'Proxy changed since deployment; refusing rollback'
    docker('stop', '--time', '30', PROXY)
    docker('rename', PROXY, state['candidate_name'])
    docker('rename', state['old_name'], PROXY)
    docker('start', PROXY)
    state['status'] = 'rolled_back'
    save(state)


def apply():
    assert not STATE.exists(), 'This rollout was already attempted; inspect status.json first'
    version, _ = get('/api/version')
    assert json.loads(version)['version'] == '0.12.3', 'Adapter supports only 0.12.3'
    old = inspect(PROXY)
    assert old['State']['Running'], 'Original proxy is not running'
    assert old['HostConfig']['NetworkMode'] == 'host', 'Unexpected proxy network; inspect manually'
    assert not old['HostConfig'].get('AutoRemove'), 'Proxy uses auto-remove; refusing'
    assert old['HostConfig']['RestartPolicy']['Name'] == 'unless-stopped', 'Unexpected restart policy; inspect manually'
    assert not (old['Config'].get('Labels') or {}).get('com.docker.compose.project'), 'Compose-managed proxy needs a Compose rollout'
    assert not old['HostConfig'].get('ContainerIDFile'), 'Proxy has an external ID file; refusing'
    assert all(not mount['RW'] for mount in old['Mounts']), 'Writable proxy mounts need manual review'
    mounts = [mount for mount in old['Mounts']
              if mount['Destination'] == '/etc/nginx/conf.d/default.conf']
    assert len(mounts) == 1 and mounts[0]['Type'] == 'bind', 'Expected a read-only config file mount'
    original_path = Path(mounts[0]['Source'])
    original = original_path.read_text(encoding='utf-8')
    assert original.count('    location / {') == 1, 'Unknown root route layout'
    assert original.count('    location /meeting-ui/ {') == 1, 'Unknown worker route layout'
    assert 'sub_filter' not in original and '/smartinis-ui/' not in original, 'Existing customization; refusing overwrite'
    assert 'proxy_set_header Accept-Encoding' not in original, 'Existing compression setting needs review'
    page, headers = get('/')
    assert page.count(b'</head>') == 1, 'Unknown HTML layout'
    # Do not alter any security policy; ask for a specific CSP review if one exists.
    assert not headers.get('Content-Security-Policy'), 'CSP requires manual compatibility review'
    worker_before, _ = get('/health', 8765)
    assert json.loads(worker_before).get('ok') is True, 'Worker is unhealthy; defer rollout'
    manifest = json.loads((BASE / 'SHA256SUMS.json').read_text())
    for relative, expected in manifest.items():
        asset = (BASE / relative).resolve()
        assert asset.is_relative_to(BASE), 'Asset path escaped rollout directory'
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == expected, 'Staged asset hash mismatch'
    backup = BASE / 'nginx.original.conf'
    backup.write_text(original, encoding='utf-8')
    backup.chmod(0o600)
    html_filter = (BASE / 'proxy-html.conf').read_text(encoding='utf-8')
    asset_route = (BASE / 'proxy-locations.conf').read_text(encoding='utf-8')
    # Inline the reviewed snippets; no new configuration include mount is needed.
    candidate_text = original.replace('    location / {',
        asset_route + '\n    location / {\n' + html_filter, 1)
    candidate = BASE / 'nginx.appearance.conf'
    candidate.write_text(candidate_text, encoding='utf-8')
    candidate.chmod(0o644)
    config = copy.deepcopy(old['Config'])
    config['Image'] = old['Image']  # Use installed immutable image, never pull.
    host = copy.deepcopy(old['HostConfig'])
    replaced = 0
    for index, binding in enumerate(host.get('Binds') or []):
        parts = binding.rsplit(':', 2)
        if len(parts) >= 2 and parts[1] == mounts[0]['Destination']:
            assert parts[0] == str(original_path), 'Mount source mismatch'
            parts[0] = str(candidate)
            host['Binds'][index] = ':'.join(parts)
            replaced += 1
    for mount in host.get('Mounts') or []:
        if mount.get('Target') == mounts[0]['Destination']:
            mount['Source'] = str(candidate)
            replaced += 1
    assert replaced == 1, 'Could not replace exactly one proxy config mount'
    host.setdefault('Binds', [])
    host['Binds'] = (host['Binds'] or []) + [str(BASE / 'public') + ':/opt/smartinis-ui:ro']
    config['HostConfig'] = host
    tag = str(int(time.time()))
    candidate_name = PROXY + '-ui-candidate-' + tag
    old_name = PROXY + '-before-ui-' + tag
    test_name = candidate_name + '-check'
    test = copy.deepcopy(config)
    test['Cmd'] = ['nginx', '-t']
    test['HostConfig']['RestartPolicy'] = {'Name': 'no', 'MaximumRetryCount': 0}
    test['HostConfig']['NetworkMode'] = 'none'
    create(test_name, test)
    try:
        docker('start', test_name)
        assert docker('wait', test_name) == '0', 'Candidate nginx validation failed; active proxy unchanged'
    finally:
        docker('rm', test_name)  # Only our stopped, temporary validation container.
    new_id = create(candidate_name, config)
    state = {'status': 'prepared', 'old_id': old['Id'], 'new_id': new_id,
             'old_name': old_name, 'candidate_name': candidate_name}
    save(state)
    switched = False
    renamed = False
    try:
        docker('stop', '--time', '30', PROXY)
        docker('rename', PROXY, old_name)
        renamed = True
        docker('rename', candidate_name, PROXY)
        switched = True
        docker('start', PROXY)
        for attempt in range(15):
            try:
                verify()
                break
            except Exception:
                if attempt == 14:
                    raise
                time.sleep(1)
        state['status'] = 'deployed_http_verified'
        save(state)
        print('DEPLOYED: proxy HTML, assets, WebUI version and worker health verified.')
        print('Open WebUI and the worker were not restarted. Old proxy retained for rollback.')
    except Exception:
        if switched:
            restore(state)
        elif renamed:
            docker('rename', old_name, PROXY)
            docker('start', PROXY)
        else:
            docker('start', PROXY)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--apply', action='store_true')
    actions.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo in your SSH terminal; do not share your password.')
    if args.rollback:
        restore(json.loads(STATE.read_text()))
        print('Original proxy restored. No application data changed.')
    else:
        apply()
