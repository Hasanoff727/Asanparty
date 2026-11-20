import os, sqlite3, uuid, csv, io, hashlib, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parent.parent
DB=Path(os.getenv('DATABASE_PATH', str(ROOT/'data.sqlite3')))
DB.parent.mkdir(parents=True, exist_ok=True)
app=FastAPI(title='Volunteer Party 2025 API')
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS admins(email TEXT PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), title TEXT, description TEXT, event_date TEXT, event_time TEXT, venue TEXT, contact_email TEXT, contact_phone TEXT);
        CREATE TABLE IF NOT EXISTS schedule(id TEXT PRIMARY KEY, time TEXT, title TEXT, description TEXT, sort_order INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS registrations(id TEXT PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT, center TEXT, song_title TEXT, song_url TEXT, status TEXT DEFAULT 'pending', created_at TEXT);
        CREATE TABLE IF NOT EXISTS gallery(id TEXT PRIMARY KEY, filename TEXT, caption TEXT, category TEXT, created_at TEXT);
        ''')
        if not c.execute('SELECT 1 FROM settings WHERE id=1').fetchone():
            c.execute('INSERT INTO settings VALUES(1,?,?,?,?,?,?,?)',('Volunteer Party 2025','A celebration of volunteers, friendship and shared memories.','2025-12-27','19:00','To be announced','info@example.com',''))
        if not c.execute('SELECT 1 FROM admins').fetchone():
            email=os.getenv('ADMIN_EMAIL','admin@volunteerparty.org'); password=os.getenv('ADMIN_PASSWORD','ChangeThisPassword123!')
            salt=secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),240000).hex()
            c.execute('INSERT INTO admins VALUES(?,?,?)',(email,salt,digest))
        if not c.execute('SELECT 1 FROM schedule').fetchone():
            rows=[('18:30','Welcome','Guest arrival and welcome'),('19:00','Opening','Opening ceremony'),('19:30','Celebration','Games and activities'),('21:00','Music','Music and dancing')]
            for i,(t,title,d) in enumerate(rows): c.execute('INSERT INTO schedule VALUES(?,?,?,?,?)',(str(uuid.uuid4()),t,title,d,i))
init()

class RegisterIn(BaseModel):
    full_name:str=Field(min_length=2,max_length=120); email:str=Field(min_length=5,max_length=200); phone:str=Field(min_length=5,max_length=40); center:str=Field(min_length=1,max_length=120); song_title:str=''; song_url:str=''; consent:bool
class LoginIn(BaseModel): email:str; password:str
class StatusIn(BaseModel): status:str
class SettingsIn(BaseModel): title:str|None=None; description:str|None=None; event_date:str|None=None; event_time:str|None=None; venue:str|None=None; contact_email:str|None=None; contact_phone:str|None=None
class ScheduleIn(BaseModel): time:str; title:str; description:str=''

def admin(request:Request):
    email=request.cookies.get('vp_admin')
    if not email: raise HTTPException(401,'Admin authentication required')
    with conn() as c:
        if not c.execute('SELECT 1 FROM admins WHERE email=?',(email,)).fetchone(): raise HTTPException(401,'Invalid session')
    return email

def rows(sql,args=()):
    with conn() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

@app.get('/api/health')
def health(): return {'ok':True}
@app.get('/api/event')
def event():
    s=rows('SELECT * FROM settings WHERE id=1')[0]; s.pop('id',None)
    s['schedule']=rows('SELECT * FROM schedule ORDER BY sort_order,time')
    return s
@app.get('/api/gallery')
def gallery(): return rows('SELECT * FROM gallery ORDER BY created_at DESC')
@app.get('/api/registrations/public/summary')
def summary():
    r=rows('SELECT status,COUNT(*) n FROM registrations GROUP BY status')
    d={x['status']:x['n'] for x in r}; return {'total_registrations':sum(d.values()),'approved':d.get('approved',0),'pending':d.get('pending',0)}
@app.post('/api/registrations')
def register(data:RegisterIn):
    if not data.consent: raise HTTPException(422,'Privacy consent is required')
    if '@' not in data.email: raise HTTPException(422,'Invalid email')
    rid=str(uuid.uuid4())
    with conn() as c:
        if c.execute('SELECT 1 FROM registrations WHERE lower(email)=lower(?)',(data.email,)).fetchone(): raise HTTPException(409,'This email is already registered')
        c.execute('INSERT INTO registrations VALUES(?,?,?,?,?,?,?,?,?)',(rid,data.full_name.strip(),data.email.strip(),data.phone.strip(),data.center.strip(),data.song_title.strip(),data.song_url.strip(),'pending',datetime.now(timezone.utc).isoformat()))
    return {'id':rid,'message':'Registration received'}
@app.post('/api/auth/login')
def login(data:LoginIn,response:Response):
    with conn() as c: row=c.execute('SELECT * FROM admins WHERE email=?',(data.email.lower(),)).fetchone()
    if not row: raise HTTPException(401,'Incorrect email or password')
    digest=hashlib.pbkdf2_hmac('sha256',data.password.encode(),row['salt'].encode(),240000).hex()
    if not secrets.compare_digest(digest,row['password_hash']): raise HTTPException(401,'Incorrect email or password')
    response.set_cookie('vp_admin',row['email'],httponly=True,samesite='lax',secure=os.getenv('COOKIE_SECURE','false').lower()=='true',max_age=604800)
    return {'email':row['email']}
@app.post('/api/auth/logout')
def logout(response:Response): response.delete_cookie('vp_admin'); return {'ok':True}
@app.get('/api/auth/me')
def me(email:str=Depends(admin)): return {'email':email}
@app.get('/api/registrations')
def registrations(email:str=Depends(admin)): return rows('SELECT * FROM registrations ORDER BY created_at DESC')
@app.get('/api/registrations/stats')
def stats(email:str=Depends(admin)):
    r=rows('SELECT status,COUNT(*) n FROM registrations GROUP BY status'); d={x['status']:x['n'] for x in r}
    return {'total':sum(d.values()),'approved':d.get('approved',0),'pending':d.get('pending',0),'rejected':d.get('rejected',0)}
@app.patch('/api/registrations/{rid}')
def update_registration(rid:str,data:StatusIn,email:str=Depends(admin)):
    if data.status not in ('pending','approved','rejected'): raise HTTPException(422,'Invalid status')
    with conn() as c:
        cur=c.execute('UPDATE registrations SET status=? WHERE id=?',(data.status,rid))
        if not cur.rowcount: raise HTTPException(404,'Registration not found')
    return {'ok':True}
@app.delete('/api/registrations/{rid}')
def delete_registration(rid:str,email:str=Depends(admin)):
    with conn() as c: c.execute('DELETE FROM registrations WHERE id=?',(rid,))
    return {'ok':True}
@app.get('/api/registrations/songs')
def songs(email:str=Depends(admin)): return rows("SELECT id,full_name,song_title,song_url,status,created_at FROM registrations WHERE song_title<>'' ORDER BY created_at DESC")
@app.get('/api/registrations/export.csv')
def export_csv(email:str=Depends(admin)):
    data=rows('SELECT * FROM registrations ORDER BY created_at DESC'); buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=list(data[0].keys()) if data else ['id','full_name','email','phone','center','song_title','song_url','status','created_at']); w.writeheader(); w.writerows(data)
    return StreamingResponse(iter([buf.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=registrations.csv'})
@app.put('/api/event')
def update_event(data:SettingsIn,email:str=Depends(admin)):
    payload=data.model_dump(exclude_none=True)
    if payload:
        with conn() as c: c.execute('UPDATE settings SET '+','.join(f'{k}=?' for k in payload)+' WHERE id=1',tuple(payload.values()))
    return event()
@app.post('/api/event/schedule')
def add_schedule(data:ScheduleIn,email:str=Depends(admin)):
    sid=str(uuid.uuid4())
    with conn() as c: c.execute('INSERT INTO schedule VALUES(?,?,?,?,?)',(sid,data.time,data.title,data.description,999))
    return {'id':sid,**data.model_dump()}
@app.put('/api/event/schedule/{sid}')
def edit_schedule(sid:str,data:ScheduleIn,email:str=Depends(admin)):
    with conn() as c:
        cur=c.execute('UPDATE schedule SET time=?,title=?,description=? WHERE id=?',(data.time,data.title,data.description,sid))
        if not cur.rowcount: raise HTTPException(404,'Schedule item not found')
    return {'id':sid,**data.model_dump()}
@app.delete('/api/event/schedule/{sid}')
def remove_schedule(sid:str,email:str=Depends(admin)):
    with conn() as c: c.execute('DELETE FROM schedule WHERE id=?',(sid,))
    return {'ok':True}
@app.post('/api/gallery')
async def upload_gallery(file:UploadFile=File(...),caption:str='',category:str='general',email:str=Depends(admin)):
    if not file.content_type or not file.content_type.startswith('image/'): raise HTTPException(415,'Image files only')
    folder=ROOT/'uploads'; folder.mkdir(exist_ok=True); suffix=Path(file.filename or 'image').suffix[:10]; name=f'{uuid.uuid4().hex}{suffix}'
    content=await file.read()
    if len(content)>8*1024*1024: raise HTTPException(413,'Maximum image size is 8 MB')
    (folder/name).write_bytes(content); gid=str(uuid.uuid4())
    with conn() as c: c.execute('INSERT INTO gallery VALUES(?,?,?,?,?)',(gid,name,caption,category,datetime.now(timezone.utc).isoformat()))
    return {'id':gid,'filename':name,'caption':caption,'category':category}
@app.get('/api/uploads/{name}')
def get_upload(name:str):
    from fastapi.responses import FileResponse
    p=ROOT/'uploads'/Path(name).name
    if not p.exists(): raise HTTPException(404,'File not found')
    return FileResponse(p)
@app.delete('/api/gallery/{gid}')
def delete_gallery(gid:str,email:str=Depends(admin)):
    with conn() as c: row=c.execute('SELECT filename FROM gallery WHERE id=?',(gid,)).fetchone(); c.execute('DELETE FROM gallery WHERE id=?',(gid,))
    if row:
        p=ROOT/'uploads'/row['filename']; p.unlink(missing_ok=True)
    return {'ok':True}
