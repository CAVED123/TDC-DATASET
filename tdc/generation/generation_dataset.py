import pandas as pd
import numpy as np
import os, sys, json 
import warnings
warnings.filterwarnings("ignore")

from .. import base_dataset
from ..utils import *


class DataLoader(base_dataset.DataLoader):
	def __init__(self, name, path, print_stats, dataset_names):
		'''
		Arguments:
			name: fuzzy name of the generation dataset. e.g., uspto50k, qed, drd, ... 
			path: directory path that stores the dataset, e.g., ./data
			print_stats: bool, whether print the stats.  
			dataset_names: exact names of dataset  e.g., ['uspto50k', 'qed', 'drd2', 'logp']
		returns:
			None
		'''
		input_smiles, output_smiles = generation_dataset_load(name, path, dataset_names)
		self.name = name 
		self.path = path 
		self.print_stats = print_stats 
		self.dataset_names = dataset_names 
		self.input_smiles = input_smiles 
		self.output_smiles = output_smiles 
		if print_stats: 
			self.print_stats() 

	# def __init__(self, name, path, print_stats, dataset_names):
	# 	if name.lower() in retrosyn_dataset_names.keys():  
	# 		print_sys("Tip: Use tdc.utils.target_list('" + name.lower() + "') to retrieve all available label targets.")

	def print_stats(self):
		print("There are " + str(len(self.input_smiles)) + ' paired samples', flush = True, file = sys.stderr)


	def get_data(self, format = 'df'):
		if format == 'df':
			return pd.DataFrame({'input': self.input_smiles, 'output':self.output_smiles})
		elif format == 'dict':
			return {'input': self.input_smiles, 'output':self.output_smiles} 
		else:
			raise AttributeError("Please use the correct format input")


	def get_split(self, method = 'random', seed = 'benchmark', frac = [0.7, 0.1, 0.2]):
		'''
		Arguments:
			method: splitting schemes: random, cold_drug, cold_target
			seed: 'benchmark' seed set to 1234, or int values
			frac: train/val/test split
		'''
		if seed == 'benchmark':
			seed = 1234

		df = self.get_data(format = 'df')

		if method == 'random':
			return create_fold(df, seed, frac)
		else:
			raise AttributeError("Please use the correct split method")




