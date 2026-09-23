import json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dotenv import dotenv_values
from backend.local_config import configure_mini

class LocalConfigTests(unittest.TestCase):
    def test_private_atomic_key_write_preserves_limits_and_no_result_secret(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ):
            path=Path(root)/'.env'
            path.write_text('BEEAGENT_AI_BUDGET_USD=2\nOTHER_SETTING=keep\nBEEAGENT_INPUT_USD_PER_MILLION=999\n')
            dummy='sk-'+'not-a-real-key-'*2
            self.assertIsNone(configure_mini(root,dummy))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            values=dotenv_values(path)
            self.assertEqual(values['OPENAI_API_KEY'],dummy)
            self.assertEqual(values['OPENAI_MODEL'],'gpt-5.4-mini')
            self.assertEqual(values['BEEAGENT_AI_BUDGET_USD'],'2')
            self.assertEqual(values['OTHER_SETTING'],'keep')
            self.assertNotIn('BEEAGENT_INPUT_USD_PER_MILLION',values)
            self.assertEqual(list(Path(root).glob('.beeagent-config-*')),[])
            with self.assertRaisesRegex(ValueError,'без пробелов'):configure_mini(root,dummy+'\nX=1')
            self.assertEqual(dotenv_values(path)['OPENAI_API_KEY'],dummy)

    def test_symlink_does_not_change_target(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ):
            target=Path(root)/'target';target.write_text('preserve')
            (Path(root)/'.env').symlink_to(target)
            with self.assertRaises(ValueError):configure_mini(root,'sk-'+'not-a-real-key-'*2)
            self.assertEqual(target.read_text(),'preserve')

if __name__=='__main__':unittest.main()
