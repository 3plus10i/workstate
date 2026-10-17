from contextlib import ExitStack
from unittest.mock import MagicMock, patch
import winreg

from workstate.desktop import Desktop
from workstate.service import Service
from test_core import RepositoryFixture


class StartupRenameTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.service = Service(self.repo)
        self.addCleanup(self.service.close)
        self.desktop = Desktop(self.service)
        self.entries = {}
        self.command = '"D:\\New\\WorkState.exe" --background --data-dir "D:\\Data"'
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.desktop,'_startup_command',return_value=self.command))
        self.stack.enter_context(patch.object(winreg,'OpenKey',return_value=MagicMock()))
        self.stack.enter_context(patch.object(winreg,'CreateKey',return_value=MagicMock()))
        self.stack.enter_context(patch.object(winreg,'QueryValueEx',side_effect=self.query))
        self.stack.enter_context(patch.object(winreg,'SetValueEx',side_effect=lambda key,name,reserved,kind,value:self.entries.__setitem__(name,value)))
        self.stack.enter_context(patch.object(winreg,'DeleteValue',side_effect=self.delete))

    def query(self,key,name):
        if name not in self.entries:
            raise FileNotFoundError(name)
        return self.entries[name],winreg.REG_SZ

    def delete(self,key,name):
        if name not in self.entries:
            raise FileNotFoundError(name)
        del self.entries[name]

    def test_enabling_new_name_replaces_known_previous_executable(self):
        self.entries['PCState'] = '"D:\\Old\\PCState.exe" --background'
        self.desktop.set_startup(True)
        self.assertEqual(self.entries,{'WorkState':self.command})
        self.assertTrue(self.desktop.startup_enabled())

    def test_disabling_old_key_for_current_command_works(self):
        self.entries['PCState'] = self.command
        self.assertTrue(self.desktop.startup_enabled())
        self.desktop.set_startup(False)
        self.assertEqual(self.entries,{})
        self.assertFalse(self.desktop.startup_enabled())

    def test_unrelated_old_entry_is_not_removed(self):
        unrelated = '"D:\\Other\\Other.exe"'
        self.entries['PCState'] = unrelated
        self.desktop.set_startup(True)
        self.assertEqual(self.entries,{'WorkState':self.command,'PCState':unrelated})
        self.desktop.set_startup(False)
        self.assertEqual(self.entries,{'PCState':unrelated})
