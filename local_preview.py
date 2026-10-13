"""Isolated local TPPL + GREY one preview. Never reads Atlas or sends email."""
import argparse, base64
from pymongo import MongoClient
import server,access,project_flow as pf
from storage import MongoStore

PASSWORD='LocalPreview!2026'
def provision(c):
 if c.one('settings',{'key':'plant_preview_seeded'}):return
 users={}
 for role in access.ROLES:
  username='preview-'+role.lower()
  row=c.one('users',{'username':username})
  if not row:
   uid=access.create_user(c,dict(username=username,name=role+' Preview',role=role,password=PASSWORD))
   row=c.one('users',{'id':uid})
  users[role]=access.public(row)
 for index,plant in enumerate(pf.PLANTS):
  pf.create(c,dict(plant_id=plant['id'],title='Demo · '+['Base frame','Machined housing','Support assembly','Precision plate'][index],customer='Preview customer — not live data',po_number='DEMO-PO-'+str(index+1),quantity=2,due='2026-12-31',route='Fabrication + machining' if index%2 else 'Fabrication only',file=dict(name='demo-po.txt',content=base64.b64encode(b'LOCAL DEMO ONLY - not a customer purchase order').decode())),users['Design'])
  j=c.all('work_jobs',sort=[('id',-1)])[0]
  pf.requirement(c,dict(job_id=j['id'],version=j['version'],product_id=1,quantity=2,material_group='Raw material'),users['Design'])
  j=c.one('work_jobs',{'id':j['id']})
  pf.chat(c,dict(job_id=j['id'],message='Demo project conversation. Messages stay inside this project.'),users['Design'])
  if index==1:pf.submit(c,dict(job_id=j['id'],version=j['version'],notes='Demo design ready for QC verification'),users['Design'])
 c.update('settings',{'key':'company'},{'value':'TPPL · Local preview'})
 c.insert('settings',key='plant_preview_seeded',value=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8001);args=parser.parse_args()
 http=server.ThreadingHTTPServer(('127.0.0.1',args.port),server.Handler)
 server.STORE=MongoStore(MongoClient('mongodb://127.0.0.1:27018/?replicaSet=tppl-test',serverSelectionTimeoutMS=5000),'grey_plants_preview')
 try:
  server.initialize(migrate_local=False,demo=True);server.STORE.run(provision)
  print(f'LOCAL preview http://localhost:{args.port} | /admin | /user. Local MongoDB only; outbound email disabled.',flush=True)
  http.serve_forever()
 finally:http.server_close();server.STORE.close()
