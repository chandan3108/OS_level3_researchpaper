import csv,hashlib,json,math,unittest
from pathlib import Path
from website.demo_service import ROOT,DEFAULT,validate_run,validate_context,run_experiment,replay,build_payload

class WebsiteChecks(unittest.TestCase):
    def test_invalid_runs_are_rejected_before_execution(self):
        for bad in ({'seed':True},{'seed':-1},{'seed':200.5},{'repeats':1000},{'profile':'measured_mac'},{'scenario':'invented'}):
            with self.assertRaises(ValueError):validate_run(bad)

    def test_published_conditions_and_all_strategies_are_present(self):
        data=build_payload();self.assertEqual(len(data['cases']),44)
        for record in data['cases'].values():
            self.assertEqual(len(record['aggregates']),7);self.assertEqual(len(record['pairs']),6)
            self.assertEqual(record['n'],20);self.assertEqual(record['seeds'],list(range(200,220)))
        self.assertEqual(sum(len(c['family']) for c in data['cases'].values()),8)

    def test_one_run_uses_all_seven_controllers_and_matched_inputs(self):
        progress=[]
        result,rows=run_experiment(dict(DEFAULT,seed=200,repeats=1),lambda done,total:progress.append((done,total)))
        self.assertEqual((len(rows),result['n'],result['policy_evaluations']),(7,1,7))
        self.assertEqual(progress,[(1,1)])
        for field in ('task_sha256','estimate_sha256','calibration_sha256','shared_config_sha256'):
            self.assertEqual(len({row[field] for row in rows}),1)
        self.assertTrue(all(p['estimated_j_per_task_delta_ci_low'] is None for p in result['pairs']))

    def test_replay_matches_paper_seed_and_preserves_energy_window(self):
        data=replay(DEFAULT)
        with (ROOT/'results/periodic/runs.csv').open() as f:raw=list(csv.DictReader(f))
        for method,trace in data['traces'].items():
            r=next(r for r in raw if r['seed']=='200' and r['controller']==method and all(r[k]==v for k,v in DEFAULT.items()))
            self.assertAlmostEqual(trace['result']['estimated_j_per_task'],float(r['estimated_j_per_task']))
            self.assertEqual(trace['states'][-1]['time_s'],40)
            self.assertAlmostEqual(trace['states'][-1]['energy_j'],float(r['estimated_energy_j']))
            self.assertTrue(all(a['time_s']<=b['time_s'] for a,b in zip(trace['states'],trace['states'][1:])))

    def test_batch_replay_has_exact_completion_boundaries(self):
        data=replay(DEFAULT,baseline='periodic_5');obs=data['traces']['periodic_5']['observations']
        for i,o in enumerate(obs,1):self.assertEqual(o['applied'],i%5==0)

    def test_zero_cost_new_condition_is_not_falsely_published(self):
        c=dict(DEFAULT,scenario='noise',overhead='zero_cost');result,rows=run_experiment(dict(c,seed=200,repeats=1))
        self.assertEqual(result['source'],'new_python')
        self.assertTrue(all(r['overhead_time_s']==0 for r in rows))

    def test_twenty_seed_means_reproduce_primary_paper_condition(self):
        result,rows=run_experiment(dict(DEFAULT,seed=200,repeats=20))
        with (ROOT/'results/periodic/aggregates.csv').open() as f:saved=list(csv.DictReader(f))
        for a in result['aggregates']:
            old=next(r for r in saved if r['controller']==a['controller'] and all(r[k]==v for k,v in DEFAULT.items()))
            for metric in ('estimated_j_per_task_mean','deadline_miss_pct_mean','overhead_time_s_mean','correction_updates_mean'):
                self.assertAlmostEqual(a[metric],float(old[metric]),places=11)
        self.assertEqual(len(rows),140)

if __name__=='__main__':unittest.main()
