"""Windowed single-file launcher. No external Python installation required."""
import ctypes
import json
import logging
import os
from pathlib import Path
import threading
import urllib.request
import webbrowser

HOME=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'FusionEvalWorkbench'
HOME.mkdir(parents=True,exist_ok=True)
CONFIG=HOME/'desktop.json'
if not os.environ.get('FUSION_EVAL_DATA'):
    if CONFIG.exists():
        try: os.environ['FUSION_EVAL_DATA']=json.loads(CONFIG.read_text(encoding='utf-8'))['data']
        except (ValueError,KeyError): pass
    if not os.environ.get('FUSION_EVAL_DATA'):
        existing=Path(r'D:\project\paper\fusion-eval\data')
        selected=existing if (existing/'workbench.sqlite').is_file() else HOME/'data'
        os.environ['FUSION_EVAL_DATA']=str(selected)
        CONFIG.write_text(json.dumps({'data':str(selected)}),encoding='utf-8')

import app
import tkinter as tk
from tkinter import messagebox
from http.server import ThreadingHTTPServer
from runtime_support import RUNTIME_URL

URL='http://127.0.0.1:8765'
logging.basicConfig(filename=HOME/'desktop.log',level=logging.INFO,encoding='utf-8')
server=None


def main():
    global server
    if os.name=='nt': ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('FusionEval.Workbench.1')
    root=tk.Tk();root.title('图像融合评估工作台');root.geometry('560x360');root.resizable(False,False)
    root.configure(bg='#f5f8f9')
    try: root.iconbitmap(str(app.ROOT/'assets/workbench.ico'))
    except tk.TclError: pass
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=2) as response: health=json.load(response)
        if health.get('app')!='FusionEvalWorkbench': raise ValueError('端口被其他程序占用')
    except Exception:
        try:
            server=ThreadingHTTPServer(('127.0.0.1',8765),app.Handler)
            app.init()
            threading.Thread(target=server.serve_forever,daemon=True).start()
        except Exception as error:
            logging.exception('Startup failed')
            messagebox.showerror('启动失败',str(error));root.destroy();return
    tk.Label(root,text='◈  图像融合评估工作台',font=('Microsoft YaHei UI',20,'bold'),fg='#086e65',bg='#f5f8f9').pack(pady=(27,10))
    tk.Label(root,text='项目管理 · 批量评估 · MATLAB 原版指标',font=('Microsoft YaHei UI',11),fg='#667b86',bg='#f5f8f9').pack()
    tk.Label(root,text='本地服务已启动，实验数据仅保存在你的电脑。',font=('Microsoft YaHei UI',10),fg='#667b86',bg='#f5f8f9').pack(pady=(19,7))
    tk.Button(root,text='打开评估工作台',command=lambda:webbrowser.open(URL),bg='#087f75',fg='white',font=('Microsoft YaHei UI',12),relief='flat',width=26,pady=9).pack(pady=8)
    tk.Button(root,text='打开数据文件夹',command=lambda:os.startfile(str(app.DATA)),font=('Microsoft YaHei UI',10),relief='flat',bg='#e8f0ef',fg='#24665f').pack(pady=4)
    tk.Button(root,text='首次使用：下载 R2026a MATLAB Runtime',command=lambda:webbrowser.open(RUNTIME_URL),relief='flat',bg='#f5f8f9',fg='#087f75',font=('Microsoft YaHei UI',9)).pack(pady=6)
    tk.Label(root,text='关闭浏览器后仍可再次打开；关闭此窗口将停止本次服务。',font=('Microsoft YaHei UI',9),fg='#82939c',bg='#f5f8f9').pack(pady=6)
    def close():
        if server:
            with app.db() as c: active=c.execute("SELECT count(*) FROM runs WHERE status IN ('running','queued')").fetchone()[0]
            if active and not messagebox.askyesno('测试仍在进行','仍有测试正在运行或排队。退出将中断这些测试，确定退出吗？'): return
            with app.LOCK:
                for p in app.ACTIVE.values():
                    if os.name=='nt':
                        import subprocess
                        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                    else: p.terminate()
            server.shutdown();server.server_close()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.after(600,lambda:webbrowser.open(URL))
    root.mainloop()


if __name__=='__main__':
    try: main()
    except Exception as e:
        logging.exception('Desktop error')
        ctypes.windll.user32.MessageBoxW(0,str(e),'图像融合评估工作台启动失败',16)
