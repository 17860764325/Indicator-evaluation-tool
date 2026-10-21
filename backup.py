"""Offline portable workspace backups. Stop app.py before restoring."""
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile
import app


def backup(destination):
    if not (app.DATA/'workbench.sqlite').is_file(): raise ValueError('工作空间尚未创建')
    destination=Path(destination).resolve()
    if destination.is_relative_to(app.DATA): raise ValueError('备份文件应放在 data 目录以外')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        snapshot=Path(tmp)/'workbench.sqlite'
        with app.db() as source, sqlite3.connect(snapshot,factory=app.Connection) as target:
            if source.execute("SELECT 1 FROM runs WHERE status IN ('running','queued')").fetchone(): raise ValueError('请等待测试结束后备份')
            source.backup(target)
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',json.dumps({'format':1,'original_data':str(app.DATA)},ensure_ascii=False))
            z.write(snapshot,'data/workbench.sqlite')
            for p in app.DATA.rglob('*'):
                if p.is_file() and not p.name.startswith('workbench.sqlite'): z.write(p,'data/'+p.relative_to(app.DATA).as_posix())
    return destination


def restore(archive,destination):
    destination=Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()): raise ValueError('恢复目标必须为空目录，避免覆盖现有记录')
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('format')!=1: raise ValueError('不支持的备份格式')
        for info in z.infolist():
            if info.filename=='manifest.json': continue
            relative=Path(info.filename)
            if relative.parts[0]!='data': raise ValueError('备份包含意外文件')
            target=(destination/Path(*relative.parts[1:])).resolve()
            if not target.is_relative_to(destination): raise ValueError('备份路径无效')
            if info.is_dir(): target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(z.read(info))
    old=manifest['original_data']
    with sqlite3.connect(destination/'workbench.sqlite',factory=app.Connection) as c:
        for table,cols in [('groups_',['a','b']),('items',['a','b','f'])]:
            for col in cols:
                for rowid,path in c.execute(f'SELECT rowid,{col} FROM {table}').fetchall():
                    relative=Path(path).relative_to(Path(old))
                    c.execute(f'UPDATE {table} SET {col}=? WHERE rowid=?',(str(destination/relative),rowid))
        c.execute("UPDATE runs SET status='interrupted' WHERE status IN ('running','queued')")
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='mode',required=True)
    b=sub.add_parser('backup'); b.add_argument('output')
    r=sub.add_parser('restore'); r.add_argument('archive'); r.add_argument('destination')
    args=parser.parse_args()
    print(backup(args.output) if args.mode=='backup' else restore(args.archive,args.destination))
