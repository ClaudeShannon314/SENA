import random
import numpy as np
import torch
import pandas as pd
import os
import scanpy as sc
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torch.utils.data.sampler import Sampler
from dataset import SCDataset, SimuDataset
from collections import defaultdict
from tqdm import tqdm

## MMD LOSS
class MMD_loss(nn.Module):
    def __init__(self, kernel_mul = 2.0, kernel_num = 5, fix_sigma=None):
        super().__init__()
        self.kernel_num = kernel_num
        self.kernel_mul = kernel_mul
        self.fix_sigma = fix_sigma
        return
    def gaussian_kernel(self, source, target, kernel_mul=2.0, kernel_num=5, fix_sigma=None):
        n_samples = int(source.size()[0])+int(target.size()[0])
        total = torch.cat([source, target], dim=0)

        total0 = total.unsqueeze(0).expand(int(total.size(0)), int(total.size(0)), int(total.size(1)))
        total1 = total.unsqueeze(1).expand(int(total.size(0)), int(total.size(0)), int(total.size(1)))
        L2_distance = ((total0-total1)**2).sum(2) 
        if fix_sigma:
            bandwidth = fix_sigma
        else:
            bandwidth = torch.sum(L2_distance.data) / (n_samples**2-n_samples)
        bandwidth /= kernel_mul ** (kernel_num // 2)
        bandwidth_list = [bandwidth * (kernel_mul**i) for i in range(kernel_num)]
        kernel_val = [torch.exp(-L2_distance / bandwidth_temp) for bandwidth_temp in bandwidth_list]
        return sum(kernel_val)

    def forward(self, source, target):
        batch_size = int(source.size()[0])
        kernels = self.gaussian_kernel(source, target, kernel_mul=self.kernel_mul, kernel_num=self.kernel_num, fix_sigma=self.fix_sigma)
        XX = kernels[:batch_size, :batch_size]
        YY = kernels[batch_size:, batch_size:]
        XY = kernels[:batch_size, batch_size:]
        YX = kernels[batch_size:, :batch_size]
        loss = torch.mean(XX + YY - XY -YX)
        return loss


def build_gene_go_relationships_latent(in_dim, out_dim):

    #init relationships dict
    rel_dict = defaultdict(list)
    mult = in_dim//out_dim
    for i in range(out_dim):
        for j in range(mult):
            rel_dict[mult*i+j].append(i)
    return rel_dict

def build_gene_go_relationships_latent_deltas(gos):

    go_to_zs = pd.read_csv(os.path.join('..','..','data','delta_selected_pathways','go_2_z_post_heuristic.csv'))

    #init relationships dict
    rel_dict = defaultdict(list)
    gos = list(gos)

    ###
    for go, z in zip(go_to_zs['GO'], go_to_zs['Z']):
        rel_dict[gos.index(go)].append(z-1)
    
    return rel_dict

def build_gene_go_relationships(dataset):

    ## get genes
    genes = dataset.genes

    #GO_to_ensembl_id_assignment = pd.read_csv(os.path.join('..','..','data','GO_to_ensembl_id_assignment_gosize5.csv'))
    GO_to_ensembl_id_assignment = pd.read_csv(os.path.join('..','..','data','delta_selected_pathways','go_kegg_gene_map.tsv'),sep='\t')
    GO_to_ensembl_id_assignment.columns = ['GO_id','ensembl_id']
    gos = pd.read_csv(os.path.join('..','..','data','delta_selected_pathways','go_2_z_post_heuristic.csv'))['GO'].values.tolist()

    go_dict, gen_dict = dict(zip(gos, range(len(gos)))), dict(zip(genes, range(len(genes))))
    rel_dict = defaultdict(list)

    for go, gen in tqdm(zip(GO_to_ensembl_id_assignment['GO_id'], GO_to_ensembl_id_assignment['ensembl_id']), total = GO_to_ensembl_id_assignment.shape[0]):
        if (gen in genes) and (go in gos):
            rel_dict[gen_dict[gen]].append(go_dict[go])

    return gos, genes, rel_dict


def get_data(batch_size=32, mode='train', perturb_targets=None):
    assert mode in ['train', 'test'], 'mode not supported!'

    if mode == 'train':
        dataset = SCDataset(perturb_type='single', perturb_targets=perturb_targets)
        train_idx, test_idx = split_scdata(
            dataset, 
            #split_ptbs=['KLF1', 'BAK1', 'CEBPE', 'UBASH3B', 'ETS2', 'OSR2', 'SLC4A1','SET', 'ELMSAN1', 'MAP2K6', 'FOXF1', 'C19orf26', 'FOXA1','UBASH3A'],
            split_ptbs = ['FOXF1', 'PRDM1', 'HK2', 'ZNF318', 'CEBPA', 'JUN', 'LHX1', 'CSRNP1', 'MAP7D1', 'CDKN1C', 'NIT1'],
            batch_size=batch_size
        ) # leave out some cells from the top 12 single target-gene interventions
    elif mode == 'test':
        assert perturb_targets is not None, 'perturb_targets has to be specified during testing, otherwise the index might be mismatched!'
        dataset = SCDataset(perturb_type='double', perturb_targets=perturb_targets)

    ptb_genes = dataset.ptb_targets
    
    if mode == 'train':
        dataset1 = Subset(dataset, train_idx)
        ptb_name = dataset.ptb_names[train_idx]
        dataloader = DataLoader(
            dataset1,
            batch_sampler=SCDATA_sampler(dataset1, batch_size, ptb_name),
            num_workers=0
        )
        
        dim = dataset[0][0].shape[0]
        cdim = dataset[0][2].shape[0]

        dataset2 = Subset(dataset, test_idx)
        ptb_name = dataset.ptb_names[test_idx]
        dataloader2 = DataLoader(
            dataset2,
            batch_sampler=SCDATA_sampler(dataset2, 8, ptb_name), #using 8 coz 20% of cells somtimes is lower than 128 and it drops that gene
            num_workers=0
        )

        return dataloader, dataloader2, dim, cdim, ptb_genes
    else:	
        dataloader = DataLoader(
            dataset,
            batch_sampler=SCDATA_sampler(dataset, batch_size),
            num_workers=0
        )
        
        dim = dataset[0][0].shape[0]
        cdim = dataset[0][2].shape[0]

        return dataloader, dim, cdim, ptb_genes


def get_simu_data(batch_size=32, mode='train', perturb_targets=None):
    assert mode in ['train', 'test'], 'mode not supported!'

    if mode == 'train':
        dataset = SimuDataset(perturb_type='single', perturb_targets=perturb_targets)
        train_idx, test_idx = split_simudata(
            dataset,
            batch_size=batch_size
        ) # leave out some cells from the top 14 single target-gene interventions
    elif mode == 'test':
        assert perturb_targets is not None, 'perturb_targets has to be specified during testing, otherwise the index might be mismatched!'
        dataset = SimuDataset(perturb_type='double', perturb_targets=perturb_targets)

    ptb_genes = dataset.ptb_targets
        
    if mode == 'train':
        dataset1 = Subset(dataset, train_idx)
        ptb_name = dataset.ptb_names[train_idx]
        dataloader = DataLoader(
            dataset1,
            batch_sampler=SCDATA_sampler(dataset1, batch_size, ptb_name),
            num_workers=0
        )

        dim = dataset[0][0].shape[0]
        cdim = dataset[0][2].shape[0]

        dataset2 = Subset(dataset, test_idx)
        ptb_name = dataset.ptb_names[test_idx]
        dataloader2 = DataLoader(
            dataset2,
            batch_sampler=SCDATA_sampler(dataset2, batch_size, ptb_name),
            num_workers=0
        )
        return dataloader, dataloader2, dim, cdim, ptb_genes, dataset.nonlinear
    else:	
        dataloader = DataLoader(
            dataset,
            batch_sampler=SCDATA_sampler(dataset, batch_size),
            num_workers=0
        )
        
        dim = dataset[0][0].shape[0]
        cdim = dataset[0][2].shape[0]

        return dataloader, dim, cdim, ptb_genes, dataset.nonlinear


def split_simudata(simudataset, batch_size=32):
    num_sample = 1024

    test_idx = []
    train_idx = []
    from tqdm import tqdm
    for ptb in tqdm(simudataset.ptb_targets):
        idx = list(np.where(simudataset.ptb_names == ptb)[0])
        test_idx.append(idx[0:num_sample])
        train_idx.append(idx[num_sample:2*num_sample])

    test_idx = list(np.hstack(test_idx))
    train_idx = list(np.hstack(train_idx)) 
    
    return train_idx, test_idx



# leave out some cells from the split_ptbs
def split_scdata(scdataset, split_ptbs, batch_size=32):

    # num_batch = 96 // batch_size
    # num_sample = num_batch * batch_size
    pct = 0.2

    test_idx = []
    for ptb in split_ptbs:
        idx = list(np.where(scdataset.ptb_names == ptb)[0])
        #print(f"{ptb} - {idx}")
        test_idx.append(np.random.choice(idx, int(len(idx)*pct), replace=False))
        #test_idx.append(idx[0:num_sample])

    test_idx = list(np.hstack(test_idx))
    train_idx = [l for l in range(len(scdataset)) if l not in test_idx]
    
    return train_idx, test_idx


# a special batch sampler that groups only cells from the same interventional distribution into a batch
class SCDATA_sampler(Sampler):
    def __init__(self, scdataset, batchsize, ptb_name=None):
        self.intervindices = []
        self.len = 0
        if ptb_name is None:
            ptb_name = scdataset.ptb_names
        for ptb in set(ptb_name):
            idx = np.where(ptb_name == ptb)[0]
            self.intervindices.append(idx)
            self.len += len(idx) // batchsize
        self.batchsize = batchsize
    
    def __iter__(self):
        comb = []
        for i in range(len(self.intervindices)):
            random.shuffle(self.intervindices[i])
        
            interv_batches = chunk(self.intervindices[i], self.batchsize)
            if interv_batches:
                comb += interv_batches

        combined = [batch.tolist() for batch in comb]
        random.shuffle(combined)
        return iter(combined)
    
    def __len__(self):
        return self.len


def chunk(indices, chunk_size):
    split = torch.split(torch.tensor(indices), chunk_size)
    
    if len(indices) % chunk_size == 0:
        return split
    elif len(split) > 0:
        return split[:-1]
    else:
        return None

