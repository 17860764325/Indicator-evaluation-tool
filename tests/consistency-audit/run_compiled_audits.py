import subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from runtime_support import runtime_env
root=Path(__file__).resolve().parent
for label in ('compiled_existing','compiled_all24'):
 out=root/(label+'.jsonl')
 if out.exists(): out.unlink()
 with (root/(label+'.log')).open('wb') as log:
  r=subprocess.run([str(root.parents[1]/'engine/fusion_engine.exe'),str(root/(label+'.json'))],env=runtime_env(Path(r'D:\matlab')),stdout=log,stderr=subprocess.STDOUT)
 print(label,r.returncode,flush=True)
 if r.returncode: print((root/(label+'.log')).read_text(errors='replace'),flush=True);break
