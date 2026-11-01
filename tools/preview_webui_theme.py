#!/usr/bin/env python3
"""Serve a synthetic, loopback-only appearance preview; never contacts the server."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    '/': (ROOT / 'assets/openwebui/preview.html', 'text/html; charset=utf-8'),
    '/smartinis-ui/smartinis-ui.css': (ROOT / 'assets/openwebui/smartinis-ui.css', 'text/css'),
    '/smartinis-ui/smartinis-ui.js': (ROOT / 'assets/openwebui/smartinis-ui.js', 'text/javascript'),
    '/smartinis-ui/smartinis-logo.png': (ROOT / 'assets/brand/smartinis-logo.png', 'image/png'),
    '/api/models/model/profile/image': (ROOT / 'assets/brand/smartinis-logo.png', 'image/png'),
}


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split('?', 1)[0]
        if route == '/api/version':
            content, kind = b'{"version":"0.12.3"}', 'application/json'
        elif route in FILES:
            path, kind = FILES[route]
            content = path.read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8099)
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Preview)
    print(f'Synthetic preview: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
