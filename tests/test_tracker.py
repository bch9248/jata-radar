"""Offline regressions; all example roles are fictional fixtures, not live jobs."""
import argparse
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch, Mock
from tracker.core import ROOT, canonical, job_id, classify, config, upsert, load, save, env, merge_duplicates
from tracker.sources import (parse_page, parse_community, collect_workday, collect_greenhouse,
                             collect_lever, detail, workday_parts, search_candidates, likely_job_url)
from tracker.network import Client, FetchError, public_url
from tracker.__main__ import main
from tracker.render import render
from tracker.ai import enrich

FIX = ROOT / 'tests/fixtures'
C = config()

def job(**kw):
    j = dict(url='https://example.org/jobs/1', title='Software Engineering Intern — Summer 2027',
             location='Taipei, Taiwan', company='Example', description='', trusted_detail=True, live=True)
    j.update(kw)
    return j

class ClassificationTests(unittest.TestCase):
    def test_swe_summer(self):
        self.assertEqual(classify(job(), C)['decision'], 'confirmed')
        self.assertEqual(classify(job(), C)['category'], 'SWE')
    def test_mle(self):
        self.assertEqual(classify(job(title='Machine Learning Intern - Summer 2027'), C)['category'], 'MLE_AI')
    def test_japanese(self):
        r = classify(job(title='2027年 夏季 機械学習 インターン', location='東京, 日本'), C)
        self.assertEqual((r['decision'], r['country'], r['category']), ('confirmed', 'Japan', 'MLE_AI'))
    def test_chinese(self):
        self.assertEqual(classify(job(title='2027 暑期軟體工程師實習', location='台北'), C)['decision'], 'confirmed')
    def test_cohort_ignored(self):
        r = classify(job(title='2027 New Graduates Software Internship', description='Summer internship for students graduating in 2027.'), C)
        self.assertIsNone(r['year'])
        self.assertEqual(r['decision'], 'review')
    def test_joining_year_not_summer(self):
        r = classify(job(title='ソフトウェア インターン 2027年入社', description='2027年入社を希望する方。'), C)
        self.assertEqual(r['decision'], 'review')
    def test_old_summer_with_new_cohort(self):
        r = classify(job(title='2027 New Graduates Software Internship', description='Summer 2026 internship. Graduating in 2027.'), C)
        self.assertEqual((r['year'], r['decision']), (2026, 'rejected'))
    def test_yearless(self):
        self.assertEqual(classify(job(title='Software Intern'), C)['decision'], 'review')
    def test_2027_not_summer(self):
        r = classify(job(title='AI Software Intern - 2027'), C)
        self.assertEqual(r['decision'], 'review')
    def test_winter(self):
        self.assertEqual(classify(job(title='Software Intern Winter 2027'), C)['decision'], 'rejected')
    def test_unknown_location(self):
        self.assertEqual(classify(job(location='Remote'), C)['decision'], 'review')
    def test_phd_flag(self):
        r = classify(job(title='Software Engineering Intern, PhD, Summer 2027'), C)
        self.assertEqual(r['decision'], 'confirmed')
        self.assertTrue(any('PhD' in x for x in r['flags']))
    def test_ai_company_does_not_change_backend(self):
        r = classify(job(title='Backend Intern Summer 2027', description='Our AI company builds machine learning products.'), C)
        self.assertEqual(r['category'], 'SWE')
    def test_generic_html_not_confirmed(self):
        self.assertEqual(classify(job(trusted_detail=False), C)['decision'], 'review')
    def test_fulltime_intern_allowed(self):
        self.assertEqual(classify(job(employment_type='Full time'), C)['decision'], 'confirmed')
    def test_fulltime_newgrad_rejected(self):
        self.assertEqual(classify(job(title='2027 Software Engineer New Graduate', employment_type='Full time'), C)['decision'], 'rejected')
    def test_posted_date_not_year(self):
        self.assertIsNone(classify(job(title='Summer Software Intern', posted_at='2027-01-01'), C)['year'])

class IdentityTests(unittest.TestCase):
    def test_identity_parameters_preserved(self):
        self.assertNotEqual(job_id('https://example.org/jobs?gh_jid=1'), job_id('https://example.org/jobs?gh_jid=2'))
        self.assertEqual(canonical('https://example.org/jobs?gh_jid=1&utm_source=foo#x'), 'https://example.org/jobs?gh_jid=1')
    def test_workday_locale_and_path(self):
        a = 'https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/Taipei/Some-Intern_JR1234567'
        b = 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Some-Intern_JR1234567'
        self.assertEqual(job_id(a), job_id(b))
    def test_bad_scheme(self):
        with self.assertRaises(ValueError):
            canonical('file:///etc/passwd')
    def test_bad_credentials(self):
        with self.assertRaises(ValueError):
            canonical('https://user:pass@example.org/jobs/1')
    def test_update_preserves_first_seen_and_manual(self):
        jobs = []
        a, created = upsert(jobs, job(), C)
        first = a['first_seen']
        a['manual_review'] = dict(decision='rejected', reason='duplicate')
        b, created = upsert(jobs, job(), C)
        self.assertFalse(created)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(b['first_seen'], first)
        self.assertEqual(b['decision'], 'rejected')
    def test_weak_hint_does_not_erase_detail(self):
        jobs = []
        upsert(jobs, job(), C)
        a, _ = upsert(jobs, job(title='Bad hint', location='Unknown', trusted_detail=False), C)
        self.assertEqual(a['title'], job()['title'])
        self.assertTrue(a['trusted_detail'])

class AdapterTests(unittest.TestCase):
    def test_jsonld(self):
        a = parse_page((FIX / 'job.html').read_text(), {'url':'https://example.org/jobs/11'})
        self.assertTrue(a['trusted_detail'])
        self.assertEqual(a['location'], 'Tokyo, JP')
        self.assertEqual(classify(a, C)['decision'], 'confirmed')
    def test_multiple_jsonld_is_listing(self):
        raw = '<title>Jobs</title><script type="application/ld+json">' + json.dumps([{'@type':'JobPosting','title':'A'}, {'@type':'JobPosting','title':'B'}]) + '</script>'
        self.assertFalse(parse_page(raw, job())['trusted_detail'])
    def test_invalid_ld_fallback(self):
        a = parse_page('<title>Software Intern</title><script type="application/ld+json">{broken}</script><p>hello</p>', job())
        self.assertFalse(a['trusted_detail'])
        self.assertNotIn('{broken}', a['description'])
    def test_community_old_posts_and_arrow(self):
        rows = parse_community((FIX/'community.md').read_text(), {'id':'community'})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['company'], 'Example')
        self.assertFalse(rows[0]['trusted_detail'])
    def test_community_html(self):
        raw = '<table><tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th></tr><tr><td>Example</td><td>Software Intern</td><td>Tokyo, Japan</td><td><a href="https://example.org/jobs/1">Apply</a></td></tr></table>'
        self.assertEqual(len(parse_community(raw, {'id':'c'})), 1)
    def test_workday(self):
        client = Mock()
        client.json.return_value = load(FIX/'workday-list.json')
        rows, truncated = collect_workday(client, {'id':'nvidia','company':'NVIDIA','url':'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite'}, C)
        self.assertEqual(len(rows), 2)
        self.assertFalse(truncated)
        self.assertEqual(client.json.call_args[0][1]['offset'], 0)
        client.json.return_value = load(FIX/'workday-detail.json')
        full = detail(client, rows[0])
        self.assertTrue(full['trusted_detail'])
        self.assertEqual(classify(full, C)['decision'], 'confirmed')
    def test_workday_pagination_truncated(self):
        client = Mock()
        client.json.return_value = {'total':1000,'jobPostings':[{'title':'Software Intern','locationsText':'Tokyo, Japan','externalPath':'/job/Tokyo/X_JR1'}] * 20}
        _, truncated = collect_workday(client, {'id':'s','company':'S','url':'https://s.wd1.myworkdayjobs.com/Careers'}, dict(C, max_pages=2))
        self.assertTrue(truncated)
        self.assertEqual(client.json.call_count, 2)
    def test_greenhouse(self):
        client = Mock()
        client.json.return_value = {'jobs':[{'title':'Software Intern Summer 2027','location':{'name':'Taipei, Taiwan'},'absolute_url':'https://example.org/jobs/1','content':'<p>summer 2027</p>'}]}
        rows, _ = collect_greenhouse(client, {'board':'example','company':'X','id':'g'}, C)
        self.assertTrue(rows[0]['trusted_detail'])
    def test_lever(self):
        client = Mock()
        client.json.return_value = [{'text':'Machine Learning Intern Summer 2027','categories':{'location':'Tokyo, Japan','commitment':'Intern'},'hostedUrl':'https://example.org/jobs/2','description':'<p>Summer 2027</p>','lists':[{'content':'<li>Python required</li>'}]}]
        rows, _ = collect_lever(client, {'board':'example','company':'X','id':'l'}, C)
        self.assertIn('Python required', rows[0]['description'])
    def test_search_discard_snippets_and_rotate(self):
        client = Mock()
        client.json.return_value = {'web':{'results':[{'url':'https://example.org/jobs/1','title':'SECRET SNIPPET','description':'SECRET'}]}}
        with patch.dict(os.environ, {'BRAVE_API_KEY':'fake'}, clear=True):
            rows, reports, cursor = search_candidates(client, [{'id':'a','country_code':'JP','query':'{year} internship Japan'},{'id':'b','country_code':'TW','query':'intern Taiwan'}], dict(C,max_search_queries=1), 0)
        self.assertEqual(cursor, 1)
        self.assertEqual(set(rows[0]), {'url','source'})
        self.assertNotIn('SECRET', json.dumps(rows))
    def test_no_search_key(self):
        with patch.dict(os.environ, {}, clear=True):
            client = Mock()
            self.assertEqual(search_candidates(client, [], C, 0), ([], [], 0))
            client.json.assert_not_called()
    def test_search_error(self):
        client = Mock()
        client.json.side_effect = FetchError('HTTP 429', 429)
        with patch.dict(os.environ, {'BRAVE_API_KEY':'fake'}, clear=True):
            rows, reports, _ = search_candidates(client, [{'id':'a','country_code':'JP','query':'intern'}], C, 0)
        self.assertEqual(reports[0]['status'], 'error')
        self.assertFalse(rows)
    def test_job_url_filter(self):
        self.assertFalse(likely_job_url('https://www.104.com.tw/jobs/search/?keyword=intern'))
        self.assertTrue(likely_job_url('https://www.104.com.tw/job/abc123'))

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('config.json','sources.json','search-queries.json','README.md'):
            shutil.copy(ROOT/name, self.root/name)
        (self.root/'job-postings').mkdir()
        save(self.root/'data/jobs.json', [])
    def tearDown(self):
        self.tmp.cleanup()
    def call(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(['--root',str(self.root),*args])
    def test_offline_never_network(self):
        with patch('tracker.__main__.Client') as network:
            self.assertEqual(self.call('sync','--offline'), 0)
            network.assert_not_called()
        self.assertIn('The List', (self.root/'README.md').read_text())
        self.assertTrue((self.root/'data/jobs.csv').exists())
    def test_complete_sync_and_repeat_dedup(self):
        source = {'id':'nvidia','type':'workday','company':'NVIDIA','enabled':True,'url':'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite'}
        save(self.root/'sources.json', [source])
        client = Mock(requests=3)
        def responses(url, *args, **kwargs):
            if url.endswith('/jobs'):
                return load(FIX/'workday-list.json')
            if 'JR2345678' in url:
                return {'jobPostingInfo':{'title':'Machine Learning Intern Summer 2027','location':'Tokyo, Japan','jobDescription':'<p>Research in summer 2027</p>'}}
            return load(FIX/'workday-detail.json')
        client.json.side_effect = responses
        with patch('tracker.__main__.Client', return_value=client):
            self.assertEqual(self.call('sync','--no-search'), 0)
            self.assertEqual(self.call('sync','--no-search'), 0)
        jobs = load(self.root/'data/jobs.json')
        self.assertEqual(len(jobs), 2)
        self.assertEqual({j['category'] for j in jobs}, {'SWE','MLE_AI'})
        self.assertTrue(all(j['decision']=='confirmed' for j in jobs))
        self.assertIn('Machine Learning Intern', (self.root/'job-postings/mle_ai.md').read_text())
    def test_all_source_failure_report_and_exit(self):
        client = Mock(requests=5)
        client.json.side_effect = FetchError('HTTP 403',403)
        client.request.side_effect = FetchError('HTTP 403',403)
        with patch('tracker.__main__.Client', return_value=client):
            self.assertEqual(self.call('sync','--no-search'), 2)
        self.assertTrue(all(s['status']=='error' for s in load(self.root/'data/source-health.json')['sources']))
    def test_manual_review_persists_and_private_notes(self):
        self.assertEqual(self.call('add','https://example.org/jobs/1','--title','Software Intern','--location','Tokyo, Japan','--no-fetch'), 0)
        j = load(self.root/'data/jobs.json')[0]
        self.assertEqual(self.call('review',j['id'],'confirmed','--country','Japan','--category','SWE','--reason','Verified July-August 2027'), 0)
        self.assertEqual(self.call('application',j['id'],'applied','--notes','PRIVATE SECRET'), 0)
        self.assertNotIn('PRIVATE SECRET', (self.root/'data/jobs.json').read_text())
        self.assertNotIn('PRIVATE SECRET', (self.root/'README.md').read_text())
        self.assertTrue((self.root/'.local/applications.json').exists())
        self.assertEqual(self.call('review',j['id'],'reset','--reason','Reset'), 0)
        self.assertEqual(load(self.root/'data/jobs.json')[0]['decision'], 'review')
    def test_import_never_trusted(self):
        save(self.root/'incoming.json', [job()])
        self.assertEqual(self.call('import',str(self.root/'incoming.json')), 0)
        self.assertEqual(load(self.root/'data/jobs.json')[0]['decision'], 'review')
    def test_consecutive_404_closes_but_403_does_not(self):
        jobs=[]
        j,_=upsert(jobs,job(),C)
        save(self.root/'data/jobs.json',jobs)
        with patch('tracker.__main__.detail', side_effect=FetchError('HTTP 404',404)):
            self.call('check','--force')
            self.assertEqual(load(self.root/'data/jobs.json')[0]['status'],'open')
            self.call('check','--force')
            self.assertEqual(load(self.root/'data/jobs.json')[0]['status'],'closed')
        self.call('close',j['id'],'open','--reason','Reopened')
        with patch('tracker.__main__.detail', side_effect=FetchError('HTTP 403',403)):
            self.call('check','--force')
            self.assertEqual(load(self.root/'data/jobs.json')[0]['status'],'open')
    def test_notify_preview_no_send(self):
        jobs=[]
        upsert(jobs,job(),C)
        save(self.root/'data/jobs.json',jobs)
        with patch('tracker.__main__.smtplib.SMTP') as smtp:
            self.assertEqual(self.call('notify','--preview'),0)
            smtp.assert_not_called()
        self.assertFalse((self.root/'.local/notified.json').exists())
    def test_render_escaping_and_csv_formula(self):
        jobs=[]
        upsert(jobs,job(title='=Software Intern | <script>alert(1)</script> Summer 2027'),C)
        save(self.root/'data/jobs.json',jobs)
        render(self.root,C)
        self.assertNotIn('<script>',(self.root/'README.md').read_text())
        self.assertIn("'=Software",(self.root/'data/jobs.csv').read_text())
    def test_env_does_not_execute_shell_or_override(self):
        (self.root/'.env').write_text('BRAVE_API_KEY=filekey\nSAMPLE=$(touch /tmp/nope)\n')
        with patch.dict(os.environ, {'BRAVE_API_KEY':'existing'}, clear=True):
            env(self.root)
            self.assertEqual(os.environ['BRAVE_API_KEY'],'existing')
            self.assertEqual(os.environ['SAMPLE'],'$(touch /tmp/nope)')

class SecurityAndAITests(unittest.TestCase):
    def test_local_addresses_refused(self):
        with patch('tracker.network.socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(FetchError):
                public_url('https://example.org/jobs/1')
    def test_nonstandard_port_refused(self):
        with self.assertRaises(FetchError):
            public_url('https://example.org:8080/jobs/1')
    def test_ai_only_exact_excerpts(self):
        client=Mock()
        client.json.return_value={'choices':[{'message':{'content':json.dumps({'education':'Master degree','visa':'guaranteed sponsorship','extra':'ignored'})}}]}
        j=job(description='Master degree preferred.')
        with patch.dict(os.environ, {'OPENAI_API_KEY':'fake'}, clear=True):
            enrich(client,j,C)
        self.assertEqual(j['ai_evidence'],{'education':'Master degree'})
        self.assertNotIn('decision',j)


class AdditionalRegressionTests(unittest.TestCase):
    def test_generic_research_not_automatically_ai(self):
        r=classify(job(title='Chemistry Research Intern Summer 2027'),C)
        self.assertIsNone(r['category'])
        self.assertEqual(r['decision'],'review')
    def test_unrecognized_community_schema_is_error(self):
        with self.assertRaises(FetchError):
            parse_community('# Moved: see new jobs page', {'id':'c'})
    def test_request_has_response_size_limit(self):
        client=Client(dict(C,request_delay_seconds=0))
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.read.return_value=b'x'*(4*1024*1024+1)
        client.opener=Mock()
        client.opener.open.return_value=response
        with patch('tracker.network.public_url'):
            with self.assertRaises(FetchError):
                client.request('https://example.org/jobs/1')
    def test_authenticated_redirect_never_forwarded(self):
        from urllib.error import HTTPError
        client=Client(dict(C,request_delay_seconds=0))
        client.opener=Mock()
        client.opener.open.side_effect=HTTPError('https://api.example.org/',302,'Redirect',{'Location':'https://other.example.org/'},None)
        with patch('tracker.network.public_url'):
            with self.assertRaises(FetchError):
                client.request('https://api.example.org/',headers={'Authorization':'Bearer fake'})
        self.assertEqual(client.opener.open.call_count,1)
    def test_429_retries_are_bounded(self):
        from urllib.error import HTTPError
        client=Client(dict(C,request_delay_seconds=0))
        client.opener=Mock()
        client.opener.open.side_effect=HTTPError('https://example.org/',429,'Too many requests',{},None)
        with patch('tracker.network.public_url'), patch('tracker.network.time.sleep'):
            with self.assertRaises(FetchError):
                client.request('https://example.org/')
        self.assertEqual(client.opener.open.call_count,3)
    def test_robots_disallow_prevents_page_fetch(self):
        from urllib.robotparser import RobotFileParser
        client=Client(C)
        policy=RobotFileParser()
        policy.parse(['User-agent: *','Disallow: /jobs/'])
        client.robots['example.org']=policy
        with self.assertRaises(FetchError):
            client.allowed('https://example.org/jobs/1')
    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root/'config.json',dict(C,max_detail_requests=-1))
            with self.assertRaises(ValueError):
                config(root)

class LiveShapeRegressions(unittest.TestCase):
    def test_markdown_posting_column_with_html_apply(self):
        raw='''| Company | Position | Location | Posting | Age |
|---|---|---|---|---|
| <a href="https://example.org"><strong>Example</strong></a> | Software Intern 2027 | Taipei, Taiwan +1 | <a href="https://example.org/jobs/1"><img alt="Apply"/></a> | 53d |'''
        rows=parse_community(raw,{'id':'live-shape'})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['company'],'Example')
        self.assertEqual(rows[0]['url'],'https://example.org/jobs/1')
    def test_rdss_flag(self):
        r=classify(job(title='System Software Engineer - 2027 RDSS Intern'),C)
        self.assertTrue(any('RDSS' in f for f in r['flags']))

class MoreLiveShapeTests(unittest.TestCase):
    def test_linked_role_with_no_application_column(self):
        raw='''| Company | Role | Location | Pay | Added |
| --- | --- | --- | --- | --- |
| **[Example](https://example.org)** | [Software Intern 2027](https://example.org/job/123) | Taiwan, Taipei | | 53d |'''
        rows=parse_community(raw,{'id':'dreamwork-shape'})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['company'],'Example')
        self.assertEqual(rows[0]['url'],'https://example.org/job/123')
    def test_japanese_hardware_not_swe(self):
        r=classify(job(title='2027 夏季 ハードウェアエンジニア インターン'),C)
        self.assertIsNone(r['category'])
    def test_google_slug_identity(self):
        self.assertEqual(job_id('https://www.google.com/about/careers/applications/jobs/results/123456789'),job_id('https://www.google.com/about/careers/applications/jobs/results/123456789-software-intern?hl=en'))

class ReviewFixTests(unittest.TestCase):
    AGG = 'https://www.dreamworkhq.com/job/abc'
    WD = 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Taiwan-Taipei/X_JR1'
    def test_workday_total_only_on_first_page(self):
        row = {'title':'Software Intern','locationsText':'Tokyo, Japan','externalPath':'/job/Tokyo/X_JR1'}
        pages = [{'total':50,'jobPostings':[row]*20}, {'total':0,'jobPostings':[row]*20}, {'total':0,'jobPostings':[row]*10}]
        client = Mock()
        client.json.side_effect = pages
        rows, truncated = collect_workday(client, {'id':'s','company':'S','url':'https://s.wd1.myworkdayjobs.com/Careers'}, C)
        self.assertEqual(client.json.call_count, 3)
        self.assertEqual(len(rows), 50)
        self.assertFalse(truncated)
    def test_aggregator_jsonld_not_trusted(self):
        raw = (FIX / 'job.html').read_text()
        a = parse_page(raw, {'url': self.AGG}, C)
        self.assertFalse(a['trusted_detail'])
        self.assertEqual(a['detail_method'], 'jsonld-aggregator')
        self.assertNotEqual(classify(a, C)['decision'], 'confirmed')
    def test_aggregator_employer_link(self):
        ld = {'@type':'JobPosting','title':'Software Intern Summer 2027','url':self.WD}
        raw = '<script type="application/ld+json">' + json.dumps(ld) + '</script>'
        self.assertEqual(parse_page(raw, {'url': self.AGG}, C)['employer_url'], canonical(self.WD))
    def test_cross_host_duplicates_merge_and_alias(self):
        jobs = []
        upsert(jobs, job(url=self.AGG, company='Nvidia', location='Taiwan, Taipei, TW', trusted_detail=False, source='dreamwork'), C)
        upsert(jobs, job(url=self.WD, company='NVIDIA', location='Taiwan, Taipei', source='nvidia'), C)
        self.assertEqual(merge_duplicates(jobs, C), 1)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['url'], canonical(self.WD))
        self.assertEqual(set(jobs[0]['sources']), {'dreamwork', 'nvidia'})
        # A later aggregator hint maps onto the survivor without replacing its URL.
        j, created = upsert(jobs, job(url=self.AGG, company='Nvidia', trusted_detail=False, source='dreamwork'), C)
        self.assertFalse(created)
        self.assertEqual(j['url'], canonical(self.WD))
    def test_repeated_aggregator_copies_merge(self):
        jobs = []
        upsert(jobs, job(url=self.WD, source='nvidia'), C)
        upsert(jobs, job(url=self.AGG, trusted_detail=False, source='dreamwork'), C)
        upsert(jobs, job(url=self.AGG + '2', trusted_detail=False, source='dreamwork'), C)
        self.assertEqual(merge_duplicates(jobs, C), 2)
        self.assertEqual(len(jobs[0]['alias_urls']), 2)
    def test_same_host_same_title_not_merged(self):
        jobs = []
        upsert(jobs, job(url='https://example.org/jobs/1'), C)
        upsert(jobs, job(url='https://example.org/jobs/2'), C)
        self.assertEqual(merge_duplicates(jobs, C), 0)
        self.assertEqual(len(jobs), 2)
    def test_passed_deadline_closes_on_upsert(self):
        jobs = []
        j, _ = upsert(jobs, job(deadline='2020-01-01'), C)
        self.assertEqual(j['status'], 'closed')
        j, _ = upsert(jobs, job(url='https://example.org/jobs/2', deadline='2999-01-01'), C)
        self.assertEqual(j['status'], 'open')
    def test_manual_status_sticky(self):
        jobs = []
        j, _ = upsert(jobs, job(), C)
        j['manual_status'] = {'status': 'closed', 'reason': 'closed per recruiter', 'at': '2026-01-01'}
        j, _ = upsert(jobs, job(), C)
        self.assertEqual(j['status'], 'closed')
    def test_location_outside_targets_rejected(self):
        self.assertEqual(classify(job(location='China, Beijing; China, Shanghai'), C)['decision'], 'rejected')
        self.assertEqual(classify(job(location='Germany, Remote; France, Remote'), C)['decision'], 'rejected')
        self.assertNotEqual(classify(job(location='Taiwan, Taipei; China, Shanghai'), C)['decision'], 'rejected')
        self.assertEqual(classify(job(location='Remote'), C)['decision'], 'review')
        self.assertEqual(classify(job(location=''), C)['decision'], 'review')
    def test_html_fallback_keeps_listing_title(self):
        a = parse_page('<title>Software Intern at Example | Board</title><p>hi</p>', {'url': 'https://example.org/jobs/1', 'title': 'Software Intern'})
        self.assertEqual(a['title'], 'Software Intern')
        self.assertEqual(parse_page('<title>Page Title</title>', {'url': 'https://example.org/jobs/2'})['title'], 'Page Title')
    def test_api_error_detail_masks_key(self):
        from email.message import Message
        from urllib.error import HTTPError
        h = Message(); h['Content-Type'] = 'application/json'
        body = io.BytesIO(b'{"error": {"code": "VALIDATION", "detail": "bad country", "token": "SECRETKEY123"}}')
        client = Client(dict(C, request_delay_seconds=0))
        with patch('tracker.network.public_url'), \
             patch.object(client.opener, 'open', side_effect=HTTPError('u', 422, 'x', h, body)):
            with self.assertRaises(FetchError) as e:
                client.request('https://api.example.org/x', headers={'X-Subscription-Token': 'SECRETKEY123'})
        self.assertIn('bad country', str(e.exception))
        self.assertNotIn('SECRETKEY123', str(e.exception))
    def test_summer_from_month_ranges(self):
        for d in ('Internship period: June to August 2027.', '實習期間 2027 年 7 月～8 月', 'Jul - Sep 2027 in Tokyo'):
            r = classify(job(title='Software Intern', description=d), C)
            self.assertEqual((r['year'], r['season']), (2027, 'summer'), d)
        r = classify(job(title='Software Intern 2027', description='Start in July; six-month program.'), C)
        self.assertIsNone(r['season'])
    def test_classification_regexes(self):
        self.assertTrue(classify(job(title='Software Engineering Interns Summer 2027'), C)['internship'])
        self.assertEqual(classify(job(title='AIエンジニア インターン 2027 夏'), C)['category'], 'MLE_AI')
        self.assertIsNone(classify(job(title='Hardware Systems Engineer Intern Summer 2027'), C)['category'])
        self.assertIsNone(classify(job(title='Intern, Taipei office'), C)['category'])

class ReviewFixWorkflowTests(unittest.TestCase):
    setUp, tearDown, call = WorkflowTests.setUp, WorkflowTests.tearDown, WorkflowTests.call
    def test_close_survives_sync_and_auto_clears(self):
        jobs = []
        j, _ = upsert(jobs, job(), C)
        save(self.root/'data/jobs.json', jobs)
        self.assertEqual(self.call('close', j['id'], 'closed', '--reason', 'Recruiter said closed'), 0)
        with patch('tracker.__main__.detail', return_value=job()):
            self.call('check', '--force')
        self.assertEqual(load(self.root/'data/jobs.json')[0]['status'], 'closed')
        self.assertEqual(self.call('close', j['id'], 'auto', '--reason', 'Back to automatic'), 0)
        with patch('tracker.__main__.detail', return_value=job()):
            self.call('check', '--force')
        self.assertEqual(load(self.root/'data/jobs.json')[0]['status'], 'open')
    def test_check_survives_parser_errors(self):
        jobs = []
        upsert(jobs, job(), C)
        upsert(jobs, job(url='https://example.org/jobs/2'), C)
        save(self.root/'data/jobs.json', jobs)
        with patch('tracker.__main__.detail', side_effect=[TypeError('bad shape'), job(url='https://example.org/jobs/2')]):
            self.assertEqual(self.call('check', '--force'), 0)
        checks = load(self.root/'data/check-health.json')['checks']
        self.assertEqual(len(checks), 2)
        self.assertIn('bad shape', checks[0]['error'])
    def test_blocked_page_not_refetched_every_sync(self):
        save(self.root/'sources.json', [{'id':'c','type':'community','enabled':True,'url':'https://example.org/list.md'}])
        client = Mock(requests=1)
        client.request.return_value = (FIX/'community.md').read_text()
        with patch('tracker.__main__.Client', return_value=client), \
             patch('tracker.__main__.detail', side_effect=FetchError('robots.txt disallows page fetching')) as d:
            self.call('sync', '--no-search')
            first = d.call_count
            self.call('sync', '--no-search')
            self.assertGreater(first, 0)
            self.assertEqual(d.call_count, first)
    def test_board_lists_only_summer_internships_newest_first(self):
        jobs = []
        upsert(jobs, job(url='https://example.org/jobs/old', title='Old Software Intern Summer 2027', posted_at='2026-09-01'), C)
        upsert(jobs, job(url='https://example.org/jobs/new', title='New Software Intern Summer 2027', posted_at='2026-10-15T00:00:00Z'), C)
        upsert(jobs, job(url='https://example.org/jobs/jd', title='Backend Intern 2027', description='The internship runs June to August.'), C)
        upsert(jobs, job(url='https://example.org/jobs/long', title='Backend Intern - 2027', description='Minimum duration of 6 months.'), C)
        upsert(jobs, job(url='https://example.org/jobs/out', title='Software Intern Summer 2026'), C)
        save(self.root/'data/jobs.json', jobs)
        render(self.root, C)
        readme = (self.root/'README.md').read_text()
        self.assertIn('>Oct 15</td>', readme)
        self.assertLess(readme.index('New Software Intern'), readme.index('Old Software Intern'))
        self.assertIn('>↳</td>', readme)  # same company collapses like JobRadar
        self.assertIn('Backend Intern 2027', readme)  # summer read from the JD
        self.assertNotIn('Backend Intern - 2027', readme)  # unstated season stays off the list
        self.assertIn('Backend Intern - 2027', (self.root/'job-postings/not-summer.md').read_text())
        self.assertNotIn('Summer 2026', readme)
        self.assertFalse((self.root/'job-postings/review.md').exists())
    def test_zero_candidates_render_as_zero(self):
        save(self.root/'data/source-health.json', {'sources':[{'id':'rakuten','status':'ok','candidates':0,'error':''}]})
        render(self.root, C)
        self.assertIn('| rakuten | ok | 0 | — |', (self.root/'README.md').read_text())

if __name__ == '__main__':
    unittest.main()
