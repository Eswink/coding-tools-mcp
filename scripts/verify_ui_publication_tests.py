"""Network-free verifier contracts, not anonymous-download or GUI proof."""
import copy
import tempfile
import unittest
import zipfile
from pathlib import Path
import verify_ui_publication as v

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.release={'id':v.RELEASE,'tag_name':'v0.5.0','target_commitish':v.SOURCE,'draft':False,'prerelease':True,
            'assets':[{'name':n,'size':s,'digest':'sha256:'+d,'state':'uploaded'} for n,(s,d) in v.ASSETS.items()]}
        self.ref={'object':{'sha':v.SOURCE,'type':'commit'}}
        self.run={'id':v.BUILD_RUN,'head_sha':v.SOURCE,'run_attempt':1,'head_branch':'release/ui-v0.5.0',
                  'status':'completed','conclusion':'failure'}
        self.jobs={'total_count':17,'jobs':[{'id':j,'run_id':v.BUILD_RUN,'status':'completed','conclusion':'success'} for j in sorted(v.JOBS)]
                   +[{'id':v.PUBLISH_JOB,'run_id':v.BUILD_RUN,'status':'completed','conclusion':'failure'}]}
    def test_valid_fixed_identities(self):
        v.assert_build(self.run,self.jobs);v.assert_release(self.release,self.ref,self.ref,self.ref)
    def test_prerequisite_failure_never_waived(self):
        for state in ['failure','skipped','cancelled',None]:
            j=copy.deepcopy(self.jobs);j['jobs'][0]['conclusion']=state
            with self.subTest(state=state),self.assertRaises(ValueError):v.assert_build(self.run,j)
    def test_missing_duplicate_or_new_job_rejected(self):
        for field in ['missing','duplicate','extra']:
            j=copy.deepcopy(self.jobs)
            if field=='missing':j['jobs'].pop()
            elif field=='duplicate':j['jobs'][1]=j['jobs'][0]
            else:j['jobs'].append({'id':999,'status':'completed','conclusion':'success'})
            with self.subTest(field=field),self.assertRaises(ValueError):v.assert_build(self.run,j)
    def test_cannot_relabel_or_reuse_another_run(self):
        for field,value in [('conclusion','success'),('head_sha','a'*40),('run_attempt',2),('id',999)]:
            r={**self.run,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):v.assert_build(r,self.jobs)
    def test_draft_or_wrong_release_identity_rejected(self):
        for field,value in [('draft',True),('prerelease',False),('target_commitish','a'*40),('id',999)]:
            r={**self.release,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):v.assert_release(r,self.ref,self.ref,self.ref)
    def test_tag_main_or_release_branch_mismatch_rejected(self):
        for i in range(3):
            refs=[self.ref,self.ref,self.ref];refs[i]={'object':{'sha':'a'*40,'type':'commit'}}
            with self.subTest(i=i),self.assertRaises(ValueError):v.assert_release(self.release,*refs)
    def test_missing_or_corrupted_public_asset_rejected(self):
        for field in ['missing','digest','size','state']:
            r=copy.deepcopy(self.release)
            if field=='missing':r['assets'].pop()
            else:r['assets'][0][field]='wrong'
            with self.subTest(field=field),self.assertRaises(ValueError):v.assert_release(r,self.ref,self.ref,self.ref)
    def test_recovery_has_no_write_path(self):
        calls=[]
        class Parent:
            def __init__(self,token):pass
            def request(self,*args,**kwargs):calls.append((args,kwargs));return {'read':True}
        client=v.read_only_client(Parent,'synthetic')
        for method in ['POST','PUT','PATCH','DELETE']:
            with self.subTest(method=method),self.assertRaises(ValueError):client.request(method,'/releases')
        for kwargs in [{'data':{}},{'upload':{}}]:
            with self.assertRaises(ValueError):client.request('GET','/releases',**kwargs)
        self.assertEqual(calls,[])
        self.assertEqual(client.request('GET','/releases'),{'read':True});self.assertEqual(len(calls),1)
    def test_network_failure_never_retries_or_mutates(self):
        calls=[]
        class Parent:
            def __init__(self,token):pass
            def request(self,*args,**kwargs):calls.append(args);raise RuntimeError('HTTP404')
        client=v.read_only_client(Parent,'synthetic')
        with self.assertRaises(RuntimeError):client.request('GET','/git/ref/tags/v0.5.0')
        self.assertEqual(calls,[('GET','/git/ref/tags/v0.5.0')])
    def test_unsafe_evidence_zip_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);f=p/'bad.zip'
            with zipfile.ZipFile(f,'w') as z:z.writestr('../outside','synthetic')
            with self.assertRaises(ValueError):v.unzip_checked(f,p/'out')
            self.assertFalse((p/'outside').exists())

if __name__=='__main__':unittest.main(verbosity=2)
