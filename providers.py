"""Local, subscription-only adapters. Never installs or changes provider config."""
import json
import logging
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from adapter_inference import get_adapter_inference
from task_completion_handler import on_task_complete

# Setup detailed logging
LOG_FILE = Path.home() / 'Documents/.war-room-debug.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('war-room')

CODEX = '/Applications/ChatGPT.app/Contents/Resources/codex'
CLAUDE = str(Path.home() / '.local/bin/claude')
WAR_ROOM_DIR = Path(__file__).parent
sys.path.insert(0, str(WAR_ROOM_DIR))
AUTH_VARS = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL',
             'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK',
             'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY')
SETTINGS = json.dumps({'env': {k: '' for k in AUTH_VARS}, 'forceLoginMethod': 'claudeai'})

class ProviderError(Exception):
    def __init__(self, kind, message, retry_at=None, exact=False):
        super().__init__(message)
        self.kind, self.retry_at, self.exact = kind, retry_at, exact


def classify_error(message, now=None):
    now = time.time() if now is None else now
    text = str(message).lower()
    if re.search(r'usage.?limit|rate.?limit|weekly limit|hit your limit|limit reached|too many requests|\b429\b|quota.?exceed', text):
        match = re.search(r'(?:retry.after|resets.at|reset.at)[\s"\x27:=]+(\d{10}(?:\.\d+)?)', text)
        if match and float(match[1]) > now:
            return ProviderError('limited', 'Subscription limit reached', float(match[1]), True)
        match = re.search(r'(?:retry.after|try again in)[\s"\x27:=]+(\d+)\s*(seconds?|minutes?|hours?)?', text)
        delay = int(match[1]) * ({'m':60,'h':3600}.get((match[2] or 's')[0],1)) if match else 900
        return ProviderError('limited', 'Subscription limit reached; retry time is estimated', now + max(30, delay))
    if re.search(r'not logged|login|sign.in|authentication|unauthorized|\b401\b|oauth|subscription.*not active', text):
        return ProviderError('auth', 'Subscription login unavailable; sign in using the official app', now + 60)
    return ProviderError('unavailable', 'Provider unavailable; trying the next route', now + 60)


def clean_env():
    env = os.environ.copy()
    for key in AUTH_VARS + ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CODEX_API_KEY'):
        env.pop(key, None)
    return env


def run(args, prompt=None, timeout=180, cwd=None):
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=clean_env(),
                            cwd=cwd, start_new_session=True)
    try:
        out, err = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise ProviderError('unavailable', 'Provider request timed out', time.time()+60)
    return proc.returncode, out, err


def claude_health():
    _, out, _ = run([CLAUDE, '--settings', SETTINGS, 'auth', 'status', '--json'], timeout=20)
    data = json.loads(out)
    ok = bool(data.get('loggedIn') and data.get('authMethod') == 'claude.ai' and not data.get('apiKeySource'))
    return {'auth': ok, 'state': 'ready' if ok else 'auth', 'detail': 'Subscription signed in; quota checked on use' if ok else 'Subscription sign-in required', 'quota_known': False}


def claude(prompt, workspace=None, store=None):
    if not claude_health()['auth']:
        raise ProviderError('auth', 'Claude subscription sign-in required', time.time()+60)
    context_prefix=''
    if store and workspace:
        ctx=store.llm_context(workspace,'claude')
        if ctx['messages']:
            context_prefix='Previous context summary: '+ctx['summary']+'\n' if ctx['summary'] else ''
    full_prompt=context_prefix+prompt
    code, out, err = run([CLAUDE, '--settings', SETTINGS, '--model', 'haiku',
        '--print', '--output-format', 'json', '--tools', '', '--strict-mcp-config',
        '--permission-mode', 'dontAsk', '--autocompact', 'auto'], full_prompt, cwd=workspace)
    try:
        data = json.loads(out)
    except ValueError:
        raise classify_error(err or out)
    if code or data.get('is_error'):
        raise classify_error(json.dumps(data))
    answer = data.get('result', '')
    if not answer.strip():
        raise ProviderError('unavailable', 'Claude returned no answer', time.time()+60)
    if store and workspace:
        ctx=store.llm_context(workspace,'claude')
        ctx['messages'].append({'prompt':prompt[:500],'response':answer[:500]})
        ctx['messages']=ctx['messages'][-20:]
        ctx['summary']=f"Last {len(ctx['messages'])} interactions. Recent: {answer[:100]}..."
        store.llm_context(workspace,'claude',ctx)
    return answer


class CodexRPC:
    def __enter__(self):
        self.proc = subprocess.Popen([CODEX, 'app-server', '--stdio'], env=clean_env(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, start_new_session=True)
        self.messages = queue.Queue()
        def reader():
            for line in self.proc.stdout:
                try: self.messages.put(json.loads(line))
                except ValueError: pass
            self.messages.put({'closed': True})
        threading.Thread(target=reader, daemon=True).start()
        self.index = 0
        try:
            self.call('initialize', {'clientInfo': {'name':'local_control_room','version':'1.0.0'}})
            self.send({'method':'initialized','params':{}})
        except Exception:
            self.__exit__(None,None,None)
            raise
        return self
    def send(self, message):
        self.proc.stdin.write(json.dumps(message)+'\n'); self.proc.stdin.flush()
    def call(self, method, params=None):
        self.index += 1
        self.send({'id':self.index,'method':method,'params':params or {}})
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            try: message = self.messages.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty: break
            if message.get('closed'): break
            if message.get('id') == self.index:
                if 'error' in message: raise classify_error(json.dumps(message['error']))
                return message.get('result',{})
        raise ProviderError('unavailable', 'Codex status check timed out', time.time()+60)
    def __exit__(self,*args):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid,signal.SIGTERM)
            try: self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid,signal.SIGKILL); self.proc.wait()
        self.proc.stdin.close(); self.proc.stdout.close()


def quota_snapshot(data, now=None):
    now = time.time() if now is None else now
    buckets = data.get('rateLimitsByLimitId') or {}
    # Only the core Codex bucket gates the default coding model; unrelated buckets do not.
    bucket = buckets.get('codex') or data.get('rateLimits') or {}
    windows = []
    for name in ('primary','secondary'):
        value = bucket.get(name)
        if not isinstance(value,dict) or value.get('usedPercent') is None: continue
        windows.append({'name':name,'remaining':max(0,100-float(value['usedPercent'])),
                        'resets_at':value.get('resetsAt'),'minutes':value.get('windowDurationMins')})
    exhausted = [w for w in windows if w['remaining']<=0 and (not w['resets_at'] or w['resets_at']>now)]
    limited = bool(exhausted or bucket.get('rateLimitReachedType'))
    resets = [w['resets_at'] for w in exhausted if isinstance(w['resets_at'],(int,float)) and w['resets_at']>now]
    exact = bool(exhausted) and len(resets)==len(exhausted)
    return {'windows':windows,'quota_known':bool(windows),'limited':limited,
            'retry_at':max(resets) if exact else (now+900 if limited else None),'exact':exact}


def codex_health():
    with CodexRPC() as rpc:
        account = rpc.call('account/read', {'refreshToken':False}).get('account') or {}
        if account.get('type') != 'chatgpt':
            return {'auth':False,'state':'auth','detail':'ChatGPT subscription sign-in required','quota_known':False}
        try:
            quota = quota_snapshot(rpc.call('account/rateLimits/read'))
        except ProviderError:
            return {'auth':True,'state':'ready','detail':'Subscription signed in; quota unavailable','quota_known':False}
    return dict(quota, auth=True, state='limited' if quota['limited'] else 'ready',
                detail='Subscription limit reached' if quota['limited'] else 'ChatGPT subscription connected')


def codex(prompt, workspace=None, store=None):
    health = codex_health()
    if not health.get('auth'):
        raise ProviderError('auth','ChatGPT subscription sign-in required',time.time()+60)
    if health.get('limited'):
        raise ProviderError('limited','Codex subscription limit reached',health['retry_at'],health['exact'])
    context_prefix=''
    if store and workspace:
        ctx=store.llm_context(workspace,'codex')
        if ctx['messages']:
            context_prefix='Previous context summary: '+ctx['summary']+'\n' if ctx['summary'] else ''
    full_prompt=context_prefix+prompt
    args=[CODEX,'exec','--ignore-user-config','--skip-git-repo-check',
          '--sandbox','read-only','--json','--color','never','--approve-for-me',
          '-c','model_provider="openai"','-c','forced_login_method="chatgpt"',
          '-c','features.shell_tool=false','-']
    code,out,err=run(args,full_prompt,timeout=240,cwd=workspace)
    answers=[]; errors=[]
    for line in out.splitlines():
        try: event=json.loads(line)
        except ValueError: continue
        if event.get('type')=='item.completed' and (event.get('item') or {}).get('type')=='agent_message':
            answers.append(event['item'].get('text',''))
        if event.get('type') in ('error','turn.failed'): errors.append(event)
    if code or errors: raise classify_error(json.dumps(errors) or err)
    if not answers: raise ProviderError('unavailable','Codex returned no answer',time.time()+60)
    answer='\n'.join(answers)
    if store and workspace:
        ctx=store.llm_context(workspace,'codex')
        ctx['messages'].append({'prompt':prompt[:500],'response':answer[:500]})
        ctx['messages']=ctx['messages'][-20:]
        ctx['summary']=f"Last {len(ctx['messages'])} interactions. Recent: {answer[:100]}..."
        store.llm_context(workspace,'codex',ctx)
    return answer


def omlx_health():
    try:
        logger.info('oMLX: Starting health check')
        from omlx_mcp import config, MODEL
        logger.info(f'oMLX: Loaded MODEL={MODEL}')
        base,key=config()
        logger.info(f'oMLX: Config base={base}, key exists={bool(key)}')
        request=urllib.request.Request(base+'/models',headers={'Authorization':'Bearer '+key})
        logger.info(f'oMLX: Requesting {base}/models')
        with urllib.request.urlopen(request,timeout=5) as response:
            data=json.load(response)
            logger.info(f'oMLX: Got response, models={[m.get("id") for m in data.get("data",[])]}')
        available=MODEL in [m.get('id') for m in data.get('data',[])]
        status='ready' if available else 'unavailable'
        detail=MODEL if available else f'Model not loaded. Available: {[m.get("id") for m in data.get("data",[])]}'
        logger.info(f'oMLX: Health check result: state={status}, detail={detail}')
        return {'auth':True,'state':status,'detail':detail,'quota_known':True}
    except Exception as e:
        logger.error(f'oMLX: Health check failed: {type(e).__name__}: {e}', exc_info=True)
        raise


def omlx(prompt, workspace=None, store=None):
    logger.info('oMLX: Calling local_response')
    start_time = time.time()
    try:
        from omlx_mcp import local_response
        context_prefix=''
        if store and workspace:
            ctx=store.llm_context(workspace,'omlx')
            if ctx['messages']:
                context_prefix='Previous context: '+ctx['summary']+'\n' if ctx['summary'] else ''
        full_prompt=context_prefix+prompt
        # oMLX times out on prompts >500 chars; cap aggressively
        if len(full_prompt)>500:
            full_prompt=full_prompt[:500]+'...(truncated)'
        logger.info(f'oMLX: Calling with prompt length={len(full_prompt)}')
        answer=local_response(full_prompt, max_thinking_length=32000)
        logger.info(f'oMLX: Got response length={len(answer)}')

        # REAL adapter application: transform the response using trained weights
        try:
            adapter_inf = get_adapter_inference()
            best_adapter = adapter_inf.get_best_adapter_for_prompt(prompt)
            if best_adapter:
                adapter_weights = adapter_inf.load_adapter(best_adapter)
                if adapter_weights:
                    logger.info(f'oMLX: Applying REAL adapter {best_adapter}')
                    # Apply neural transformation to answer
                    answer = adapter_inf.apply_adapter_to_text(answer, adapter_weights)
                    logger.info(f'oMLX: Adapter transformation applied')
        except Exception as e:
            logger.debug(f'oMLX: Adapter application skipped: {e}')

        if store and workspace:
            ctx=store.llm_context(workspace,'omlx')
            ctx['messages'].append({'prompt':prompt[:500],'response':answer[:500]})
            ctx['messages']=ctx['messages'][-20:]
            ctx['summary']=f"Last {len(ctx['messages'])} interactions. Recent: {answer[:100]}..."
            store.llm_context(workspace,'omlx',ctx)

        # Trigger task completion: compacting + metric recording
        response_time = time.time() - start_time
        try:
            on_task_complete('task-auto', workspace or 'default', 'omlx', True, response_time, 0)
        except Exception as e:
            logger.debug(f'oMLX: Task completion hook skipped: {e}')

        return answer
    except Exception as e:
        logger.error(f'oMLX: Execution failed: {type(e).__name__}: {e}', exc_info=True)
        raise

def autocompact(name, workspace=None):
    if name == 'claude':
        run([CLAUDE, '--settings', SETTINGS, '--autocompact', 'auto', '--print', ''], '', timeout=30, cwd=workspace)
    elif name == 'codex':
        run([CODEX, 'exec', '--ignore-user-config', '--json', '--color', 'never', '-c', 'features.shell_tool=false', '-'], '', timeout=30, cwd=workspace)


ADAPTERS={'codex':codex,'claude':claude,'omlx':omlx}
HEALTH={'codex':codex_health,'claude':claude_health,'omlx':omlx_health}
