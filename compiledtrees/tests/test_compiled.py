from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from sklearn import ensemble, tree
from compiledtrees.compiled import CompiledRegressionPredictor, CompiledClassifierPredictor
from sklearn.utils.testing import \
    assert_array_almost_equal, assert_raises, assert_equal, assert_allclose, \
    assert_array_equal
import numpy as np
import unittest
import tempfile
import pickle
from six.moves import cPickle, zip

REGRESSORS = {
    ensemble.GradientBoostingRegressor,
    ensemble.RandomForestRegressor,
    tree.DecisionTreeRegressor,
}

UNSUPPORTED_CLASSIFIERS = {
    ensemble.GradientBoostingClassifier,
}

CLASSIFIERS = {
    ensemble.RandomForestClassifier,
    tree.DecisionTreeClassifier,
}


def pairwise(iterable):
    import itertools
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def assert_equal_predictions(cls, X, y, kind='regressor'):
    clf = cls()
    clf.fit(X, y)
    if kind == 'regressor':
        compiled = CompiledRegressionPredictor(clf)
    elif kind == 'classifier':
        compiled = CompiledClassifierPredictor(clf)
    else:
        raise ValueError('Unsupported type "%s"' % kind)

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        pickle.dump(compiled, tf)
    depickled = pickle.load(open(tf.name, 'rb'))

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        pickle.dump(depickled, tf)
    dedepickled = pickle.load(open(tf.name, 'rb'))

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        cPickle.dump(compiled, tf)
    decpickled = cPickle.load(open(tf.name, 'rb'))

    predictors = [clf, compiled, depickled, decpickled, dedepickled]
    predictions = [p.predict(X) for p in predictors]
    # test predictions for single samples
    if kind == 'classifier':
        single_predictions = []
        for p in predictors:
            tmp = [p.predict(x.reshape(1, -1)) for x in X]
            single_predictions.append(np.vstack(tmp))
    for (p1, p2) in pairwise(predictions):
        assert_array_almost_equal(p1, p2, decimal=10)


class TestCompiledTreesClassifier(unittest.TestCase):
    def test_rejects_unfitted_classifiers_as_compilable(self):
        for cls in CLASSIFIERS:
            assert_equal(CompiledClassifierPredictor.compilable(cls()), False)
            assert_raises(ValueError, CompiledRegressionPredictor, cls())

    def test_rejects_regressors_as_compilable(self):
        for cls in REGRESSORS | UNSUPPORTED_CLASSIFIERS:
            assert_equal(CompiledClassifierPredictor.compilable(cls()), False)
            assert_raises(ValueError, CompiledRegressionPredictor, cls())

    def test_correct_predictions(self):
        num_features = 20
        num_examples = 1000
        num_classes = 4
        X = np.random.normal(size=(num_examples, num_features))
        X = X.astype(np.float32)
        y = np.random.randint(0, num_classes, size=num_examples)
        for cls in CLASSIFIERS:
            assert_equal_predictions(cls, X, y, kind='classifier')

    def test_few_compiled(self):
        num_features = 20
        num_examples = 1000
        num_classes = 4

        X1 = np.random.normal(size=(num_examples, num_features))
        X1 = X1.astype(np.float32)
        y1 = np.random.randint(0, num_classes, size=num_examples)

        X2 = np.random.normal(size=(num_examples, num_features))
        X2 = X2.astype(np.float32)
        y2 = np.random.randint(0, num_classes, size=num_examples)

        rf1 = ensemble.RandomForestClassifier()
        rf1.fit(X1, y1)

        rf2 = ensemble.RandomForestClassifier()
        rf2.fit(X2, y2)

        rf1_compiled = CompiledClassifierPredictor(rf1)
        rf2_compiled = CompiledClassifierPredictor(rf2)

        assert_array_almost_equal(rf1.predict(X1), rf1_compiled.predict(X1), decimal=10)
        assert_array_almost_equal(rf2.predict(X2), rf2_compiled.predict(X2), decimal=10)

    def test_many_trees(self):
        num_features = 20
        num_examples = 1000
        num_classes = 4

        X1 = np.random.normal(size=(num_examples, num_features))
        X1 = X1.astype(np.float32)
        y1 = np.random.randint(0, num_classes, size=num_examples)

        rf1 = ensemble.RandomForestClassifier(n_estimators=500, max_depth=2)
        rf1.fit(X1, y1)

        rf1_compiled = CompiledClassifierPredictor(rf1)
        assert_array_almost_equal(rf1.predict(X1), rf1_compiled.predict(X1), decimal=10)

    def test_predictions_with_invalid_input(self):
        num_features = 100
        num_examples = 100
        num_classes = 4

        X = np.random.normal(size=(num_examples, num_features))
        X = X.astype(np.float32)
        y = np.random.choice([-1, 1], size=num_examples)

        for cls in CLASSIFIERS:
            clf = cls()
            clf.fit(X, y)
            compiled = CompiledClassifierPredictor(clf)
            assert_raises(ValueError, compiled.predict,
                          np.resize(X, (1, num_features, num_features)))
            assert_allclose(compiled.score(X, y), clf.score(X, y))

    def test_float32_and_float_64_predictions_are_equal(self):
        num_features = 100
        num_examples = 100
        num_classes = 4

        X = np.random.normal(size=(num_features, num_examples))
        X_32 = X.astype(np.float32)
        X_64 = X.astype(np.float64)
        y = np.random.randint(0, num_classes, size=num_examples)

        # fit on X_32
        rf = ensemble.RandomForestClassifier()
        rf.fit(X_32, y)
        rf = CompiledClassifierPredictor(rf)

        assert_array_equal(rf.predict(X_32), rf.predict(X_64))

        # fit on X_64
        rf = ensemble.RandomForestClassifier()
        rf.fit(X_64, y)
        rf = CompiledClassifierPredictor(rf)

        assert_array_equal(rf.predict(X_32), rf.predict(X_64))

    def test_predictions_with_non_contiguous_input(self):
        num_features = 100
        num_examples = 100
        num_classes = 4

        X_non_contiguous = np.random.normal(size=(num_features, num_examples)).T
        X_non_contiguous = X_non_contiguous.astype(np.float32)
        self.assertFalse(X_non_contiguous.flags['C_CONTIGUOUS'])

        y = np.random.randint(0, num_classes, size=num_examples)

        rf = ensemble.RandomForestClassifier()
        rf.fit(X_non_contiguous, y)
        rf_compiled = CompiledClassifierPredictor(rf)

        try:
            rf_compiled.predict(X_non_contiguous)
        except ValueError as e:
            self.fail("predict(X) raised ValueError")

        X_contiguous = np.ascontiguousarray(X_non_contiguous)
        self.assertTrue(X_contiguous.flags['C_CONTIGUOUS'])
        assert_array_equal(rf_compiled.predict(X_non_contiguous), rf_compiled.predict(X_contiguous))


class TestCompiledTrees(unittest.TestCase):
    def test_rejects_unfitted_regressors_as_compilable(self):
        for cls in REGRESSORS:
            assert_equal(CompiledRegressionPredictor.compilable(cls()), False)
            assert_raises(ValueError, CompiledRegressionPredictor, cls())

    def test_rejects_classifiers_as_compilable(self):
        for cls in CLASSIFIERS | UNSUPPORTED_CLASSIFIERS:
            assert_equal(CompiledRegressionPredictor.compilable(cls()), False)
            assert_raises(ValueError, CompiledRegressionPredictor, cls())

    def test_correct_predictions(self):
        num_features = 20
        num_examples = 1000
        X = np.random.normal(size=(num_examples, num_features))
        X = X.astype(np.float32)
        y = np.random.normal(size=num_examples)
        for cls in REGRESSORS:
            assert_equal_predictions(cls, X, y)
        y = np.random.choice([-1, 1], size=num_examples)
        for cls in REGRESSORS:
            assert_equal_predictions(cls, X, y)

    def test_few_compiled(self):
        num_features = 20
        num_examples = 1000

        X1 = np.random.normal(size=(num_examples, num_features))
        X1 = X1.astype(np.float32)
        y1 = np.random.normal(size=num_examples)

        X2 = np.random.normal(size=(num_examples, num_features))
        X2 = X2.astype(np.float32)
        y2 = np.random.normal(size=num_examples)

        rf1 = ensemble.RandomForestRegressor()
        rf1.fit(X1,y1)

        rf2 = ensemble.RandomForestRegressor()
        rf2.fit(X2,y2)

        rf1_compiled = CompiledRegressionPredictor(rf1)
        rf2_compiled = CompiledRegressionPredictor(rf2)

        assert_array_almost_equal(rf1.predict(X1), rf1_compiled.predict(X1), decimal=10)
        assert_array_almost_equal(rf2.predict(X2), rf2_compiled.predict(X2), decimal=10)

    def test_many_trees(self):
        num_features = 20
        num_examples = 1000

        X1 = np.random.normal(size=(num_examples, num_features))
        X1 = X1.astype(np.float32)
        y1 = np.random.normal(size=num_examples)

        rf1 = ensemble.RandomForestRegressor(n_estimators=500, max_depth=2)
        rf1.fit(X1,y1)

        rf1_compiled = CompiledRegressionPredictor(rf1)
        assert_array_almost_equal(rf1.predict(X1), rf1_compiled.predict(X1), decimal=10)

    def test_predictions_with_invalid_input(self):
        num_features = 100
        num_examples = 100
        X = np.random.normal(size=(num_examples, num_features))
        X = X.astype(np.float32)
        y = np.random.choice([-1, 1], size=num_examples)

        for cls in REGRESSORS:
            clf = cls()
            clf.fit(X, y)
            compiled = CompiledRegressionPredictor(clf)
            assert_raises(ValueError, compiled.predict,
                          np.resize(X, (1, num_features, num_features)))
            assert_allclose(compiled.score(X, y), clf.score(X, y))

    def test_float32_and_float_64_predictions_are_equal(self):
        num_features = 100
        num_examples = 100

        X = np.random.normal(size=(num_features, num_examples))
        X_32 = X.astype(np.float32)
        X_64 = X.astype(np.float64)
        y = np.random.normal(size=num_examples)

        # fit on X_32
        rf = ensemble.RandomForestRegressor()
        rf.fit(X_32, y)
        rf = CompiledRegressionPredictor(rf)

        assert_array_equal(rf.predict(X_32), rf.predict(X_64))

        # fit on X_64
        rf = ensemble.RandomForestRegressor()
        rf.fit(X_64, y)
        rf = CompiledRegressionPredictor(rf)

        assert_array_equal(rf.predict(X_32), rf.predict(X_64))

    def test_predictions_with_non_contiguous_input(self):
        num_features = 100
        num_examples = 100

        X_non_contiguous = np.random.normal(size=(num_features, num_examples)).T
        X_non_contiguous = X_non_contiguous.astype(np.float32)
        self.assertFalse(X_non_contiguous.flags['C_CONTIGUOUS'])

        y = np.random.normal(size=num_examples)

        rf = ensemble.RandomForestRegressor()
        rf.fit(X_non_contiguous, y)
        rf_compiled = CompiledRegressionPredictor(rf)

        try:
            rf_compiled.predict(X_non_contiguous)
        except ValueError as e:
            self.fail("predict(X) raised ValueError")

        X_contiguous = np.ascontiguousarray(X_non_contiguous)
        self.assertTrue(X_contiguous.flags['C_CONTIGUOUS'])
        assert_array_equal(rf_compiled.predict(X_non_contiguous), rf_compiled.predict(X_contiguous))
