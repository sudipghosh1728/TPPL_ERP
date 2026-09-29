"""Exercise finance forms in a browser against an isolated, disposable database."""
import os, pathlib, tempfile, threading, subprocess, sys
import server

def main():
    with tempfile.TemporaryDirectory() as temp:
        server.DB=pathlib.Path(temp)/'erp.db'
        server.initialize()
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            env={**os.environ,'ERP_TEST_URL':f'http://127.0.0.1:{http.server_port}'}
            result=subprocess.run(['node',sys.argv[1] if len(sys.argv)>1 else 'browser-finance.cjs'],env=env)
        finally:
            http.shutdown();http.server_close()
        return result.returncode

if __name__=='__main__':raise SystemExit(main())
