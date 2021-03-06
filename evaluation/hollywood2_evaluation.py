from ipdb import set_trace
import numpy as np

from sklearn import svm
from sklearn.grid_search import GridSearchCV
from sklearn.cross_validation import StratifiedShuffleSplit
from sklearn.preprocessing import LabelBinarizer

from .base_evaluation import BaseEvaluation
from utils import average_precision


class MySVC(svm.SVC):
    def predict(self, X):
        return self.decision_function(X)


class Hollywood2Evaluation(BaseEvaluation):
    """ Evaluation procedure for the Hollywood2 dataset. Fits a one-vs-rest
    classifier for each class.

    """
    def __init__(self, **kwargs):
        pass

    def fit(self, Kxx, cx):
        """ Fits one-vs-rest classifiers for each class.

        Parameters
        ----------
        Kxx: array [n_samples, n_samples]
            Precomputed kernel matrix of the training data.

        cx: list of tuples
            Labels array. Each tuple may contain one or multiple labels.
            Hollywood2 is a multi-label dataset.
        """
        # Convert labels to a label matrix. Element cx[i, j] is 1 if sample `i`
        # belongs to class `j`; otherwise it is -1.
        self.lb = LabelBinarizer(pos_label=1, neg_label=-1)
        cx = self.lb.fit_transform(cx)

        self.nr_classes = cx.shape[1]
        self.clf = []

        for ii in xrange(self.nr_classes):
            labels = cx[:, ii]

            # Better results with these weights:
            my_weights = {-1: 1, 1: 100}
            my_svm = MySVC(kernel='precomputed', probability=True,
                             class_weight=my_weights)  #'auto')

            #c_values = np.power(3.0, np.arange(-2, 8))
            tuned_parameters = {
                'C': np.power(3.0, np.arange(-2, 8)),}
                #'class_weight': [{-1: 1, 1: 2 ** jj} for jj in xrange(10)]}

            splits = StratifiedShuffleSplit(labels, 5, test_size=0.25, random_state=1)
            self.clf.append(
                GridSearchCV(my_svm, tuned_parameters,
                             score_func=average_precision,
                             cv=splits, n_jobs=4))
            self.clf[ii].fit(Kxx, labels)
        return self

    def score(self, Kyx, cy):
        """ Returns the mean average precision score. """
        cy = self.lb.transform(cy)
        average_precisions = np.zeros(self.nr_classes)
        preds = []
        for ii in xrange(self.nr_classes):
            true_labels = cy[:, ii]
            predicted_values = self.clf[ii].predict_proba(Kyx)[:, 1]
            preds.append(predicted_values)
            average_precisions[ii] = average_precision(
                true_labels, predicted_values)
        #return np.mean(average_precisions) * 100
        #return preds
        return average_precisions

    @classmethod
    def is_evaluation_for(cls, dataset_to_evaluate):
        if dataset_to_evaluate == 'hollywood2':
            return True
        else:
            return False
