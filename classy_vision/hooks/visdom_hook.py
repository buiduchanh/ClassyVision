#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import collections
import logging
from typing import Any, Dict

from classy_vision.generic.distributed_util import is_master
from classy_vision.generic.util import flatten_dict
from classy_vision.generic.visualize import plot_learning_curves
from classy_vision.hooks.classy_hook import ClassyHook
from classy_vision.state.classy_state import ClassyState


try:
    from visdom import Visdom

    visdom_available = True
except ImportError:
    visdom_available = False


class VisdomHook(ClassyHook):
    """
    Plots metrics on to visdom.
    """

    on_rendezvous = ClassyHook._noop
    on_start = ClassyHook._noop
    on_phase_start = ClassyHook._noop
    on_sample = ClassyHook._noop
    on_forward = ClassyHook._noop
    on_loss = ClassyHook._noop
    on_backward = ClassyHook._noop
    on_update = ClassyHook._noop
    on_end = ClassyHook._noop

    def __init__(
        self, server: str, port: str, env: str = "main", title_suffix: str = ""
    ) -> None:
        if not visdom_available:
            raise RuntimeError("Visdom is not installed, cannot use VisdomHook")

        self.server: str = server
        self.port: str = port
        self.env: str = env
        self.title_suffix: str = title_suffix

        self.metrics: Dict = {}
        self.visdom: Visdom = Visdom(self.server, self.port)

    def on_phase_end(self, state: ClassyState, local_variables: Dict[str, Any]) -> None:
        """
        Plot the metrics on visdom.
        """
        phase_type = state.phase_type
        metrics = self.metrics
        config = state.task.get_config()
        batches = len(state.losses)

        if batches == 0:
            return

        # Loss for the phase
        loss = sum(state.losses) / (batches * state.get_batchsize_per_replica())
        loss_key = phase_type + "_loss"
        if loss_key not in metrics:
            metrics[loss_key] = []
        metrics[loss_key].append(loss)

        # Optimizer LR for the phase
        optimizer_lr = state.optimizer.optimizer_config["lr"]
        lr_key = phase_type + "_learning_rate"
        if lr_key not in metrics:
            metrics[lr_key] = []
        metrics[lr_key].append(optimizer_lr)

        # Calculate meters
        for meter in state.meters:
            if isinstance(meter.value, collections.MutableMapping):
                flattened_meters_dict = flatten_dict(meter.value, prefix=meter.name)
                for k, v in flattened_meters_dict.items():
                    metric_key = phase_type + "_" + k
                    if metric_key not in metrics:
                        metrics[metric_key] = []
                    metrics[metric_key].append(v)
            else:
                metric_key = phase_type + "_" + meter.name
                if metric_key not in metrics:
                    metrics[metric_key] = []
                metrics[metric_key].append(meter.value)

        # update learning curve visualizations:
        phase_type = "train" if state.train else "test"
        title = "%s-%s-%d" % (
            config["dataset"][phase_type]["name"],
            config["model"]["name"],
            state.base_model.model_depth,
        )
        title += self.title_suffix

        if not state.train and is_master():
            logging.info("Plotting learning curves to visdom")
            plot_learning_curves(
                metrics, visdom_server=self.visdom, env=self.env, win=title, title=title
            )