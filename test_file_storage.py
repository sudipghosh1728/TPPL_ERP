import base64,io,json,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import file_storage as fs,file_server,storage_admin,access,seed,project_flow,project_deletion,report_workshop,server
from mongo_test_support import test_store,clean

class DriveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.sid=fs.DiskStore.initialize(self.tmp.name);self.disk=fs.DiskStore(self.tmp.name,self.sid)
    def tearDown(self):self.tmp.cleanup()
    def test_atomic_immutable_integrity_and_wrong_drive(self):
        raw=b'original drawing\x00\xff';ref=self.disk.put(raw)
        self.assertEqual(self.disk.get(ref),raw);self.assertEqual(self.disk.put(raw),ref)
        self.assertEqual(len(list(Path(self.tmp.name).rglob(ref['key']))),1)
        with self.assertRaises(fs.StorageError):self.disk.get({**ref,'key':'../../secret'})
        with self.assertRaises(fs.StorageError):fs.DiskStore(self.tmp.name,'wrong').put(raw)
        self.disk.path(ref['key']).write_bytes(b'corrupt')
        with self.assertRaises(fs.StorageError):self.disk.get(ref)
        with self.assertRaises(fs.StorageError):self.disk.put(raw)
        (Path(self.tmp.name)/'.grey-store.json').unlink()
        with self.assertRaises(fs.StorageError):self.disk.put(b'new')
    def test_remote_auth_hash_verification_and_download(self):
        token='test-private-token-'*3;srv=file_server.make_server(('127.0.0.1',0),self.disk,token)
        threading.Thread(target=srv.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{srv.server_port}'
        try:
            remote=fs.RemoteStore(url,token,self.sid);self.assertEqual(remote.health()['store_id'],self.sid)
            ref=remote.put(b'original report');self.assertEqual(remote.get(ref),b'original report')
            with self.assertRaises(HTTPError) as exc:urlopen(url+'/health')
            self.assertEqual(exc.exception.code,401)
            exc.exception.close()
            with self.assertRaises(fs.StorageError):fs.RemoteStore(url,'incorrect-key-'*4,self.sid).health()
            req=Request(url+'/files/'+'0'*64,data=b'mismatch',method='PUT',headers={'Authorization':'Bearer '+token,'X-Store-ID':self.sid})
            with self.assertRaises(HTTPError) as exc:urlopen(req)
            exc.exception.close()
            with self.assertRaises(fs.StorageError):fs.RemoteStore('http://192.168.1.5:8090',token,self.sid)
        finally:srv.shutdown();srv.server_close()
    def test_disabled_default_and_vercel_rejects_local_disk(self):
        self.assertIsNone(fs.configured({}))
        with self.assertRaises(fs.StorageError):fs.configured({'FILE_STORAGE_MODE':'disk','VERCEL':'1'})

class OffloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();sid=fs.DiskStore.initialize(self.tmp.name);self.disk=fs.DiskStore(self.tmp.name,sid)
        self.store=test_store();self.store.prepare();self.store.run(lambda c:seed.initialize(c,demo=True))
        self.admin={'id':1,'name':'Admin fixture','role':'Admin'};self.qc={'id':2,'name':'QC fixture','role':'QC'}
        self.raw=b'unchanged original drawing';self.file={'name':'po.txt','content':base64.b64encode(self.raw).decode()}
        self.store.run(lambda c:project_flow.create(c,dict(plant_id='solu',title='Drive project',customer='Fixture',po_number='DRIVE-1',quantity=1,due='2026-12-01',route='Fabrication only',file=self.file,drawing_file={**self.file,'name':'drawing.txt'}),self.admin))
        self.jid=self.store.run(lambda c:c.all('work_jobs')[0]['id'])
        self.rid=self.store.run(lambda c:report_workshop.upload(c,dict(name='External report',job_id=self.jid,file={**self.file,'name':'inspection.pdf'}),self.qc))['id']
    def tearDown(self):clean(self.store);self.tmp.cleanup()
    def test_migration_preserves_downloads_archive_permissions_and_metadata(self):
        original=self.store.run(lambda c:project_deletion.snapshot(c,self.jid,self.admin))[2]
        self.store.files=self.disk
        with self.assertRaises(access.AccessError):self.store.run(lambda c:storage_admin.move_one(c,{},self.qc))
        moved=0
        while True:
            result=self.store.run(lambda c:storage_admin.move_one(c,{'job_id':self.jid},self.admin));moved+=result['moved']
            if not result['remaining']:break
        self.assertEqual(moved,3);self.assertEqual(self.store.db.work_jobs.count_documents({'id':self.jid}),1)
        self.assertTrue(fs.is_reference(self.store.db.job_documents.find_one()['content']))
        self.assertEqual(self.store.run(lambda c:project_deletion.snapshot(c,self.jid,self.admin))[2],original)
        self.assertEqual(self.store.run(lambda c:report_workshop.export(c,self.rid,self.qc))['_download']['content'],self.raw)
        def archive(c):
            data,_,digest=project_deletion.snapshot(c,self.jid,self.admin)
            return project_deletion.make_zip(c,data,digest,self.admin)
        with zipfile.ZipFile(io.BytesIO(self.store.run(archive))) as z:
            self.assertEqual(z.read(next(n for n in z.namelist() if n.startswith('documents/'))),self.raw)
            self.assertEqual(z.read(next(n for n in z.namelist() if n.startswith('uploaded-reports/'))),self.raw)
            self.assertIn('project_messages.json',z.namelist())
        with patch.object(self.disk,'get',side_effect=fs.StorageError('Offline')):
            # Listing metadata must not fetch the original document.
            self.assertEqual(len(self.store.run(lambda c:c.all('job_documents',projection={'content':0}))),2)
            with self.assertRaises(fs.StorageError):self.store.run(lambda c:report_workshop.export(c,self.rid,self.qc))
        self.assertEqual(self.store.run(lambda c:storage_admin.move_one(c,{},self.admin))['moved'],0)
    def test_failed_verification_and_transaction_rollback_keep_original(self):
        self.store.files=self.disk
        with patch.object(self.disk,'get',return_value=b'bad'):
            with self.assertRaises(fs.StorageError):self.store.run(lambda c:storage_admin.move_one(c,{},self.admin))
        self.assertEqual(bytes(self.store.db.job_documents.find_one()['content']),self.raw)
        def rollback(c):
            storage_admin.move_one(c,{},self.admin)
            raise ValueError('Cancel transaction')
        with self.assertRaises(ValueError):self.store.run(rollback)
        self.assertEqual(bytes(self.store.db.job_documents.find_one()['content']),self.raw)
    def test_new_uploads_and_deletion_parts_stay_outside_mongo(self):
        self.store.files=self.disk
        self.store.run(lambda c:project_flow.attach(c,dict(job_id=self.jid,version=c.one('work_jobs',{'id':self.jid})['version'],kind='TC',file=self.file),self.qc))
        self.assertTrue(fs.is_reference(self.store.db.job_documents.find_one({'kind':'TC'})['content']))
        meta=self.store.run(lambda c:project_deletion.prepare(c,{'job_id':self.jid},self.admin))
        self.assertTrue(fs.is_reference(self.store.db.project_delete_parts.find_one()['content']))
        chunks=[self.store.run(lambda c,n=n:project_deletion.download_part(c,meta['token'],n,self.admin))['_download']['content'] for n in range(meta['parts'])]
        self.assertEqual(fs.digest(b''.join(chunks)),meta['sha256'])
        self.store.run(lambda c:project_deletion.delete(c,dict(job_id=self.jid,export_token=meta['token'],download_confirmed=True,confirmation=project_deletion.reference(self.jid)),self.admin))
        self.assertTrue(fs.is_reference(self.store.db.dispatch_archives.find_one()['content']))
        # Queued mail can still read the exact verified attachment through the store.
        self.assertEqual(b''.join(self.store.run(lambda c:[r['content'] for r in c.all('dispatch_archives',sort=[('chunk',1)])])),b''.join(chunks))
    def test_status_api_is_admin_only(self):
        for user,allowed in ((self.admin,True),(self.qc,False)):
            with patch('server.access.current',return_value=user):
                if allowed:self.assertFalse(self.store.run(lambda c:server.read_api(c,'/api/file-storage/status',None))['configured'])
                else:
                    with self.assertRaises(access.AccessError):self.store.run(lambda c:server.read_api(c,'/api/file-storage/status',None))
    def test_admin_connects_network_server_privately_and_other_requests_use_it(self):
        token='fixture-private-server-key-'*3;srv=file_server.make_server(('127.0.0.1',0),self.disk,token)
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        payload=dict(name='Windows fixture',url=f'http://127.0.0.1:{srv.server_port}',store_id=self.disk.store_id,token=token)
        def connect(d=payload,user=None):return self.store.run(lambda c:storage_admin.connect(c,d,user or self.admin))
        try:
            with self.assertRaises(access.AccessError):connect(user=self.qc)
            with self.assertRaises(fs.StorageError):connect({**payload,'token':'incorrect-private-key-'*3})
            self.assertIsNone(self.store.db['_metadata'].find_one({'_id':'company-file-server'}))
            with patch.dict('os.environ',{'VERCEL':'1'}):
                with self.assertRaisesRegex(ValueError,'HTTPS'):connect()
            self.assertNotIn(token,json.dumps(connect()))
            self.assertTrue(self.store.run(lambda c:isinstance(c.files,fs.RemoteStore)))
            self.store.run(lambda c:storage_admin.move_one(c,{'job_id':self.jid},self.admin))
            self.assertTrue(fs.is_reference(self.store.db.job_documents.find_one()['content']))
            self.assertEqual(self.store.run(lambda c:c.one('job_documents'))['content'],self.raw)
            with patch('server.STORE',self.store),patch('server.access.current',return_value=self.admin):
                state=self.store.run(lambda c:server.read_api(c,'/api/state',None))
                status=self.store.run(lambda c:server.read_api(c,'/api/file-storage/status',None))
            self.assertNotIn(token,json.dumps(state));self.assertNotIn(token,json.dumps(status))
            self.assertEqual(status['server']['name'],'Windows fixture')
            connect({**payload,'token':'','name':'Renamed server'})
            for changed in ({'token':'bad-key-'*5},{'token':'','url':'https://changed.example.invalid'},{'store_id':'another-disk'}):
                with self.assertRaises(ValueError):connect({**payload,**changed})
            saved=self.store.db['_metadata'].find_one({'_id':'company-file-server'})
            self.assertEqual(saved['name'],'Renamed server');self.assertEqual(saved['token'],token)
        finally:srv.shutdown();srv.server_close()
