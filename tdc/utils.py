import wget
from zipfile import ZipFile 
import os, sys
import numpy as np
import pandas as pd
import json
import warnings
import subprocess
import pickle
from fuzzywuzzy import fuzz
warnings.filterwarnings("ignore")

from .metadata import name2type, name2id, dataset_list, dataset_names
from .metadata import retrosyn_dataset_names, forwardsyn_dataset_names, molgenpaired_dataset_names, generation_datasets

from .target_list import dataset2target_lists

try:
    from urllib.error import HTTPError
    from urllib.parse import quote, urlencode
    from urllib.request import urlopen
except ImportError:
    from urllib import urlencode
    from urllib2 import quote, urlopen, HTTPError

def fuzzy_search(name, dataset_names):
	name = name.lower()
	if name in dataset_list:
		s =  name
	else: 
		s =  get_closet_match(dataset_list, name)[0]
	if s in dataset_names:
		return s
	else:
		raise ValueError(s + " does not belong to this task, please refer to the correct task name!")

def download_wrapper(name, path, dataset_names):
	name = fuzzy_search(name, dataset_names)
	server_path = 'https://dataverse.harvard.edu/api/access/datafile/'
	dataset_path = server_path + str(name2id[name])

	if not os.path.exists(path):
		os.mkdir(path)

	if os.path.exists(os.path.join(path, name + '.' + name2type[name])):
		print_sys('Dataset already downloaded in the local system...')
	else:
		print_sys("Downloading " + name + " ...")
		dataverse_download(dataset_path, path)
	return name

def pd_load(name, path):
	if name2type[name] == 'tab':
		df = pd.read_csv(os.path.join(path, name + '.' + name2type[name]), sep = '\t')
	elif name2type[name] == 'csv':
		df = pd.read_csv(os.path.join(path, name + '.' + name2type[name]))
	else:
		raise ValueError("The file type must be one of tab/csv.")
	return df

def property_dataset_load(name, path, target, dataset_names):
	if target is None:
		target = 'Y'		
	name = download_wrapper(name, path, dataset_names)
	df = pd_load(name, path)
	df = df[df[target].notnull()].reset_index(drop = True)

	return df['X'], df[target], df['ID']

def interaction_dataset_load(name, path, target, dataset_names):
	name = download_wrapper(name, path, dataset_names)
	df = pd_load(name, path)
	if target is None:
		target = 'Y'
	if target not in df.columns.values:
		# for binary interaction data, the labels are all 1. negative samples can be sampled from utils.NegSample function
		df[target] = 1

	df = df[df[target].notnull()].reset_index(drop = True)

	return df['X1'], df['X2'], df[target], df['ID1'], df['ID2']

def generation_dataset_load(name, path, dataset_names):
	name = download_wrapper(name, path, dataset_names)
	df = pd_load(name, path)
	return df['input'], df['target'] 

def get_label_map(name, path, target = None, file_format = 'csv', output_format = 'dict'):
	if target is None:
		target = 'Y'		
	df = pd.read_csv(os.path.join(path, name + '.' + name2type[name]))

	if output_format == 'dict':
		return dict(zip(df[target].values, df['Map'].values))
	elif output_format == 'df':
		return df
	elif output_format == 'array':
		return df['Map'].values
	else:
		raise ValueError("Please use the correct output format, select from dict, df, array.")

def dataverse_download(dataset_path, path):
	wget.download(dataset_path, path)

def convert_y_unit(y, from_, to_):
	"""
	Arguments:
		y: a list of labels
		from_: 'nM' or 'p'
		to_: 'nM' or 'p'

	Returns:
		y: a numpy array of transformed labels
	"""
	if from_ == 'nM':
		y = y
	elif from_ == 'p':
		y = 10**(-y) / 1e-9

	if to_ == 'p':
		y = -np.log10(y*1e-9 + 1e-10)
	elif to_ == 'nM':
		y = y

	return y

def label_transform(y, binary, threshold, convert_to_log, verbose = True):
	"""
	Arguments:
		y: a list of labels
		binary: binarize the label given the threshold
		threshold: threshold values
		convert_to_log: for continuous values such as Kd and etc

	Returns:
		y: a numpy array of transformed labels
	"""

	if (len(np.unique(y)) > 2) and binary:
		if verbose:
			print("Binariztion using threshold' + str(threshold) + ', you use specify your threhsold values by DataLoader(threshold = X)", flush = True, file = sys.stderr)
		y = np.array([1 if i else 0 for i in np.array(y) < threshold])
	else:
		if (len(np.unique(y)) > 2) and convert_to_log:
			if verbose:
				print('To log space...', flush = True, file = sys.stderr)
			y = convert_y_unit(np.array(y), 'nM', 'p') 
		else:
			y = y

	return y

def convert_to_log(y):
	y = convert_y_unit(np.array(y), 'nM', 'p') 
	return y

def convert_back_log(y):
	y = convert_y_unit(np.array(y), 'p', 'nM') 
	return y

def binarize(y, threshold, order = 'ascending'):
	if order == 'ascending':
		y = np.array([1 if i else 0 for i in np.array(y) > threshold])
	elif order == 'descending':
		y = np.array([1 if i else 0 for i in np.array(y) < threshold])
	else:
		raise AttributeError("'order' must be either ascending or descending")
	return y

# random split
def create_fold(df, fold_seed, frac):
	train_frac, val_frac, test_frac = frac
	test = df.sample(frac = test_frac, replace = False, random_state = fold_seed)
	train_val = df[~df.index.isin(test.index)]
	val = train_val.sample(frac = val_frac/(1-test_frac), replace = False, random_state = 1)
	train = train_val[~train_val.index.isin(val.index)]

	return {'train': train.reset_index(drop = True), 
			'valid': val.reset_index(drop = True), 
			'test': test.reset_index(drop = True)}

# cold setting
def create_fold_setting_cold(df, fold_seed, frac, entity):
	train_frac, val_frac, test_frac = frac
	gene_drop = df[entity].drop_duplicates().sample(frac = test_frac, replace = False, random_state = fold_seed).values

	test = df[df[entity].isin(gene_drop)]

	train_val = df[~df[entity].isin(gene_drop)]

	gene_drop_val = train_val[entity].drop_duplicates().sample(frac = val_frac/(1-test_frac), replace = False, random_state = fold_seed).values
	val = train_val[train_val[entity].isin(gene_drop_val)]
	train = train_val[~train_val[entity].isin(gene_drop_val)]

	return {'train': train.reset_index(drop = True), 
			'valid': val.reset_index(drop = True), 
			'test': test.reset_index(drop = True)}

# scaffold split
def create_scaffold_split(df, fold_seed, frac, entity):
	# reference: https://github.com/chemprop/chemprop/blob/master/chemprop/data/scaffold.py
	try:
		from rdkit import Chem
		from rdkit.Chem.Scaffolds import MurckoScaffold
	except:
		raise ImportError("Please install rdkit by 'conda install -c conda-forge rdkit'! ")
	from tqdm import tqdm

	from collections import defaultdict

	s = df[entity].values
	scaffolds = defaultdict(set)
	idx2mol = dict(zip(list(range(len(s))),s))

	for i, smiles in tqdm(enumerate(s), total=len(s)):
		scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol = Chem.MolFromSmiles(smiles), includeChirality = False)
		scaffolds[scaffold].add(i)
	index_sets = sorted(list(scaffolds.values()), key=lambda i: len(i), reverse=True)

	train, val, test = [], [], []
	train_size = int(len(df) * frac[0])
	val_size = int(len(df) * frac[1])
	test_size = len(df) - train_size - val_size
	train_scaffold_count, val_scaffold_count, test_scaffold_count = 0, 0, 0

	for index_set in index_sets:
		if len(train) + len(index_set) <= train_size:
			train += index_set
			train_scaffold_count += 1
		elif len(val) + len(index_set) <= val_size:
			val += index_set
			val_scaffold_count += 1
		else:
			test += index_set
			test_scaffold_count += 1

	return {'train': df.iloc[train].reset_index(drop = True), 
			'valid': df.iloc[val].reset_index(drop = True), 
			'test': df.iloc[test].reset_index(drop = True)}

def train_val_test_split(len_data, frac, seed):
	test_size = int(len_data * frac[2])
	train_size = int(len_data * frac[0])
	val_size = len_data - train_size - test_size
	np.random.seed(seed)
	x = np.array(list(range(len_data)))
	np.random.shuffle(x)
	return x[:train_size], x[train_size:(train_size + val_size)], x[-test_size:]

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def print_sys(s):
	print(s, flush = True, file = sys.stderr)

def _parse_prop(search, proplist):
    """Extract property value from record using the given urn search filter."""
    props = [i for i in proplist if all(item in i['urn'].items() for item in search.items())]
    if len(props) > 0:
        return props[0]['value'][list(props[0]['value'].keys())[0]]

def request(identifier, namespace='cid', domain='compound', operation=None, output='JSON', searchtype=None):
    """
    copied from https://github.com/mcs07/PubChemPy/blob/e3c4f4a9b6120433e5cc3383464c7a79e9b2b86e/pubchempy.py#L238
    Construct API request from parameters and return the response.
    Full specification at http://pubchem.ncbi.nlm.nih.gov/pug_rest/PUG_REST.html
    """
    API_BASE = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug'
    text_types = str, bytes
    if not identifier:
        raise ValueError('identifier/cid cannot be None')
    # If identifier is a list, join with commas into string
    if isinstance(identifier, int):
        identifier = str(identifier)
    if not isinstance(identifier, text_types):
        identifier = ','.join(str(x) for x in identifier)
    
    # Build API URL
    urlid, postdata = None, None
    if namespace == 'sourceid':
        identifier = identifier.replace('/', '.')
    if namespace in ['listkey', 'formula', 'sourceid'] \
            or searchtype == 'xref' \
            or (searchtype and namespace == 'cid') or domain == 'sources':
        urlid = quote(identifier.encode('utf8'))
    else:
        postdata = urlencode([(namespace, identifier)]).encode('utf8')
    comps = filter(None, [API_BASE, domain, searchtype, namespace, urlid, operation, output])
    apiurl = '/'.join(comps)
    # Make request
    response = urlopen(apiurl, postdata)
    return response

def NegSample(df):
    """Negative Sampling for Binary Interaction Dataset
    
    Parameters
    ----------
    df : pandas.DataFrame
        Data File
    """
    raise ValueError


def GetProteinSequence(ProteinID):
	"""Get protein sequence from Uniprot ID
	
	Parameters
	----------
	ProteinID : str
	    Uniprot ID
	
	Returns
	-------
	str
	    Amino acid sequence of input uniprot ID
	"""
	import urllib
	import string
	import urllib.request as ur

	ID = str(ProteinID)
	localfile = ur.urlopen('http://www.uniprot.org/uniprot/' + ID + '.fasta')
	temp = localfile.readlines()
	res = ''
	for i in range(1, len(temp)):
		res = res + temp[i].strip().decode("utf-8")
	return res

def cid2smiles(cid):
	try:
		smiles = _parse_prop({'label': 'SMILES', 'name': 'Canonical'}, json.loads(request(cid).read().decode())['PC_Compounds'][0]['props'])
	except:
		print('cid ' + str(cid) + ' failed, use NULL string')
		smiles = 'NULL'
	return smiles

def get_closet_match(predefined_tokens, test_token, threshold=0.8):
    """Get the closest match by Levenshtein Distance.

    Parameters
    ----------
    predefined_tokens : list of string
        Predefined string tokens.
        
    test_token : string 
        User input that needs matching to existing tokens.
        
    threshold : float in (0, 1), optional (default=0.8)
        The lowest match score to raise errors.

    Returns
    -------

    """
    prob_list = []

    for token in predefined_tokens:
        # print(token)
        prob_list.append(
            fuzz.ratio(str(token).lower(), str(test_token).lower()))

    assert (len(prob_list) == len(predefined_tokens))

    prob_max = np.nanmax(prob_list)
    token_max = predefined_tokens[np.nanargmax(prob_list)]

    # match similarity is low
    if prob_max / 100 < threshold:
        raise ValueError(test_token,
                         "does not match to existing datasets. "
                         "Please double check.")
    return token_max, prob_max / 100

def save_dict(path, obj):
	with open(path, 'wb') as f:
		pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_dict(path):
	with open(path, 'rb') as f:
		return pickle.load(f)

def target_list(name):
	return dataset2target_lists[name]

def retrieve_dataset_names(name):
	return dataset_names[name]