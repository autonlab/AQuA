import os, torch, copy
import numpy as np
import pandas as pd

# AUM imports
from aum import AUMCalculator


class AUM:
    def __init__(self, model, optimizer):
        self.model = model
        self.optimizer = optimizer
        self.dthr = None
        self.orig_dim = self.model.output_dim


    def _fit_get_aum(self, thr_inds):
        self._aum_calculator = AUMCalculator(os.getcwd())
        train_metrics = self.model.get_training_metrics()
        for i in range(len(train_metrics['output'])):
            self._aum_calculator.update(train_metrics['output'][i],
                                        train_metrics['target'][i],
                                        train_metrics['sample_id'][i])
        self._aum_calculator.finalize()
        aum_file = pd.read_csv(os.path.join(os.getcwd(), 'aum_values.csv'))
        thresh = np.percentile(aum_file.iloc[thr_inds]['aum'].values, self.alpha*100)
        #d_thresh = aum_file.iloc[thr_inds]['aum'].values
        mask = np.array([True]*aum_file.shape[0])  # Selects train indices only, discards THR indices
        mask[thr_inds] = False

        return np.array(aum_file.index)[mask][aum_file['aum'].values[mask] < thresh]
        

    def find_label_issues(self, data_aq,
                          **kwargs):
        # Read: https://discuss.pytorch.org/t/does-deepcopying-optimizer-of-one-model-works-across-the-model-or-should-i-create-new-optimizer-every-time/14359/6
        # Save initial states of models before training 
        orig_model = copy.deepcopy(self.model.model)
        orig_optim = type(self.optimizer)(orig_model.parameters(), lr=self.optimizer.defaults['lr'])
        orig_optim.load_state_dict(self.optimizer.state_dict())

        self.alpha = kwargs['alpha']
        # Refer to paper for training strategy

        labels = data_aq.labels
        # Randomly assign N/(c+1) data as the (c+1)th class
        label_val = np.unique(labels).max()+1
        N, c = labels.shape[0], np.unique(labels).shape[0]+1
        
        rand_inds = np.random.randint(0, N, size=2*(N//c))

        # Pass 1
        temp_data_aq = copy.deepcopy(data_aq)
        labels_step_1 = labels.copy()
        labels_step_1[rand_inds[:(N//c)]] = label_val
        temp_data_aq.labels = labels_step_1
        self.fit(temp_data_aq)
        incorrect_labels_idx = self._fit_get_aum(rand_inds[:(N//c)])
        del temp_data_aq
        #print(incorrect_labels_idx.shape)

        # Pass 2
        temp_data_aq = copy.deepcopy(data_aq)
        self.model.reinit_model(orig_model, orig_optim)
        labels_step_2 = labels.copy()
        labels_step_2[rand_inds[(N//c):]] = label_val
        temp_data_aq.labels = labels_step_2
        self.fit(temp_data_aq)
        incorrect_labels_idx_thresh = self._fit_get_aum(rand_inds[(N//c):])
        total_incorrect_labels = np.union1d(incorrect_labels_idx, incorrect_labels_idx_thresh)
        del temp_data_aq
        #print(incorrect_labels_idx_thresh.shape)
        #print(total_incorrect_labels.shape)

        mask = np.array([False]*labels.shape[0])  # Selects train indices only, discards THR indices
        mask[total_incorrect_labels] = True

        # Re-instantiate the model with correct number of output neurons
        return mask
    
    
    def fit(self, data_aq):        
        return self.model.fit(data_aq, 
                              lr_tune=True,
                              early_stop=True)

    def predict(self, data):
        return self.model.predict(data)

    def predict_proba(self, data):
        return self.model.predict_proba(data)