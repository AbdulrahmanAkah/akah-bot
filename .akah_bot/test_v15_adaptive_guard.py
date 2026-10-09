import unittest
import ctypes
import os
import subprocess
import sys
import time
from v15_adaptive_guard import decision,start_ready,descendant,MIB,launch_allowance
from v15_adaptive_guard import OwnedProcess,OwnedJob
from v15_resource_guard import resources


class Tests(unittest.TestCase):
    def test_launch_envelope_defaults_and_explicit_bootstrap(self):
        self.assertEqual(launch_allowance(192),192)
        self.assertEqual(launch_allowance(384,128),128)
        self.assertEqual(launch_allowance(192,128),128)
    def test_invalid_launch_envelope_cannot_relax_process_limit(self):
        for budget,launch in ((385,128),(15,16),(192,193),(192,15),(192,0)):
            with self.assertRaises(ValueError):launch_allowance(budget,launch)
    def test_bootstrap_envelope_does_not_change_live_reserves(self):
        sample={'available_physical_bytes':640*MIB,'commit_available_bytes':2048*MIB,
                'process_private_bytes':200*MIB,'process_rss_bytes':210*MIB}
        self.assertTrue(start_ready(sample,launch_allowance(384,128)))
        self.assertEqual(decision(sample,384),'RUN')
        self.assertEqual(decision(dict(sample,available_physical_bytes=511*MIB),384),'PAUSE')
        self.assertEqual(decision(dict(sample,commit_available_bytes=1023*MIB),384),'PAUSE')
        self.assertEqual(decision(dict(sample,process_private_bytes=385*MIB),384),'BUDGET_EXCEEDED')
    def test_same_reserve_smaller_memory_budget(self):
        sample={'available_physical_bytes':704*MIB,'commit_available_bytes':1216*MIB,'process_private_bytes':100*MIB}
        self.assertTrue(start_ready(sample,192));self.assertEqual(decision(sample,192),'RUN')
        low=dict(sample,available_physical_bytes=511*MIB)
        self.assertEqual(decision(low,192),'PAUSE')
        self.assertEqual(decision(low,192,paused=True),'WAIT')
        self.assertEqual(decision(sample,192,paused=True),'RESUME')
        self.assertFalse(start_ready(dict(sample,available_physical_bytes=703*MIB),192))
    def test_private_budget_not_softened_by_pause(self):
        sample={'available_physical_bytes':900*MIB,'commit_available_bytes':2048*MIB,'process_private_bytes':193*MIB}
        self.assertEqual(decision(sample,192),'BUDGET_EXCEEDED')
        self.assertEqual(decision(sample,192,paused=True),'BUDGET_EXCEEDED')
    def test_commit_pressure_pauses_instead_of_faking_success(self):
        sample={'available_physical_bytes':900*MIB,'commit_available_bytes':1023*MIB,'process_private_bytes':100*MIB}
        self.assertEqual(decision(sample,192),'PAUSE')
        self.assertEqual(decision(sample,192,paused=True),'WAIT')
    def test_resume_does_not_double_count_already_resident_memory(self):
        sample={'available_physical_bytes':520*MIB,'commit_available_bytes':1024*MIB,
                'process_private_bytes':85*MIB,'process_rss_bytes':100*MIB}
        self.assertEqual(decision(sample,192,True,resident_restore_bytes=100*MIB),'RESUME')
        self.assertEqual(decision(dict(sample,available_physical_bytes=511*MIB),192,True,
                                  resident_restore_bytes=100*MIB),'WAIT')
        self.assertEqual(decision(dict(sample,process_rss_bytes=10*MIB),192,True,
                                  resident_restore_bytes=100*MIB),'WAIT')
        self.assertEqual(decision(dict(sample,available_physical_bytes=603*MIB,process_rss_bytes=10*MIB),
                                  192,True,resident_restore_bytes=100*MIB),'RESUME')
    def test_ownership_requires_exact_child_ancestry(self):
        tree={1:(0,'guardian'),2:(1,'our launcher'),3:(2,'our real worker'),4:(0,'user application')}
        self.assertTrue(descendant(3,2,tree));self.assertFalse(descendant(4,2,tree))
        self.assertFalse(descendant(1,2,tree));self.assertFalse(descendant(999,2,tree))
        self.assertFalse(descendant(2,4,{2:(3,'x'),3:(2,'y')}))
    def test_actual_unowned_process_refused(self):
        with self.assertRaisesRegex(RuntimeError,'REFUSE_UNOWNED'):
            OwnedProcess(os.getpid(),0,os.getpid())
    def test_native_observer_does_not_leak_ctypes_pointer_classes(self):
        resources()
        before=len(ctypes._pointer_type_cache)
        for _ in range(2000):
            self.assertGreater(resources()['total_physical_bytes'],0)
        self.assertEqual(len(ctypes._pointer_type_cache),before)
    def test_job_loss_terminates_only_owned_suspended_child(self):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],
            creationflags=subprocess.CREATE_NO_WINDOW)
        owned=OwnedProcess(child.pid,child.pid,os.getpid());job=OwnedJob()
        try:
            began=time.monotonic()
            job.assign(owned);owned.suspend();job.close()
            # Windows can report exit code zero for kill-on-job-close. An OS
            # exit and elapsed time shorter than the 30s payload prove kill;
            # success/failure code is not the lifetime test's estimand.
            child.wait(timeout=10)
            self.assertLess(time.monotonic()-began,10)
            self.assertFalse(owned.alive())
        finally:
            job.close();owned.stop_failed(76);owned.close()


if __name__=='__main__':unittest.main()
