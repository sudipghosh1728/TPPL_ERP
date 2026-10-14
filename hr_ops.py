"""Employee self service, restricted HR records, attendance and payroll drafts."""
import base64, calendar, datetime as dt, math, re, secrets
from decimal import Decimal, ROUND_HALF_UP
import access
from storage import identifier

IST=dt.timezone(dt.timedelta(hours=5, minutes=30))
def now(): return dt.datetime.now(IST)
def today(): return now().date().isoformat()
def hr(user): access.require(user,('HR',))
def text(d,k,limit=250):
    value=str(d.get(k,'')).strip()
    if not value or len(value)>limit: raise ValueError('Enter a valid '+k.replace('_',' '))
    return value
def date(value): return dt.date.fromisoformat(str(value)).isoformat()
def audit(c,user,action): c.insert('hr_audit',actor_id=user['id'],action=action,at=now().isoformat())
def person(c,uid):
    u=c.one('users',{'id':identifier(uid),'active':1})
    if not u: raise ValueError('Choose an active employee')
    return u
def profile(c,d,user):
    import project_flow
    uid=identifier(d.get('user_id',user['id']))
    if uid!=user['id']: hr(user)
    u=person(c,uid); old=c.one('employee_profiles',{'user_id':uid}) or {}
    values={k:text(d,k) for k in ('name','phone','email','blood_group','dob')}
    values['plant_id']=project_flow.plant(d.get('plant_id'))
    if not re.fullmatch(r'\+?[0-9 ()-]{7,20}',values['phone']): raise ValueError('Enter a valid phone number')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values['email']): raise ValueError('Enter a valid email address')
    if values['blood_group'] not in ('A+','A-','B+','B-','AB+','AB-','O+','O-'): raise ValueError('Choose blood group')
    values['dob']=date(values['dob'])
    if values['dob']>=today(): raise ValueError('Date of birth must be in the past')
    if d.get('department',u['role'])!=u['role']: raise ValueError('Department is assigned by Admin')
    photo=d.get('photo',old.get('photo',''))
    if photo:
        if not isinstance(photo,str) or not re.match(r'^data:image/(png|jpeg);base64,',photo): raise ValueError('Photo must be PNG or JPEG')
        try: raw=base64.b64decode(photo.split(',',1)[1],validate=True)
        except Exception: raise ValueError('Invalid photo')
        if len(raw)>300000 or not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff')): raise ValueError('Use a PNG/JPEG photo below 300 KB')
    if not photo: raise ValueError('Please upload your profile photo')
    values.update(user_id=uid,photo=photo,marital_status=str(d.get('marital_status',''))[:50],address=str(d.get('address',''))[:1000],emergency_contact=str(d.get('emergency_contact',''))[:100],updated_at=now().isoformat(),complete=True)
    if old: c.update('employee_profiles',{'id':old['id']},values)
    else: c.insert('employee_profiles',**values)
    c.update('users',{'id':uid},{'name':values['name']});audit(c,user,'Employee profile updated: '+str(uid))

def unavailable(c,uid,on=None):
    on=on or today()
    for leave in c.all('employee_leave',{'user_id':uid,'status':'Approved','start':{'$lte':on},'end':{'$gte':on}}):
        if (dt.date.fromisoformat(leave['end'])-dt.date.fromisoformat(leave['start'])).days+1>5 and (not leave.get('returned_on') or leave['returned_on']>on): return True
    return False

def leave(c,d,user):
    action=d.get('action','request')
    if action=='request':
        start=date(d.get('start'));end=date(d.get('end'))
        if end<start: raise ValueError('Leave end must follow start')
        if c.one('employee_leave',{'user_id':user['id'],'status':{'$in':['Pending','Approved']},'start':{'$lte':end},'end':{'$gte':start}}): raise ValueError('Leave dates overlap an existing request')
        c.insert('employee_leave',user_id=user['id'],start=start,end=end,reason=text(d,'reason',1000),status='Pending',paid=False,created_at=now().isoformat())
    else:
        r=c.one('employee_leave',{'id':identifier(d.get('id'))})
        if not r: raise ValueError('Leave request not found')
        c.touch('employee_leave',r['id'])
        if action=='resume':
            if user['id']!=r['user_id']: hr(user)
            if r['status']!='Approved' or r.get('returned_on') or not r['start']<=today()<=r['end']: raise ValueError('No active leave to resume')
            c.update('employee_leave',{'id':r['id']},{'returned_on':today()})
        elif action in ('Approved','Rejected'):
            hr(user)
            if r['status']!='Pending': raise ValueError('Leave already decided')
            c.update('employee_leave',{'id':r['id']},{'status':action,'paid':d.get('paid') is True,'reviewer':user['id'],'review_notes':text(d,'notes',1000)})
        else: raise ValueError('Invalid leave action')
    audit(c,user,'Leave '+action)

def assignment(c,d,user):
    access.require(user,('Design',))
    import project_flow as p,manufacturing as m
    j=p.project(c,d,user);m.version(j,d);p.open_job(j)
    department=text(d,'department')
    if department not in access.ROLES: raise ValueError('Choose a department')
    uid=identifier(d.get('user_id'));u=person(c,uid)
    if u['role']!=department: raise ValueError('Employee does not belong to that department')
    values={**j.get('assignments',{}),department:uid}
    c.update('work_jobs',{'id':j['id']},{'assignments':values})
    p.record(c,j,user,'Assigned '+department+' to '+u['name']);p.notify(c,j,user,'Project assignment: '+u['name'],(department,'Admin'))

def assigned(c,j,user):
    if user['role']=='Admin': return
    uid=j.get('assignments',{}).get(user['role'])
    if not uid or uid==user['id']: return
    if user['role']=='QC' and unavailable(c,uid): return
    raise access.AccessError('Only the assigned '+user['role']+' employee can act on this project')

def pin(c,d,user):
    hr(user)
    import project_flow as p
    plant=p.plant(d.get('plant_id'));lat=finite(d.get('latitude'),-90,90);lon=finite(d.get('longitude'),-180,180)
    values={'plant_id':plant,'latitude':lat,'longitude':lon,'updated_by':user['id'],'updated_at':now().isoformat()}
    old=c.one('plant_locations',{'plant_id':plant})
    if old:c.update('plant_locations',{'id':old['id']},values)
    else:c.insert('plant_locations',**values)
    audit(c,user,'Plant attendance pin updated: '+plant)
def finite(value,low=0,high=100000000):
    n=float(value)
    if not math.isfinite(n) or not low<=n<=high: raise ValueError('Invalid number')
    return n
def distance(a,b,c,d):
    x,y=math.radians(c-a),math.radians(d-b)
    h=math.sin(x/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(y/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))
def attendance(c,d,user):
    stamp=now();day=stamp.date().isoformat();action=d.get('action');uid=user['id']
    row=c.one('employee_attendance',{'user_id':uid,'date':day})
    if action=='out':
        rows=c.all('employee_attendance',{'user_id':uid,'status':'Present','out_at':{'$in':['',None]}},sort=[('date',-1)])
        row=rows[0] if rows else row
    if row:c.touch('employee_attendance',row['id'])
    if action=='out':
        if not row or row['status']!='Present': raise ValueError('Complete check-in or obtain HR regularization before checkout')
        if row.get('out_at'): raise ValueError('Already checked out')
        c.update('employee_attendance',{'id':row['id']},{'out_at':stamp.isoformat()});return
    if action not in ('start','heartbeat'): raise ValueError('Unknown attendance action')
    if row and row['status']=='Present': return
    location=c.one('plant_locations',{'plant_id':d.get('plant_id')})
    if not location: raise ValueError('HR must pin this plant location first')
    lat=finite(d.get('latitude'),-90,90);lon=finite(d.get('longitude'),-180,180);accuracy=finite(d.get('accuracy'),0,100000)
    meters=distance(lat,lon,location['latitude'],location['longitude'])
    valid=accuracy<=30 and meters+accuracy<=30
    if action=='start':
        if stamp.time().replace(tzinfo=None)>dt.time(9,15): raise ValueError('Check-in closes at 9:15 AM IST. Request regularization.')
        if not valid: raise ValueError('Accurate GPS within the 30 metre plant boundary is required')
        values=dict(user_id=uid,date=day,plant_id=location['plant_id'],status='Verifying',started_at=stamp.isoformat(),last_at=stamp.isoformat(),seconds=0,nonce=secrets.token_urlsafe(24),accuracy=accuracy,distance=round(meters,1))
        if row:c.update('employee_attendance',{'id':row['id']},values)
        else:c.insert('employee_attendance',**values)
    else:
        if not row or row['status']!='Verifying' or row['plant_id']!=location['plant_id'] or d.get('nonce')!=row['nonce']: raise ValueError('Restart attendance verification')
        gap=(stamp-dt.datetime.fromisoformat(row['last_at'])).total_seconds()
        seconds=row['seconds']+gap if valid and 0<gap<=120 else 0
        values=dict(last_at=stamp.isoformat(),seconds=seconds,nonce=secrets.token_urlsafe(24),accuracy=accuracy,distance=round(meters,1))
        if seconds>1800: values.update(status='Present',in_at=row['started_at'],confirmed_at=stamp.isoformat())
        elif not valid or gap>120: values.update(status='Interrupted',seconds=0)
        c.update('employee_attendance',{'id':row['id']},values)

def regularize(c,d,user):
    if not d.get('id'):
        day=date(d.get('date'))
        if day>today(): raise ValueError('Cannot regularize a future date')
        if c.one('attendance_requests',{'user_id':user['id'],'date':day,'status':'Pending'}):raise ValueError('Request already pending')
        start=dt.time.fromisoformat(str(d.get('in_time')));end=dt.time.fromisoformat(str(d['out_time'])) if d.get('out_time') else None
        if end and end<=start:raise ValueError('Checkout must follow check-in')
        c.insert('attendance_requests',user_id=user['id'],date=day,in_time=start.isoformat(),out_time=end.isoformat() if end else '',reason=text(d,'reason',1000),status='Pending')
    else:
        hr(user);r=c.one('attendance_requests',{'id':identifier(d['id']),'status':'Pending'})
        if not r:raise ValueError('Request already decided')
        status=d.get('status')
        if status not in ('Approved','Rejected'):raise ValueError('Choose approve or reject')
        c.touch('attendance_requests',r['id']);c.update('attendance_requests',{'id':r['id']},{'status':status,'reviewer':user['id'],'notes':text(d,'notes')})
        if status=='Approved':
            q={'user_id':r['user_id'],'date':r['date']};old=c.one('employee_attendance',q)
            v={**q,'status':'Present','in_at':r['date']+'T'+r['in_time']+'+05:30','out_at':r['date']+'T'+r['out_time']+'+05:30' if r['out_time'] else '', 'regularized':True,'regularization_id':r['id']}
            if old:c.update('employee_attendance',{'id':old['id']},v)
            else:c.insert('employee_attendance',**v)
        audit(c,user,'Attendance '+status+': '+str(r['id']))

def paise(value):return int((Decimal(str(finite(value)))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def salary(c,d,user):
    hr(user);uid=person(c,d.get('user_id'))['id'];mode=d.get('mode')
    if mode not in ('Monthly','Daily'):raise ValueError('Choose Monthly or Daily wages')
    values=dict(user_id=uid,mode=mode,rate_paise=paise(d.get('rate')),allowance_paise=paise(d.get('allowance',0)),deduction_paise=paise(d.get('deduction',0)),overtime_paise=paise(d.get('overtime_rate',0)),effective_from=date(d.get('effective_from')),updated_by=user['id'])
    old=c.one('salary_structures',{'user_id':uid})
    if old:c.update('salary_structures',{'id':old['id']},values)
    else:c.insert('salary_structures',**values)
    audit(c,user,'Salary structure updated: '+str(uid))

def payroll(c,d,user):
    hr(user)
    if d.get('id'):
        r=c.one('payroll_runs',{'id':identifier(d['id'])})
        if not r:raise ValueError('Payroll not found')
        action=d.get('action');expected={'Approve':'Draft','Paid':'Approved','Void':'Draft'}.get(action)
        if r['status']!=expected:raise ValueError('Invalid payroll transition')
        c.touch('payroll_runs',r['id']);values={'status':{'Approve':'Approved','Paid':'Paid','Void':'Void'}[action],'reviewer':user['id'],'notes':text(d,'notes')}
        if action=='Paid':values.update(payment_reference=text(d,'reference'),paid_at=now().isoformat())
        c.update('payroll_runs',{'id':r['id']},values);audit(c,user,'Payroll '+action+': '+str(r['id']));return
    uid=person(c,d.get('user_id'))['id'];month=text(d,'month')
    c.touch('users',uid)
    if not re.fullmatch(r'\d{4}-\d{2}',month):raise ValueError('Choose payroll month')
    first=dt.date.fromisoformat(month+'-01');last=first.replace(day=calendar.monthrange(first.year,first.month)[1])
    s=c.one('salary_structures',{'user_id':uid})
    if not s or s['effective_from']>first.isoformat():raise ValueError('Configure a salary structure effective on or before this month')
    if c.one('payroll_runs',{'user_id':uid,'month':month,'status':{'$ne':'Void'}}):raise ValueError('Payroll for this employee and month already exists')
    working=finite(d.get('working_days'),1,31);payable=finite(d.get('payable_days'),0,working);overtime=finite(d.get('overtime_hours',0),0,400)
    base=Decimal(s['rate_paise'])*Decimal(str(payable))/(Decimal(str(working)) if s['mode']=='Monthly' else Decimal(1))
    gross=int(base.quantize(Decimal('1'),rounding=ROUND_HALF_UP))+s['allowance_paise']+int(Decimal(str(overtime))*s['overtime_paise'])
    deductions=s['deduction_paise']+paise(d.get('additional_deduction',0))
    if deductions>gross:raise ValueError('Deductions exceed gross salary')
    c.insert('payroll_runs',user_id=uid,month=month,status='Draft',working_days=working,payable_days=payable,overtime_hours=overtime,gross_paise=gross,deductions_paise=deductions,net_paise=gross-deductions,structure=s,notes=text(d,'notes',1000),created_by=user['id'],created_at=now().isoformat())
    audit(c,user,'Payroll draft created: '+str(uid)+' '+month)

def state(c,data,user):
    import project_flow
    admin=user['role'] in ('Admin','HR');uid=user['id'];q={} if admin else {'user_id':uid}
    data['employee_profile']=c.one('employee_profiles',{'user_id':uid})
    data['hr_profiles']=c.all('employee_profiles',projection={'photo':0}) if admin else []
    plant_ids={p['id'] for p in project_flow.PLANTS}
    for profile in [data['employee_profile'],*data['hr_profiles']]:
        if profile:profile['complete']=bool(profile.get('complete') and profile.get('plant_id') in plant_ids)
    directory_allowed=user['role'] in ('Admin','HR','Design')
    profile_plants={p['user_id']:p.get('plant_id','') for p in c.all('employee_profiles',projection={'user_id':1,'plant_id':1})} if directory_allowed else {}
    data['employee_directory']=[dict(id=u['id'],name=u['name'],department=u['role'],plant_id=profile_plants.get(u['id'],'') if profile_plants.get(u['id']) in plant_ids else '',active=u['active'],on_extended_leave=unavailable(c,u['id'])) for u in c.all('users',{'active':1})] if directory_allowed else []
    ids={uid for j in data.get('work_jobs',[]) for uid in j.get('assignments',{}).values()}
    data['project_assignees']={str(u['id']):u['name'] for u in c.all('users',{'id':{'$in':list(ids)}})}
    for name in ('employee_leave','employee_attendance','attendance_requests','salary_structures','payroll_runs'):
        data[name]=c.all(name,q,sort=[('id',-1)])
    for r in data['employee_attendance']:
        if r['user_id']!=uid:r.pop('nonce',None)
    data['plant_locations']=c.all('plant_locations')
    data['hr_audit']=c.all('hr_audit',sort=[('id',-1)])[:100] if admin else []
    data['hr_today']=today();data['attendance_open']=now().time().replace(tzinfo=None)<=dt.time(9,15)
    data['dispatch_alerts']=alerts(c,data.get('work_jobs',[]),user)

def alerts(c,jobs,user):
    import manufacturing
    owners={'Design review':'Design','QC approval':'QC','QC inspection':'QC','Store issue':'Store','Fabrication execution':'Fabrication','Machining execution':'Machining','Packing & dispatch':'Fabrication','Admin review':'Admin','Accounts review':'Accounts','Maintenance review':'Maintenance','HR review':'HR'}
    read={r['key'] for r in c.all('alert_reads',{'user_id':user['id']})}
    result=[]
    for j in jobs:
        due=j.get('revised_due') or j.get('due')
        if not manufacturing.visible(j,user) or j.get('stage')=='Completed' or not due:continue
        roles={'Design',owners.get(j['stage'])}
        if user['role']!='Admin':
            if user['role'] not in roles:continue
            uid=j.get('assignments',{}).get(user['role'])
            if uid and uid!=user['id'] and not (user['role']=='QC' and unavailable(c,uid)):continue
        remaining=(dt.date.fromisoformat(due)-now().date()).days
        if remaining<=2:
            key=f'{today()}:{j["id"]}:{due}:{j["stage"]}'
            result.append(dict(key=key,job_id=j['id'],title=j['title'],due=due,days=remaining,stage=j['stage'],read=key in read))
    return sorted(result,key=lambda r:(r['due'],r['job_id']))

def read_alert(c,d,user):
    key=text(d,'key')
    if key not in {r['key'] for r in alerts(c,c.all('work_jobs'),user)}:raise access.AccessError('Reminder not available',404)
    if not c.one('alert_reads',{'user_id':user['id'],'key':key}):c.insert('alert_reads',user_id=user['id'],key=key,read_at=now().isoformat())

HANDLERS={'profile':profile,'leave':leave,'assign':assignment,'pin':pin,'attendance':attendance,'regularize':regularize,'salary':salary,'payroll':payroll,'read-alert':read_alert}
