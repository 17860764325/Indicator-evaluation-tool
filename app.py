"""Local MATLAB fusion evaluation workbench. Python standard library + Pillow."""
import base64
import csv
import hashlib
import io
import json
import math
import os
import sys
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
import zipfile
from xml.sax.saxutils import escape as xml_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from PIL import Image
from runtime_support import runtime_root, runtime_env

FROZEN=bool(getattr(sys,'frozen',False))
ROOT = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
DEFAULT_DATA=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'FusionEvalWorkbench/data' if FROZEN else ROOT/'data'
DATA = Path(os.environ.get('FUSION_EVAL_DATA', DEFAULT_DATA)).resolve()
DEFAULT_MEFB = r'D:\project\matlab\测试指标\测试指标\MEFB'
LOCK = threading.Lock()
ACTIVE = {}
MATLAB_SLOT = threading.Semaphore(1)
EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
METRICS = {
 'Cross_entropy': ('交叉熵', '↓'), 'Entropy': ('信息熵', '↑'),
 'FMI': ('特征互信息', '↑'), 'NMI': ('归一化互信息', '↑'),
 'Psnr': ('PSNR（原版公式）', '↑'), 'Qncie': ('非线性相关信息熵', '↑'),
 'TE': ('Tsallis 熵', '↑'), 'Avg_gradient': ('平均梯度', '↑'),
 'Edge_intensity': ('边缘强度', '↑'), 'Qabf': ('边缘保留 QABF', '↑'),
 'Qp': ('相位一致性', '↑'), 'SD': ('标准差', '↑'),
 'Spatial_frequency': ('空间频率', '↑'), 'Qc': ('结构相似 QC', '↑'),
 'Qw': ('结构相似 QW', '↑'), 'Qy': ('结构相似 QY', '↑'),
 'MEF_SSIM': ('多尺度 MEF-SSIM', '↑'), 'Qcb': ('视觉感知 QCB', '↑'),
 'Qcv': ('视觉感知 QCV', '↓'), 'VIF': ('视觉信息保真度', '↑'),
 'MI': ('互信息', '↑'), 'CC': ('相关系数', '↑'),
 'SCD': ('差分相关和', '↑'), 'Nabf': ('融合伪影', '↓')}
DEFAULT_METRICS = [x for x in METRICS if x not in ('Avg_gradient','MI','CC','SCD','Nabf')]


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


def db():
    con = sqlite3.connect(DATA / 'workbench.sqlite', timeout=30, factory=Connection)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def init():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,note TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS groups_(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),name TEXT,a TEXT,b TEXT,meta TEXT,UNIQUE(project_id,name));
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),name TEXT,method TEXT,note TEXT,created TEXT,status TEXT,metrics TEXT,engine TEXT,error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,run_id TEXT REFERENCES runs(id),name TEXT,a TEXT,b TEXT,f TEXT,meta TEXT,UNIQUE(run_id,name));
        CREATE TABLE IF NOT EXISTS results(item_id TEXT REFERENCES items(id),metric TEXT,value REAL,status TEXT,error TEXT,seconds REAL,PRIMARY KEY(item_id,metric));
        ''')
        c.execute("INSERT OR IGNORE INTO settings VALUES('mefb',?)", (DEFAULT_MEFB,))
        c.execute("INSERT OR IGNORE INTO settings VALUES('matlab',?)", (shutil.which('matlab') or r'D:\matlab\bin\matlab.exe',))
        c.execute("INSERT OR IGNORE INTO settings VALUES('engine',?)",('compiled' if FROZEN else 'matlab',))
        c.execute("INSERT OR IGNORE INTO settings VALUES('runtime','')")
        c.execute("UPDATE runs SET status='interrupted',error='服务曾中断；可复制本次测试重新计算。' WHERE status IN ('queued','running')")
        columns={x[1] for x in c.execute('PRAGMA table_info(groups_)')}
        if 'batch' not in columns:
            c.execute("ALTER TABLE groups_ ADD COLUMN batch TEXT NOT NULL DEFAULT ''")


def uid(): return uuid.uuid4().hex
def now(): return time.strftime('%Y-%m-%d %H:%M:%S')
def rows(c, sql, args=()): return [dict(r) for r in c.execute(sql, args)]
def settings():
    with db() as c: return dict(c.execute('SELECT key,value FROM settings').fetchall())


def metric_dir(s):
    return ROOT/'engine_src/metrics' if s.get('engine')=='compiled' else Path(s['mefb'])/'metrics'
def required(c, table, key):
    r = c.execute(f'SELECT * FROM {table} WHERE id=?', (key,)).fetchone()
    if not r: raise ValueError('记录不存在')
    return dict(r)


def image_meta(path):
    with Image.open(path) as im:
        if im.width * im.height > 100_000_000: raise ValueError('图片像素过大')
        im.verify()
    with Image.open(path) as im:
        return {'width': im.width, 'height': im.height, 'mode': im.mode,
                'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def import_files(spec, dest):
    """Copy user-selected files into app-owned immutable storage."""
    dest.mkdir(parents=True, exist_ok=True)
    candidates = []
    if spec.get('path'):
        src = Path(spec['path']).expanduser().resolve()
        if not src.is_dir(): raise ValueError(f'文件夹不存在：{src}')
        paths=src.rglob('*') if spec.get('recursive',True) else src.iterdir()
        candidates = [(p.relative_to(src).as_posix(), p) for p in sorted(paths) if p.is_file() and p.suffix.lower() in EXTS]
    else:
        candidates = [(f['name'], f) for f in spec.get('files', []) if Path(f['name']).suffix.lower() in EXTS]
    if not candidates: raise ValueError('没有找到支持的图片（PNG / JPG / BMP / TIFF）')
    output = []
    for name, src in candidates:
        out = dest / (uid() + Path(name).suffix.lower())
        if isinstance(src, Path): shutil.copy2(src, out)
        else: out.write_bytes(base64.b64decode(src['data'], validate=True))
        meta = image_meta(out)
        meta['original_name']=name
        if isinstance(src,Path): meta['original_path']=str(src)
        output.append({'original': name, 'stem': Path(name).stem, 'path': str(out), 'meta': meta})
    return output


def key_of(stem, role):
    return re.sub(r'[_\-](?:' + role + r')$', '', stem, flags=re.I).casefold()


def unique_map(files, role):
    mapped = {}
    for f in files:
        key = source_key(f,role).casefold()
        if key in mapped: raise ValueError(f'组编号重复或有歧义：{f["original"]}')
        mapped[key] = f
    return mapped


def source_key(f,role=None):
    if 'original' not in f: return f['stem']
    p=Path(f.get('original',f['stem']))
    stem=re.sub(r'[_\-]'+role+r'$', '',p.stem,flags=re.I) if role else p.stem
    return (p.parent/stem).as_posix()


def pair_sources(a, b):
    aa, bb = unique_map(a, 'A'), unique_map(b, 'B')
    if aa.keys() != bb.keys():
        raise ValueError('源图配对不完整。缺少 B：' + ', '.join(sorted(aa.keys()-bb.keys())) + '；缺少 A：' + ', '.join(sorted(bb.keys()-aa.keys())))
    paired = []
    for k, x in aa.items():
        y = bb[k]
        if (x['meta']['width'], x['meta']['height']) != (y['meta']['width'], y['meta']['height']):
            raise ValueError(f'源图尺寸不一致：{k}')
        paired.append((source_key(x,'A'), x, y))
    return paired


def match_fused(groups, files, method, allow_missing=False):
    used, matched = set(), []
    by_key={}
    for f in files: by_key.setdefault(source_key(f).casefold(),[]).append(f)
    local_counts={}
    for g in groups:
        local=json.loads(g['meta']).get('pair_key',g['name']).casefold()
        local_counts[local]=local_counts.get(local,0)+1
    for g in groups:
        local=json.loads(g['meta']).get('pair_key',g['name']).casefold()
        names=[g['name'].casefold()]
        if local_counts[local]==1 and local not in names: names.append(local)
        candidates=[]
        for name in names:
            exact=by_key.get(name,[])
            method_matches=by_key.get(name+'_'+method.casefold(),[]) if method else []
            candidates=exact or method_matches
            if not candidates:
                candidates=[f for key,fs in by_key.items() if key.startswith(name+'_') and '/' not in key[len(name):] for f in fs]
            if candidates: break
        if not candidates and allow_missing: continue
        if len(candidates) != 1: raise ValueError(f'组 {g["name"]} 匹配到 {len(candidates)} 张融合图；请用“组名.png”或“组名_算法名.png”命名。若只有部分融合结果，请选择对应批次并启用“仅评估有融合结果的图片组”。')
        f = candidates[0]
        if f['path'] in used: raise ValueError('同一张融合图不能匹配多个组')
        used.add(f['path'])
        gm = json.loads(g['meta'])['a']
        if (gm['width'], gm['height']) != (f['meta']['width'], f['meta']['height']): raise ValueError(f'融合图尺寸与源图不一致：{g["name"]}')
        matched.append((g, f))
    if len(used) != len(files): raise ValueError(f'有 {len(files)-len(used)} 张融合图未匹配，请移除多余图片')
    if not matched: raise ValueError('没有任何源图与融合图匹配，请检查批次、文件名和目录层级')
    return matched


def state():
    with db() as c:
        projects = rows(c, 'SELECT p.*,(SELECT count(*) FROM groups_ WHERE project_id=p.id) AS group_count,(SELECT count(*) FROM runs WHERE project_id=p.id) AS run_count FROM projects p ORDER BY created DESC')
    s = settings()
    metrics_dir = metric_dir(s)
    compiled=s.get('engine')=='compiled'
    runtime=runtime_root(s.get('matlab',''),s.get('runtime','')) if compiled else None
    available=(ROOT/'engine/fusion_engine.exe').is_file() and runtime is not None if compiled else Path(s['matlab']).is_file()
    return {'projects': projects, 'settings': s, 'matlab_available': Path(s['matlab']).is_file(),
            'data_dir':str(DATA),
            'engine_available':available,'engine_name':'MATLAB 编译引擎' if compiled else 'MATLAB','runtime_detected':str(runtime) if runtime else '',
            'metrics': [{'id': k, 'name': v[0], 'direction': v[1], 'default': k in DEFAULT_METRICS} for k,v in METRICS.items() if (metrics_dir / ('metrics'+k+'.m')).is_file()]}


def project_detail(pid):
    with db() as c:
        p = required(c, 'projects', pid)
        p['groups'] = rows(c, 'SELECT * FROM groups_ WHERE project_id=? ORDER BY name', (pid,))
        p['runs'] = rows(c, 'SELECT r.*,(SELECT count(*) FROM items WHERE run_id=r.id) AS group_count,(SELECT count(*) FROM results z JOIN items i ON z.item_id=i.id WHERE i.run_id=r.id) AS done FROM runs r WHERE project_id=? ORDER BY created DESC,rowid DESC', (pid,))
    return p


def run_detail(rid):
    with db() as c:
        r = required(c, 'runs', rid)
        r['metrics'] = json.loads(r['metrics'])
        r['engine'] = json.loads(r['engine'])
        r['items'] = rows(c, 'SELECT * FROM items WHERE run_id=? ORDER BY name', (rid,))
        for item in r['items']:
            item['results'] = {x['metric']: x for x in rows(c, 'SELECT * FROM results WHERE item_id=?', (item['id'],))}
    r['summary'] = {}
    for m in r['metrics']:
        vals = [i['results'][m]['value'] for i in r['items'] if m in i['results'] and i['results'][m]['status']=='ok']
        avg = sum(vals)/len(vals) if vals else None
        r['summary'][m] = {'mean': avg, 'std': math.sqrt(sum((x-avg)**2 for x in vals)/len(vals)) if vals else None, 'valid': len(vals), 'total': len(r['items'])}
    return r


def create_run(body):
    rid = uid()
    folder = DATA / 'runs' / rid
    folder.mkdir(parents=True)
    try:
        s = settings()
        selected = list(dict.fromkeys(body.get('metrics', [])))
        if not selected or any(m not in METRICS for m in selected): raise ValueError('请选择有效指标')
        compiled=s.get('engine')=='compiled'
        if compiled:
            if not (ROOT/'engine/fusion_engine.exe').is_file(): raise ValueError('未找到编译计算引擎')
            if not runtime_root(s.get('matlab',''),s.get('runtime','')): raise ValueError('请安装 MATLAB Runtime R2026a Update 5 或更新的 R2026a Runtime，并在设置中指定安装根目录。')
        elif not Path(s['matlab']).is_file(): raise ValueError('找不到 MATLAB，请在设置中配置 matlab.exe')
        with db() as c:
            required(c, 'projects', body['project_id'])
            groups = rows(c, 'SELECT * FROM groups_ WHERE project_id=? ORDER BY name', (body['project_id'],))
        if not groups: raise ValueError('请先导入源图')
        if body.get('clone_id'):
            old = run_detail(body['clone_id'])
            if old['project_id'] != body['project_id']: raise ValueError('只能复制同项目测试')
            # Clones must retain the original test's source scope after appends.
            groups=old['items']
            files = [{'stem': i['name'], 'path': i['f'], 'meta': json.loads(i['meta'])['f']} for i in old['items']]
            copied = []
            for f in files:
                p = folder / 'fused' / (uid()+Path(f['path']).suffix)
                p.parent.mkdir(exist_ok=True)
                shutil.copy2(f['path'], p)
                copied.append(dict(f, path=str(p)))
            files = copied
        else:
            if body.get('batch') is not None:
                groups=[g for g in groups if g['batch']==body['batch']]
                if not groups: raise ValueError('所选批次没有源图')
            files = import_files(body['fused'], folder / 'fused')
        pairs = match_fused(groups, files, body.get('method',''),body.get('allow_missing',False))
        engine_dir = folder / 'engine'
        engine_dir.mkdir()
        source = metric_dir(s)
        for m in selected:
            if not (source / ('metrics'+m+'.m')).is_file(): raise ValueError('缺少指标文件：'+m)
        hashes = {}
        executed_hashes = {}
        compatibility = []
        for p in source.glob('*.m'):
            shutil.copy2(p, engine_dir / p.name)
            hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
            # Only fix the obsolete runtime detector, never metric formulas.
            target=engine_dir/p.name
            raw=target.read_bytes()
            old=b"v = version; Octave = v(1)<'5';"
            if old in raw:
                target.write_bytes(raw.replace(old,b"v = version; Octave = exist('OCTAVE_VERSION','builtin') ~= 0;"))
                compatibility.append(p.name+': 仅修复 Octave 环境识别，指标公式未改动')
            executed_hashes[p.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        engine = {'mode': 'MATLAB 原版兼容', 'source': str(source), 'files_sha256': hashes, 'executed_files_sha256':executed_hashes, 'compatibility':compatibility, 'matlab': s['matlab'], 'preprocess': '无额外预处理；图像按原指标接口读取'}
        engine['backend']='compiled' if compiled else 'matlab'
        if compiled:
            manifest=json.loads((ROOT/'engine/manifest.json').read_text(encoding='utf-8'))
            if manifest['files']!=executed_hashes: raise ValueError('编译引擎的指标代码指纹与当前文件不一致，请重新构建后使用')
            engine['compiler_manifest']=manifest
            engine['binary_sha256']=hashlib.sha256((ROOT/'engine/fusion_engine.exe').read_bytes()).hexdigest()
            engine['runtime_root']=str(runtime_root(s.get('matlab',''),s.get('runtime','')))
        matched_names={g['name'] for g,f in pairs}
        engine['scope']={'selected':len(groups),'evaluated':len(pairs),'unmatched':len(groups)-len(pairs),'excluded_groups':[g['name'] for g in groups if g['name'] not in matched_names],'batch':body.get('batch','全部批次')}
        with db() as c:
            c.execute('INSERT INTO runs(id,project_id,name,method,note,created,status,metrics,engine) VALUES(?,?,?,?,?,?,?,?,?)', (rid,body['project_id'], body.get('name','').strip() or '未命名测试',body.get('method',''),body.get('note',''),now(),'queued',json.dumps(selected),json.dumps(engine,ensure_ascii=False)))
            for g,f in pairs:
                meta = json.loads(g['meta']); meta['f'] = f['meta']
                c.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?)', (uid(),rid,g['name'],g['a'],g['b'],f['path'],json.dumps(meta),))
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    thread = threading.Thread(target=execute_run, args=(rid,), daemon=True)
    thread.start()
    return {'id':rid}


MATLAB_SCRIPT = r"""
job = jsondecode(fileread(fullfile(fileparts(mfilename('fullpath')), 'job.json')));
addpath(job.engine);
v = version;
fid = fopen(job.version_file,'w','n','UTF-8'); fprintf(fid,'%s',v); fclose(fid);
for ii=1:numel(job.items)
    item=job.items(ii);
    for mm=1:numel(job.metrics)
        metric=job.metrics{mm};
        record=struct('item_id',item.id,'metric',metric,'value',[],'status','error','error','','seconds',0);
        started=tic;
        try
            A=imread(item.a); B=imread(item.b); F=imread(item.f);
            value=feval(['metrics' metric],A,B,F);
            if ~isnumeric(value) || ~isscalar(value) || ~isreal(value) || ~isfinite(value)
                error('FusionEval:InvalidResult','指标返回非有限实数标量（NaN / Inf 等）');
            end
            record.value=double(value); record.status='ok';
        catch err
            record.error=getReport(err,'basic','hyperlinks','off');
        end
        record.seconds=toc(started);
        fid=fopen(job.results,'a','n','UTF-8');
        fprintf(fid,'%s\n',jsonencode(record)); fclose(fid);
    end
end
"""


def execute_run(rid):
    folder = DATA / 'runs' / rid
    proc = None
    MATLAB_SLOT.acquire()
    try:
        r = run_detail(rid)
        output = folder / 'results.jsonl'
        job = {'engine': str(folder/'engine'), 'items': [{k:i[k] for k in ('id','a','b','f')} for i in r['items']], 'metrics':r['metrics'], 'results':str(output),'version_file':str(folder/'matlab_version.txt')}
        (folder/'job.json').write_text(json.dumps(job,ensure_ascii=True),encoding='utf-8')
        script = folder/'evaluate_job.m'
        script.write_text(MATLAB_SCRIPT,encoding='utf-8')
        with db() as c:
            if required(c,'runs',rid)['status']=='cancelled': return
            c.execute("UPDATE runs SET status='running' WHERE id=?", (rid,))
        with (folder/'matlab.log').open('wb') as log:
            if r['engine'].get('backend')=='compiled':
                command=[str(ROOT/'engine/fusion_engine.exe'),str(folder/'job.json')]
                env=runtime_env(Path(r['engine']['runtime_root']))
            else:
                command=[r['engine']['matlab'],'-batch',"run('"+str(script).replace("'","''")+"')"]
                env=None
            proc = subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with LOCK: ACTIVE[rid] = proc
            with db() as c:
                if required(c,'runs',rid)['status']=='cancelled':
                    proc.terminate()
            offset = 0
            def ingest():
                nonlocal offset
                if not output.exists(): return
                with output.open('rb') as f:
                    f.seek(offset)
                    for line in f:
                        if not line.endswith(b'\n'): break
                        x=json.loads(line.decode('utf-8'))
                        value=x.get('value')
                        if x['status']!='ok' or not isinstance(value,(int,float)) or not math.isfinite(value): value=None
                        with db() as c:
                            c.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?)',(x['item_id'],x['metric'],value,x['status'],x['error'],x['seconds']))
                        offset=f.tell()
            while proc.poll() is None:
                ingest(); time.sleep(.5)
            ingest()
        with db() as c:
            current=required(c,'runs',rid)
            if current['status']=='cancelled': return
            count=c.execute('SELECT count(*) FROM results z JOIN items i ON z.item_id=i.id WHERE i.run_id=?',(rid,)).fetchone()[0]
            failed=c.execute("SELECT count(*) FROM results z JOIN items i ON z.item_id=i.id WHERE i.run_id=? AND z.status!='ok'",(rid,)).fetchone()[0]
            status='completed' if proc.returncode==0 and count==len(r['items'])*len(r['metrics']) else 'failed'
            error='' if status=='completed' else 'MATLAB 未正常完成，请查看运行日志。'
            if failed and status=='completed': status='partial'
            version_file=folder/'matlab_version.txt'
            engine=r['engine']
            if version_file.exists(): engine['matlab_version']=version_file.read_text(encoding='utf-8')
            c.execute('UPDATE runs SET status=?,error=?,engine=? WHERE id=?',(status,error,json.dumps(engine,ensure_ascii=False),rid))
    except Exception as e:
        with db() as c: c.execute("UPDATE runs SET status='failed',error=? WHERE id=?",(str(e),rid))
    finally:
        if proc and proc.poll() is None: proc.terminate()
        with LOCK: ACTIVE.pop(rid,None)
        MATLAB_SLOT.release()


def xlsx_bytes(r):
    """Small standards-compliant XLSX writer; strings never become formulas."""
    sheets=[('逐组结果',[['图片组']+r['metrics']]+[[i['name']]+[i['results'].get(m,{}).get('value') for m in r['metrics']] for i in r['items']]),
            ('统计汇总',[['指标','平均值','标准差（总体）','有效组数','全部组数']]+[[m]+[r['summary'][m][k] for k in ('mean','std','valid','total')] for m in r['metrics']]),
            ('实验信息',[['字段','内容'],['测试名称',r['name']],['算法',r['method']],['备注',r['note']],['时间',r['created']],['状态',r['status']],['指标实现',json.dumps(r['engine'],ensure_ascii=False)]]),
            ('逐项状态',[['图片组','指标','状态','错误','耗时（秒）']]+[[i['name'],m,i['results'].get(m,{}).get('status','pending'),i['results'].get(m,{}).get('error',''),i['results'].get(m,{}).get('seconds')] for i in r['items'] for m in r['metrics']])]
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for n in range(1,len(sheets)+1))+'</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{name}" sheetId="{n}" r:id="rId{n}"/>' for n,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{n}.xml"/>' for n in range(1,len(sheets)+1))+'</Relationships>')
        for n,(_,data) in enumerate(sheets,1):
            lines=[]
            for row in data:
                cells=[]
                for v in row:
                    if v is None: cells.append('<c/>')
                    elif isinstance(v,(int,float)): cells.append(f'<c><v>{v}</v></c>')
                    else:
                        text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(v))[:32767]
                        cells.append('<c t="inlineStr"><is><t xml:space="preserve">'+xml_escape(text)+'</t></is></c>')
                lines.append('<row>'+''.join(cells)+'</row>')
            z.writestr(f'xl/worksheets/sheet{n}.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(lines)+'</sheetData></worksheet>')
    return out.getvalue()


def reproduction_script(r):
    job={'engine':str(DATA/'runs'/r['id']/'engine'),'items':[{k:i[k] for k in ('name','a','b','f')} for i in r['items']],'metrics':r['metrics']}
    payload=json.dumps(job,ensure_ascii=True).replace("'","''")
    return ("% Fusion Lab: direct MATLAB verification, no result cache.\n"
            "% Uses the exact image and code snapshots of this test.\n"
            "clear; clc; format long g;\njob=jsondecode('"+payload+"');\n"
            "addpath(job.engine);\nclear "+' '.join('metrics'+m for m in r['metrics'])+";\n"
            "records={}; resultsMetrics=nan(numel(job.items),1,numel(job.metrics));\n"
            "for ii=1:numel(job.items)\n t=job.items(ii); A=imread(t.a); B=imread(t.b); F=imread(t.f);\n"
            " for mm=1:numel(job.metrics)\n  m=job.metrics{mm}; v=NaN; status='error'; note='';\n"
            "  try\n   v=feval(['metrics' m],A,B,F);\n"
            "   if ~isnumeric(v)||~isscalar(v)||~isreal(v)||~isfinite(v),error('Invalid scalar result');end\n"
            "   status='ok';resultsMetrics(ii,1,mm)=double(v);\n"
            "  catch err,note=getReport(err,'basic','hyperlinks','off');v=NaN;end\n"
            "  records(end+1,:)={t.name,m,v,status,note};\n end\nend\n"
            "resultsMetricsAverageImg=mean(resultsMetrics,1,'omitnan');\n"
            "verification=cell2table(records,'VariableNames',{'Group','Metric','Value','Status','Error'});\n"
            "disp(verification); disp(resultsMetricsAverageImg);\n"
            "writetable(verification,fullfile(fileparts(mfilename('fullpath')),'matlab_verification.csv'));\n").encode('utf-8')


def mutate(route, body):
    if route=='/api/settings':
        matlab=Path(body['matlab']).resolve(); mefb=Path(body['mefb']).resolve()
        engine=body.get('engine',settings().get('engine','matlab'))
        if engine not in ('matlab','compiled'): raise ValueError('无效计算引擎')
        if engine=='matlab' and (not matlab.is_file() or not (mefb/'metrics').is_dir()): raise ValueError('MATLAB 可执行文件或 MEFB metrics 目录不存在')
        configured_runtime=body.get('runtime','').strip()
        if configured_runtime and not runtime_root('',configured_runtime): raise ValueError('未在指定目录找到 R2026a Runtime')
        with db() as c:
            c.executemany('UPDATE settings SET value=? WHERE key=?',[(str(matlab),'matlab'),(str(mefb),'mefb'),(engine,'engine'),(configured_runtime,'runtime')])
        return state()
    if route=='/api/projects':
        name=body.get('name','').strip()
        if not name: raise ValueError('请输入项目名称')
        pid=uid()
        with db() as c: c.execute('INSERT INTO projects VALUES(?,?,?,?)',(pid,name,body.get('note',''),now()))
        return {'id':pid}
    if route=='/api/sources':
        pid=body['project_id']; folder=DATA/'sources'/uid()
        try:
            with db() as c: required(c,'projects',pid)
            a=import_files(body['a'],folder/'a'); b=import_files(body['b'],folder/'b')
            # MEFB stores both source roles together under per-group folders.
            if any(re.search(r'[_\-]A$',f['stem'],re.I) for f in a) and any(re.search(r'[_\-]B$',f['stem'],re.I) for f in a):
                a=[f for f in a if re.search(r'[_\-]A$',f['stem'],re.I)]
            if any(re.search(r'[_\-]A$',f['stem'],re.I) for f in b) and any(re.search(r'[_\-]B$',f['stem'],re.I) for f in b):
                b=[f for f in b if re.search(r'[_\-]B$',f['stem'],re.I)]
            paired=pair_sources(a,b)
            batch=body.get('batch','').strip()
            if any(ch in batch for ch in '/\\') or batch in ('.','..'): raise ValueError('批次名称不能包含斜杠')
            imported=skipped=0
            keep=set()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                existing={g['name'].casefold():g for g in rows(c,'SELECT * FROM groups_ WHERE project_id=?',(pid,))}
                for pair_key,x,y in paired:
                    name=(batch+'/'+pair_key) if batch else pair_key
                    previous=existing.get(name.casefold())
                    if previous:
                        meta=json.loads(previous['meta'])
                        if any(meta[role]['sha256']!=f['meta']['sha256'] for role,f in [('a',x),('b',y)]):
                            raise ValueError(f'已有同名源图且内容不同：{name}。请使用新的批次名称，已有图片不会覆盖。')
                        skipped+=1
                        continue
                    meta={'a':x['meta'],'b':y['meta'],'pair_key':pair_key}
                    c.execute('INSERT INTO groups_(id,project_id,name,a,b,meta,batch) VALUES(?,?,?,?,?,?,?)',(uid(),pid,name,x['path'],y['path'],json.dumps(meta),batch))
                    keep.update([x['path'],y['path']]); imported+=1
            for p in folder.rglob('*'):
                if p.is_file() and str(p) not in keep: p.unlink()
            return {'count':imported,'skipped':skipped,'batch':batch}
        except Exception:
            shutil.rmtree(folder,ignore_errors=True); raise
    if route=='/api/runs': return create_run(body)
    if route=='/api/cancel':
        rid=body['id']
        with db() as c:
            r=required(c,'runs',rid)
            if r['status'] not in ('running','queued'): raise ValueError('该测试已结束')
            c.execute("UPDATE runs SET status='cancelled' WHERE id=?",(rid,))
        with LOCK: proc=ACTIVE.get(rid)
        if proc:
            if os.name=='nt': subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            else: proc.terminate()
        return {'ok':True}
    raise ValueError('未知操作')


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def validate_host(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed: raise ValueError('仅允许本机地址访问')
    def send(self, data, kind='application/json; charset=utf-8', status=200, headers=None):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        try:
            self.validate_host()
            u=urlparse(self.path); q=parse_qs(u.query); route=u.path
            if route=='/api/health': return self.send({'app':'FusionEvalWorkbench','version':'1.1','frozen':FROZEN,'data':str(DATA)})
            if route=='/api/state': return self.send(state())
            if route=='/api/project': return self.send(project_detail(q['id'][0]))
            if route=='/api/run': return self.send(run_detail(q['id'][0]))
            if route=='/api/log':
                rid=q['id'][0]
                with db() as c: required(c,'runs',rid)
                p=DATA/'runs'/rid/'matlab.log'
                return self.send({'text':p.read_bytes()[-30000:].decode('utf-8',errors='replace') if p.exists() else '等待 MATLAB 启动…'})
            if route=='/api/image':
                with db() as c:
                    table='items' if q['kind'][0]=='item' else 'groups_'
                    row=required(c,table,q['id'][0]); role=q['role'][0]
                    if role not in ('a','b','f') or role not in row: raise ValueError('图片不存在')
                    path=Path(row[role]).resolve()
                    if not path.is_relative_to(DATA): raise ValueError('图片不可访问')
                with Image.open(path) as im:
                    im.thumbnail((1600,1600)); out=io.BytesIO(); im.convert('RGB').save(out,format='JPEG',quality=90)
                return self.send(out.getvalue(),'image/jpeg')
            if route=='/api/export':
                r=run_detail(q['id'][0]); stream=io.StringIO(newline=''); w=csv.writer(stream)
                w.writerow(['测试',r['name'],'算法',r['method'],'创建时间',r['created'],'指标实现','MATLAB 原版兼容'])
                w.writerow(['备注',r['note']]); w.writerow(['组编号']+r['metrics'])
                for i in r['items']: w.writerow([i['name']]+[i['results'].get(m,{}).get('value','') if i['results'].get(m,{}).get('value') is not None else '' for m in r['metrics']])
                for label,key in [('平均值','mean'),('标准差（总体）','std'),('有效数量','valid')]: w.writerow([label]+[r['summary'][m][key] for m in r['metrics']])
                w.writerow([]); w.writerow(['组编号','指标','状态','错误','耗时（秒）'])
                for i in r['items']:
                    for m in r['metrics']:
                        z=i['results'].get(m,{})
                        w.writerow([i['name'],m,z.get('status','pending'),z.get('error',''),z.get('seconds','')])
                w.writerow([]); w.writerow(['引擎快照',json.dumps(r['engine'],ensure_ascii=False)])
                return self.send(('\ufeff'+stream.getvalue()).encode('utf-8'),'text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="evaluation.csv"'})
            if route=='/api/export-json':
                return self.send(run_detail(q['id'][0]),headers={'Content-Disposition':'attachment; filename="evaluation.json"'})
            if route=='/api/export-xlsx':
                return self.send(xlsx_bytes(run_detail(q['id'][0])),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="evaluation.xlsx"'})
            if route=='/api/reproduce':
                return self.send(reproduction_script(run_detail(q['id'][0])),'text/plain; charset=utf-8',headers={'Content-Disposition':'attachment; filename="verify_in_matlab.m"'})
            if route=='/': route='/index.html'
            p=(ROOT/'static'/route.lstrip('/')).resolve()
            if not p.is_relative_to(ROOT/'static') or not p.is_file(): return self.send({'error':'未找到'},status=404)
            mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}.get(p.suffix,'application/octet-stream')
            return self.send(p.read_bytes(),mime)
        except Exception as e: self.send({'error':str(e)},status=400)
    def do_POST(self):
        try:
            self.validate_host()
            # Reject cross-origin requests to this local file-access service.
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''): raise ValueError('拒绝跨站请求')
            if 'application/json' not in self.headers.get('Content-Type',''): raise ValueError('需要 JSON 请求')
            n=int(self.headers.get('Content-Length','0'))
            if n>512*1024*1024: raise ValueError('导入过大，请使用本地文件夹路径')
            return self.send(mutate(urlparse(self.path).path,json.loads(self.rfile.read(n))))
        except Exception as e: self.send({'error':str(e)},status=400)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--open',action='store_true'); args=parser.parse_args()
    try: server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        print(f'端口 {args.port} 已被使用；如果工具已启动，请直接打开 http://127.0.0.1:{args.port}',flush=True)
        if args.open:
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{args.port}')
        raise SystemExit(1)
    init()
    print(f'Fusion Eval: http://127.0.0.1:{args.port}',flush=True)
    if args.open:
        import webbrowser
        threading.Timer(.5,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        with LOCK:
            for p in ACTIVE.values(): p.terminate()
        server.server_close()
