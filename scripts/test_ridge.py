"""Check recursion, raw-unit feedback, and training-only scaling."""
import unittest
import numpy as np
from train_ridge import fit_model, rollout, load_design, CUTOFF, LAG


class SumModel:
    def predict(self, x):
        return x.sum(axis=1)


class RidgeTests(unittest.TestCase):
    def test_hand_computable_recursive_feedback(self):
        x = np.array([[1., 2.], [2., 3.]])
        original = x.copy()
        np.testing.assert_array_equal(rollout(SumModel(), x, 3), [[3, 5, 8], [5, 8, 13]])
        np.testing.assert_array_equal(x, original)

    def test_scaling_fitted_only_on_training(self):
        x = np.array([[1., 10.], [2., 20.], [3., 30.], [4., 40.]])
        model = fit_model(x, np.array([2., 4., 6., 8.]), 1.)
        scaler = model.named_steps['standardscaler']
        before = scaler.mean_.copy()
        np.testing.assert_allclose(before, [2.5, 25.])
        model.predict(np.array([[1000., 2000.]]))
        np.testing.assert_array_equal(before, scaler.mean_)
        self.assertEqual(scaler.n_samples_seen_, 4)

    def test_rollout_matches_manual_raw_feedback(self):
        x = np.array([[1., 2.], [2., 4.], [4., 8.], [8., 16.]])
        model = fit_model(x, np.array([4., 8., 16., 32.]), 1.)
        first = model.predict([[8., 16.]])[0]
        second = model.predict([[16., first]])[0]
        np.testing.assert_allclose(rollout(model, [8., 16.], 2), [[first, second]])

    def test_date_boundaries_and_common_sample(self):
        _, _, close, sessions, origins, fitting, training, xv = load_design()
        self.assertEqual(len(origins), 1240)
        self.assertEqual(xv.shape, (1240, LAG))
        self.assertLessEqual(max(close).year, 2020)
        for h, indices in fitting.items():
            self.assertTrue(all(sessions[i+h] <= CUTOFF for i in indices))
            self.assertEqual(training[h][0].shape[1], LAG)


if __name__ == '__main__':
    unittest.main()
