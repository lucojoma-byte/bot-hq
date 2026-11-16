"""Lecturas Drive vía el MCP OAuth existente de Hermes, sin copiar credenciales.

Solo expone metadatos y exportación de texto de archivos dentro de raíces fijas.
No expone COMPOSIO_MULTI_EXECUTE_TOOL ni HTTP arbitrario al modelo.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import threading
import urllib.request
import urllib.error
from .core import Problem, SCOPES

TOKEN_FILE=Path('/Users/m4/.hermes/mcp-tokens/composio-lucojoma.json')
ENDPOINT='https://connect.composio.dev/mcp'

def unpack(result):
    if isinstance(result,dict) and 'content' in result:
        for part in result['content']:
            if part.get('type')=='text':
                try:return json.loads(part['text'])
                except (ValueError,TypeError):continue
    return result

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class ComposioMCP:
    def __init__(self,store,config):
        self.store=store
        self.roots=json.loads(Path(config).read_text(encoding='utf-8'))
        self.lock=threading.RLock()
        self.session_id=None
        self.tool_names={}
        self.request_id=0
        self.status='OAuth existente detectado; conexión local pendiente de comprobar.' if TOKEN_FILE.is_file() else 'No se encontró OAuth composio-lucojoma.'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def rpc(self,method,params,notification=False):
        try:
            token=json.loads(TOKEN_FILE.read_text(encoding='utf-8')).get('access_token')
            if not isinstance(token,str) or not token:raise ValueError()
        except (OSError,ValueError):
            raise Problem('No se puede leer OAuth de composio-lucojoma. No se modificó Hermes.',503)
        self.request_id+=1
        payload={'jsonrpc':'2.0','method':method,'params':params}
        if not notification:payload['id']=self.request_id
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'}
        if self.session_id:headers['Mcp-Session-Id']=self.session_id
        req=urllib.request.Request(ENDPOINT,data=json.dumps(payload).encode(),headers=headers,method='POST')
        try:
            with self.opener.open(req,timeout=25) as response:
                self.session_id=response.headers.get('Mcp-Session-Id') or self.session_id
                if notification:return {}
                size=0
                if 'text/event-stream' in response.headers.get('Content-Type',''):
                    for line in response:
                        size+=len(line)
                        if size>4000000:raise Problem('Respuesta MCP demasiado grande.',502)
                        if line.startswith(b'data:'):
                            try:parsed=json.loads(line[5:])
                            except ValueError:continue
                            if parsed.get('id')==payload['id']:break
                    else:raise Problem('MCP no devolvió resultado.',502)
                else:
                    raw=response.read(4000001)
                    if len(raw)>4000000:raise Problem('Respuesta MCP demasiado grande.',502)
                    parsed=json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):raise Problem('OAuth MCP vencido o sin acceso. Renueva la conexión en Hermes sin compartir tokens.',503)
            raise Problem('MCP no disponible (HTTP '+str(exc.code)+').',503)
        except (OSError,ValueError,TimeoutError):raise Problem('No fue posible conectar al MCP Composio desde esta Mac.',503)
        if 'error' in parsed:raise Problem('MCP rechazó la solicitud; no se ejecutó otra herramienta.',502)
        result=parsed.get('result',{})
        if result.get('isError'):raise Problem('Composio devolvió un error. No se reintentará una escritura.',502)
        return result

    def initialize(self):
        if self.tool_names:return
        self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'joe-hq','version':'0.1.0'}})
        self.rpc('notifications/initialized',{},True)
        result=self.rpc('tools/list',{})
        for t in result.get('tools',[]):
            name=t['name']
            for key in ['COMPOSIO_SEARCH_TOOLS','COMPOSIO_MULTI_EXECUTE_TOOL']:
                if name.upper().endswith(key):self.tool_names[key]=name
        if len(self.tool_names)!=2:raise Problem('El MCP no expone las herramientas Composio esperadas.',503)

    def execute_read(self,slug,args):
        allowed={'GOOGLEDRIVE_FIND_FILE','GOOGLEDRIVE_GET_FILE_METADATA','GOOGLEDRIVE_DOWNLOAD_FILE'}
        if slug not in allowed:raise Problem('Herramienta fuera de la lista de lectura.',403)
        # Descubrimiento y ejecución permanecen en la misma superficie MCP.
        with self.lock:
            self.initialize()
            discovery=unpack(self.rpc('tools/call',{'name':self.tool_names['COMPOSIO_SEARCH_TOOLS'],'arguments':{'queries':[{'use_case':'Read Google Drive folder files and metadata'}],'session':{'generate_id':True},'search_strategy':'tool_search'}}))
            data=discovery.get('data',discovery)
            statuses=data.get('toolkit_connection_statuses',[])
            status=next((s for s in statuses if s.get('toolkit')=='googledrive'),None)
            if not status or not status.get('has_active_connection'):raise Problem('Google Drive no está conectado en este MCP.',503)
            schemas=data.get('tool_schemas',{})
            if slug not in schemas:raise Problem('La herramienta requerida no fue descubierta por MCP.',503)
            accounts=status.get('accounts',[])
            if len(accounts)!=1:raise Problem('Hay varias cuentas Drive; falta asignación explícita por bot.',503)
            session=data.get('session',{}).get('id')
            call={'tools':[{'tool_slug':slug,'arguments':args,'account':accounts[0]['id']}],
                  'sync_response_to_workbench':False,'current_step':'SCOPED_DRIVE_READ'}
            if session:call['session_id']=session
            result=unpack(self.rpc('tools/call',{'name':self.tool_names['COMPOSIO_MULTI_EXECUTE_TOOL'],'arguments':call}))
            outer=result.get('data',result)
            results=outer.get('results',[])
            if not results:raise Problem('Composio no devolvió datos Drive.',502)
            response=results[0].get('response',{})
            if not response.get('successful'):raise Problem('Lectura Drive rechazada.',502)
            self.status='Lectura MCP confirmada.'
            return response.get('data',{})

    def permitted_roots(self,bot_id):
        scope=self.store.bot(bot_id)['scope']
        return {self.roots[name] for name in SCOPES[scope] if name in self.roots}

    def validate_id(self,value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,150}',value):raise Problem('ID de Drive inválido.',403)
        return value

    def authorize(self,bot_id,file_id):
        self.validate_id(file_id)
        roots=self.permitted_roots(bot_id)
        if file_id in set(self.roots.values())-roots:
            raise Problem('Carpeta de otra unidad de negocio bloqueada.',403)
        # Camino de padres de Drive v3. No seguir shortcuts ni enlaces externos.
        current=file_id
        seen=set()
        for depth in range(32):
            if current in seen:break
            seen.add(current)
            meta=self.execute_read('GOOGLEDRIVE_GET_FILE_METADATA',{'fileId':current,'fields':'id,name,mimeType,parents,trashed','supportsAllDrives':True})
            if meta.get('trashed') or meta.get('mimeType')=='application/vnd.google-apps.shortcut':break
            if current in roots:return meta if depth==0 else self.execute_read('GOOGLEDRIVE_GET_FILE_METADATA',{'fileId':file_id,'fields':'id,name,mimeType,parents,trashed'})
            parents=meta.get('parents',[])
            if len(parents)!=1:break
            current=parents[0]
        raise Problem('Archivo fuera de las carpetas autorizadas de este bot.',403)

    def list(self,bot_id,folder_id=None,page_token=None):
        roots=self.permitted_roots(bot_id)
        if not roots:raise Problem('Raíces Drive sin configurar.',503)
        chosen=[self.validate_id(folder_id)] if folder_id else sorted(roots)
        if folder_id:self.authorize(bot_id,folder_id)
        files=[];continuations={}
        for folder in chosen:
            query={'folder_id':folder,'q':'trashed = false','pageSize':100,'fields':'nextPageToken,files(id,name,mimeType,parents,size,webViewLink)','orderBy':'name'}
            if page_token:query['pageToken']=page_token
            result=self.execute_read('GOOGLEDRIVE_FIND_FILE',query)
            for f in result.get('files',[]):
                if folder not in f.get('parents',[]) or f.get('mimeType')=='application/vnd.google-apps.shortcut':continue
                # Solo metadatos mínimos del bot, nunca datos de cuenta/propietarios.
                files.append({k:f[k] for k in ['id','name','mimeType','size'] if k in f})
            if result.get('nextPageToken'):continuations[folder]=result['nextPageToken']
        return {'files':files,'next_pages':continuations,'truncated':bool(continuations),'transport':'hermes-mcp-composio-lucojoma'}

    def read_text(self,bot_id,file_id):
        meta=self.authorize(bot_id,file_id)
        if meta.get('mimeType') not in {'application/vnd.google-apps.document','application/vnd.google-apps.spreadsheet','text/plain','text/markdown','text/csv'}:
            raise Problem('Por ahora solo se admite lectura de documentos de texto y hojas.')
        args={'fileId':file_id}
        if meta.get('mimeType')=='application/vnd.google-apps.document':args['mime_type']='text/plain'
        if meta.get('mimeType')=='application/vnd.google-apps.spreadsheet':args['mime_type']='text/csv'
        result=self.execute_read('GOOGLEDRIVE_DOWNLOAD_FILE',args)
        content=result.get('downloaded_file_content')
        if not isinstance(content,str):raise Problem('El conector devolvió un archivo que este visor no admite.',502)
        return {'id':file_id,'name':meta.get('name'),'content':content[:100000],'truncated':len(content)>100000}

    def execute_action(self,bot_id,action,payload):
        # La aprobación es obligatoria, pero no basta para habilitar un conector
        # que aún no tiene cuenta y permisos por negocio comprobados.
        self.store.bot(bot_id)
        raise Problem('Acción conservada como propuesta. Falta validar la cuenta y el adaptador de escritura por negocio; no se envió, publicó ni borró nada.',503)
