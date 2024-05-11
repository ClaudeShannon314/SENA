import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from networkx.drawing.nx_agraph import graphviz_layout
import scanpy as sc
import pickle
import torch
from inference import evaluate_single_leftout, evaluate_double
import pandas as pd 
import os
import seaborn as sns

def draw(pdag, colored_set=set(), solved_set=set(), affected_set=set(), nw_ax=None, edge_weights=None, savefile=None, node_label=None):
    """ 
    plot a partially directed graph
    """
    plt.clf()

    p = pdag.nnodes

    if nw_ax is None:
        nw_ax = plt.subplot2grid((4, 4), (0, 0), colspan=12, rowspan=12)

    plt.gcf().set_size_inches(20, 20)

    # directed edges
    d = nx.DiGraph()
    d.add_nodes_from(list(range(p)))
    for (i, j) in pdag.arcs:
        d.add_edge(i, j)

    # undirected edges
    e = nx.Graph()
    try:
        for pair in pdag.edges:
            (i, j) = tuple(pair, length = 10)
            e.add_edge(i, j)
    except:
        print('there are no undirected edges')
    
    # edge color
    if edge_weights is not None:
        color_d = []
        for i,j in d.edges:
            color_d.append(edge_weights[i,j])

        color_e = []
        for i,j in e.edges:
            color_e.append(edge_weights[i, j])
    else:
        color_d = 'k'
        color_e = 'k'


    # plot
    print("plotting...")
    # pos = nx.circular_layout(d)
    pos = graphviz_layout(d, prog='dot')
    nx.draw(e, pos=pos, node_color='w', style = 'dashed',  edge_cmap=plt.cm.Blues, edge_vmin=-0.025, edge_vmax=0.025, edge_color=color_e)
    color = ['w']*p
    for i in affected_set:
        color[i] = 'orange'
    for i in colored_set:
        color[i] = 'y'
    for i in solved_set:
        color[i] = 'grey'
    nx.draw(d, pos=pos, node_color=color, ax=nw_ax, edge_cmap=plt.cm.RdBu_r, edge_vmin=-0.025, edge_vmax=0.025, edge_color=color_d, width=1.5) #  edge_color='blue',
    nx.draw_networkx_labels(d, pos, labels={node: node_label[node] for node in range(p)}, ax=nw_ax, font_size=12.5)

    if savefile is not None:
        plt.savefig(savefile)
    plt.show()
    plt.close()

def draw_spectrum(A, B, savefile=None):
    plt.clf()
    plt.figure(figsize=(3,3))
    e_A = np.linalg.eigvalsh(np.matmul(A.T, A))[::-1]
    e_B = np.linalg.eigvalsh(np.matmul(B.T, B))[::-1]
    plt.plot(np.maximum(e_A,0)**0.5, label=r'$(I-B)^{-1}$')
    plt.plot(np.maximum(e_B,0)**0.5, label=r'$B$')
    plt.legend()
    plt.ylabel('eigenvalues')
    plt.xlabel('index')
    plt.title('Spectrum of SCM')
    plt.tight_layout()
    
    if savefile is not None:
        plt.savefig(savefile)
    plt.show()
    plt.close()

def visualize_data_generation(model_name = 'gosize5_orig_Adam'):

    #load data
    adata = sc.read_h5ad('./../../data/Norman2019_raw.h5ad')
    savedir = f'./../../result/{model_name}' 

    with open(f'{savedir}/ptb_targets.pkl', 'rb') as f:
        ptb_targets = pickle.load(f)

    ## load gosize=5 files
    GO_to_ensembl_id_assignment = pd.read_csv(os.path.join('..', '..', 'data', 'GO_to_ensembl_id_assignment_gosize5.csv'))

    # keep only GO_genes
    adata = adata[:, adata.var_names.isin(GO_to_ensembl_id_assignment['ensembl_id'])]
    ctrl_X = adata.X.toarray()

    #load model
    model = torch.load(f'{savedir}/best_model.pt') 
    mode = 'CMVAE'

    ## generate test results
    rmse, signerr, gt_y, pred_y, c_y, gt_x, mu, var = evaluate_single_leftout(model, savedir, model.device, mode)
    C_y = [','.join([str(l) for l in np.where(c_y[i]!=0)[0]]) for i in range(c_y.shape[0])]

    ## generate plots
    all_data = np.vstack([ctrl_X, gt_y, pred_y])
    adata_new = sc.AnnData(all_data)

    #plot them
    sc.tl.pca(adata_new, svd_solver='arpack')
    sc.pp.neighbors(adata_new, n_neighbors=30, n_pcs=50)
    sc.tl.umap(adata_new, min_dist=0.3) 
    
    #plot for each target
    for c in set(C_y):
        label = ['NA' for _ in range(len(ctrl_X))] + ['Actual Cells' if C_y[i]==c else 'NA' for i in range(len(C_y))] + ['Generated Cells' if C_y[i]==c else 'NA' for i in range(len(C_y))]
        adata_new.obs['label'] = label
        sc.pl.umap(adata_new, size=50, color=['label'], 
                legend_fontsize=14, groups=['Actual Cells','Generated Cells'], 
                title=ptb_targets[int(c)], 
                palette={'Actual Cells': 'blue', 
                            'Generated Cells': 'orange',
                            'NA': 'grey'
                        },
                legend_loc=None,  
                save=f'_test_{ptb_targets[int(c)]}_CMVAE-obs_{model_name}.png'
                )

def visualize_data_generation_comparison(model_names = ['gosize5_orig_Adam']):

    def retrieve_single_run(model_name):

        #load data
        adata = sc.read_h5ad('./../../data/Norman2019_raw.h5ad')
        savedir = f'./../../result/{model_name}' 

        with open(f'{savedir}/ptb_targets.pkl', 'rb') as f:
            ptb_targets = pickle.load(f)

        ## load gosize=5 files
        GO_to_ensembl_id_assignment = pd.read_csv(os.path.join('..', '..', 'data', 'GO_to_ensembl_id_assignment_gosize5.csv'))

        # keep only GO_genes
        adata = adata[:, adata.var_names.isin(GO_to_ensembl_id_assignment['ensembl_id'])]
        ctrl_X = adata.X.toarray()

        #load model
        model = torch.load(f'{savedir}/best_model.pt') 
        mode = 'CMVAE'

        ## generate test results
        rmse, signerr, gt_y, pred_y, c_y, gt_x, mu, var = evaluate_single_leftout(model, savedir, model.device, mode)
        C_y = [','.join([str(l) for l in np.where(c_y[i]!=0)[0]]) for i in range(c_y.shape[0])]

        return ctrl_X, gt_y, pred_y, ptb_targets, C_y
    
    preds = []
    for model_name in model_names:
        ctrl_X, gt_y, pred_y, ptb_targets, C_y = retrieve_single_run(model_name)
        preds.append(pred_y)

    ## generate plots
    all_data = np.vstack([ctrl_X, gt_y, np.vstack(preds)])
    adata_new = sc.AnnData(all_data)

    #plot them
    sc.tl.pca(adata_new, svd_solver='arpack')
    sc.pp.neighbors(adata_new, n_neighbors=30, n_pcs=50)
    sc.tl.umap(adata_new, min_dist=0.3) 

    ## create palettes
    palette_groups = sns.color_palette("husl", len(model_names))
    palette_colors = ['#%02x%02x%02x'%tuple((np.array(color)*255).astype(int)) for color in palette_groups]
    palette_dict = {'Actual Cells': 'blue'}
    palette_dict.update({f'Generated Cells_{mn}':pcolor for mn,pcolor in zip(model_names, palette_colors)})
    palette_dict.update({'NA': '#C0C0C08F'})

    #plot for each target
    for c in set(C_y):
        
        legend_groups = []
        for mn in model_names:
            legend_groups += [f'Generated Cells_{mn}' if C_y[i]==c else 'NA' for i in range(len(C_y))]

        label = ['NA' for _ in range(len(ctrl_X))] + ['Actual Cells' if C_y[i]==c else 'NA' for i in range(len(C_y))] + legend_groups
        adata_new.obs['label'] = label
        sizes = [30 if l != 'NA' else 15 for l in label]

        sc.pl.umap(adata_new, size=sizes, color=['label'], 
                legend_fontsize=14, groups=['Actual Cells'] + legend_groups, 
                title=ptb_targets[int(c)], 
                palette=palette_dict,
                #legend_loc=None,  
                save=f'_test_{ptb_targets[int(c)]}_CMVAE-obs_comparison.png'
                )

def visualize_data_generation_double_comparison(model_names = ['gosize5_orig_Adam']):
    
    def retrieve_single_run(model_name):

        #load data
        adata = sc.read_h5ad('./../../data/Norman2019_raw.h5ad')
        savedir = f'./../../result/{model_name}' 

        with open(f'{savedir}/ptb_targets.pkl', 'rb') as f:
            ptb_targets = pickle.load(f)

        ## load gosize=5 files
        GO_to_ensembl_id_assignment = pd.read_csv(os.path.join('..', '..', 'data', 'GO_to_ensembl_id_assignment_gosize5.csv'))

        # keep only GO_genes
        adata = adata[:, adata.var_names.isin(GO_to_ensembl_id_assignment['ensembl_id'])]
        ctrl_X = adata.X.toarray()

        #load model
        model = torch.load(f'{savedir}/best_model.pt') 
        mode = 'CMVAE'

        ## generate test results
        rmse, signerr, gt_y, pred_y, c_y, gt_x, mu, var = evaluate_double(model, savedir, model.device, mode, temp=1)
        C_y = [','.join([str(l) for l in np.where(c_y[i]!=0)[0]]) for i in range(c_y.shape[0])]

        return ctrl_X, gt_y, pred_y, ptb_targets, C_y
    
    preds = []
    for model_name in model_names:
        ctrl_X, gt_y, pred_y, ptb_targets, C_y = retrieve_single_run(model_name)
        preds.append(pred_y)

    ## generate plots
    all_data = np.vstack([ctrl_X, gt_y, np.vstack(preds)])
    adata_new = sc.AnnData(all_data)

    #plot them
    sc.tl.pca(adata_new, svd_solver='arpack')
    sc.pp.neighbors(adata_new, n_neighbors=30, n_pcs=50)
    sc.tl.umap(adata_new, min_dist=0.3) 

    ## create palettes
    palette_groups = sns.color_palette("husl", len(model_names))
    palette_colors = ['#%02x%02x%02x'%tuple((np.array(color)*255).astype(int)) for color in palette_groups]
    palette_dict = {'Actual Cells': 'blue'}
    palette_dict.update({f'Generated Cells_{mn}':pcolor for mn,pcolor in zip(model_names, palette_colors)})
    palette_dict.update({'NA': '#C0C0C02F'})

    #plot for each target
    for c in set(C_y):
        
        legend_groups = []
        for mn in model_names:
            legend_groups += [f'Generated Cells_{mn}' if C_y[i]==c else 'NA' for i in range(len(C_y))]

        idx = c.split(',') 
        label = ['NA' for _ in range(len(ctrl_X))] + ['Actual Cells' if C_y[i]==c else 'NA' for i in range(len(C_y))] + legend_groups
        adata_new.obs['label'] = label
        sizes = [45 if l != 'NA' else 15 for l in label]

        sc.pl.umap(adata_new, size=sizes, color=['label'], 
                legend_fontsize=14, groups=['Actual Cells'] + legend_groups, 
                title=f'{ptb_targets[int(idx[0])]}+{ptb_targets[int(idx[1])]}', 
                palette=palette_dict,
                #legend_loc=None,  
                save=f'_test_{ptb_targets[int(idx[0])]}+{ptb_targets[int(idx[1])]}_CMVAE-obs_double_comparison.png'
                )


## single perturbations
model_names = ['gosize5_orig_Adam', 'gosize5_sparse_unfreezed_NA_Adam', 'gosize5_sparse_unfreezed_vincenzo_Adam']
visualize_data_generation_comparison(model_names)
visualize_data_generation_double_comparison(model_names)