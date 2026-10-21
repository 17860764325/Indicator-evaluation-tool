"""Generate an evidence report after direct and compiled validation runs."""
from pathlib import Path
import csv
import json
import math
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app


def main():
    root=app.ROOT/'tests/consistency-audit'
    read=lambda name:[json.loads(line) for line in (root/name).read_text(encoding='utf-8').splitlines()]
    direct={(r['item_id'],r['metric']):r for r in read('direct.jsonl')}
    run=app.run_detail('a6ee9a475262468693eccf711592b86f')
    comparisons=[]
    for i in run['items']:
        for metric,result in i['results'].items():
            d=direct[i['id'],metric]
            assert d['status']==result['status']
            delta=abs(result['value']-d['value']) if d['status']=='ok' else None
            comparisons.append({'comparison':'网页 / MATLAB 直接运行','group':i['name'],'metric':metric,'reference':d.get('value'),'actual':result.get('value'),'abs_error':delta})
    for file in ('compiled_existing.jsonl','compiled_all24.jsonl'):
        expected=600 if file=='compiled_existing.jsonl' else 48
        compiled=read(file)
        assert len(compiled)==expected,(file,len(compiled),expected)
        for r in compiled:
            d=direct[r['item_id'],r['metric']]
            assert r['status']==d['status']=='ok',(file,r)
            comparisons.append({'comparison':'编译引擎 / MATLAB 直接运行','group':next(i['name'] for i in run['items'] if i['id']==r['item_id']),'metric':r['metric'],'reference':d['value'],'actual':r['value'],'abs_error':abs(r['value']-d['value'])})
    for row in comparisons:
        assert math.isclose(row['reference'],row['actual'],rel_tol=1e-12,abs_tol=1e-12),row
    with (root/'逐项一致性核对.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
    report={'release':'R2026a Update 5','original_experiment_groups':100,'web_vs_direct_count':600,'compiled_vs_direct_count':648,'all_available_metrics_sample_groups':2,'all_available_metrics_count':24,'maximum_absolute_error':max(r['abs_error'] for r in comparisons),'tolerance_absolute':1e-12,'tolerance_relative':1e-12,'passed':True,'note':'直接调用原版指标，绕过 compute_metrics 的文本缓存；QP 只修正 Octave 环境识别。所有输入使用保存的同一份图片快照，未转码。'}
    (root/'核对报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'核对报告.md').write_text('# 图像融合指标一致性核对\n\n'+
        '- 原实验：100 组图片，6 项指标，共 600 个网页分数，对照 MATLAB 直接调用全部通过。\n'+
        '- MATLAB 编译引擎：同一 100 组 × 6 项，以及 2 组 × 全部 24 项，共 648 项对照全部通过。\n'+
        f'- 所有 1248 次比较的最大绝对差：{report["maximum_absolute_error"]}。\n'+
        '- 核对使用 R2026a Update 5，所有输入均为相同图片快照，无 JPG/PNG 转码，无旧结果缓存。\n'+
        '- 原指标公式保持不变；仅 QP 的 Octave 环境识别作兼容修复。\n'+
        '- 本报告证明所列样本的一致性。其他图片可通过每条测试导出的 MATLAB 复核脚本重新核对。\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
