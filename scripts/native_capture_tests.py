"""Readiness command contracts; mocked values are not native capture evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import exclusive_native_acceptance as native

class NativeCaptureReadiness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.png'
        self.driver = Mock()
        self.driver.call.return_value = {'ready': True, 'visibility': 'visible', 'width': 1280, 'height': 800}
    def test_observes_fonts_and_two_frames_before_exactly_one_capture(self):
        trace=[]
        self.driver.call.side_effect=lambda *a: (trace.append('barrier') or {'ready':True,'visibility':'visible','width':1280,'height':800})
        self.driver.screenshot.side_effect=lambda *a:trace.append('capture')
        native.capture_rendered(self.driver,self.path)
        self.assertEqual(trace,['barrier','capture'])
        call=self.driver.call.call_args
        self.assertEqual(call.args[0],'execute/async')
        script=call.args[1]['script']
        self.assertIn('document.fonts?.ready',script)
        self.assertEqual(script.count('requestAnimationFrame('),2)
        self.assertIn('5000',script)
        for forbidden in ('.click(','.invoke(','.focus(','.scroll', 'setAttribute('):self.assertNotIn(forbidden,script)
        self.driver.screenshot.assert_called_once_with(self.path)
    def test_hidden_or_invalid_viewport_never_captures(self):
        for fields in ({'visibility':'hidden'},{'width':0},{'height':False},{'width':'1280'},{'ready':'true'}):
            self.driver.call.return_value={'ready':True,'visibility':'visible','width':1280,'height':800,**fields}
            with self.subTest(fields=fields),self.assertRaises(AssertionError):native.capture_rendered(self.driver,self.path)
        self.driver.screenshot.assert_not_called()
    def test_bounded_barrier_timeout_never_captures(self):
        self.driver.call.return_value={'ready':False,'visibility':'visible','width':1280,'height':800}
        with self.assertRaises(AssertionError):native.capture_rendered(self.driver,self.path)
        self.driver.call.assert_called_once();self.driver.screenshot.assert_not_called()
    def test_driver_failure_is_propagated_without_replay(self):
        self.driver.call.side_effect=TimeoutError('native script timed out')
        with self.assertRaises(TimeoutError):native.capture_rendered(self.driver,self.path)
        self.driver.call.assert_called_once();self.driver.screenshot.assert_not_called()
    def test_invalid_screenshot_is_not_retried(self):
        self.driver.screenshot.side_effect=AssertionError('native screenshot is missing or invalid')
        with self.assertRaises(AssertionError):native.capture_rendered(self.driver,self.path)
        self.driver.screenshot.assert_called_once()
    def test_diagnostics_exclude_page_text_and_credentials(self):
        self.driver.call.return_value.update(page_text='synthetic-secret-not-to-export')
        native.capture_rendered(self.driver,self.path)
        value=json.loads(self.path.with_suffix('.capture.json').read_text())
        self.assertEqual(set(value),{'ready','visibility','width','height'})
    def test_initial_settings_capture_uses_barrier_not_direct_capture(self):
        source=Path(native.__file__).read_text()
        self.assertIn("capture_rendered(session, output / 'native-session-settings.png')",source)
        self.assertNotIn("session.screenshot(output / 'native-session-settings.png')",source)

if __name__=='__main__':unittest.main(verbosity=2)
