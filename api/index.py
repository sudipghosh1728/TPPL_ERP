"""Vercel HTTP entry point; uses the already provisioned Atlas database."""
import threading
from pymongo import timeout
from urllib.parse import urlparse
import server
from storage import MongoStore

_lock = threading.Lock()

class handler(server.Handler):
    def failure(self, error):
        # Log categories only: driver exception text can contain private connection details.
        message = str(error).lower()
        categories = [label for label, terms in {
            'dns': ('dns', 'resolution', 'nameserver', 'srv'),
            'tls': ('ssl', 'tls', 'certificate'),
            'authentication': ('authentication failed', 'bad auth'),
            'timeout': ('timed out', 'timeout'),
            'network': ('connection refused', 'network is unreachable'),
        }.items() if any(term in message for term in terms)]
        print('Database request failure: '+type(error).__name__+' categories='+','.join(categories), flush=True)
        return super().failure(error)

    def ready(self):
        if server.STORE is None:
            with _lock:
                if server.STORE is None:
                    server.STORE = MongoStore()

    def reply(self, data, status=200, content_type='application/json', cookie=None):
        if cookie:
            cookie += '; Secure'
        return super().reply(data, status, content_type, cookie)

    def do_GET(self):
        try:
            with timeout(20):
                self.ready()
                super().do_GET()
        except Exception as error:
            self.failure(error)

    def do_POST(self):
        if urlparse(self.path).path == '/api/auth/setup':
            return self.reply({'error': 'Create the initial Admin through the local application before deployment.'}, 403)
        try:
            with timeout(20):
                self.ready()
                super().do_POST()
        except Exception as error:
            self.failure(error)
