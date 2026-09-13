"""Deterministic W3C command-boundary contracts, not installed GUI evidence."""
from __future__ import annotations
import unittest
from unittest.mock import patch
import exclusive_native_acceptance as native

ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'

class Driver:
    def __init__(self, enabled=(True,), *, click_error=False, settle=0):
        self.enabled = list(enabled)
        self.index = 0
        self.last_enabled = enabled[0]
        self.trace = []
        self.clicked = 0
        self.effective = False
        self.click_error = click_error
        self.settle = settle
    def call(self, path, data=None):
        self.trace.append(path)
        if path == 'element':
            assert data['using'] == 'xpath' and '撤销全部' in data['value']
            return {ELEMENT: 'revoke-button'}
        if path == 'element/revoke-button/enabled':
            self.last_enabled = self.enabled[min(self.index, len(self.enabled)-1)]
            self.index += 1
            return self.last_enabled
        if path == 'element/revoke-button/click':
            self.clicked += 1
            if self.click_error: raise RuntimeError('native click transport failed')
            # Native click delivery to a disabled button need not run its handler.
            self.effective = self.last_enabled is True
            return None
        raise AssertionError('unexpected driver operation: ' + path)
    def status(self):
        if self.effective and self.settle == 0:
            return {'records':[{'status':'revoked'}], 'lease_state':'draining'}
        if self.effective: self.settle -= 1
        return {'records':[{'status':'active'}], 'lease_state':'active'}


def bounded_observe(fetch, predicate=bool, timeout=30):
    # No sleeps in contracts; production retains its original bounded wait.
    for _ in range(5):
        value = fetch()
        if predicate(value): return value
    raise AssertionError('read-only readiness/completion did not settle')

class NativeRevokeReadiness(unittest.TestCase):
    def invoke(self, driver):
        with patch.object(native, 'visit'), \
             patch.object(native.gui, 'wait_for', side_effect=bounded_observe), \
             patch.object(native, 'status', side_effect=lambda *a: driver.status()):
            native.revoke(driver, {'id':'synthetic-profile'})
    def test_disabled_loading_state_is_read_before_the_only_click(self):
        driver=Driver((False,False,True));self.invoke(driver)
        self.assertEqual(driver.clicked,1)
        self.assertEqual(driver.index,3)
        self.assertEqual(driver.trace[-1],'element/revoke-button/click')
    def test_permanently_disabled_never_receives_a_click(self):
        driver=Driver((False,))
        with self.assertRaises(AssertionError): self.invoke(driver)
        self.assertEqual(driver.clicked,0)
    def test_non_boolean_enabled_is_not_readiness(self):
        driver=Driver(('true',1,True));self.invoke(driver)
        self.assertEqual(driver.index,3);self.assertEqual(driver.clicked,1)
    def test_enabled_control_is_clicked_once_then_status_is_observed(self):
        driver=Driver((True,),settle=2);self.invoke(driver)
        self.assertEqual(driver.clicked,1);self.assertEqual(driver.index,1)
        self.assertEqual(driver.settle,0)
    def test_click_failure_is_never_retried_or_suppressed(self):
        driver=Driver((True,),click_error=True)
        with self.assertRaisesRegex(RuntimeError,'native click transport failed'): self.invoke(driver)
        self.assertEqual(driver.clicked,1)
    def test_no_effective_revoke_is_not_reported_as_success(self):
        driver=Driver((True,),settle=10)
        with self.assertRaises(AssertionError): self.invoke(driver)
        self.assertEqual(driver.clicked,1)

if __name__=='__main__':unittest.main(verbosity=2)
