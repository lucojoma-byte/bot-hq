"""Persistencia y límites de negocio. Inspirado en store/engine-memory de bot-hq.

No ejecuta red, modelos ni acciones externas al importar este módulo.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid

ROOT = Path('/Volumes/JOE_HQ')
SCOPES = {
    'guardian': ['02_GUARDIAN_ACCESOS_CNC'],
    'casa_kiraz': ['03_CASA_KIRAZ'],
    'holding': ['01_PLAN_DE_VIDA_Y_RETIRO_CHAPALA', '04_SISTEMAS_MARKETING_Y_VIRALIDAD'],
}
PROFILES = [
    {'id': 'codex', 'name': 'ChatGPT Pro · Codex Terra', 'model': 'gpt-5.6-terra'},
    {'id': 'codex_sol', 'name': 'ChatGPT Pro · Codex Sol', 'model': 'gpt-5.6-sol'},
]
MODEL_ALLOWLIST = {p['model'] for p in PROFILES}

class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

def short_text(value, limit=12000, empty=False):
    if not isinstance(value, str) or len(value) > limit or ('\x00' in value):
        raise Problem('Texto inválido o demasiado largo.')
    if not empty and not value.strip():
        raise Problem('Falta el texto.')
    return value.strip() if not empty else value

def safe_path(base: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or '\x00' in name or '\\' in name:
        raise Problem('Ruta no permitida.', 403)
    parts = Path(name)
    if parts.is_absolute() or any(x in ('.', '..') for x in parts.parts):
        raise Problem('Ruta no permitida.', 403)
    base = base.absolute()
    if base.is_symlink():
        raise Problem('No se permiten enlaces simbólicos.', 403)
    target = base / parts
    # Comprobar TODOS los componentes existentes, incluso padres de base.
    for component in (target, *target.parents):
        if component.is_symlink():
            raise Problem('No se permiten enlaces simbólicos.', 403)
    if not target.resolve().is_relative_to(base.resolve()):
        raise Problem('Archivo fuera del bot.', 403)
    if target.exists() and not target.is_file():
        raise Problem('Solo se permiten archivos normales.', 403)
    return target

def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.tmp-' + secrets.token_hex(6))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(content)
    os.replace(temp, path)

def cache_environment(root=ROOT):
    c = root / 'cache'
    return {
        'npm_config_cache': str(c/'npm'), 'PNPM_HOME': str(c/'pnpm-bin'),
        'npm_config_store_dir': str(c/'pnpm'), 'PIP_CACHE_DIR': str(c/'pip'),
        'UV_CACHE_DIR': str(c/'uv'), 'UV_PYTHON_INSTALL_DIR': str(c/'uv-python'),
        'PLAYWRIGHT_BROWSERS_PATH': str(c/'playwright'), 'XDG_CACHE_HOME': str(c/'xdg'),
        'HF_HOME': str(c/'huggingface'), 'HUGGINGFACE_HUB_CACHE': str(c/'huggingface/hub'),
        'TORCH_HOME': str(c/'torch'), 'TMPDIR': str(c/'tmp'),
        'PYTHONDONTWRITEBYTECODE': '1', 'HF_HUB_OFFLINE': '1',
        'TRANSFORMERS_OFFLINE': '1', 'UV_NO_CACHE': '0',
        'PIP_CONFIG_FILE': str(root/'app/pip.conf'),
    }

def preflight(root=ROOT, require_mount=True):
    if require_mount and (root != ROOT or not root.is_mount()):
        raise Problem('JOE_HQ no está montado en /Volumes/JOE_HQ. Conecta el volumen y vuelve a iniciar.', 503)
    for folder in ['app', 'data', 'cache', 'logs', 'backups', 'memoria/guardian', 'memoria/casa_kiraz', 'memoria/holding']:
        target = root/folder
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            raise Problem('El almacenamiento debe permanecer dentro de JOE_HQ: '+folder, 503)
        try:
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            # No crear probes que luego habría que borrar sin autorización.
            fd = os.open(target, os.O_RDONLY)
            os.close(fd)
            if not os.access(target, os.W_OK):
                raise PermissionError()
        except OSError:
            raise Problem('Sin permiso de escritura en '+str(target)+'. Ejecuta desde Terminal con acceso al volumen.', 503)
    for name in ['npm', 'pnpm', 'pip', 'uv', 'uv-python', 'playwright', 'xdg', 'huggingface', 'torch', 'tmp']:
        try:
            (root/'cache'/name).mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            raise Problem('No se puede escribir la caché en JOE_HQ. No se usará el disco interno.', 503)

class Store:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.lock = threading.RLock()
        db_path=safe_path(self.root/'data','joe-hq.sqlite3')
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        os.chmod(db_path,0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bots(id TEXT PRIMARY KEY,name TEXT NOT NULL,scope TEXT NOT NULL,profile TEXT NOT NULL,model TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'listo',generation TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,bot_id TEXT NOT NULL REFERENCES bots(id),generation TEXT NOT NULL,role TEXT NOT NULL,text TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,bot_id TEXT NOT NULL REFERENCES bots(id),title TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,bot_id TEXT NOT NULL REFERENCES bots(id),action TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,result TEXT);
        CREATE TABLE IF NOT EXISTS drive_roots(scope TEXT NOT NULL,name TEXT NOT NULL,file_id TEXT NOT NULL,PRIMARY KEY(scope,name));
        ''')
        self.db.commit()
        self.sessions = {}
        self.computer = {'owner': 'user', 'bot_id': None, 'available': False,
                         'reason': 'Control del escritorio y pantallas independientes pendientes de integración macOS.'}
        self.bot_locks = {}
        self.active_processes = {}
        self.engine_tickets = {}
        self.events = []
        if not self.bots():
            for key, name in [('guardian','Guardián Ventas'),('casa_kiraz','Casa Kiraz'),('holding','Holding D7')]:
                self.create_bot(name, key, key)
        # Una ejecución interrumpida nunca se representa como éxito ni se repite.
        self.db.execute("UPDATE bots SET status='listo'")
        self.db.execute("UPDATE approvals SET status='interrumpida',result='Verificar destino manualmente; no se reintentará.' WHERE status='ejecutando'")
        self.db.execute("UPDATE messages SET status='interrumpido' WHERE status='pensando'")
        self.db.commit()

    def setting(self, key, value=None):
        with self.lock:
            if value is not None:
                self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,value));self.db.commit()
            row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
            return row[0] if row else None

    def bots(self):
        with self.lock:
            return [dict(x) for x in self.db.execute('SELECT * FROM bots ORDER BY rowid')]

    def bot(self, bot_id):
        if not isinstance(bot_id,str) or not re.fullmatch(r'[a-z0-9_]{1,40}',bot_id):
            raise Problem('Bot inválido.',404)
        with self.lock:
            row=self.db.execute('SELECT * FROM bots WHERE id=?',(bot_id,)).fetchone()
            if not row:raise Problem('Bot no encontrado.',404)
            return dict(row)

    def home(self, bot_id):
        b=self.bot(bot_id)
        # Bot inicial usa el directorio canónico; identidades adicionales tienen home propio.
        home=self.root/'memoria'/b['scope']
        if b['id'] != b['scope']:home=home/'bots'/b['id']
        return home

    def workspace(self, bot_id):
        b=self.bot(bot_id)
        return self.root/'data'/b['scope']/b['id']/'files'

    def create_bot(self,name,scope,bot_id=None):
        name=short_text(name,60)
        if scope not in SCOPES:raise Problem('Unidad de negocio inválida.')
        with self.lock:
            if len(self.bots())>=5:raise Problem('Máximo cinco bots. Crea un hilo en un bot existente.',409)
            bot_id=bot_id or 'bot_'+secrets.token_hex(6)
            self.db.execute('INSERT INTO bots VALUES(?,?,?,?,?,?,?)',(bot_id,name,scope,'codex',PROFILES[0]['model'],'listo',uuid.uuid4().hex))
            try:
                home=self.home(bot_id)
                for p in [home/'memories',self.workspace(bot_id)]:p.mkdir(parents=True,exist_ok=True,mode=0o700)
                soul=f'''# {name}
Eres un agente de José María (Joe). Trabaja exclusivamente para {scope}.
Responde en español con mensajes breves y digeribles. Distingue datos de supuestos.
No transfieras memoria, archivos ni conexiones entre Guardián y Casa Kiraz.
No inventes precios, márgenes, plazos ni éxitos de herramientas.
Solo puedes usar herramientas controladas por JOE HQ. Acciones externas requieren aprobación de Joe.
No hay herramientas de terminal ni navegador libre. No solicites proveedores de API de pago.
'''
                if scope=='guardian':soul+='No-List: cero proyectos sin anticipo; cero diagnósticos gratis; cero herrería informal de tubo delgado. Margen neto objetivo 25%-30% debe comprobarse con costos, nunca suponerse.\n'
                for path,content in [('SOUL.md',soul),('memories/MEMORY.md',''),('memories/USER.md','Joe gobierna y toma las decisiones.\n')]:
                    atomic_write(safe_path(home,path),content)
                atomic_write(safe_path(home,'config.yaml'),'model:\n  provider: openai-codex\n  default: gpt-5.6-terra\nfallback_providers: []\nfallback_model: {}\nplatform_toolsets:\n  cli: [memory, joe_hq]\nmcp_servers: {}\n')
                self.db.commit()
            except BaseException:
                self.db.rollback();raise
            return self.bot(bot_id)

    def memory(self,bot_id,values=None):
        home=self.home(bot_id)
        mapping={'soul':'SOUL.md','memory':'memories/MEMORY.md','user':'memories/USER.md'}
        with self.lock:
            if values is not None:
                if self.bot(bot_id)['status']=='pensando':raise Problem('Espera a que el bot termine antes de editar su memoria.',409)
                content={k:short_text(v,40000,True) for k,v in values.items() if k in mapping}
                stamp=str(time.time_ns())
                for k,v in content.items():
                    p=safe_path(home,mapping[k])
                    backup=safe_path(self.root/'backups',bot_id+'/'+stamp+'/'+mapping[k])
                    atomic_write(backup,p.read_text(encoding='utf-8') if p.exists() else '')
                    atomic_write(p,v)
            return {k:safe_path(home,p).read_text(encoding='utf-8') for k,p in mapping.items()}

    def add_message(self,bot_id,role,text,status='completo'):
        b=self.bot(bot_id)
        with self.lock:
            cur=self.db.execute('INSERT INTO messages(bot_id,generation,role,text,status,created) VALUES(?,?,?,?,?,?)',(bot_id,b['generation'],role,text,status,time.time()))
            self.db.commit();return cur.lastrowid

    def detail(self,bot_id):
        b=self.bot(bot_id)
        with self.lock:
            messages=[dict(x) for x in self.db.execute('SELECT * FROM messages WHERE bot_id=? AND generation=? ORDER BY id',(bot_id,b['generation']))]
            tasks=[dict(x) for x in self.db.execute('SELECT * FROM tasks WHERE bot_id=?',(bot_id,))]
        base=self.workspace(bot_id)
        files=[]
        if base.exists():
            for p in base.rglob('*'):
                if p.is_file() and not p.is_symlink():
                    try:
                        p=safe_path(base,str(p.relative_to(base)))
                        files.append({'name':str(p.relative_to(base)),'size':p.stat().st_size})
                    except Problem:pass
        return {'bot':b,'messages':messages[-500:],'tasks':tasks,'files':files,'memory':self.memory(bot_id),'approvals':self.approvals(bot_id),'drive':[]}

    def save_file(self,bot_id,name,content):
        short_text(name,200);short_text(content,500000,True)
        path=safe_path(self.workspace(bot_id),name)
        with self.lock:
            if path.exists():raise Problem('Ese archivo ya existe; usa otro nombre para conservarlo.',409)
            atomic_write(path,content)
        return {'name':name,'size':path.stat().st_size}

    def read_file(self,bot_id,name):
        p=safe_path(self.workspace(bot_id),name)
        if not p.exists():raise Problem('Archivo no encontrado.',404)
        if p.stat().st_size>500000:raise Problem('Archivo demasiado grande para mostrar.')
        try:return {'name':name,'content':p.read_text(encoding='utf-8')}
        except UnicodeError:raise Problem('Este visor admite texto UTF-8.')

    def task(self,bot_id,title):
        self.bot(bot_id);title=short_text(title,300)
        task={'id':uuid.uuid4().hex,'bot_id':bot_id,'title':title,'status':'pendiente'}
        with self.lock:
            self.db.execute('INSERT INTO tasks VALUES(:id,:bot_id,:title,:status)',task);self.db.commit()
        return task

    def profile(self,bot_id,profile):
        self.bot(bot_id)
        chosen=next((p for p in PROFILES if p['id']==profile),None)
        if not chosen:raise Problem('Solo se permiten perfiles Codex verificados sin API de pago.')
        with self.lock:
            if self.bot(bot_id)['status']=='pensando':raise Problem('El bot está trabajando.',409)
            self.db.execute('UPDATE bots SET profile=?,model=? WHERE id=?',(profile,chosen['model'],bot_id));self.db.commit()
        return self.bot(bot_id)

    def new_session(self,bot_id):
        self.bot(bot_id)
        with self.lock:
            if self.bot(bot_id)['status']=='pensando':raise Problem('El bot está trabajando.',409)
            self.db.execute('UPDATE bots SET generation=? WHERE id=?',(uuid.uuid4().hex,bot_id));self.db.commit()
        return self.detail(bot_id)

    def relay(self,source,target,text):
        a,b=self.bot(source),self.bot(target)
        if source==target:raise Problem('Elige otro bot.')
        # Holding tampoco es un puente automático entre datos de negocios.
        if a['scope']!=b['scope']:raise Problem('Aislamiento: mensajes entre unidades de negocio bloqueados.',403)
        text=short_text(text,4000)
        self.add_message(target,'user',f"Mensaje explícito de {a['name']}: {text}")
        self.add_message(source,'system',f"Mensaje entregado a {b['name']}. Transporte JOE HQ; comunicación nativa Hermes pendiente.")
        return {'delivered':True,'native':False}

    def approval(self,bot_id,action,payload):
        self.bot(bot_id)
        if action not in {'gmail_send','calendar_create','instagram_publish','drive_delete'}:
            raise Problem('Acción no permitida.',403)
        if not isinstance(payload,dict):raise Problem('Carga inválida.')
        raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        if len(raw)>16000:raise Problem('Carga demasiado grande.')
        ident=uuid.uuid4().hex
        with self.lock:
            self.db.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)',(ident,bot_id,action,raw,hashlib.sha256(raw.encode()).hexdigest(),'pendiente',time.time(),None));self.db.commit()
        return {'id':ident,'status':'pendiente','message':'Joe debe aprobar la carga exacta en la UI.'}

    def approvals(self,bot_id=None):
        with self.lock:
            query='SELECT * FROM approvals'+(' WHERE bot_id=?' if bot_id else '')+' ORDER BY created DESC LIMIT 100'
            rows=[dict(x) for x in self.db.execute(query,(bot_id,) if bot_id else ())]
            for row in rows:row['payload']=json.loads(row['payload'])
            return rows

    def decide(self,ident,decision,execute):
        if decision not in {'approve','reject'}:raise Problem('Decisión inválida.')
        with self.lock:
            row=self.db.execute('SELECT * FROM approvals WHERE id=?',(ident,)).fetchone()
            if not row:raise Problem('Aprobación no encontrada.',404)
            row=dict(row)
            if row['status']!='pendiente':raise Problem('Esta aprobación ya fue resuelta.',409)
            if time.time()-row['created']>900:
                self.db.execute("UPDATE approvals SET status='expirada' WHERE id=?",(ident,));self.db.commit()
                raise Problem('Aprobación expirada.',409)
            if decision=='reject':
                self.db.execute("UPDATE approvals SET status='rechazada' WHERE id=?",(ident,));self.db.commit()
                return {'status':'rechazada'}
            if not hmac.compare_digest(hashlib.sha256(row['payload'].encode()).hexdigest(),row['digest']):
                raise Problem('La carga cambió. Acción bloqueada.',403)
            self.db.execute("UPDATE approvals SET status='ejecutando' WHERE id=? AND status='pendiente'",(ident,));self.db.commit()
        try:
            result=execute(row['bot_id'],row['action'],json.loads(row['payload']))
            status='completa'
        except Exception as exc:
            status='fallida'
            result={'error':str(exc) if isinstance(exc,Problem) else 'La ejecución no se confirmó. Verifica el destino antes de volver a crear la acción.'}
        with self.lock:
            self.db.execute('UPDATE approvals SET status=?,result=? WHERE id=?',(status,json.dumps(result,ensure_ascii=False),ident));self.db.commit()
        return {'status':status,'result':result}

    def setup_password(self,password):
        if not isinstance(password,str) or len(password)<12 or len(password)>256:raise Problem('Usa una contraseña local de 12 a 256 caracteres.')
        with self.lock:
            if self.setting('password'):raise Problem('La contraseña ya fue configurada.',409)
            salt=secrets.token_bytes(32)
            digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
            self.setting('password',salt.hex()+':'+digest)

    def password_ok(self,password):
        stored=self.setting('password')
        if not stored or not isinstance(password,str) or len(password)>256:return False
        salt,expected=stored.split(':')
        actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        return hmac.compare_digest(actual,expected)

    def login(self):
        token=secrets.token_urlsafe(40)
        session={'csrf':secrets.token_urlsafe(32),'expires':time.time()+12*3600}
        with self.lock:self.sessions[token]=session
        return token,session

    def session(self,token):
        with self.lock:
            s=self.sessions.get(token)
            return s if s and s['expires']>time.time() else None
