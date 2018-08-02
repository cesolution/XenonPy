# Copyright 2018 TsumiNa. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

from multiprocessing import cpu_count

import numpy as np
import pandas as pd
import pytest

from xenonpy.descriptor import BaseDescriptor, BaseFeaturizer


@pytest.fixture(scope='module')
def data():
    # ignore numpy warning
    import warnings
    print('ignore NumPy RuntimeWarning\n')
    warnings.filterwarnings("ignore", message="numpy.dtype size changed")
    warnings.filterwarnings("ignore", message="numpy.ndarray size changed")

    class _FakeFeaturier(BaseFeaturizer):
        def __init__(self, n_jobs=1):
            super().__init__(n_jobs=n_jobs)

        def featurize(self, *x):
            return x[0]

        @property
        def feature_labels(self):
            return ['labels']

    class _FakeDescriptor(BaseDescriptor):
        def __init__(self):
            self.g1 = _FakeFeaturier()
            self.g1 = _FakeFeaturier()
            self.g2 = _FakeFeaturier()

    # prepare test data
    yield dict(featurizer=_FakeFeaturier, descriptor=_FakeDescriptor)

    print('test over')


def test_base_feature_props(data):
    bf = BaseFeaturizer()

    # test n_jobs
    assert bf.n_jobs == cpu_count()
    bf.n_jobs = 1
    assert bf.n_jobs == 1
    bf.n_jobs = 100
    assert bf.n_jobs == cpu_count()

    # test citation, author
    assert bf.citations == 'No citations'
    assert bf.authors == 'anonymous'

    # test labels, featurize
    try:
        bf.featurize(1)
    except NotImplementedError:
        assert True
    else:
        assert False, 'should got NotImplementedError'

    try:
        bf.feature_labels
    except NotImplementedError:
        assert True
    else:
        assert False, 'should got NotImplementedError'


def test_base_feature_1(data):
    featurizer = data['featurizer']()
    assert isinstance(featurizer, BaseFeaturizer)
    assert featurizer.n_jobs == 1
    assert featurizer.featurize(10) == 10
    assert featurizer.feature_labels == ['labels']
    try:
        featurizer.fit_transform(56)
    except TypeError:
        assert True
    else:
        assert False


def test_base_feature_2(data):
    featurizer = data['featurizer']()
    ret = featurizer.fit_transform([1, 2, 3, 4])
    assert isinstance(ret, list)
    assert ret == [1, 2, 3, 4]
    ret = featurizer.fit_transform(np.array([1, 2, 3, 4]))
    assert isinstance(ret, np.ndarray)
    assert (ret == np.array([1, 2, 3, 4])).all()
    ret = featurizer.fit_transform(pd.Series([1, 2, 3, 4]))
    assert isinstance(ret, pd.DataFrame)
    assert (ret.values.ravel() == np.array([1, 2, 3, 4])).all()


def test_base_descriptor_1(data):
    bd = BaseDescriptor()

    # test n_jobs
    assert bd.elapsed == 0
    assert bd.n_jobs == 1
    bd.n_jobs = 100
    assert bd.n_jobs == cpu_count()

    # test featurizers list
    assert hasattr(bd, '__features__')
    assert not bd.__features__


def test_base_descriptor_2(data):
    bd = data['descriptor']()
    assert len(bd.__features__) == 2
    assert 'g1' in bd.__features__.keys()
    assert 'g2' in bd.__features__.keys()


if __name__ == "__main__":
    pytest.main()