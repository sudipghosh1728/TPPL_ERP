"""Exercise finance forms in a browser against an isolated, disposable database."""
import os, pathlib, tempfile, threading, subprocess, sys
import server
from mongo_test_support import test_store,clean

def main():
    os.environ['ARCHIVE_MAIL_ENABLED']='false'
    with tempfile.TemporaryDirectory() as temp:
        server.STORE=test_store();server.initialize(migrate_local=False,demo=os.environ.get("ERP_TEST_CLEAN")!="1")
        if os.environ.get('ERP_TEST_FILES')=='1':
            import file_storage,project_flow,report_workshop,base64
            actor=dict(id=1,name='File storage fixture',role='Admin')
            source=dict(name='fixture.txt',content=base64.b64encode(b'ORIGINAL FILE FIXTURE').decode())
            def fixture(c):
                project_flow.create(c,dict(plant_id='solu',title='Drive migration fixture',customer='Test',po_number='DRIVE',quantity=1,due='2026-12-01',route='Fabrication only',file=source,drawing_file=source),actor)
                jid=c.all('work_jobs')[0]['id']
                report_workshop.upload(c,dict(job_id=jid,name='Report fixture',file=source),actor)
            server.STORE.run(fixture)
            drive=pathlib.Path(temp)/'drive';sid=file_storage.DiskStore.initialize(drive)
            server.STORE.files=file_storage.DiskStore(drive,sid)
        if os.environ.get('ERP_TEST_CATALOG')=='1':
            import store_catalog
            server.STORE.run(lambda c:store_catalog.import_names(c,[dict(row=1,name='Test imported wheel',source_values=['10','15'])],'browser-fixture',True))
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            env={**os.environ,'ERP_TEST_URL':f'http://127.0.0.1:{http.server_port}'}
            result=subprocess.run(['node',sys.argv[1] if len(sys.argv)>1 else 'browser-finance.cjs'],env=env)
        finally:
            http.shutdown();http.server_close();clean(server.STORE)
        return result.returncode

if __name__=='__main__':raise SystemExit(main())
