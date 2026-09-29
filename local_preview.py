"""Run an isolated local VECTORone preview without changing the private Atlas config."""
from pymongo import MongoClient
import server
from storage import MongoStore

if __name__=='__main__':
    http=server.ThreadingHTTPServer(('127.0.0.1',8001),server.Handler)
    server.STORE=MongoStore(MongoClient('mongodb://127.0.0.1:27018/?replicaSet=tppl-test',serverSelectionTimeoutMS=5000),'vectorone_preview')
    try:
        server.initialize(migrate_local=False)
        print('VECTORone local MongoDB preview: http://localhost:8001',flush=True)
        http.serve_forever()
    finally:
        http.server_close();server.STORE.close()
