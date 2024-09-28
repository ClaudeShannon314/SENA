import pickle
import os
from sklearn.preprocessing import MinMaxScaler
from tqdm import tqdm
import pandas as pd
import utils
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
from statannotations.Annotator import Annotator

def compute_activation_df(na_activity_score, scoretype, gos, mode, gene_go_dict, genename_ensemble_dict, ptb_targets):

    ## define control cells
    ctrl_cells = na_activity_score[na_activity_score.index == 'ctrl'].to_numpy()

    ## init df
    ttest_df = []

    for knockout in tqdm(ptb_targets):

        if knockout not in genename_ensemble_dict:
            continue
        
        #get knockout cells       
        knockout_cells = na_activity_score[na_activity_score.index == knockout].to_numpy()

        #compute affected genesets
        if mode[:4] == 'sena':
            belonging_genesets = [geneset for geneset in gos if geneset in gene_go_dict[genename_ensemble_dict[knockout]]] 

        for i, geneset in enumerate(gos):
            
            if scoretype == 'mu_diff':
                score = abs(ctrl_cells[:,i].mean() - knockout_cells[:,i].mean())

            #append info
            if mode[:4] == 'sena':
                ttest_df.append([knockout, geneset, scoretype, score, geneset in belonging_genesets])
            elif mode[:7] == 'regular' or mode[:2] == 'l1':
                ttest_df.append([knockout, i, scoretype, score, i in belonging_genesets])

    ttest_df = pd.DataFrame(ttest_df)
    ttest_df.columns = ['knockout', 'geneset', 'scoretype', 'score', 'affected']

    return ttest_df


dataset = 'full_go'
mode = 'sena_delta_0'
model_name = f'{dataset}_{mode}'
seed = 42
latdim = 105
layer = 'fc1'

#load summary file
with open(os.path.join(f'./../../result/uhler/{model_name}/seed_{seed}_latdim_{latdim}/post_analysis_{model_name}_seed_{seed}_latdim_{latdim}.pickle'), 'rb') as handle:
    model_summary = pickle.load(handle)

#activation layer
_, _, ptb_targets_all, ptb_targets_affected, gos, rel_dict, gene_go_dict, genename_ensemble_dict = utils.load_norman_2019_dataset()
fc1 = model_summary[layer]

#compute DA by geneset at the output of the SENA layer
DA_df_by_geneset = compute_activation_df(fc1, scoretype = 'mu_diff', gos=gos, mode=mode, 
                                        gene_go_dict=gene_go_dict, genename_ensemble_dict=genename_ensemble_dict,
                                        ptb_targets=ptb_targets_affected)

"""p-value analysis"""

#th gene
th_genes = 7

# Only 
affected_counter = DA_df_by_geneset.groupby(['knockout'])['affected'].sum()
relevant_knockouts = sorted(affected_counter[affected_counter.values>=th_genes].index)
sorted_knockouts = affected_counter[relevant_knockouts].sort_values(ascending=False).index

# Filter
DA_df_by_geneset_filtered = DA_df_by_geneset[DA_df_by_geneset['knockout'].isin(relevant_knockouts)]

# Set the 'knockout' column to categorical with specified order
DA_df_by_geneset_filtered['knockout'] = pd.Categorical(
    DA_df_by_geneset_filtered['knockout'],
    categories=sorted_knockouts,
    ordered=True
)

# Create pairs for statistical comparison
pairs = [((knockout, False), (knockout, True)) for knockout in sorted_knockouts]


"""plot"""

# Set the style and color palette
sns.set(style='whitegrid')  # Adds a clean grid to the background
custom_palette = sns.color_palette("Set2")[:2]  # Choose a fancy color palette

# Adjusting the data to plot with seaborn
plt.figure(figsize=(8, 10))

# Create a boxplot with customizations
ax = sns.boxplot(
    x='knockout',
    y='score',
    hue='affected',
    data=DA_df_by_geneset_filtered,
    fliersize=3,
    palette=custom_palette,
    linewidth=1.5,
    whis=1.5,  # Adjust whisker length
    boxprops=dict(edgecolor='black'),
    medianprops=dict(color='black', linewidth=2),
    whiskerprops=dict(color='black'),
    capprops=dict(color='black'),
    flierprops=dict(
        marker='o',                # Marker style
        markerfacecolor='black',     # Fill color of outliers
        markeredgecolor='black',     # Edge color of outliers
        markersize=2,              # Size of outlier markers
        linestyle='none'           # No connecting lines
    )
)

# Initialize the Annotator
annotator = Annotator(
    ax,
    pairs,
    data=DA_df_by_geneset_filtered,
    x='knockout',
    y='score',
    hue='affected'
)

# Configure and apply the statistical test
annotator.configure(
    test='Mann-Whitney',
    text_format='star',
    loc='outside',
    comparisons_correction='Benjamini-Hochberg',
    show_test_name=False
)

annotator.apply_and_annotate()

# Customize axes labels and title
plt.xlabel('Knockout', fontsize=20)
plt.ylabel('Score', fontsize=20)
plt.yticks(fontsize=15)
# Add tick marks on the x-axis
plt.tick_params(axis='x', which='both', bottom=True, top=False, length=5, width=1, direction='out')
plt.xticks(ticks=range(len(sorted_knockouts)), labels=sorted_knockouts, fontsize=15)

# Adjust y-axis scale to logarithmic
plt.yscale('log')
plt.ylim(1e-6, 2)

# Adjust legend
plt.legend(title='', fontsize=12, title_fontsize=12, loc='lower right')

# Adjust layout
plt.tight_layout()

# Save the figure before showing it
plt.savefig(os.path.join('./../../', 'figures', 'uhler', 'final_figures', f'DA_analysis_thgene_{th_genes}.pdf'))
