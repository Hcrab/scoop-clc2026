"""Stdio transport for browser acceptance against the real app without a key.

No TCP listener is opened. Requests run through FastAPI TestClient and the
configured demonstration database, including real recomputation and Undo.
"""
import base64
import json
import os
import sys

from scoop.main import app
from scoop.ai.chat import provider_info
from fastapi.testclient import TestClient

# dotenv has loaded the project configuration; this test process has no key.
os.environ['GEMINI_API_KEY'] = ''
assert not provider_info()['live']

with TestClient(app) as client:
    for line in sys.stdin:
        message = json.loads(line)
        try:
            response = client.request(message['method'], message['path'],
                                      content=message.get('body'),
                                      headers={'Content-Type': 'application/json'})
            result = {'id': message['id'], 'status': response.status_code,
                      'headers': {k: v for k, v in response.headers.items()
                                  if k not in {'content-length', 'content-encoding', 'transfer-encoding'}},
                      'body': base64.b64encode(response.content).decode('ascii')}
        except Exception as error:
            result = {'id': message['id'], 'error': type(error).__name__}
        sys.stdout.write(json.dumps(result) + '\n')
        sys.stdout.flush()
