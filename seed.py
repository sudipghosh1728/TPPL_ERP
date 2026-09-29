"""Fictional data for a new MongoDB workspace. Existing workspaces are not reseeded."""
import datetime
import accounting

def initialize(c,demo=False):
    if not c.one('settings'):
        for key,value in [('company','Your company'),('tally_company','Your company'),('tally_url','http://localhost:9000'),('manufacturing_v1','1')]:
            c.insert('settings',key=key,value=value)
        if not demo:
            accounting.initialize(c)
            return
        materials=[(1,'MS plate · 20mm','PLT-020','Fabrication raw materials','Raw material yard',124,30,18500),(2,'Machining insert · CNMG','MCH-002','Machining supplies','Tool crib',18,25,2450),(3,'Structural steel beam','STL-003','Fabrication raw materials','Raw material yard',46,15,12800),(4,'Grinding wheel · 7 inch','GRD-004','Grinding supplies','Tool crib',85,20,620),(5,'Epoxy primer · 20L','PNT-005','Painting supplies','Paint store',12,20,4850),(6,'Welding wire · 15kg','WLD-006','Welding supplies','Consumables store',32,10,3600)]
        for row in materials:c.insert('products',**dict(zip(('id','name','sku','category','warehouse','stock','minimum','price'),row)))
        today=datetime.date.today();prices=[18500,2450,12800,6200,1850,9600]
        for i in range(18):
            pid=i%6+1;qty=i%4+1
            c.insert('orders',customer=['Eastern Engineering','Apex Manufacturing','Horizon Projects','Bengal Industrial Co.'][i%4],product_id=pid,quantity=qty,total=prices[pid-1]*qty,status='Paid' if i%3 else 'Pending',date=(today-datetime.timedelta(days=i*4)).isoformat())
        c.insert('purchases',supplier='Eastern Steel Traders',product_id=1,quantity=20,unit_cost=17200,status='Ordered',date=today.isoformat())
        c.insert('jobs',name='Heavy base frame · BF-104',customer='Apex Manufacturing',product_id=1,quantity=8,due=(today+datetime.timedelta(days=10)).isoformat(),status='Planned')
        c.insert('activity',message='Demo workspace created. Welcome to VECTORone.',date=datetime.datetime.now().isoformat(timespec='seconds'))
    accounting.initialize(c)
