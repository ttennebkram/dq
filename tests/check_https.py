import base64
import http.server
import os
import ssl
import subprocess
import tempfile
import sys
import threading

# Run this test harness with a modern Python (3.6+). Optional arguments select
# the DQ interpreters to exercise, including Python 3.4.10.
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with tempfile.TemporaryDirectory() as directory:
    cert = os.path.join(directory, 'server.pem')
    key = os.path.join(directory, 'server.key')
    config = os.path.join(directory, 'openssl.cnf')
    with open(config, 'w') as stream:
        stream.write('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\nbasicConstraints=critical,CA:TRUE\n')
    subprocess.check_call(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-config', config, '-keyout', key, '-out', cert], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            expected = 'Basic ' + base64.b64encode(b'mark:secret').decode('ascii')
            self.send_response(200 if self.headers.get('Authorization') == expected else 401)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    code = '''
import sys
from dq.connection import Connection
from dq.solr import get_json, SolrError
url, cert = sys.argv[1:]
assert get_json(url, 'select', connection=Connection('mark', 'secret', cert))['ok']
for target, connection in [(url, Connection('mark', 'secret')), (url.replace('localhost', '127.0.0.1'), Connection('mark', 'secret', cert)), (url, Connection('mark', 'wrong', cert))]:
    try:
        get_json(target, 'select', connection=connection)
    except SolrError as error:
        assert 'secret' not in str(error)
        assert 'wrong' not in str(error)
    else:
        raise AssertionError('expected verification/authentication failure')
print('PASS: trusted TLS + Basic auth; rejected untrusted cert, wrong hostname and wrong password')
'''
    env = dict(os.environ, PYTHONPATH=os.path.join(root, 'src'))
    try:
        for executable in (sys.argv[1:] or [sys.executable]):
            subprocess.check_call([executable, '-B', '-c', code, 'https://localhost:{0}/solr/files'.format(server.server_port), cert], env=env)
    finally:
        server.shutdown()
        server.server_close()
