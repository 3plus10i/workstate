import json
from datetime import date, timedelta

from workstate.classification import classify
from workstate.paths import default_data_directory
from workstate.report import build_report
from workstate.service import Service
from workstate.settings import DEFAULT_PROGRAMS, validate_settings
from test_core import RepositoryFixture


class ProgramListTests(RepositoryFixture):
    def test_one_note_titles_and_explicit_opt_out(self):
        settings = self.repo.settings()
        for title in ('研究计划 - OneNote', '研究计划 - Microsoft OneNote', '研究计划 – OneNote'):
            identity = classify('ONENOTE.EXE', title, settings)
            self.assertEqual((identity.context, identity.kind), ('研究计划', 'document'))
        self.assertEqual(classify('ONENOTE.EXE', 'OneNote', settings).context, '')
        settings['documentProcesses'].remove('onenote')
        self.assertEqual(classify('ONENOTE.EXE', '研究计划 - OneNote', settings).context, '')
        settings['documentProcesses'].append('onenote')
        settings['splitDocuments'] = False
        self.assertEqual(classify('ONENOTE.EXE', '研究计划 - OneNote', settings).context, '')

    def test_removed_defaults_stay_removed_after_save_and_reopen(self):
        saved = self.repo.save_settings({'ideProcesses': [], 'documentProcesses': ['onenote'], 'browserProcesses': []})
        reopened = type(self.repo)(self.test_directory).settings()
        self.assertEqual(saved, reopened)
        self.assertEqual(reopened['ideProcesses'], [])
        self.assertEqual(reopened['documentProcesses'], ['onenote'])
        self.assertEqual(reopened['browserProcesses'], [])
        for process, title in [('Code.exe','x.py - Project - VSCode'),('winword.exe','report - Word'),('chrome.exe','GitHub - Google Chrome')]:
            self.assertEqual(classify(process,title,reopened).context, '')

    def test_category_can_be_changed_but_not_duplicated(self):
        settings = validate_settings({'ideProcesses': [], 'browserProcesses': ['CODE.exe']})
        identity = classify('Code.exe', 'GitHub - Code', settings)
        self.assertEqual((identity.context, identity.kind), ('GitHub', 'site'))
        with self.assertRaises(ValueError):
            validate_settings({'browserProcesses': ['CODE.exe']})

    def test_old_custom_lists_upgrade_once_and_keep_existing_preferences(self):
        old = {'customIdeProcesses':['Trae'], 'customDocumentProcesses':['wps'], 'customBrowserProcesses':['brave'],
               'detailThreshold':25, 'displayNames':{'code':'我的编辑器'}}
        with self.repo.connect() as db:
            db.execute("INSERT INTO settings VALUES ('preferences', ?)",(json.dumps(old),))
        settings = self.repo.settings()
        self.assertEqual(settings['ideProcesses'],DEFAULT_PROGRAMS['ideProcesses']+['trae'])
        self.assertEqual(settings['documentProcesses'],DEFAULT_PROGRAMS['documentProcesses']+['wps'])
        self.assertEqual(settings['browserProcesses'],DEFAULT_PROGRAMS['browserProcesses']+['brave'])
        self.assertEqual(settings['detailThreshold'],25)
        self.assertEqual(settings['displayNames']['code'],'我的编辑器')
        self.assertEqual(settings['displayNames']['workstate'],'WorkState')
        self.assertEqual(settings['displayNames']['onenote'],'Microsoft OneNote')
        settings['ideProcesses'] = []
        self.repo.save_settings(settings)
        self.assertEqual(self.repo.settings()['ideProcesses'],[])
        self.assertFalse(any(key.startswith('custom') for key in self.repo.settings()))

    def test_default_lists_are_independent_from_user_lists(self):
        first = validate_settings({})
        first['documentProcesses'].clear()
        second = validate_settings({})
        self.assertEqual(second['documentProcesses'],['winword','excel','powerpnt','onenote'])
        bootstrap = Service(self.repo).dispatch('bootstrap')['data']
        self.assertEqual(bootstrap['programDefaults'],DEFAULT_PROGRAMS)

    def test_onenote_threshold_remains_strictly_daily(self):
        day = date(2026,8,20)
        self.put(day,16,process='ONENOTE.EXE',title='研究计划 - OneNote')
        self.put(day+timedelta(days=1),15,process='ONENOTE.EXE',title='研究计划 - OneNote')
        result = build_report(self.repo,day.isoformat(),(day+timedelta(days=1)).isoformat(),True)
        self.assertEqual(result['summary']['activeMinutes'],31)
        self.assertEqual(sorted((app['context'],app['minutes']) for app in result['apps']),[('',15),('研究计划',16)])


class DataDirectoryTests(RepositoryFixture):
    def test_new_install_and_demo_use_workstate(self):
        self.assertEqual(default_data_directory(self.test_directory),self.test_directory/'WorkState'/'data')
        self.assertEqual(default_data_directory(self.test_directory,True),self.test_directory/'WorkState'/'demo')

    def test_existing_records_are_reused_and_current_folder_takes_priority(self):
        previous = self.test_directory/'PCState'/'data'
        previous.mkdir(parents=True)
        (previous/'activity.sqlite3').write_bytes(b'old fixture')
        self.assertEqual(default_data_directory(self.test_directory),previous)
        self.assertEqual(default_data_directory(self.test_directory,True),self.test_directory/'WorkState'/'demo')
        current = self.test_directory/'WorkState'/'data'
        current.mkdir(parents=True)
        (current/'activity.sqlite3').write_bytes(b'current fixture')
        self.assertEqual(default_data_directory(self.test_directory),current)
