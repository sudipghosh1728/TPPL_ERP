"""Vercel HTTP entry point; uses the already provisioned Atlas database."""
import threading
import ipaddress
import urllib.request
from pymongo import timeout
from urllib.parse import urlparse
import server
from storage import MongoStore

_lock = threading.Lock()

class handler(server.Handler):
    def ready(self):
        if server.STORE is None:
            with _lock:
                if server.STORE is None:
                    server.STORE = MongoStore()
                    # Record only the public egress address for Atlas network diagnostics.
                    try:
                        with urllib.request.urlopen('https://api.ipify.org', timeout=3) as response:
                            address = str(ipaddress.ip_address(response.read(64).decode().strip()))
                        print('Vercel outbound IP: '+address, flush=True)
                    except Exception:
                        pass

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
