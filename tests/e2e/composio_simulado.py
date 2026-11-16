#!/usr/bin/env python3
"""Composio SIMULADO para probar la interfaz de la llave sin una llave real.

Solo 127.0.0.1. Acepta exactamente una llave de prueba (argumento 1) y rechaza todo lo demás
con 401, igual que el servicio real. No toca ninguna cuenta: devuelve cuentas ficticias.
Uso:  python3 tests/e2e/composio_simulado.py ck_llave_de_prueba 8799
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys

KEY, PORT = sys.argv[1], int(sys.argv[2])
APPS = ('googledrive', 'googlesheets', 'gmail', 'googlecalendar', 'instagram', 'github')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0')) or 0) or b'{}')
        if self.path != '/mcp' or self.headers.get('x-consumer-api-key') != KEY:
            return self.send(401, {'error': 'Missing or invalid x-consumer-api-key'})
        method = body.get('method')
        if method == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'composio-simulado', 'version': '0'}}
        elif method == 'tools/list':
            result = {'tools': [{'name': 'COMPOSIO_SEARCH_TOOLS'}, {'name': 'COMPOSIO_MULTI_EXECUTE_TOOL'}]}
        elif method == 'tools/call' and body['params']['name'] == 'COMPOSIO_SEARCH_TOOLS':
            data = {'data': {'session': {'id': 'simulada'}, 'toolkit_connection_statuses': [
                {'toolkit': name, 'has_active_connection': True,
                 'accounts': [{'id': name + '_simulada', 'status': 'ACTIVE', 'user_info': {'email': 'cuenta.simulada@example.com'}}]}
                for name in APPS]}}
            result = {'content': [{'type': 'text', 'text': json.dumps(data)}]}
        elif method == 'notifications/initialized':
            return self.send(202, {})
        else:
            result = {'isError': True, 'content': [{'type': 'text', 'text': '{"error":"no simulado"}'}]}
        self.send(200, {'jsonrpc': '2.0', 'id': body.get('id'), 'result': result}, {'Mcp-Session-Id': 'simulada'})

    def send(self, status, payload, extra=None):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
