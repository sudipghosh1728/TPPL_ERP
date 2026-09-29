import json
import threading
import unittest
import urllib.request
import urllib.error
import access
import server
from api.index import handler
from mongo_test_support import test_store, clean


class VercelTests(unittest.TestCase):
    def test_hosted_login_and_setup_protection(self):
        previous = server.STORE
        store = test_store()
        server.STORE = store
        server.initialize(migrate_local=False)
        store.run(lambda c: access.create_user(c, dict(name='Cloud Admin', username='cloudadmin', password='Hosted-test-password-123', role='Admin')))
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{http.server_port}'
        try:
            request = urllib.request.Request(url+'/api/auth/setup', data=b'{}', headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
            request = urllib.request.Request(url+'/api/auth/login', data=json.dumps(dict(username='cloudadmin', password='Hosted-test-password-123')).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                cookie = response.headers['Set-Cookie']
                self.assertIn('; Secure', cookie)
                self.assertIn('HttpOnly', cookie)
            with urllib.request.urlopen(urllib.request.Request(url+'/api/state', headers={'Cookie':cookie.split(';')[0]})) as response:
                self.assertEqual(json.load(response)['database']['engine'], 'MongoDB')
        finally:
            http.shutdown()
            http.server_close()
            clean(store)
            server.STORE = previous
