from datetime import datetime
import json
import secrets
import os
from pathlib import Path
import re
from fastapi import FastAPI, Form, Header, Request, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import psycopg
from psycopg.rows import dict_row
from psycopg import errors
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
UPLOADS = ROOT / 'uploads'
UPLOADS.mkdir(exist_ok=True)
app = FastAPI(title='Northstar Studio API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origin_regex=r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$', allow_methods=['*'], allow_headers=['*'])
app.mount('/uploads', StaticFiles(directory=UPLOADS), name='uploads')
admin_tokens = set()

class ResultCursor:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)

class Database:
    def __init__(self):
        if not DATABASE_URL:
            raise RuntimeError('DATABASE_URL must point to an online PostgreSQL database')
        self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type:
            self.raw.rollback()
        else:
            self.raw.commit()
        self.raw.close()

    def execute(self, query, params=()):
        query = query.replace('?', '%s')
        if query.lstrip().upper().startswith('INSERT') and 'RETURNING' not in query.upper():
            query += ' RETURNING id'
            cursor = self.raw.execute(query, params)
            row = cursor.fetchone()
            return ResultCursor(cursor, row['id'] if row else None)
        return ResultCursor(self.raw.execute(query, params))

    def executemany(self, query, params):
        with self.raw.cursor() as cursor:
            return cursor.executemany(query.replace('?', '%s'), params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

def connection():
    return Database()

def init_db():
    with connection() as db:
        tables = {name: bool(db.execute('SELECT to_regclass(?) AS table_name', (f'public.{name}',)).fetchone()['table_name']) for name in ('inquiries', 'internship_applications', 'inquiry_fields', 'certificates', 'content')}
        if not tables['inquiries']:
            db.execute('CREATE TABLE inquiries (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, service TEXT, details TEXT, status TEXT DEFAULT \'new\', created_at TEXT NOT NULL, extra_fields TEXT DEFAULT \'{}\')')
        if not tables['internship_applications']:
            db.execute('CREATE TABLE internship_applications (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, category TEXT, status TEXT DEFAULT \'pending\', created_at TEXT NOT NULL)')
        db.execute('ALTER TABLE internship_applications ADD COLUMN IF NOT EXISTS resume TEXT')
        if not tables['inquiry_fields']:
            db.execute('CREATE TABLE inquiry_fields (id BIGSERIAL PRIMARY KEY, label TEXT NOT NULL, field_name TEXT UNIQUE NOT NULL, field_type TEXT NOT NULL DEFAULT \'text\', required INTEGER NOT NULL DEFAULT 0, options TEXT DEFAULT \'[]\', created_at TEXT NOT NULL)')
        if not tables['certificates']:
            db.execute('CREATE TABLE certificates (id BIGSERIAL PRIMARY KEY, number TEXT UNIQUE NOT NULL, candidate TEXT NOT NULL, category TEXT NOT NULL, duration TEXT NOT NULL, issue_date TEXT NOT NULL)')
        db.execute('ALTER TABLE certificates ADD COLUMN IF NOT EXISTS image TEXT')
        if not tables['content']:
            db.execute('CREATE TABLE content (id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('INSERT INTO certificates(number,candidate,category,duration,issue_date) VALUES (?,?,?,?,?) ON CONFLICT (number) DO NOTHING', ('NS-2026-041','Aarav Sharma','Full Stack Development','January - April 2026','2026-04-30'))
        if db.execute('SELECT COUNT(*) AS count FROM inquiry_fields').fetchone()['count'] == 0:
            default_fields = [('Company name', 'company_name', 'text', 0), ('Budget range', 'budget', 'text', 0), ('Project timeline', 'timeline', 'text', 0)]
            db.executemany('INSERT INTO inquiry_fields(label,field_name,field_type,required,created_at) VALUES(?,?,?,?,?)', [(label, name, kind, required, datetime.now().isoformat(timespec='seconds')) for label, name, kind, required in default_fields])
        if db.execute('SELECT COUNT(*) AS count FROM content').fetchone()['count'] == 0:
            default_content = [
                ('services', {'icon': '01', 'title': 'Websites that work hard', 'text': 'High-converting digital homes with a sharp point of view and effortless performance.', 'tags': ['Strategy', 'Design systems', 'Development']}),
                ('services', {'icon': '02', 'title': 'Products people keep using', 'text': 'Web and mobile applications that make complex workflows feel remarkably simple.', 'tags': ['UX research', 'React', 'FastAPI']}),
                ('services', {'icon': '03', 'title': 'Operations, untangled', 'text': 'Automation, GST and bookkeeping support that gives your team its time back.', 'tags': ['Automation', 'GST', 'Accounting']}),
                ('projects', {'name': 'Rill marketplace', 'type': 'E-commerce', 'color': 'coral', 'result': '+184% conversion', 'text': 'A considered commerce experience for a new generation of independent makers.'}),
                ('projects', {'name': 'Atlas operations', 'type': 'SaaS platform', 'color': 'blue', 'result': '11 hrs saved / week', 'text': 'One calm command centre replacing five noisy spreadsheets.'}),
                ('projects', {'name': 'Morrow health', 'type': 'Mobile app', 'color': 'lime', 'result': '4.9 App Store rating', 'text': 'A warmer, more human way to build a daily care habit.'}),
                *[('internships', {'title': title, 'text': '12-week paid placement'}) for title in ['React Development', 'Python + FastAPI', 'Full Stack', 'UI / UX Design', 'GST Management', 'Accounting']]
            ]
            db.executemany('INSERT INTO content(kind,data,created_at) VALUES(?,?,?)', [(kind, json.dumps(data), datetime.now().isoformat(timespec='seconds')) for kind, data in default_content])
        for row in db.execute("SELECT data FROM content WHERE kind = 'certificates'"):
            certificate = json.loads(row['data'])
            if all(certificate.get(key) for key in ('number', 'candidate', 'category', 'duration', 'issue_date')):
                db.execute('INSERT INTO certificates(number,candidate,category,duration,issue_date,image) VALUES(?,?,?,?,?,?) ON CONFLICT (number) DO UPDATE SET candidate = EXCLUDED.candidate, category = EXCLUDED.category, duration = EXCLUDED.duration, issue_date = EXCLUDED.issue_date, image = COALESCE(EXCLUDED.image, certificates.image)', (certificate['number'], certificate['candidate'], certificate['category'], certificate['duration'], certificate['issue_date'], certificate.get('image')))
        db.commit()

def content_rows(kind):
    with connection() as db:
        return [{'id': row['id'], **json.loads(row['data'])} for row in db.execute('SELECT id, data FROM content WHERE kind = ? ORDER BY id', (kind,))]

def admin_is_authenticated(token):
    return bool(token and token in admin_tokens)

def authenticated_token(authorization):
    return authorization.removeprefix('Bearer ').strip() if authorization else None

@app.on_event('startup')
def startup(): init_db()

@app.get('/api/health')
def health(): return {'status': 'ok', 'local_only': True}

@app.get('/api/content/{kind}')
def get_content(kind: str):
    return content_rows(kind)

@app.get('/api/inquiry-fields')
def get_inquiry_fields():
    with connection() as db:
        return [{**dict(row), 'options': json.loads(row['options'] or '[]')} for row in db.execute('SELECT id, label, field_name, field_type, required, options FROM inquiry_fields ORDER BY id')]

@app.get('/api/service-options')
def get_service_options():
    options = [item.get('title') for item in content_rows('service_option') if item.get('title')]
    return options or ['Website development', 'Web application', 'Mobile application', 'GST / Accounting', 'Consulting']

@app.post('/api/admin/service-options')
def add_service_option(title: str = Form(...), authorization: str | None = Header(default=None)):
    if not admin_is_authenticated(authenticated_token(authorization)):
        return {'detail': 'Admin login required'}
    clean_title = title.strip()
    if not clean_title:
        return {'detail': 'Option name is required'}
    with connection() as db:
        existing = next((item for item in db.execute('SELECT id, data FROM content WHERE kind = ?', ('service_option',)) if json.loads(item['data']).get('title') == clean_title), None)
        if existing:
            return {'detail': 'This option already exists'}
        cursor = db.execute('INSERT INTO content(kind,data,created_at) VALUES(?,?,?)', ('service_option', json.dumps({'title': clean_title}), datetime.now().isoformat(timespec='seconds')))
        db.commit()
    return {'id': cursor.lastrowid, 'title': clean_title}

@app.delete('/api/admin/service-options/{option_id}')
def delete_service_option(option_id: int, authorization: str | None = Header(default=None)):
    if not admin_is_authenticated(authenticated_token(authorization)):
        return {'detail': 'Admin login required'}
    with connection() as db:
        db.execute('DELETE FROM content WHERE id = ? AND kind = ?', (option_id, 'service_option'))
        db.commit()
    return {'deleted': option_id}

@app.post('/api/admin/login')
def admin_login(email: str = Form(...), password: str = Form(...)):
    configured_email = os.getenv('ADMIN_EMAIL', 'admin@gmail.com')
    configured_password = os.getenv('ADMIN_PASSWORD', '900AB')
    if not configured_email or not configured_password or not secrets.compare_digest(email, configured_email) or not secrets.compare_digest(password, configured_password):
        return {'authenticated': False}
    token = secrets.token_urlsafe(32)
    admin_tokens.add(token)
    return {'authenticated': True, 'token': token}

@app.post('/api/admin/inquiry-fields')
def add_inquiry_field(label: str = Form(...), field_type: str = Form('text'), required: bool = Form(False), options: str = Form(''), authorization: str | None = Header(default=None)):
    if not admin_is_authenticated(authenticated_token(authorization)):
        return {'detail': 'Admin login required'}
    field_name = ''.join(char.lower() if char.isalnum() else '_' for char in label).strip('_')
    if not field_name:
        return {'detail': 'Field label is required'}
    try:
        with connection() as db:
            safe_type = field_type if field_type in {'text', 'email', 'number', 'date', 'textarea', 'multi_option'} else 'text'
            parsed_options = [option.strip() for option in options.split(',') if option.strip()] if safe_type == 'multi_option' else []
            if safe_type == 'multi_option' and not parsed_options:
                return {'detail': 'Add at least two options for a multiple-option field'}
            cursor = db.execute('INSERT INTO inquiry_fields(label,field_name,field_type,required,options,created_at) VALUES(?,?,?,?,?,?)', (label.strip(), field_name, safe_type, int(required), json.dumps(parsed_options), datetime.now().isoformat(timespec='seconds')))
            db.commit()
            return {'id': cursor.lastrowid, 'label': label.strip(), 'field_name': field_name, 'field_type': safe_type, 'required': int(required), 'options': parsed_options}
    except errors.UniqueViolation:
        return {'detail': 'A field with this label already exists'}

@app.delete('/api/admin/inquiry-fields/{field_id}')
def delete_inquiry_field(field_id: int, authorization: str | None = Header(default=None)):
    if not admin_is_authenticated(authenticated_token(authorization)):
        return {'detail': 'Admin login required'}
    with connection() as db:
        db.execute('DELETE FROM inquiry_fields WHERE id = ?', (field_id,))
        db.commit()
    return {'deleted': field_id}

@app.post('/api/admin/background-video')
async def upload_background_video(video: UploadFile = File(...), authorization: str | None = Header(default=None)):
    if not admin_is_authenticated(authenticated_token(authorization)):
        return {'detail': 'Admin login required'}
    if not video.content_type or not video.content_type.startswith('video/'):
        return {'detail': 'Only video files are allowed'}
    safe_name = Path(video.filename or 'background-video.mp4').name
    content = await video.read()
    if len(content) > 100 * 1024 * 1024:
        return {'detail': 'Video must be smaller than 100 MB'}
    (UPLOADS / safe_name).write_bytes(content)
    video_path = f'/uploads/{safe_name}'
    with connection() as db:
        db.execute('DELETE FROM content WHERE kind = ?', ('background_video',))
        db.execute('INSERT INTO content(kind,data,created_at) VALUES(?,?,?)', ('background_video', json.dumps({'video': video_path, 'name': safe_name}), datetime.now().isoformat(timespec='seconds')))
        db.commit()
    return {'video': video_path, 'name': safe_name}

@app.post('/api/inquiries')
async def create_inquiry(request: Request, name: str = Form(...), email: str = Form(...), country_code: str = Form('+91'), mobile_number: str = Form(...), service: str = Form('General'), details: str = Form(''), attachment: UploadFile | None = File(None)):
    if not re.fullmatch(r'\+[1-9]\d{0,3}', country_code) or not re.fullmatch(r'\d{7,15}', mobile_number.strip()):
        return {'detail': 'Enter a valid country code and mobile number'}
    attachment_name = None
    attachment_content = None
    if attachment and attachment.filename:
        safe_name = Path(attachment.filename).name
        attachment_content = attachment.file.read()
        (UPLOADS / safe_name).write_bytes(attachment_content)
        attachment_name = safe_name
    form_data = await request.form()
    reserved = {'name', 'email', 'country_code', 'mobile_number', 'service', 'details', 'attachment'}
    with connection() as field_db:
        multi_field_names = {row['field_name'] for row in field_db.execute("SELECT field_name FROM inquiry_fields WHERE field_type = 'multi_option'")}
    extra_fields = {}
    for key, value in form_data.multi_items():
        if key in reserved or hasattr(value, 'filename'):
            continue
        if key in multi_field_names:
            extra_fields.setdefault(key, []).append(str(value))
        else:
            extra_fields[key] = str(value)
    with connection() as db:
        extra_fields['mobile_number'] = f'{country_code}{mobile_number.strip()}'
        cursor = db.execute('INSERT INTO inquiries(name,email,service,details,extra_fields,created_at) VALUES(?,?,?,?,?,?)', (name,email,service,details,json.dumps(extra_fields),datetime.now().isoformat(timespec='seconds')))
        db.commit()
        return {'id': cursor.lastrowid, 'status': 'new', 'attachment': attachment_name}

@app.get('/api/inquiries')
def list_inquiries(authorization: str | None = Header(default=None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    if not admin_is_authenticated(token):
        return {'detail': 'Admin login required'}
    with connection() as db: return [dict(row) for row in db.execute('SELECT * FROM inquiries ORDER BY id DESC')]

@app.delete('/api/inquiries/{inquiry_id}')
def delete_inquiry(inquiry_id: int, authorization: str | None = Header(default=None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    if not admin_is_authenticated(token): return {'detail': 'Admin login required'}
    with connection() as db:
        db.execute('DELETE FROM inquiries WHERE id = ?', (inquiry_id,))
        db.commit()
    return {'deleted': inquiry_id}

@app.get('/api/admin/content')
def admin_content(authorization: str | None = Header(default=None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    if not admin_is_authenticated(token): return {'detail': 'Admin login required'}
    with connection() as db:
        return [{'id': row['id'], 'kind': row['kind'], **json.loads(row['data'])} for row in db.execute('SELECT id, kind, data FROM content ORDER BY id DESC')]

@app.post('/api/admin/content')
async def add_content(kind: str = Form(...), title: str = Form(''), name: str = Form(''), text: str = Form(''), content_type: str = Form(''), result: str = Form(''), color: str = Form('coral'), icon: str = Form(''), tags: str = Form(''), quote: str = Form(''), role: str = Form(''), candidate: str = Form(''), category: str = Form(''), duration: str = Form(''), issue_date: str = Form(''), number: str = Form(''), image: UploadFile | None = File(None), authorization: str | None = Header(default=None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    if not admin_is_authenticated(token): return {'detail': 'Admin login required'}
    parsed = {key: value for key, value in {
        'title': title, 'name': name, 'text': text, 'type': content_type,
        'result': result, 'color': color, 'icon': icon, 'tags': [tag.strip() for tag in tags.split(',') if tag.strip()],
        'quote': quote, 'role': role, 'candidate': candidate, 'category': category,
        'duration': duration, 'issue_date': issue_date, 'number': number
    }.items() if value}
    if kind == 'certificates':
        parsed['category'] = parsed.get('category') or parsed.get('title') or 'Certificate'
        parsed['duration'] = parsed.get('duration') or parsed.get('text') or 'Not specified'
        parsed['issue_date'] = parsed.get('issue_date') or datetime.now().date().isoformat()
    if image and image.filename:
        safe_name = Path(image.filename).name
        (UPLOADS / safe_name).write_bytes(await image.read())
        parsed['image'] = f'/uploads/{safe_name}'
    if not parsed.get('title') and not parsed.get('name') and not parsed.get('candidate'):
        return {'detail': 'A title, name, or candidate is required'}
    if kind == 'certificates' and not all(parsed.get(key) for key in ('number', 'candidate', 'category', 'duration', 'issue_date')):
        return {'detail': 'Candidate, certificate number, category, duration, and issue date are required'}
    with connection() as db:
        cursor = db.execute('INSERT INTO content(kind,data,created_at) VALUES(?,?,?)', (kind, json.dumps(parsed), datetime.now().isoformat(timespec='seconds')))
        if kind == 'certificates':
            db.execute('INSERT INTO certificates(number,candidate,category,duration,issue_date,image) VALUES(?,?,?,?,?,?) ON CONFLICT (number) DO UPDATE SET candidate = EXCLUDED.candidate, category = EXCLUDED.category, duration = EXCLUDED.duration, issue_date = EXCLUDED.issue_date, image = EXCLUDED.image', (parsed['number'], parsed['candidate'], parsed['category'], parsed['duration'], parsed['issue_date'], parsed.get('image')))
        db.commit()
        return {'id': cursor.lastrowid, 'kind': kind, **parsed}

@app.delete('/api/admin/content/{content_id}')
def delete_content(content_id: int, authorization: str | None = Header(default=None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    if not admin_is_authenticated(token): return {'detail': 'Admin login required'}
    with connection() as db:
        existing = db.execute('SELECT kind, data FROM content WHERE id = ?', (content_id,)).fetchone()
        db.execute('DELETE FROM content WHERE id = ?', (content_id,))
        if existing and existing['kind'] == 'certificates':
            certificate = json.loads(existing['data'])
            db.execute('DELETE FROM certificates WHERE number = ?', (certificate.get('number'),))
        db.commit()
    return {'deleted': content_id}

@app.put('/api/admin/content/{content_id}')
async def update_content(content_id: int, kind: str = Form(...), title: str = Form(''), name: str = Form(''), text: str = Form(''), content_type: str = Form(''), result: str = Form(''), color: str = Form('coral'), icon: str = Form(''), tags: str = Form(''), quote: str = Form(''), role: str = Form(''), candidate: str = Form(''), category: str = Form(''), duration: str = Form(''), issue_date: str = Form(''), number: str = Form(''), image: UploadFile | None = File(None), authorization: str | None = Header(default=None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else None
    if not admin_is_authenticated(token): return {'detail': 'Admin login required'}
    parsed = {key: value for key, value in {
        'title': title, 'name': name, 'text': text, 'type': content_type,
        'result': result, 'color': color, 'icon': icon, 'tags': [tag.strip() for tag in tags.split(',') if tag.strip()],
        'quote': quote, 'role': role, 'candidate': candidate, 'category': category,
        'duration': duration, 'issue_date': issue_date, 'number': number
    }.items() if value}
    if kind == 'certificates':
        parsed['category'] = parsed.get('category') or parsed.get('title') or 'Certificate'
        parsed['duration'] = parsed.get('duration') or parsed.get('text') or 'Not specified'
        parsed['issue_date'] = parsed.get('issue_date') or datetime.now().date().isoformat()
    with connection() as db:
        existing = db.execute('SELECT data FROM content WHERE id = ?', (content_id,)).fetchone()
        if not existing: return {'detail': 'Content not found'}
        previous = json.loads(existing['data'])
        if image and image.filename:
            safe_name = Path(image.filename).name
            (UPLOADS / safe_name).write_bytes(await image.read())
            parsed['image'] = f'/uploads/{safe_name}'
        elif previous.get('image'):
            parsed['image'] = previous['image']
        if kind == 'certificates' and not all(parsed.get(key) for key in ('number', 'candidate', 'category', 'duration', 'issue_date')):
            return {'detail': 'Candidate, certificate number, category, duration, and issue date are required'}
        db.execute('UPDATE content SET kind = ?, data = ? WHERE id = ?', (kind, json.dumps(parsed), content_id))
        if previous.get('number') or kind == 'certificates':
            db.execute('DELETE FROM certificates WHERE number = ?', (previous.get('number'),))
        if kind == 'certificates':
            db.execute('INSERT INTO certificates(number,candidate,category,duration,issue_date,image) VALUES(?,?,?,?,?,?) ON CONFLICT (number) DO UPDATE SET candidate = EXCLUDED.candidate, category = EXCLUDED.category, duration = EXCLUDED.duration, issue_date = EXCLUDED.issue_date, image = EXCLUDED.image', (parsed['number'], parsed['candidate'], parsed['category'], parsed['duration'], parsed['issue_date'], parsed.get('image')))
        db.commit()
    return {'id': content_id, 'kind': kind, **parsed}

@app.post('/api/internships')
async def apply_internship(name: str = Form(...), email: str = Form(...), category: str = Form(...), resume: UploadFile | None = File(None)):
    resume_name = None
    if resume and resume.filename:
        resume_name = Path(resume.filename).name
        (UPLOADS / resume_name).write_bytes(await resume.read())
    with connection() as db:
        cursor = db.execute('INSERT INTO internship_applications(name,email,category,resume,created_at) VALUES(?,?,?,?,?)', (name,email,category,resume_name,datetime.now().isoformat(timespec='seconds')))
        db.commit()
        return {'id': cursor.lastrowid, 'status': 'pending'}

def find_certificate(number: str):
    normalized_number = re.sub(r'[\s-]+', '', number).upper()
    with connection() as db:
        row = db.execute("SELECT * FROM certificates WHERE REPLACE(REPLACE(UPPER(number), ' ', ''), '-', '') = ?", (normalized_number,)).fetchone()
        if row:
            return dict(row)
        for content_row in db.execute("SELECT id, data FROM content WHERE kind = 'certificates' ORDER BY id DESC"):
            certificate = json.loads(content_row['data'])
            stored_number = re.sub(r'[\s-]+', '', str(certificate.get('number', ''))).upper()
            if stored_number == normalized_number:
                return {'id': content_row['id'], **certificate}
    return None

@app.get('/api/certificates/{number}')
def verify_certificate(number: str):
    certificate = find_certificate(number)
    return {'valid': bool(certificate), 'certificate': certificate}

@app.get('/api/certificates/{number}/download')
def download_certificate(number: str):
    certificate = find_certificate(number)
    image = certificate.get('image') if certificate else None
    if not image or not image.startswith('/uploads/'):
        return {'detail': 'Certificate image not found'}
    image_path = (UPLOADS / Path(image).name).resolve()
    if not image_path.is_file() or image_path.parent != UPLOADS.resolve():
        return {'detail': 'Certificate image not found'}
    return FileResponse(image_path, filename=f'certificate-{certificate["number"]}{image_path.suffix}')

@app.get('/api/analytics')
def analytics():
    with connection() as db:
        return {'leads': db.execute('SELECT COUNT(*) AS count FROM inquiries').fetchone()['count'], 'interns': db.execute('SELECT COUNT(*) AS count FROM internship_applications').fetchone()['count'], 'certificates': db.execute('SELECT COUNT(*) AS count FROM certificates').fetchone()['count'], 'projects': 3, 'testimonials': 2}
