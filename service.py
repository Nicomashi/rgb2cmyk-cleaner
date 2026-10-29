"""Manage this project's per-user macOS launchd service (run through uv)."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
LABEL='local.rgb2cmyk-cleaner'
DOMAIN=f'gui/{os.getuid()}'
TARGET=f'{DOMAIN}/{LABEL}'
PLIST=Path.home()/'Library'/'LaunchAgents'/f'{LABEL}.plist'
LAUNCHCTL='/bin/launchctl'


def call(*args,check=True):
    result=subprocess.run([LAUNCHCTL,*args],text=True,capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'launchctl failed')
    return result


def configuration():
    uv=shutil.which('uv')
    if not uv: raise RuntimeError('Не найден uv.')
    if not (ROOT/'.venv/bin/python').exists():
        raise RuntimeError('Сначала выполните uv sync в папке проекта.')
    return {
        'Label':LABEL,
        'ProgramArguments':[uv,'run','--offline','--no-sync','--no-cache',
            'python','-B','-m','uvicorn','app:app','--host','127.0.0.1','--port','8765',
            '--no-access-log','--log-level','error'],
        'WorkingDirectory':str(ROOT),
        'RunAtLoad':True,
        'KeepAlive':True,
        'ThrottleInterval':5,
        'ExitTimeOut':20,
        'EnvironmentVariables':{'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1',
                                'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
        # No accumulating log files or persistent caches.
        'StandardOutPath':'/dev/null',
        'StandardErrorPath':'/dev/null',
    }


def installed():
    return call('print',TARGET,check=False).returncode==0


def unload():
    if not installed(): return
    call('bootout',TARGET)
    # launchd removes the job asynchronously; immediate bootstrap can return EIO.
    deadline=time.monotonic()+10
    while installed() and time.monotonic()<deadline:
        time.sleep(.1)


def bootstrap():
    deadline=time.monotonic()+10
    while True:
        result=call('bootstrap',DOMAIN,str(PLIST),check=False)
        if result.returncode==0:return
        if time.monotonic()>=deadline:
            raise RuntimeError(result.stderr.strip() or 'Не удалось загрузить службу.')
        time.sleep(.25)


def install():
    config=configuration()
    loaded=installed()
    if not loaded:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',8765))==0:
                raise RuntimeError('Порт 8765 занят ручным сервером. Сначала остановите его.')
    if loaded: unload()
    PLIST.parent.mkdir(parents=True,exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(config,sort_keys=False))
    PLIST.chmod(0o600)
    call('enable',TARGET)
    bootstrap()
    print(f'Автозапуск и восстановление включены: {TARGET}')
    print('http://127.0.0.1:8765/')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','status','restart','stop','uninstall'])
    action=parser.parse_args().action
    if action=='install': install()
    elif action=='status':
        state=call('print',TARGET,check=False)
        if state.returncode:
            print('Служба не загружена.');return 1
        for line in state.stdout.splitlines():
            value=line.strip()
            if line.startswith(('\tstate =','\tpid =','\truns =','\tlast exit code =','\tlast terminating signal =')):
                print(value)
        print(f'Настройки автозапуска: {PLIST}')
    elif action=='restart':
        if installed(): call('kickstart','-k',TARGET);print('Служба перезапущена.')
        else: install()
    elif action in ('stop','uninstall'):
        if installed(): unload()
        if action=='uninstall':
            PLIST.unlink(missing_ok=True);print('Автозапуск удалён.')
        else: print('Служба остановлена до следующего входа или запуска.')
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
