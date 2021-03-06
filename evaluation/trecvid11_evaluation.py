import numpy as np
from numpy import arange, array, ceil, Inf, mean
from sklearn import svm
from sklearn.grid_search import GridSearchCV
from sklearn.preprocessing import LabelBinarizer
from sklearn.cross_validation import StratifiedShuffleSplit
from ipdb import set_trace

from .base_evaluation import BaseEvaluation
from utils import tuple_labels_to_list_labels
from utils import average_precision
#from utils import calc_ap as average_precision # Danila's metric.
import result_file_functions as rff


class TrecVid11Evaluation(BaseEvaluation):
    """ We evaluate the performance on TrecVid11 dataset by computing the mean
    average precision of each class against the background class NULL.

    """
    def __init__(self, **kwargs):
        self.null_class_idx = 15
        self.scenario = kwargs.get('eval_type', 'versus_null_sklearn')
        assert self.scenario in ('multiclass', 'versus_null',
                                 'versus_null_sklearn')

    def fit(self, Kxx, cx):
        if self.scenario == 'multiclass':
            cx = tuple_labels_to_list_labels(cx)
            self._fit_one_vs_one(Kxx, cx)
        elif self.scenario == 'versus_null':
            cx = tuple_labels_to_list_labels(cx)
            self._fit_one_vs_rest(Kxx, cx)
        elif self.scenario == 'versus_null_sklearn':
            cx = tuple_labels_to_list_labels(cx)
            self._fit_one_vs_rest_sklearn(Kxx, cx)
        return self

    def score(self, Kyx, cy):
        if self.scenario == 'multiclass':
            cy = tuple_labels_to_list_labels(cy)
            return self._score_one_vs_one(Kyx, cy)
        elif self.scenario == 'versus_null':
            cy = tuple_labels_to_list_labels(cy)
            return self._score_one_vs_rest(Kyx, cy)
        elif self.scenario == 'versus_null_sklearn':
            cy = tuple_labels_to_list_labels(cy)
            return self._score_one_vs_rest_sklearn(Kyx, cy)

    def predict(self, Kyx, cy):
        cy = tuple_labels_to_list_labels(cy)
        if self.scenario == 'multiclass':
            return self._predict_one_vs_one(Kyx, cy)
        return None
    
    def _fit_one_vs_rest_sklearn(self, Kxx, cx):
        """ Fits one-vs-rest classifier and crossvalidates using sklearn. """
        self.nr_classes = len(set(cx))
        self.clf = []
        self.cx_idxs = []
        for ii in xrange(self.nr_classes - 1):
            # Slice only the elements with index ii and null_class_idx.
            good_idxs = (cx == ii) | (cx == self.null_class_idx)
            self.cx_idxs.append(good_idxs)

            K_good_idxs = np.ix_(good_idxs, good_idxs)
            # Get a +1, -1 vector of labels.
            cx_ = map(lambda label: +1 if label != self.null_class_idx else -1,
                      cx[good_idxs])

            my_svm = svm.SVC(kernel='precomputed', probability=True,
                             class_weight='auto')

            c_values = np.power(3.0, np.arange(-2, 8))
            tuned_parameters = [{'C': c_values}]

            cx_ = np.array(cx_)
            splits = StratifiedShuffleSplit(cx_, 3, test_size=0.25,
                                            random_state=0)

            self.clf.append(
                GridSearchCV(my_svm, tuned_parameters,
                             score_func=average_precision,
                             cv=splits, n_jobs=4))
            self.clf[ii].fit(Kxx[K_good_idxs], cx_)

        return self

    def _score_one_vs_rest_sklearn(self, Kyx, cy):
        """ Returns the mean average precision score. """
        ap_scores = np.zeros(self.nr_classes - 1)
        for ii in xrange(self.nr_classes - 1):
        #for ii in xrange(1):
            good_idxs = (cy == ii) | (cy == self.null_class_idx)
            K_good_idxs = np.ix_(good_idxs, self.cx_idxs[ii])

            # Get a +1, -1 vector of labels.
            cy_ = map(lambda label: +1 if label == ii else -1, cy[good_idxs])
            # Predict.
            predicted_values = self.clf[ii].predict_proba(Kyx[K_good_idxs])[:, 1]
            ap_scores[ii] = average_precision(
                cy_, predicted_values)
            #print "%d sklearn %2.3f" % (ii, 100 * ap_scores[ii])
            print 'Class #%d, test score: %2.3f' % (ii, 100 * ap_scores[ii])
        return np.mean(ap_scores) * 100

    def _fit_one_vs_rest(self, Kxx, cx):
        """ Fits a one-vs-null SVM classifier. """
        self.nr_classes = len(set(cx))
        self.clf = []
        self.cx_idxs = []

        cx = np.array(cx)
        nr_null_samples = len(cx[cx == self.null_class_idx])

        for ii in xrange(self.nr_classes - 1):  # Skip NULL class.
            # Slice only the elements with index ii and null_class_idx.
            good_idxs = (cx == ii) | (cx == self.null_class_idx)
            K_good_idxs = np.ix_(good_idxs, good_idxs)
            # Get a +1, -1 vector of labels.
            self.cx_idxs.append(good_idxs)
            cx_ = map(lambda label: +1 if label != self.null_class_idx else -1,
                      cx[good_idxs])
            nr_ii = len(cx_)
            # Crossvalidate parameters on the sliced matrix.
            self.clf.append(svm.SVC(kernel='precomputed', probability=True))
            C = self._crossvalidate_C_one_vs_rest(Kxx[K_good_idxs], cx_, ii)
            # As classes are unbalanced, use some weighting.
            weight = np.ones(nr_ii)
            weight[cx_ == +1] *= nr_null_samples
            # Finally, fit the classifier.
            self.clf[ii].C = C
            self.clf[ii].fit(Kxx[K_good_idxs], cx_,
                             sample_weight=weight)
        return self

    def _score_one_vs_rest(self, Kyx, cy):
        """ Score each class against the rest 15. I don't have a NULL class for
        the testing set at the moment.

        """
        cy = np.array(cy)
        ap_scores = np.zeros(self.nr_classes - 1)

        print
        for ii in xrange(self.nr_classes - 1):
            # Scenario 1. Each class vs rest classes
            # good_idxs = cy != self.null_class_idx
            # Scenario 2. Each class vs NULL
            good_idxs = (cy == ii) | (cy == self.null_class_idx)
            K_good_idxs = np.ix_(good_idxs, self.cx_idxs[ii])
            # Get a +1, -1 vector of labels.
            cy_ = map(lambda label: +1 if label == ii else -1, cy[good_idxs])
            # Predict.
            confidence_values = self.clf[ii].predict_proba(
                Kyx[K_good_idxs])[:, 1]
            ap_scores[ii] = rff.get_ap(confidence_values, cy_)

            print "Score for class %d as positive is %2.4f MAP." % (
                ii, ap_scores[ii])

        return mean(ap_scores) * 100

    def _crossvalidate_C_one_vs_rest(self, K, cc, idx_clf):
        # TODO Try to avoid duplication of some of this code.
        # 1. Split Gram matrix and labels into a training set and a validation
        # set.
        pp = 0.3  # Proportion of examples used for cross-validation.
        M, N = K.shape
        assert M == N, 'K is not Gram matrix.'
        classes = list(set(cc))
        nr_classes = len(classes)
        assert nr_classes == 2, 'Number of classes is not two.'
        # Randomly pick a subset of the data for cross-validation, but enforce
        # to get a proportion of pp points from each of the two classes.
        idxs_0 = [ii for ii, ci in enumerate(cc) if ci == classes[0]]
        idxs_1 = [ii for ii, ci in enumerate(cc) if ci == classes[1]]
        rand_idxs_0 = np.random.permutation(idxs_0)
        rand_idxs_1 = np.random.permutation(idxs_1)
        P0 = ceil(pp * len(rand_idxs_0))
        P1 = ceil(pp * len(rand_idxs_1))
        cv_idxs = np.hstack((rand_idxs_0[:P0], rand_idxs_1[:P1]))
        tr_idxs = np.hstack((rand_idxs_0[P0:], rand_idxs_1[P1:]))
        # Get indices in numpy format.
        cv_ix_ = np.ix_(cv_idxs, tr_idxs)
        tr_ix_ = np.ix_(tr_idxs, tr_idxs)
        # Slice Gram matrix K.
        cv_K = K[cv_ix_]
        tr_K = K[tr_ix_]
        # Get corresponding labels.
        cc = array(cc)
        cv_cc = cc[cv_idxs]
        tr_cc = cc[tr_idxs]
        # 2. Try different values for the regularization term C and pick the
        # one that yields the best score on the cross-validation set.
        log3cs = arange(-2, 8)  # Vary C on an exponantional scale.
        best_score = - Inf
        best_C = 0
        for log3c in log3cs:
            self.clf[idx_clf].C = 3 ** log3c
            weight = np.ones(len(tr_cc))
            weight[tr_cc == +1] *= len(tr_cc[tr_cc == -1])
            self.clf[idx_clf].fit(tr_K, tr_cc, sample_weight=weight)
            confidence_values = self.clf[idx_clf].predict_proba(cv_K)[:, 1]
            score = rff.get_ap(confidence_values, cv_cc)
            if score >= best_score:
                best_score = score
                best_C = self.clf[idx_clf].C
        print "Best score for class %d as positive is %2.4f MAP." % (
            idx_clf, best_score)
        return best_C

    def _fit_one_vs_one(self, Kxx, cx):
        """ Classify in a multiclass scenario. LibSVM uses one-vs-one SVM
        classifiers to achieve this.

        """
        cx = np.array(cx)  # More possibilities to slice as np.array.
        good_idxs = cx != self.null_class_idx
        K_good_idxs = np.ix_(good_idxs, good_idxs)

        self.clf = svm.SVC(kernel='precomputed')
        self.clf.C = self._crossvalidate_C_one_vs_one(
            Kxx[K_good_idxs], cx[good_idxs])
        self.clf.fit(Kxx[K_good_idxs], cx[good_idxs])
        self.cx_idxs = good_idxs

        return self

    def _score_one_vs_one(self, Kyx, cy):
        cy = np.array(cy)
        good_idxs = cy != self.null_class_idx
        K_good_idxs = np.ix_(good_idxs, self.cx_idxs)
        return self.clf.score(Kyx[K_good_idxs], cy[good_idxs]) * 100

    def _predict_one_vs_one(self, Kyx, cy):
        """ Returns true labels and predicted labels. This is implemented only
        for ploting purposes.
        
        """
        cy = np.array(cy)
        good_idxs = cy != self.null_class_idx
        K_good_idxs = np.ix_(good_idxs, self.cx_idxs)
        return cy[good_idxs], self.clf.predict(Kyx[K_good_idxs])

    def _crossvalidate_C_one_vs_one(self, K, cc):
        # 1. Split Gram matrix and labels into a training set and a validation
        # set.
        pp = 0.3  # Proportion of examples used for cross-validation.
        M, N = K.shape
        assert M == N, 'K is not Gram matrix.'
        classes = list(set(cc))
        nr_classes = len(classes)
        assert nr_classes >= 2, 'Number of classes is less than two.'
        # Randomly pick a subset of the data for cross-validation.
        rand_idxs = np.random.permutation(arange(N))
        P = ceil(pp * N)
        cv_idxs = rand_idxs[:P]
        tr_idxs = rand_idxs[P:]
        # Get indices in numpy format.
        cv_ix_ = np.ix_(cv_idxs, tr_idxs)
        tr_ix_ = np.ix_(tr_idxs, tr_idxs)
        # Slice Gram matrix K.
        cv_K = K[cv_ix_]
        tr_K = K[tr_ix_]
        # Get corresponding labels.
        cc = array(cc)
        cv_cc = cc[cv_idxs]
        tr_cc = cc[tr_idxs]
        # 2. Try different values for the regularization term C and pick the
        # one that yields the best score on the cross-validation set.
        log3cs = arange(-2, 8)  # Vary C on an exponantional scale.
        best_score = - Inf
        best_C = 0
        for log3c in log3cs:
            self.clf.C = 3 ** log3c
            self.clf.fit(tr_K, tr_cc)
            score = self.clf.score(cv_K, cv_cc)
            if score >= best_score:
                best_score = score
                best_C = self.clf.C
        return best_C

    @classmethod
    def is_evaluation_for(cls, dataset_to_evaluate):
        if dataset_to_evaluate == 'trecvid11':
            return True
        else:
            return False
