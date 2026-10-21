"""Find the R2026a runtime without requiring a licensed MATLAB session."""
import os
from pathlib import Path

RUNTIME_URL='https://www.mathworks.com/products/compiler/matlab-runtime.html'


def runtime_root(matlab='', configured=''):
    candidates=[]
    if configured: candidates.append(Path(configured))
    if matlab: candidates.append(Path(matlab).parent.parent)
    candidates.extend(Path(p).parent.parent for p in os.environ.get('PATH','').split(os.pathsep) if p and Path(p).name.lower()=='win64')
    if os.name=='nt':
        import winreg
        for key in (r'SOFTWARE\MathWorks\MATLAB Runtime\26.1',r'SOFTWARE\MathWorks\MATLAB\26.1'):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,key) as k:
                    for name in ('MATLABROOT','InstallPath'):
                        try: candidates.append(Path(winreg.QueryValueEx(k,name)[0]))
                        except OSError: pass
            except OSError: pass
    for base in (Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))/'MATLAB',Path(r'D:\matlab')):
        candidates.append(base)
        if base.is_dir():
            candidates.extend(base.glob('*'))
            candidates.extend(base.glob('*/*'))
    for p in candidates:
        if (p/'runtime/win64/mclmcrrt26_1.dll').is_file(): return p.resolve()
    return None


def runtime_env(root):
    env=os.environ.copy()
    if root:
        dirs=[root/'runtime/win64',root/'bin/win64',root/'sys/os/win64',root/'extern/bin/win64']
        env['PATH']=os.pathsep.join(str(p) for p in dirs)+os.pathsep+env.get('PATH','')
    return env
