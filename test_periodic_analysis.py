import unittest
from analyze_periodic_study import directional_test,holm_adjust
from check_current_feasibility import exact_edf
from calibrated_study import Task

class PeriodicAnalysisChecks(unittest.TestCase):
    def test_all_ties_receive_p_one_and_zero_nonzero_n(self):
        r=directional_test([0.]*20)
        self.assertEqual((r['sign_p'],r['nonzero_n'],r['tied_n']),(1.,0,20))

    def test_exact_direction_and_ties(self):
        r=directional_test([-1.]*20)
        self.assertAlmostEqual(r['sign_p'],1/2**20)
        self.assertEqual(directional_test([1.]*20)['sign_p'],1.)
        r=directional_test([-1.,-1.,0.]);self.assertEqual(r['sign_p'],.25)
        self.assertEqual(r['tied_n'],1)

    def test_holm_includes_all_endpoints_and_is_monotone(self):
        self.assertEqual(holm_adjust([.01,.04,.03]),[.03,.06,.06])
        self.assertEqual(holm_adjust([1.]*8),[1.]*8)
        self.assertAlmostEqual(holm_adjust([1/2**20]*8)[0],8/2**20)

    def test_event_edf_handles_preemption_and_infeasibility(self):
        feasible=(Task(0,.1,.05),Task(.01,.03,.01))
        self.assertEqual(exact_edf(feasible)['missed_tasks'],0)
        self.assertEqual(exact_edf((Task(0,.01,.02),))['missed_tasks'],1)

if __name__=='__main__':unittest.main()
