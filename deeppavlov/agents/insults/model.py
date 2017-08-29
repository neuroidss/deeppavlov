from .metrics import roc_auc_score
import os
import numpy as np
import copy
import tensorflow as tf
from keras.layers import Dense, Activation, Input, Embedding, concatenate
from keras.models import Model
from keras.layers.embeddings import Embedding
from keras.layers.pooling import MaxPooling1D, GlobalMaxPooling1D
from keras.layers.convolutional import Conv1D
from keras.layers.core import Dropout, Reshape
from keras.regularizers import l2
from keras.optimizers import Adam
from keras.losses import binary_crossentropy
from sklearn import linear_model, svm
from keras import backend as K
from keras.metrics import binary_accuracy
import json
from sklearn.externals import joblib
from .utils import vectorize_select_from_data

from .embeddings_dict import EmbeddingsDict

class InsultsModel(object):

    def __init__(self, model_name, word_index, embedding_matrix, opt):
        self.model_name = model_name
        self.word_index = word_index
        self.embedding_matrix = embedding_matrix
        self.opt = copy.deepcopy(opt)
        self.kernel_sizes = [int(x) for x in opt['kernel_sizes'].split(' ')]
        self.pool_sizes = [int(x) for x in opt['pool_sizes'].split(' ')]
        self.model_type = None
        self.from_saved = False

        if self.model_name == 'cnn_word':
            self.model_type = 'nn'
        if self.model_name == 'log_reg' or self.model_name == 'svc':
            self.model_type = 'ngrams'
            self.num_ngrams = None
            self.vectorizers = None
            self.selectors = None

        if self.opt.get('model_file') and \
                ( (os.path.isfile(opt['model_file'] + '.h5') and self.model_type == 'nn')
                 or (os.path.isfile(opt['model_file'] + '_opt.json') and
                     os.path.isfile(opt['model_file'] + '_cls.pkl') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_special.bin') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_general_0.bin') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_general_1.bin') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_general_2.bin') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_general_3.bin') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_general_4.bin') and
                     os.path.isfile(self.opt['model_file'] + '_ngrams_vect_general_5.bin') and
                             self.model_type == 'ngrams') ):
            self.from_saved = True
            self._init_from_saved(opt['model_file'])
        else:
            if self.opt.get('pretrained_model'):
                self.from_saved = True
                self._init_from_saved(opt['pretrained_model'])
            else:
                self._init_from_scratch()
        self.opt['cuda'] = not self.opt['no_cuda']
        # if self.opt['cuda']:
        #     print('[ Using CUDA (GPU %d) ]' % opt['gpu'])
        #     config = tf.ConfigProto()
        #     config.gpu_options.per_process_gpu_memory_fraction = 0.45
        #     config.gpu_options.visible_device_list = str(opt['gpu'])
        #     set_session(tf.Session(config=config))
        self.n_examples = 0
        self.updates = 0
        self.train_loss = 0.0
        self.train_acc = 0.0
        self.train_auc = 0.0
        self.val_loss = 0.0
        self.val_acc = 0.0
        self.val_auc = 0.0


    def _init_from_scratch(self):
        print('[ Initializing model from scratch ]')
        if self.model_name == 'log_reg':
            self.model = self.log_reg_model()
        if self.model_name == 'svc':
            self.model = self.svc_model()
        if self.model_name == 'cnn_word':
            self.model = self.cnn_word_model()

        if self.model_type == 'nn':
            optimizer = Adam(lr=self.opt['learning_rate'], decay=self.opt['learning_decay'])
            self.model.compile(loss='binary_crossentropy',
                               optimizer=optimizer,
                               metrics=['binary_accuracy'])

    def save(self, fname=None):
        """Save the parameters of the agent to a file."""
        fname = self.opt.get('model_file', None) if fname is None else fname

        if fname:
            if self.model_type == 'nn':
                print("[ saving model: " + fname + " ]")
                self.model.save_weights(fname + '.h5')

            if self.model_type == 'ngrams':
                print("[ saving model: " + fname + " ]")
                with open(fname + '_cls.pkl', 'wb') as model_file:
                    joblib.dump(self.model, model_file)

            with open(fname + '_opt.json', 'w') as opt_file:
                json.dump(self.opt, opt_file)

    def _init_from_saved(self, fname):

        with open(fname + '_opt.json', 'r') as opt_file:
            self.opt = json.load(opt_file)

        if self.model_type == 'nn':
            if self.model_name == 'cnn_word':
                self.model = self.cnn_word_model()
            optimizer = Adam(lr=self.opt['learning_rate'], decay=self.opt['learning_decay'])
            self.model.compile(loss='binary_crossentropy',
                               optimizer=optimizer,
                               metrics=['binary_accuracy'])
            print('[ Loading model weights %s ]' % fname)
            self.model.load_weights(fname + '.h5')

        if self.model_type == 'ngrams':
            with open(fname + '_cls.pkl', 'rb') as model_file:
                self.model = joblib.load(model_file)
            print('CLS:', self.model)

    def update(self, batch):
        x, y = batch
        y = np.array(y)

        if self.model_type == 'nn':
            self.train_loss, self.train_acc = self.model.train_on_batch(x, y)
            y_pred = self.model.predict_on_batch(x).reshape(-1)
            self.train_auc = roc_auc_score(y, y_pred)

        if self.model_type == 'ngrams':
            x = vectorize_select_from_data(x, self.vectorizers, self.selectors)
            print('Train shapes:', x.shape, y.shape)
            self.model.fit(x, y.reshape(-1))
            y_pred = np.array(self.model.predict_proba(x)[:,1]).reshape(-1)
            y_pred_tensor = K.constant(y_pred, dtype='float64')
            self.train_loss = K.eval(binary_crossentropy(y.astype('float'), y_pred_tensor))
            self.train_acc = K.eval(binary_accuracy(y.astype('float'), y_pred_tensor))
            self.train_auc = roc_auc_score(y, y_pred)
        self.updates += 1
        return y_pred

    def predict(self, batch):
        if self.model_type == 'nn':
            y_pred = np.array(self.model.predict_on_batch(batch)).reshape(-1)
            return y_pred
        if self.model_type == 'ngrams':
            x = vectorize_select_from_data(batch, self.vectorizers, self.selectors)
            print('Predict shapes:', x.shape)
            predictions = self.model.predict_proba(x)[:,1]
            return np.array(predictions).reshape(-1)

    def log_reg_model(self):
        model = linear_model.LogisticRegression(C=10, penalty='l1')
        return model

    def svc_model(self):
        model = svm.SVC(probability=True, C=0.3, kernel='linear')
        return model

    def cnn_word_model(self):

        input = Input(shape=(self.opt['max_sequence_length'],))
        embed_input = Embedding(len(self.word_index) + 1, self.opt['embedding_dim'],
                                weights=[self.embedding_matrix] if self.embedding_matrix is not None else None,
                                input_length=self.opt['max_sequence_length'],
                                trainable=self.embedding_matrix is None)(input)

        output_0 = Conv1D(self.opt['num_filters'], kernel_size=self.kernel_sizes[0], activation='relu',
                          kernel_regularizer=l2(self.opt['regul_coef_conv']), padding='same')(embed_input)
        output_0 = MaxPooling1D(pool_size=self.pool_sizes[0], strides=1, padding='same')(output_0)

        output_1 = Conv1D(self.opt['num_filters'], kernel_size=self.kernel_sizes[1], activation='relu',
                          kernel_regularizer=l2(self.opt['regul_coef_conv']), padding='same')(embed_input)
        output_1 = MaxPooling1D(pool_size=self.pool_sizes[1], strides=1, padding='same')(output_1)

        output_2 = Conv1D(self.opt['num_filters'], kernel_size=self.kernel_sizes[2], activation='relu',
                          kernel_regularizer=l2(self.opt['regul_coef_conv']), padding='same')(embed_input)
        output_2 = MaxPooling1D(pool_size=self.pool_sizes[2], strides=1, padding='same')(output_2)
        output = concatenate([output_0, output_1, output_2], axis=1)
        output = Reshape(((self.opt['max_sequence_length']
                           * len(self.kernel_sizes))
                          * self.opt['num_filters'],))(output)
        output = Dropout(rate=self.opt['dropout_rate'])(output)
        output = Dense(self.opt['dense_dim'], activation='relu',
                       kernel_regularizer=l2(self.opt['regul_coef_dense']))(output)
        output = Dropout(rate=self.opt['dropout_rate'])(output)
        output = Dense(1, activation=None, kernel_regularizer=l2(self.opt['regul_coef_dense']))(output)
        act_output = Activation('sigmoid')(output)
        model = Model(inputs=input, outputs=act_output)
        return model
