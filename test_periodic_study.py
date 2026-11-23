import math,unittest
from dataclasses import asdict,replace
import calibrated_study as old
from periodic_study import Correction,Settings,Task,simulate
from run_calibrated_study import calibration,workload,config

class PeriodicChecks(unittest.TestCase):
    def test_batch_updates_only_at_declared_completion_boundary(self):
        c=Correction('periodic_5',1.)
        for _ in range(4):c.observe_completion(2.,1.,.2)
        self.assertEqual(c.gain,1.);self.assertEqual(c.updates,0)
        c.observe_completion(2.,1.,.2)
        self.assertEqual(c.gain,2.);self.assertEqual(c.updates,1)
        self.assertEqual(c.completed,5);self.assertEqual(c.batch,[])

    def test_nonoverlapping_batch_replaces_old_batch(self):
        c=Correction('periodic_5',1.)
        for ratio in [2.]*5+[.5]*5:c.observe_completion(ratio,1.,.2)
        self.assertEqual(c.gain,.5);self.assertEqual(c.updates,2)

    def test_rolling_window_uses_only_latest_twenty_completed_ratios(self):
        c=Correction('rolling_20',1.,[{'observed_work':1.,'estimate':1.} for _ in range(20)])
        c.observe_completion(2.,1.,.2);self.assertAlmostEqual(c.gain,1.05)
        for _ in range(19):c.observe_completion(2.,1.,.2)
        self.assertEqual(c.gain,2.);self.assertEqual(len(c.window),20)

    def test_clipping_and_incomplete_batch(self):
        c=Correction('periodic_5',1.)
        for _ in range(5):c.observe_completion(10.,1.,.2)
        self.assertEqual(c.gain,2.)
        for _ in range(4):c.observe_completion(.1,1.,.2)
        self.assertEqual(c.gain,2.)
        c.observe_completion(.1,1.,.2);self.assertEqual(c.gain,.5)

    def test_split_cost_including_final_empty_queue(self):
        tasks=tuple(Task(i*.1,i*.1+.1,.01) for i in range(5))
        cfg=Settings(seconds=.5,horizon_s=1,protection_enabled=False,decision_cost_s=0,switch_cost_s=0,
                     completion_observation_cost_s=.002,recalibration_application_cost_s=.003)
        result,_=simulate('periodic_5',tasks,cfg)
        self.assertAlmostEqual(result['overhead_time_s'],5*.002+.003)
        self.assertEqual(result['correction_updates'],1)
        self.assertEqual(result['tasks'],5)

    def test_prior_static_and_feedback_exactly_reproduce(self):
        tasks,estimates=workload(202,'bursty','high_to_low',seconds=2.)
        gain,history=calibration(202,'high_to_low')
        for profile in ('generic','apple_inspired'):
            cfg=replace(config(profile,'ordinary','modeled_cost',gain),seconds=2,horizon_s=4)
            for method,policy in [('calibrated_feedback','feedback'),('calibrated_static','guard'),('legacy_guard','guard')]:
                original=replace(cfg,guard_gain=(1/.7 if method=='legacy_guard' else gain))
                a,_=old.simulate(policy,tasks,original,estimates)
                b,_=simulate(method,tasks,Settings(**asdict(cfg)),estimates,history)
                for key,value in a.items():self.assertEqual(value,b[key],(profile,method,key))

    def test_gain_does_not_change_before_completion_or_partial_batch(self):
        result,trace=simulate('periodic_5',(Task(0,.1,.02),),
                              Settings(seconds=.1,horizon_s=1),(.01,),record_trace=True)
        self.assertEqual(result['correction_updates'],0)
        self.assertEqual(result['feedback_gain_final'],1.)
        self.assertTrue(all(t['feedback_gain']==1. for t in trace))

    def test_invalid_configuration_or_missing_history(self):
        with self.assertRaises(ValueError):Settings(completion_observation_cost_s=-1).validate()
        with self.assertRaises(ValueError):Correction('rolling_20',1.,[])
        with self.assertRaises(ValueError):Settings(recalibration_application_cost_s=math.nan).validate()

if __name__=='__main__':unittest.main()
