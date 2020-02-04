# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""A binary to train CIFAR-10 using a single GPU.

Accuracy:
cifar10_train.py achieves ~86% accuracy after 100K steps (256 epochs of
data) as judged by cifar10_eval.py.

Speed: With batch_size 128.

System        | Step Time (sec/batch)  |     Accuracy
------------------------------------------------------------------
1 Tesla K20m  | 0.35-0.60              | ~86% at 60K steps  (5 hours)
1 Tesla K40m  | 0.25-0.35              | ~86% at 100K steps (4 hours)

Usage:
Please see the tutorial and website for how to download the CIFAR-10
data set, compile the program and train the model.

http://tensorflow.org/tutorials/deep_cnn/
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from datetime import datetime
import time
import collections
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.colors import ListedColormap
from matplotlib.colors import BoundaryNorm

import tensorflow as tf

import resnet 
import sparsity_util
import sparsity_monitor

import os

os.environ["CUDA_VISIBLE_DEVICES"]="0"

FLAGS = tf.app.flags.FLAGS

tf.app.flags.DEFINE_string('train_dir', '/tmp/imagenet_resnet_train',
                           """Directory where to write event logs """
                           """and checkpoint.""")
tf.app.flags.DEFINE_integer('max_steps', 10000,
                            """Number of batches to run.""")
tf.app.flags.DEFINE_boolean('log_device_placement', False,
                            """Whether to log device placement.""")
tf.app.flags.DEFINE_integer('log_frequency', 100,
                            """How often to log results to the console.""")
tf.app.flags.DEFINE_string('sparsity_dir', '/tmp/imagenet_resnet_sparsity',
                           """Directory where to write summaries""")
tf.app.flags.DEFINE_integer('monitor_interval', 10,
                           """The interval of monitoring sparsity""")
tf.app.flags.DEFINE_integer('monitor_period', 500,
                           """The period of monitoring sparsity""")
tf.app.flags.DEFINE_boolean('file_io', False,
                           """Weather or not log the animation for tracking
                           the change of spatial pattern and output results to file""")
tf.app.flags.DEFINE_string('io_path', 'resnet_50Kiter',
                           """Directory where to write sparsity log""")
tf.app.flags.DEFINE_string('model', 'resnet',
                           """Model Type""")

def train():
  """Train CIFAR-10 for a number of steps."""
  with tf.Graph().as_default() as g:
    global_step = tf.train.get_or_create_global_step()

    # Get images and labels for CIFAR-10.
    # Force input pipeline to CPU:0 to avoid operations sometimes ending up on
    # GPU and resulting in a slow down.
    with tf.device('/cpu:0'):
      images, labels = resnet.distorted_inputs()

    # Build a Graph that computes the logits predictions from the
    # inference model.
    logits, tensor_list = resnet.inference(images)

    # Calculate loss.
    loss = resnet.loss(logits, labels)

    # Build a Graph that trains the model with one batch of examples and
    # updates the model parameters.
    train_op, retrieve_list = resnet.train(loss, tensor_list, global_step)

    class _LoggerHook(tf.train.SessionRunHook):
      """Logs loss and runtime."""

      def begin(self):
        self._step = -1
        self._start_time = time.time()

      def before_run(self, run_context):
        self._step += 1
        return tf.train.SessionRunArgs(loss)  # Asks for loss value.

      def after_run(self, run_context, run_values):
        if self._step % FLAGS.log_frequency == 0:
          current_time = time.time()
          duration = current_time - self._start_time
          self._start_time = current_time

          loss_value = run_values.results
          examples_per_sec = FLAGS.log_frequency * FLAGS.batch_size / duration
          sec_per_batch = float(duration / FLAGS.log_frequency)

          format_str = ('%s: step %d, loss = %.2f (%.1f examples/sec; %.3f '
                        'sec/batch)')
          print (format_str % (datetime.now(), self._step, loss_value,
                               examples_per_sec, sec_per_batch))

    class _SparsityHook(tf.train.SessionRunHook):
      """Logs loss and runtime."""

      def begin(self):
       self._step = -1
       mode = sparsity_monitor.Mode.monitor
       data_format = "NHWC"
       self.monitor = sparsity_monitor.SparsityMonitor(mode, data_format, FLAGS.monitor_interval,\
                                                       FLAGS.monitor_period, retrieve_list)

      def before_run(self, run_context):
        self._step += 1
        selected_list = self.monitor.scheduler_before(self._step)
        return tf.train.SessionRunArgs(selected_list)  # Asks for loss value.

      def after_run(self, run_context, run_values):
        self.monitor.scheduler_after(run_values.results, self._step, FLAGS.model, os.getcwd()+'/'+FLAGS.io_path, FLAGS.file_io)

    sparsity_summary_op = tf.summary.merge_all()
    summary_writer = tf.summary.FileWriter(FLAGS.sparsity_dir, g)

    start = time.time()
    with tf.train.MonitoredTrainingSession(
        checkpoint_dir=FLAGS.train_dir,
        hooks=[tf.train.StopAtStepHook(last_step=FLAGS.max_steps),
               tf.train.NanTensorHook(loss),
               #tf.train.SummarySaverHook(save_steps=1, summary_writer=summary_writer, summary_op=sparsity_summary_op),
               _LoggerHook(),
               _SparsityHook()],
        config=tf.ConfigProto(
            log_device_placement=FLAGS.log_device_placement)) as mon_sess:
      while not mon_sess.should_stop():
        mon_sess.run(train_op)
    end = time.time()
    print(end - start)


def main(argv=None):  # pylint: disable=unused-argument
  if tf.io.gfile.exists(FLAGS.train_dir):
    tf.io.gfile.rmtree(FLAGS.train_dir)
  tf.io.gfile.makedirs(FLAGS.train_dir)
  train()


if __name__ == '__main__':
  tf.compat.v1.app.run()
