import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import backup
from PIL import Image


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=app.DATA
        app.DATA=Path(self.temp.name)/'data'
        app.init()
        self.pid=app.mutate('/api/projects',{'name':'实验项目','note':'测试'})['id']
        self.src=Path(self.temp.name)/'input'; self.src.mkdir()
        for group in ('001','002'):
            for role in ('A','B'): Image.new('RGB',(16,16),(20,40,60)).save(self.src/f'{group}_{role}.png')
        self.fused=Path(self.temp.name)/'fused'; self.fused.mkdir()
        for group in ('001','002'): Image.new('RGB',(16,16),(35,45,55)).save(self.fused/f'{group}_model.png')
    def tearDown(self):
        app.DATA=self.old; self.temp.cleanup()
    def sources(self):
        return app.mutate('/api/sources',{'project_id':self.pid,'a':{'path':str(self.src)},'b':{'path':str(self.src)}})
    def run_fixture(self):
        self.sources()
        with patch.object(app.threading,'Thread'):
            return app.create_run({'project_id':self.pid,'name':'测试','method':'model','metrics':['Entropy','SD'],'fused':{'path':str(self.fused)}})['id']
    def test_mefb_nested_sources_and_immutable_dataset(self):
        self.assertEqual(self.sources()['count'],2)
        p=app.project_detail(self.pid)
        self.assertEqual([g['name'] for g in p['groups']],['001','002'])
        self.assertTrue(Path(p['groups'][0]['a']).is_relative_to(app.DATA))
        repeat=self.sources()
        self.assertEqual((repeat['count'],repeat['skipped']),(0,2))
        self.assertEqual(len(app.project_detail(self.pid)['groups']),2)
    def test_missing_pair_rolls_back(self):
        (self.src/'002_B.png').unlink()
        with self.assertRaisesRegex(ValueError,'配对不完整'): self.sources()
        self.assertEqual(app.project_detail(self.pid)['groups'],[])
    def test_duplicate_names_rejected(self):
        Image.new('RGB',(16,16)).save(self.src/'001_A.jpg')
        with self.assertRaisesRegex(ValueError,'重复'): self.sources()
    def test_average_excludes_failed_and_keeps_zero(self):
        rid=self.run_fixture(); r=app.run_detail(rid)
        with app.db() as c:
            for index,item in enumerate(r['items']):
                c.execute('INSERT INTO results VALUES(?,?,?,?,?,?)',(item['id'],'Entropy',index*4,'ok','',.1))
                c.execute('INSERT INTO results VALUES(?,?,?,?,?,?)',(item['id'],'SD',2 if index==0 else None,'ok' if index==0 else 'error','bad channels' if index else '',.1))
        r=app.run_detail(rid)
        self.assertEqual(r['summary']['Entropy'],{'mean':2,'std':2,'valid':2,'total':2})
        self.assertEqual(r['summary']['SD']['mean'],2)
        self.assertEqual(r['summary']['SD']['valid'],1)
        with zipfile.ZipFile(io.BytesIO(app.xlsx_bytes(r))) as z:
            self.assertEqual(len([n for n in z.namelist() if n.startswith('xl/worksheets/')]),4)
            for name in z.namelist(): ET.fromstring(z.read(name))
        engine=r['engine']
        self.assertIn('metricsEntropy.m',engine['files_sha256'])
        self.assertTrue(engine['compatibility'])
        self.assertNotEqual(engine['files_sha256']['metricsQp.m'],engine['executed_files_sha256']['metricsQp.m'])
    def test_ambiguous_fused_rejected_and_no_partial_run(self):
        self.sources()
        Image.new('RGB',(16,16)).save(self.fused/'001_other.png')
        with patch.object(app.threading,'Thread'):
            # Missing method makes both suffix candidates ambiguous.
            with self.assertRaisesRegex(ValueError,'匹配到 2'):
                app.create_run({'project_id':self.pid,'metrics':['Entropy'],'fused':{'path':str(self.fused)}})
        self.assertEqual(app.project_detail(self.pid)['runs'],[])
    def test_snapshot_and_recovery(self):
        rid=self.run_fixture(); first=app.run_detail(rid)
        Image.new('RGB',(16,16),(250,250,250)).save(self.fused/'001_model.png')
        self.assertNotEqual(app.image_meta(self.fused/'001_model.png')['sha256'],json.loads(first['items'][0]['meta'])['f']['sha256'])
        app.init()
        self.assertEqual(app.run_detail(rid)['status'],'interrupted')
    def test_backup_restore_relocates_images(self):
        rid=self.run_fixture()
        with app.db() as c: c.execute("UPDATE runs SET status='completed' WHERE id=?",(rid,))
        archive=Path(self.temp.name)/'backup.zip'
        backup.backup(archive)
        restored=Path(self.temp.name)/'restored'
        backup.restore(archive,restored)
        app.DATA=restored
        r=app.run_detail(rid)
        self.assertEqual(r['name'],'测试')
        for i in r['items']:
            for role in ('a','b','f'):
                self.assertTrue(Path(i[role]).is_relative_to(restored))
                self.assertTrue(Path(i[role]).is_file())
        with self.assertRaisesRegex(ValueError,'空目录'): backup.restore(archive,restored)
    def test_append_500_pairs_after_existing_test(self):
        rid=self.run_fixture()
        initial=app.run_detail(rid)
        batch_src=Path(self.temp.name)/'bulk'
        for role in ('a','b'):
            (batch_src/role).mkdir(parents=True)
            for n in range(500): Image.new('RGB',(8,8),(n%256,30,50)).save(batch_src/role/f'{n:03}.png')
        body={'project_id':self.pid,'batch':'第二批500组','a':{'path':str(batch_src/'a')},'b':{'path':str(batch_src/'b')}}
        self.assertEqual(app.mutate('/api/sources',body)['count'],500)
        self.assertEqual(len(app.project_detail(self.pid)['groups']),502)
        self.assertEqual(app.run_detail(rid)['items'],initial['items'])
        self.assertEqual(app.mutate('/api/sources',body)['skipped'],500)
        # Repeating a historical test still selects only its original 2 pairs.
        with patch.object(app.threading,'Thread'):
            clone=app.create_run({'project_id':self.pid,'clone_id':rid,'metrics':['Entropy']})
        self.assertEqual(len(app.run_detail(clone['id'])['items']),2)
    def test_same_name_changed_image_rejected_atomically(self):
        self.sources()
        Image.new('RGB',(16,16),(0,0,0)).save(self.src/'002_A.png')
        with self.assertRaisesRegex(ValueError,'内容不同'): self.sources()
        self.assertEqual(len(app.project_detail(self.pid)['groups']),2)
        result=app.mutate('/api/sources',{'project_id':self.pid,'batch':'新版本','a':{'path':str(self.src)},'b':{'path':str(self.src)}})
        self.assertEqual(result['count'],2)
    def test_nested_repeated_names_and_batch_scoped_fusion(self):
        for parent in ('scene1','scene2'):
            (self.src/parent).mkdir()
            for role in ('A','B'): Image.new('RGB',(16,16),(20,40,60)).save(self.src/parent/f'001_{role}.png')
            (self.fused/parent).mkdir()
            Image.new('RGB',(16,16)).save(self.fused/parent/'001_model.png')
        result=app.mutate('/api/sources',{'project_id':self.pid,'batch':'嵌套批次','a':{'path':str(self.src)},'b':{'path':str(self.src)}})
        self.assertEqual(result['count'],4)
        with patch.object(app.threading,'Thread'):
            run=app.create_run({'project_id':self.pid,'batch':'嵌套批次','metrics':['Entropy'],'method':'model','fused':{'path':str(self.fused)}})
        self.assertEqual(len(app.run_detail(run['id'])['items']),4)
    def test_partial_fusion_scope_is_explicit_and_recorded(self):
        self.sources()
        (self.fused/'002_model.png').unlink()
        body={'project_id':self.pid,'metrics':['Entropy'],'method':'model','fused':{'path':str(self.fused),'recursive':False}}
        with patch.object(app.threading,'Thread'):
            with self.assertRaisesRegex(ValueError,'匹配到 0'): app.create_run(body)
            run=app.create_run(dict(body,allow_missing=True))
        r=app.run_detail(run['id'])
        self.assertEqual(len(r['items']),1)
        self.assertEqual(r['engine']['scope']['excluded_groups'],['002'])
        self.assertEqual(r['engine']['scope']['unmatched'],1)
    def test_fused_directory_can_exclude_luminance(self):
        sub=self.fused/'luminance';sub.mkdir()
        Image.new('RGB',(16,16)).save(sub/'001_model.png')
        dest=Path(self.temp.name)/'imported'
        self.assertEqual(len(app.import_files({'path':str(self.fused),'recursive':False},dest)),2)
        self.assertEqual(len(app.import_files({'path':str(self.fused),'recursive':True},dest)),3)


if __name__=='__main__': unittest.main()
