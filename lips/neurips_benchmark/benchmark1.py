# Copyright (c) 2021, IRT SystemX (https://www.irt-systemx.fr/en/)
# See AUTHORS.txt
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of LIPS, LIPS is a python platform for power networks benchmarking

import os
import shutil
import numpy as np
import warnings
import copy
import logging

from lips.benchmark import Benchmark
from lips.neurips_benchmark.scen1_utils import (get_kwargs_simulator_scenario1,
                                                get_actor_training_scenario1,
                                                get_actor_test_ood_topo_scenario1,
                                                get_actor_test_scenario1)

from lips.physical_simulator import Grid2opSimulator
from lips.dataset import PowerGridDataSet
from lips.evaluation import Evaluation

logging.basicConfig(filename="logs.log", level=logging.INFO,format="%(levelname)s:%(message)s")



class NeuripsBenchmark1(Benchmark):
    def __init__(self,
                 path_benchmark,
                 benchmark_name="NeuripsBenchmark1",
                 load_data_set=False,
                 train_env_seed: int = 1,
                 val_env_seed: int = 2,
                 test_env_seed: int = 3,
                 test_ood_topo_env_seed: int = 4,
                 initial_chronics_id: int = 0,
                 train_actor_seed: int = 5,
                 val_actor_seed: int = 6,
                 test_actor_seed: int = 7,
                 test_ood_topo_actor_seed: int = 8,
                 evaluation=None
                 ):
        self.benchmark_name = benchmark_name
        self.path_benchmark = path_benchmark
        self.is_loaded = False

        if evaluation is None:
            self.evaluation = Evaluation()
            # TODO fill that appropriately
            self.evaluation.active_dict["evaluate_ML"] = True
            self.evaluation.activate_physic_compliances()
            self.evaluation.active_dict["evaluate_adaptability"] = False
            self.evaluation.active_dict["evaluate_readiness"] = False
            self.evaluation.active_dict["evaluate_physic"]["verify_current_pos"] = True
            self.evaluation.active_dict["evaluate_physic"]["verify_voltage_pos"] = False
            self.evaluation.active_dict["evaluate_physic"]["verify_loss_pos"] = False
            self.evaluation.active_dict["evaluate_physic"]["verify_predict_disc"] = True
            self.evaluation.active_dict["evaluate_physic"]["verify_current_eq"] = False
            self.evaluation.active_dict["evaluate_physic"]["verify_EL"] = False
            self.evaluation.active_dict["evaluate_physic"]["verify_LCE"] = False
            self.evaluation.active_dict["evaluate_physic"]["verify_KCL"] = False
            #self.evaluation.active_dict["evaluate_physics"] = {}

        else:
            self.evaluation = evaluation

        self.training_simulator = None
        self.val_simulator = None
        self.test_simulator = None
        self.test_ood_topo_simulator = None

        self.training_actor = None
        self.val_actor = None
        self.test_actor = None
        self.test_ood_topo_actor = None

        self.train_env_seed = train_env_seed
        self.val_env_seed = val_env_seed
        self.test_env_seed = test_env_seed
        self.test_ood_topo_env_seed = test_ood_topo_env_seed

        self.train_actor_seed = train_actor_seed
        self.val_actor_seed = val_actor_seed
        self.test_actor_seed = test_actor_seed
        self.test_ood_topo_actor_seed = test_ood_topo_actor_seed

        self.initial_chronics_id = initial_chronics_id

        self.train_dataset = PowerGridDataSet("train",
                                              attr_names=("prod_p", "prod_v", "load_p", "load_q", 
                                                          "line_status", "topo_vect",
                                                          "a_or", "a_ex"), # consider only currents as the variables
                                              theta_attr_names=()) # set the theta to empty, not used for benchmark 1
                                              
        self.val_dataset = PowerGridDataSet("val", 
                                            attr_names=("prod_p", "prod_v", "load_p", "load_q", 
                                                         "line_status", "topo_vect",
                                                         "a_or", "a_ex"),
                                            theta_attr_names=())

        self._test_dataset = PowerGridDataSet("test", 
                                              attr_names=("prod_p", "prod_v", "load_p", "load_q", 
                                                          "line_status", "topo_vect",
                                                          "a_or", "a_ex"),
                                              theta_attr_names=())

        self._test_ood_topo_dataset = PowerGridDataSet("test_ood_topo", 
                                                       attr_names=("prod_p", "prod_v", "load_p", "load_q", 
                                                                   "line_status", "topo_vect",
                                                                   "a_or", "a_ex"), 
                                                       theta_attr_names=())

        self.path_datasets = None
        if load_data_set:
            self.load()
        else:
            self.is_loaded = False

        # TODO create the base class from this interface
        # Benchmark.__init__(self,
        #                    benchmark_name=benchmark_name,
        #                    dataset=self.train_dataset,
        #                    simulator=None,
        #                    evaluator=None,
        #                    save_path=None,
        #                    )

    def load(self):
        if self.is_loaded:
            print("Previously saved data will be erased and new data will be reloaded")
        # TODO: set this attribute in class constructor
        self.path_datasets = os.path.join(self.path_benchmark, self.benchmark_name)
        if not os.path.exists(self.path_datasets):
            raise RuntimeError(f"No data are found in {self.path_datasets}. Have you generated or downloaded "
                               f"some data ?")
        self.train_dataset.load(path=self.path_datasets)
        self.val_dataset.load(path=self.path_datasets)
        self._test_dataset.load(path=self.path_datasets)
        self._test_ood_topo_dataset.load(path=self.path_datasets)
        self.is_loaded = True

    def generate(self, nb_sample_train, nb_sample_val,
                 nb_sample_test, nb_sample_test_ood_topo):
        if self.is_loaded:
            print("Previously saved data will be erased by this new generation")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self._fills_actor_simulator()
        # TODO : to set this variable in constructor
        self.path_datasets = os.path.join(self.path_benchmark, self.benchmark_name)
        if os.path.exists(self.path_datasets):
            print(f"Deleting path {self.path_datasets} that might contain previous runs")  # TODO logger
            shutil.rmtree(self.path_datasets)

        print(f"Creating path {self.path_datasets} to save the current data")  # TODO logger
        os.mkdir(self.path_datasets)

        self.train_dataset.generate(simulator=self.training_simulator,
                                    actor=self.training_actor,
                                    path_out=self.path_datasets,
                                    nb_samples=nb_sample_train
                                    )
        self.val_dataset.generate(simulator=self.training_simulator,
                                  actor=self.training_actor,
                                  path_out=self.path_datasets,
                                  nb_samples=nb_sample_val
                                  )
        self._test_dataset.generate(simulator=self.test_simulator,
                                    actor=self.test_actor,
                                    path_out=self.path_datasets,
                                    nb_samples=nb_sample_test
                                    )
        self._test_ood_topo_dataset.generate(simulator=self.test_ood_topo_simulator,
                                             actor=self.test_ood_topo_actor,
                                             path_out=self.path_datasets,
                                             nb_samples=nb_sample_test_ood_topo
                                             )

    def evaluate_augmented_simulator(self,
                                     augmented_simulator,
                                     batch_size=32,
                                     # "all" or the list of dataset name on which to perform the evaluation
                                     dataset: str = "all",  # TODO
                                     EL_tolerance=0.04,
                                     LCE_tolerance=1e-3,
                                     KCL_tolerance=1e-2,
                                     active_flow=True,
                                     save_path=None  # currently unused
                                     ):
        print("A log file including some verifications is created at root directory with the name logs.log")
        self._create_training_simulator()
        li_dataset = []
        if dataset == "all":
            li_dataset = [self.val_dataset, self._test_dataset, self._test_ood_topo_dataset]
            keys = ["val", "test", "test_ood_topo"]
        elif dataset == "val" or dataset == "val_dataset":
            li_dataset = [self.val_dataset]
            keys = ["val"]
        elif dataset == "test" or dataset == "test_dataset":
            li_dataset = [self._test_dataset]
            keys = ["test"]
        elif dataset == "test_ood_topo" or dataset == "test_ood_topo_dataset":
            li_dataset = [self._test_ood_topo_dataset]
            keys = ["test_ood_topo"]
        else:
            raise RuntimeError(f"Unknown dataset {dataset}")

        res = {}
        for dataset_, nm in zip(li_dataset, keys):
            logging.info("Experiment on dataset : {}".format(nm))
            tmp, ref_data, predictions = self._aux_evaluate_on_single_dataset(dataset_,
                                                                              augmented_simulator=augmented_simulator,
                                                                              batch_size=batch_size,
                                                                              EL_tolerance=EL_tolerance,
                                                                              LCE_tolerance=LCE_tolerance,
                                                                              KCL_tolerance=KCL_tolerance,
                                                                              active_flow=active_flow
                                                                             )
            res[nm] = copy.deepcopy(tmp)
            self.observations[nm] = copy.deepcopy(ref_data)
            self.predictions[nm] = copy.deepcopy(predictions)
        return res

    def _aux_evaluate_on_single_dataset(self,
                                        dataset,
                                        augmented_simulator,
                                        batch_size,
                                        EL_tolerance=0.04,
                                        LCE_tolerance=1e-3,
                                        KCL_tolerance=1e-2,
                                        active_flow=True
                                        ):
        predictions = augmented_simulator.evaluate(dataset, batch_size)
        ref_data = dataset.get_data(np.arange(len(dataset)))
        logging.info("Experimented simulator : {}".format(augmented_simulator.name))
        res = self.evaluation.do_evaluations(env=self.training_simulator._simulator,  # TODO this is relatively ugly
                                             env_name=None,
                                             predictions=predictions,
                                             observations=ref_data,
                                             choice="predictions",  # we want to evaluate only the predictions here
                                             EL_tolerance=EL_tolerance,
                                             LCE_tolerance=LCE_tolerance,
                                             KCL_tolerance=KCL_tolerance,
                                             active_flow=active_flow,
                                             save_path=None  # TODO currently not used
                                             )
        return res, ref_data, predictions

    def _create_training_simulator(self):
        """"""
        if self.training_simulator is None:
            self.training_simulator = Grid2opSimulator(get_kwargs_simulator_scenario1(),
                                                       initial_chronics_id=self.initial_chronics_id,
                                                       # i use 994 chronics out of the 904 for training
                                                       chronics_selected_regex="^((?!(.*9[0-9][0-9].*)).)*$"
                                                       )

    def _fills_actor_simulator(self):
        """This function is only called when the data are simulated"""
        self._create_training_simulator()
        self.training_simulator.seed(self.train_env_seed)

        self.val_simulator = Grid2opSimulator(get_kwargs_simulator_scenario1(),
                                              initial_chronics_id=self.initial_chronics_id,
                                              # i use 50 full chronics for testing
                                              chronics_selected_regex=".*9[0-4][0-9].*")
        self.val_simulator.seed(self.val_env_seed)

        self.test_simulator = Grid2opSimulator(get_kwargs_simulator_scenario1(),
                                               initial_chronics_id=self.initial_chronics_id,
                                               # i use 25 full chronics for testing
                                               chronics_selected_regex=".*9[5-9][0-4].*")
        self.test_simulator.seed(self.test_env_seed)

        self.test_ood_topo_simulator = Grid2opSimulator(get_kwargs_simulator_scenario1(),
                                                        initial_chronics_id=self.initial_chronics_id,
                                                        # i use 25 full chronics for testing
                                                        chronics_selected_regex=".*9[5-9][5-9].*")
        self.test_ood_topo_simulator.seed(self.test_ood_topo_env_seed)

        self.training_actor = get_actor_training_scenario1(self.training_simulator)
        self.training_actor.seed(self.train_actor_seed)

        self.val_actor = get_actor_test_scenario1(self.val_simulator)
        self.val_actor.seed(self.val_actor_seed)

        self.test_actor = get_actor_test_scenario1(self.test_simulator)
        self.test_actor.seed(self.test_actor_seed)

        self.test_ood_topo_actor = get_actor_test_ood_topo_scenario1(self.test_ood_topo_simulator)
        self.test_ood_topo_actor.seed(self.test_ood_topo_actor_seed)
