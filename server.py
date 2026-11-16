#!/usr/bin/env python3
"""JOE HQ local. API stdlib sin instalaciones ni proveedores de API de pago.

La UI conserva tokens y estructura visual de Bot HQ; el backend reemplaza sus
integraciones Linux/Orgo/xAI, inseguras para los límites de esta instalación.
"""
from __future__ import annotations
import argparse
import base64
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, unquote, parse_qs
from local_engine.core import Store, Problem, ROOT, PROFILES, SCOPES, MODEL_ALLOWLIST, preflight, cache_environment, safe_path, short_text
from local_engine.composio_mcp import ComposioMCP, TOKEN_FILE

APP=Path(__file__).resolve().parent
HERMES_PYTHON=Path('/Users/m4/.hermes/installs/038c51e759d66ce1/environments/e5a1728f585a44cdb63518d0e4d705e5/venv/bin/python')
ALLOWED_HOSTS={'127.0.0.1:8787','localhost:8787'}
ALLOWED_ORIGINS={'http://127.0.0.1:8787','http://localhost:8787'}

def process_env(root,home=None):
    # No heredar credenciales ni proveedores presentes en la terminal.
    result={k:os.environ[k] for k in ['PATH','HOME','USER','LANG','LC_ALL','SYSTEMROOT'] if k in os.environ}
    result.update(cache_environment(root))
    if home:result['HERMES_HOME']=str(home)
    return result

class Application:
    def __init__(self,store):
        self.store=store
        self.mcp=ComposioMCP(store,APP/'drive-folders.json')
        self.login_attempts=[]
        self.login_lock=threading.Lock()

    def capabilities(self):
        return {
            'hermes':{'installed':HERMES_PYTHON.is_file(),'provider':'openai-codex','verified_chat':False},
            'drive':{'configured':TOKEN_FILE.is_file(),'status':self.mcp.status,'transport':'composio-lucojoma'},
            'voice':{'stt':'faster-whisper local; audio de silencio probado','tts':'VibeVoice pendiente: runtime compatible ausente'},
            'computer':{'available':False,'status':'Coordinación de control disponible; escritorio remoto macOS pendiente'},
            'native_interbot':False,
            'connectors':{'drive':'lectura acotada implementada; MCP local pendiente de red',
                          'docs':'lectura de texto vía Drive','sheets':'lectura CSV vía Drive',
                          'gmail':'propuesta con aprobación; ejecución pendiente',
                          'calendar':'propuesta con aprobación; ejecución pendiente',
                          'instagram':'propuesta con aprobación; ejecución pendiente',
                          'github':'fork creado; conector de bots pendiente'},
            'imessage':'fase 2',
        }

    def state(self):
        return {'bots':self.store.bots(),'profiles':PROFILES,'capabilities':self.capabilities(),
                'approvals':self.store.approvals(),'computer':self.store.computer,
                'version':'0.1.0 · implementación parcial verificable'}

    def run_json(self,script,payload,timeout=180):
        if not HERMES_PYTHON.is_file():raise Problem('No se encontró el Python existente de Hermes.',503)
        try:
            result=subprocess.run([str(HERMES_PYTHON),'-B',str(APP/'local_engine'/script)],
                    input=json.dumps(payload,ensure_ascii=False),text=True,stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,cwd=str(APP),env=process_env(self.store.root),timeout=timeout)
            parsed=json.loads(result.stdout)
            if not parsed.get('ok'):raise Problem(parsed.get('error','El componente local no completó la operación.'),503)
            return parsed
        except subprocess.TimeoutExpired:raise Problem('El componente local excedió el tiempo de espera.',504)
        except (ValueError,OSError):raise Problem('No se pudo ejecutar el componente local. No se usó ningún proveedor alternativo.',503)

    def send(self,bot_id,text,already_saved=False):
        text=short_text(text,12000)
        bot=self.store.bot(bot_id)
        if bot['model'] not in MODEL_ALLOWLIST:raise Problem('Modelo no permitido.',403)
        with self.store.lock:
            if self.store.bot(bot_id)['status']=='pensando':raise Problem('Este bot sigue trabajando. Espera su respuesta.',409)
            if self.store.computer['owner']=='user' and self.store.computer['bot_id'] is not None:
                raise Problem('Devuelve el control al agente antes de iniciar otro turno.',409)
            if not already_saved:self.store.add_message(bot_id,'user',text)
            self.store.db.execute("UPDATE bots SET status='pensando' WHERE id=?",(bot_id,));self.store.db.commit()
            ident=self.store.add_message(bot_id,'assistant','',status='pensando')
        threading.Thread(target=self.turn,args=(bot_id,text,ident),daemon=True).start()
        return {'queued':True,'message_id':ident}

    def turn(self,bot_id,text,ident):
        ticket=secrets.token_urlsafe(40)
        bot=self.store.bot(bot_id)
        home=self.store.home(bot_id)
        history_path=safe_path(home,'sessions/'+bot['generation']+'.json')
        process=None
        try:
            if not HERMES_PYTHON.is_file():raise Problem('No se encontró el runtime de Hermes.',503)
            history=json.loads(history_path.read_text()) if history_path.exists() else []
            with self.store.lock:self.store.engine_tickets[ticket]={'bot_id':bot_id,'expires':time.time()+180}
            payload={'command':'run','home':str(home),'workspace':str(self.store.workspace(bot_id)),
                     'message':text,'model':bot['model'],'history':history,'session_id':bot['generation'],
                     'bot_id':bot_id,'callback_token':ticket,'callback_url':'http://127.0.0.1:8787/api/engine/tool'}
            process=subprocess.Popen([str(HERMES_PYTHON),'-B',str(APP/'local_engine/hermes_bridge.py')],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
                    cwd=str(APP),env=process_env(self.store.root,home),start_new_session=True)
            with self.store.lock:self.store.active_processes[bot_id]=process
            output,_=process.communicate(json.dumps(payload,ensure_ascii=False),timeout=150)
            if len(output)>5000000:raise Problem('Respuesta de Hermes demasiado grande.',502)
            result=json.loads(output)
            if not result.get('ok'):raise Problem(result.get('error','Hermes no completó la conversación.'),503)
            response=short_text(result.get('response',''),100000)
            if isinstance(result.get('history'),list):
                from local_engine.core import atomic_write
                atomic_write(history_path,json.dumps(result['history'],ensure_ascii=False))
            status='completo'
        except subprocess.TimeoutExpired:
            response='Hermes no respondió en 150 segundos. Verifica la conexión Codex en Terminal. No se usó otro proveedor.';status='error'
        except Exception as exc:
            response=str(exc) if isinstance(exc,Problem) else 'No se pudo completar la conversación Hermes. Revisa el diagnóstico local.'
            status='error'
        finally:
            if process and process.poll() is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=5)
            with self.store.lock:
                self.store.engine_tickets.pop(ticket,None)
                self.store.active_processes.pop(bot_id,None)
                self.store.db.execute('UPDATE messages SET text=?,status=? WHERE id=?',(response,status,ident))
                self.store.db.execute("UPDATE bots SET status='listo' WHERE id=?",(bot_id,));self.store.db.commit()

    def engine_tool(self,token,data):
        with self.store.lock:
            info=self.store.engine_tickets.get(token)
            if not info or info['expires']<time.time() or info['bot_id']!=data.get('bot_id'):
                raise Problem('Credencial de herramienta inválida.',403)
            bot_id=info['bot_id']
            if self.store.computer['owner']=='user' and self.store.computer['bot_id'] is not None:
                raise Problem('Joe tomó el control; herramienta suspendida.',409)
        args=data.get('arguments',{})
        if not isinstance(args,dict):raise Problem('Argumentos inválidos.')
        name=data.get('tool')
        if name=='save_file':return self.store.save_file(bot_id,args.get('path'),args.get('content'))
        if name=='list_files':return {'files':self.store.detail(bot_id)['files']}
        if name=='task_create':return self.store.task(bot_id,args.get('title'))
        if name=='drive_list':return self.mcp.list(bot_id,args.get('folder_id'))
        if name=='request_action':
            action=args.get('action')
            if action=='file_delete':action='drive_delete'
            payload=args.get('details')
            if action=='drive_delete':
                if not isinstance(payload,dict):raise Problem('Falta archivo Drive.')
                self.mcp.authorize(bot_id,payload.get('file_id'))
            return self.store.approval(bot_id,action,payload)
        raise Problem('Herramienta no permitida.',403)

    def control(self,bot_id,owner):
        self.store.bot(bot_id)
        if owner not in {'user','agent'}:raise Problem('Control inválido.')
        with self.store.lock:
            if owner=='agent' and self.store.computer['bot_id'] not in (None,bot_id):
                raise Problem('Otro bot tiene la coordinación del equipo.',409)
            if owner=='user':
                # Un único escritorio físico compartido. Suspender TODOS los turnos.
                for process in self.store.active_processes.values():
                    if process.poll() is None:
                        try:os.killpg(process.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                self.store.engine_tickets.clear()
            self.store.computer.update({'owner':owner,'bot_id':bot_id})
        return self.store.computer.copy()

    def voice(self,bot_id,data):
        self.store.bot(bot_id)
        mime=data.get('mime','audio/webm')
        extension={'audio/webm':'.webm','audio/webm;codecs=opus':'.webm','audio/mp4':'.m4a','audio/wav':'.wav','audio/ogg':'.ogg'}.get(mime)
        if not extension:raise Problem('Formato de audio no admitido.')
        encoded=data.get('audio')
        if not isinstance(encoded,str) or len(encoded)>28000000:raise Problem('Audio demasiado grande.')
        try:raw=base64.b64decode(encoded,validate=True)
        except ValueError:raise Problem('Audio inválido.')
        if not raw:raise Problem('Audio vacío.')
        # Audio retenido como archivo del bot: ninguna eliminación automática.
        path=safe_path(self.store.workspace(bot_id),'audio/'+secrets.token_hex(10)+extension)
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as handle:handle.write(raw)
        return self.run_json('voice.py',{'command':'transcribe','input_path':str(path),'language':'es'})

class Handler(BaseHTTPRequestHandler):
    server_version='JOE-HQ'
    protocol_version='HTTP/1.1'

    @property
    def app(self):return self.server.app

    def log_message(self,*args):
        # No logs de URL, mensajes, cookies ni identificadores de usuario.
        return

    def reply(self,status,data,extra=None,ctype='application/json; charset=utf-8'):
        body=json.dumps(data,ensure_ascii=False).encode() if not isinstance(data,bytes) else data
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Connection','close')
        self.close_connection=True
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Permissions-Policy','camera=(), geolocation=(), microphone=(self)')
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)

    def guard(self,mutating=False):
        if self.headers.get('Host') not in ALLOWED_HOSTS:raise Problem('Host no permitido.',403)
        origin=self.headers.get('Origin')
        if origin and origin not in ALLOWED_ORIGINS:raise Problem('Origen no permitido.',403)
        if self.headers.get('Sec-Fetch-Site')=='cross-site':raise Problem('Solicitud de otro sitio bloqueada.',403)
        if mutating and (self.headers.get('Content-Type','').split(';')[0]!='application/json'):
            raise Problem('Se requiere JSON.',415)

    def authenticated(self,csrf=False):
        try:
            cookie=cookies.SimpleCookie(self.headers.get('Cookie',''))
            token=cookie['joe_session'].value if 'joe_session' in cookie else ''
        except cookies.CookieError:token=''
        session=self.app.store.session(token)
        if not session:raise Problem('Inicia sesión con tu contraseña local.',401)
        if csrf and not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
            raise Problem('Token de sesión inválido; recarga la página.',403)
        return session

    def json_body(self):
        if self.headers.get('Transfer-Encoding'):raise Problem('Transferencia no admitida.',400)
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:raise Problem('Tamaño inválido.')
        if length<1 or length>29000000:raise Problem('Carga vacía o demasiado grande.',413)
        try:body=json.loads(self.rfile.read(length))
        except (ValueError,UnicodeError):raise Problem('JSON inválido.')
        if not isinstance(body,dict):raise Problem('Se requiere un objeto JSON.')
        return body

    def do_GET(self):
        try:
            self.guard()
            parsed=urlsplit(self.path)
            path=unquote(parsed.path)
            if path=='/api/session':
                try:s=self.authenticated()
                except Problem:s=None
                return self.reply(200,{'authenticated':bool(s),'setupRequired':not bool(self.app.store.setting('password')),'csrf':s['csrf'] if s else None})
            if path.startswith('/api/'):
                self.authenticated()
                if path=='/api/state':return self.reply(200,self.app.state())
                parts=path.strip('/').split('/')
                if len(parts) in (3,4) and parts[:2]==['api','bots']:
                    bot_id=parts[2]
                    if len(parts)==3:return self.reply(200,self.app.store.detail(bot_id))
                    if parts[3]=='files':return self.reply(200,self.app.store.read_file(bot_id,parse_qs(parsed.query).get('name',[''])[0]))
                raise Problem('Ruta no encontrada.',404)
            if path in ('/','/index.html'):file=APP/'local_web/index.html'
            elif path in ('/app.js','/styles.css','/upstream-tokens.css'):file=APP/'local_web'/path[1:]
            else:raise Problem('Ruta no encontrada.',404)
            return self.reply(200,file.read_bytes(),ctype=mimetypes.guess_type(file.name)[0] or 'text/plain')
        except Problem as exc:self.reply(exc.status,{'error':str(exc)})
        except (OSError,ValueError):self.reply(503,{'error':'No se pudo leer el recurso local.'})

    def do_POST(self):
        try:
            self.guard(True)
            path=urlsplit(self.path).path
            data=self.json_body()
            if path=='/api/engine/tool':
                auth=self.headers.get('Authorization','')
                if not auth.startswith('Bearer '):raise Problem('Credencial requerida.',401)
                return self.reply(200,{'ok':True,'result':self.app.engine_tool(auth[7:],data)})
            if path in ('/api/login','/api/setup'):
                if self.headers.get('Origin') not in ALLOWED_ORIGINS:raise Problem('Inicia sesión desde la página local.',403)
                with self.app.login_lock:
                    self.app.login_attempts=[x for x in self.app.login_attempts if x>time.time()-60]
                    if len(self.app.login_attempts)>=8:raise Problem('Espera un minuto antes de volver a intentar.',429)
                    self.app.login_attempts.append(time.time())
                    if path=='/api/setup':self.app.store.setup_password(data.get('password'))
                    if not self.app.store.password_ok(data.get('password')):raise Problem('Contraseña incorrecta.',401)
                token,s=self.app.store.login()
                return self.reply(200,{'authenticated':True,'csrf':s['csrf']},{'Set-Cookie':f'joe_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
            self.authenticated(True)
            store=self.app.store
            if path=='/api/logout':
                token=cookies.SimpleCookie(self.headers.get('Cookie',''))['joe_session'].value
                with store.lock:store.sessions.pop(token,None)
                return self.reply(200,{'ok':True},{'Set-Cookie':'joe_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if path=='/api/bots':return self.reply(201,store.create_bot(data.get('name'),data.get('scope')))
            parts=path.strip('/').split('/')
            if len(parts)==3 and parts[:2]==['api','approvals']:
                return self.reply(200,store.decide(parts[2],data.get('decision'),self.app.mcp.execute_action))
            if len(parts)==4 and parts[:2]==['api','bots']:
                bot_id,action=parts[2:]
                store.bot(bot_id)
                if action=='message':return self.reply(202,self.app.send(bot_id,data.get('text')))
                if action=='session':result=store.new_session(bot_id)
                elif action=='profile':result=store.profile(bot_id,data.get('profile'))
                elif action=='memory':result=store.memory(bot_id,data)
                elif action=='tasks':result=store.task(bot_id,data.get('title'))
                elif action=='files':result=store.save_file(bot_id,data.get('name'),data.get('content'))
                elif action=='relay':
                    source=store.bot(bot_id)
                    target=store.bot(data.get('target_id'))
                    if source['scope']!=target['scope']:raise Problem('Aislamiento entre unidades de negocio.',403)
                    relay_text=short_text(data.get('text'),4000)
                    result=self.app.send(target['id'],f"Mensaje explícito de {source['name']}: {relay_text}")
                    store.add_message(bot_id,'system',f"Mensaje enviado a {target['name']}; transporte JOE HQ, comunicación nativa pendiente.")
                    result['native']=False
                elif action=='computer':result=self.app.control(bot_id,data.get('owner'))
                elif action=='drive':result=self.app.mcp.list(bot_id,data.get('folder_id'),data.get('page_token'))
                elif action=='drive-read':result=self.app.mcp.read_text(bot_id,data.get('file_id'))
                elif action=='transcribe':result=self.app.voice(bot_id,data)
                elif action=='speak':result=self.app.run_json('voice.py',{'command':'synthesize','text':short_text(data.get('text'),4000)})
                elif action=='proposal':result=store.approval(bot_id,data.get('action'),data.get('payload'))
                else:raise Problem('Acción no encontrada.',404)
                return self.reply(200,result)
            raise Problem('Ruta no encontrada.',404)
        except Problem as exc:self.reply(exc.status,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'La operación local no se completó. No se ejecutó ninguna alternativa.'})

def doctor():
    report={'volume_mounted':ROOT.is_mount(),'hermes_python':HERMES_PYTHON.is_file(),
            'composio_oauth_present':TOKEN_FILE.is_file(),'paid_provider_fallback':False,
            'localhost':'127.0.0.1:8787','global_hermes_modified':False}
    try:preflight();report['storage']='listo'
    except (Problem,OSError) as exc:report['storage']=str(exc)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['storage']=='listo' else 1

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description='JOE HQ local en español')
    parser.add_argument('--doctor',action='store_true',help='Diagnóstico local sin arrancar HTTP')
    args=parser.parse_args()
    if args.doctor:return doctor()
    try:
        preflight()
        os.environ.update(cache_environment())
        store=Store()
        server=ThreadingHTTPServer(('127.0.0.1',8787),Handler)
        server.app=Application(store)
        server.daemon_threads=True
        print('JOE HQ: http://127.0.0.1:8787 — crea tu contraseña local al entrar.',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:
            for bot in store.bots():server.app.control(bot['id'],'user')
            server.server_close();store.db.close()
        return 0
    except (Problem,OSError) as exc:
        print('JOE HQ no pudo iniciar: '+str(exc),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
