#!/bin/env python
#-*- coding: utf8 -*-

import sys
import os
import re
import pickle
from   optparse import OptionParser
import numpy as np
import tensorflow as tf

import util
import model

# --verbose
VERBOSE = 0

if __name__ == '__main__':
	parser = OptionParser()
	parser.add_option("--verbose", action="store_const", const=1, dest="verbose", help="verbose mode")
	parser.add_option("-t", "--train", dest="train_path", help="train file path", metavar="train_path")
	parser.add_option("-v", "--validation", dest="validation_path", help="validation file path", metavar="validation_path")
	parser.add_option("-m", "--model", dest="model_dir", help="dir path to save model", metavar="model_dir")
	(options, args) = parser.parse_args()
	if options.verbose == 1 : VERBOSE = 1
	train_path = options.train_path
	if train_path == None :
		parser.print_help()
		exit(1)
	validation_path = options.validation_path
	if validation_path == None :
		parser.print_help()
		exit(1)
	model_dir = options.model_dir
	if model_dir == None :
		parser.print_help()
		exit(1)
	if not os.path.isdir(model_dir) :
		os.makedirs(model_dir)

	# config
	n_steps = 100                   # time steps
	padd = '\t'                     # special padding chracter
	char_dic = util.build_dictionary(train_path, padd)
	n_input = len(char_dic)         # input dimension, vocab size
	n_hidden = 16                   # hidden layer size
	n_classes = 2                   # output classes,  space or not
	vocab_size = n_input
	'''
	util.test_next_batch(train_path, char_dic, vocab_size, n_steps, padd)
	'''
	x = tf.placeholder(tf.float32, [None, n_steps, n_input])
	y_ = tf.placeholder(tf.int32, [None, n_steps])
	early_stop = tf.placeholder(tf.int32)

	# LSTM layer
	# 2 x n_hidden length (state & cell)
	istate = tf.placeholder(tf.float32, [None, 2*n_hidden])
	weights = {
		'hidden' : model.weight_variable([n_input, n_hidden]),
		'out' : model.weight_variable([n_hidden, n_classes])
	}
	biases = {
		'hidden' : model.bias_variable([n_hidden]),
		'out': model.bias_variable([n_classes])
	}

	# training
	y = model.RNN(x, istate, weights, biases, n_hidden, n_steps, n_input, early_stop)

	batch_size = 1
	learning_rate = 0.01
	training_iters = 30
	logits = tf.reshape(tf.concat(1, y), [-1, n_classes])
	targets = y_
	seq_weights = tf.ones([n_steps * batch_size])
	loss = tf.nn.seq2seq.sequence_loss_by_example([logits], [targets], [seq_weights])
	cost = tf.reduce_sum(loss) / batch_size 
	optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(cost)

	correct_pred = tf.equal(tf.argmax(logits,1), tf.cast(y_, tf.int64))
	accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

	NUM_THREADS = 1
	config = tf.ConfigProto(intra_op_parallelism_threads=NUM_THREADS,
			inter_op_parallelism_threads=NUM_THREADS,
			log_device_placement=False)
	sess = tf.Session(config=config)
	init = tf.initialize_all_variables()
	sess.run(init)
	saver = tf.train.Saver() # save all variables
	checkpoint_dir = model_dir
	checkpoint_file = 'segm.ckpt'

	validation_data = util.get_validation_data(validation_path, char_dic, vocab_size, n_steps, padd)

	seq = 0
	while seq < training_iters :
		c_istate = np.zeros((batch_size, 2*n_hidden))
		i = 0
		fid = util.open_file(train_path, 'r')
		for line in fid :
			line = line.strip()
			if line == "" : continue
			line = line.decode('utf-8')
			sentence = util.snorm(line)
			pos = 0
			while pos != -1 :
				batch_xs, batch_ys, next_pos, count = util.next_batch(sentence, pos, char_dic, vocab_size, n_steps, padd)
				'''
				print 'window : ' + sentences[begin][pos:pos+n_steps]
				print 'count : ' + str(count)
				print 'next_pos : ' + str(next_pos)
				print batch_ys
				'''
				feed={x: batch_xs, y_: batch_ys, istate: c_istate, early_stop:count}
				sess.run(optimizer, feed_dict=feed)
				pos = next_pos
			print '%s th sentence ... done' % i
			i += 1
		util.close_file(fid)
		# validation
		validation_cost = 0
		validation_accuracy = 0
		for validation_xs, validation_ys, count in validation_data :
			feed={x: validation_xs, y_: validation_ys, istate: c_istate, early_stop:count}
			validation_cost += sess.run(cost, feed_dict=feed)
			validation_accuracy += sess.run(accuracy, feed_dict=feed)
		validation_accuracy /= len(validation_data)
		print 'seq : %s' % (seq) + ',' + 'validation cost : %s' % validation_cost + ',' + 'validation accuracy : %s' % (validation_accuracy)
		seq += 1

	print 'save dic'
	dic_path = model_dir + '/' + 'dic.pickle'
	with open(dic_path, 'wb') as handle :
		pickle.dump(char_dic, handle)
	print 'save model(final)'
	saver.save(sess, checkpoint_dir + '/' + checkpoint_file)
	print 'end of training'
