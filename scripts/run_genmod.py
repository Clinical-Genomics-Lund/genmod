#!/usr/bin/env python
# encoding: utf-8
"""
run_genmod.py

Script for annotating genetic models in variant files.

Created by Måns Magnusson on 2014-01-21.
Copyright (c) 2013 __MyCompanyName__. All rights reserved.
"""

import sys
import os
import argparse
import click
from multiprocessing import JoinableQueue, Manager, cpu_count
from codecs import open
from datetime import datetime
from tempfile import mkdtemp
import shutil
import pkg_resources
import genmod

try:
    import cPickle as pickle
except:
    import pickle


from pysam import tabix_index, tabix_compress

from ped_parser import parser
from vcf_parser import vcf_parser

from genmod.utils import variant_consumer, variant_sorter, annotation_parser, variant_printer, variant_annotator


def get_family(family_file, family_type):
    """Return the family"""
    
    my_family_parser = parser.FamilyParser(family_file, family_type)
    # Stupid thing but for now when we only look at one family
    return my_family_parser.families.popitem()[1]

def add_metadata(head, **kwargs):
    """Add metadata for the information added by this script."""
    if not kwargs.get('vep', False):
        head.add_info('ANN', '.', 'String', 'Annotates what feature(s) this variant belongs to.')
    head.add_info('Comp', '.', 'String', "':'-separated list of compound pairs for this variant.")
    head.add_info('GM', '.', 'String', "':'-separated list of genetic models for this variant.")
    head.add_info('MS', '1', 'Integer', "PHRED score for genotype models.")
    if kwargs.get('cadd_file', None) or kwargs.get('cadd_1000g', None):
        head.add_info('CADD', '1', 'Float', "The CADD relative score for this alternative.")
    if kwargs.get('thousand_g', None):
        head.add_info('1000G_freq', '1', 'Float', "Frequency in the 1000G database.")
    return

def print_headers(head, outfile, silent=False):
    """Print the headers to a results file."""
    if outfile:
        with open(outfile, 'w', encoding='utf-8') as f: 
            for head_count in head.print_header():
                f.write(head_count+'\n')
    else:
        if not silent:
            for line in head.print_header():
                print(line)
    return

def check_tabix_index(compressed_file, file_type='cadd', verbose=False):
    """Check if a compressed file have a tabix index. If not build one."""
    if file_type == 'cadd':
        try:
            tabix_index(compressed_file, seq_col=0, start_col=1, end_col=1, meta_char='#')
        except IOError as e:
            if verbose:
                print(e)
    elif file_type == 'vcf':
        try:
            tabix_index(compressed_file, preset='vcf')
        except IOError as e:
            if verbose:
                print(e)
    return

# def print_version(ctx, param, value):
#     # if not value or ctx.resilient_parsing:
#     #     return
#     click.echo(pkg_resources.require("genmod")[0].version)
#     ctx.exit()

class Config(object):
    """Store variables that are used of all subprograms"""
    def __init__(self):
        super(Config, self).__init__()
        self.verbose = False
    
pass_config = click.make_pass_decorator(Config, ensure=True)
default_annotations = os.path.join(os.path.split(os.path.dirname(genmod.__file__))[0], 'annotations/')


###         This is the main script         ###
@click.group()
@click.option('-v', '--verbose', 
                is_flag=True,
                help='Increase output verbosity.'
)
# @click.option('--version', 
#                 is_flag=True, 
#                 callback=print_version,
#                 expose_value=False, 
#                 is_eager=True
# )
@pass_config
def run_genmod(config, verbose):
    """Annotate genetic models in variant files."""
    config.verbose = verbose


###        This is for building new annotations     ###

@click.command()
@click.argument('annotation_file', 
                nargs=1, 
                type=click.Path(exists=True)
)
@click.option('-t' ,'--annotation_type', 
                type=click.Choice(['bed', 'ccds', 'gtf', 'gene_pred']), 
                default='gene_pred',
                help='Specify the format of the annotation file.'
)
@click.option('-o', '--outdir', 
                    type=click.Path(exists=True),
                    default=default_annotations,
                    help=("""Specify the path to a folder where the annotation files should be stored. 
                            Default is the annotations dir of the ditribution.""")
)
@click.option('--splice_padding',
                    type=int, nargs=1, default=2,
                    help='Specify the the number of bases that the exons should be padded with.'
)
@pass_config
def build_annotation(config, annotation_file, annotation_type, outdir, splice_padding):
    """Build a new annotation."""
    if config.verbose:
        click.echo('Building new annotation databases from %s into %s.' % (annotation_file, outdir))
    
    anno_parser = annotation_parser.AnnotationParser(annotation_file, annotation_type, 
                            splice_padding = splice_padding, verbosity=config.verbose)
    
    gene_db = os.path.join(outdir, 'genes.db')
    exon_db = os.path.join(outdir, 'exons.db')
    
    with open(gene_db, 'wb') as f:
        pickle.dump(anno_parser.gene_trees, f)
    
    with open(exon_db, 'wb') as g:
        pickle.dump(anno_parser.exon_trees, g)
    


###           This is for annotating the variants       ###

@click.command()
@click.argument('family_file', 
                    nargs=1, 
                    type=click.Path(exists=True),
                    metavar='<ped_file>'
)
@click.argument('variant_file', 
                    nargs=1, 
                    type=click.Path(exists=True),
                    metavar='<vcf_file>'
)
@click.option('-f' ,'--family_type', 
                type=click.Choice(['ped', 'alt', 'cmms', 'mip']), 
                default='ped',
                help='If the analysis use one of the known setups, please specify which one.'
)
@click.option('--vep', 
                    is_flag=True,
                    help='If variants are annotated with the Variant Effect Predictor.'
)
@click.option('-p' ,'--phased', 
                    is_flag=True,
                    help='If data is phased use this flag.'
)
@click.option('-s' ,'--silent', 
                    is_flag=True,
                    help='Do not print the variants.'
)
@click.option('-g' ,'--whole_gene', 
                    is_flag=True,
                    help='If compounds should be checked in the whole gene regions. Not only exonic/splice sites.'
)
@click.option('-a' ,'--annotation_dir', 
                    type=click.Path(exists=True), 
                    default=default_annotations,
                    help="""Specify the path to the directory where the annotation databases are. 
                            Default is the gene pred files that comes with the distribution."""
)
@click.option('-o', '--outfile', 
                    type=click.Path(exists=False),
                    help='Specify the path to a file where results should be stored.'
)
@click.option('--cadd_file', 
                    type=click.Path(exists=True), 
                    help="""Specify the path to a bgzipped cadd file with variant scores.
                            If no index is present it will be created."""
)
@click.option('--cadd_1000g',
                    type=click.Path(exists=True), 
                    help="""Specify the path to a bgzipped cadd file with variant scores for all 1000g variants.
                            If no index is present it will be created."""
)
@click.option('--thousand_g',
                    type=click.Path(exists=True), 
                    help="""Specify the path to a bgzipped vcf file frequency info of all 1000g variants. 
                            If no index is present it will be created."""
)

@pass_config
def annotate(config, family_file, variant_file, family_type, vep, silent, phased, whole_gene, 
                annotation_dir, cadd_file, cadd_1000g, thousand_g, outfile):
    """Annotate genetic inheritance patterns followed for all variants in a VCF file.
        
        Individuals that are not present in ped file will not be considered in the analysis.
    """
    kwargs = {'config':config, 'family_file':family_file, 'variant_file':variant_file, 
                'family_type':family_type, 'vep':vep, 'silent':silent, 'phased':phased, 
                'whole_gene':whole_gene, 'annotation_dir':annotation_dir, 
                'cadd_file':cadd_file, 'cadd_1000g':cadd_1000g, 'thousand_g':thousand_g, 
                'outfile':outfile, 'verbosity':config.verbose}
    
    verbosity = config.verbose
    gene_db = os.path.join(annotation_dir, 'genes.db')
    exon_db = os.path.join(annotation_dir, 'exons.db')
    try:
        with open(gene_db, 'rb') as f:
            gene_trees = pickle.load(f)
        with open(exon_db, 'rb') as g:
            exon_trees = pickle.load(g)
    except FileNotFoundError:
        print('You need to build annotations! See documentation.')
        pass
    
    family = get_family(family_file, family_type)
    
    if cadd_file:
        if verbosity:
            click.echo('Cadd file! %s' % cadd_file)
        check_tabix_index(cadd_file, 'cadd', verbosity)
    if cadd_1000g:
        if verbosity:
            click.echo('Cadd file! %s' % cadd_1000g)
        check_tabix_index(cadd_1000g, 'cadd', verbosity)
    if thousand_g:
        if config.verbose:
            click.echo('Cadd file! %s' % thousand_g)
        check_tabix_index(thousand_g, 'vcf', verbosity)
    
    variant_parser = vcf_parser.VCFParser(variant_file)
    head = variant_parser.metadata
    
    if set(family.individuals.keys()) != set(variant_parser.individuals):
        
        print('There must be same individuals in ped file and vcf file! Aborting...')
        print('Individuals in PED file: %s' % '\t'.join(list(family.individuals.keys())))
        print('Individuals in VCF file: %s' % '\t'.join(list(variant_parser.individuals)))
        sys.exit()
    
    ##################################################################
    ### The task queue is where all jobs(in this case batches that ###
    ### represents variants in a region) is put the consumers will ###
    ### then pick their jobs from this queue.                      ###
    ##################################################################
    
    variant_queue = JoinableQueue(maxsize=1000)
    # The consumers will put their results in the results queue
    results = Manager().Queue()
    
    # Create a directory to keep track of temp files
    temp_dir = mkdtemp()
    #Adapt the number of processes to the machine that run the analysis    
    # num_model_checkers = (cpu_count()*2-1)
    num_model_checkers = (1)
    
    if verbosity:
        print('Number of CPU:s %s' % cpu_count())
    
    # These are the workers that do the analysis
    model_checkers = [variant_consumer.VariantConsumer(variant_queue, results, kwargs) 
                            for i in range(num_model_checkers)]
    
    for w in model_checkers:
        w.start()
    
    # This process prints the variants to temporary files
    var_printer = variant_printer.VariantPrinter(results, temp_dir, head, kwargs)
    var_printer.start()
    
    if verbosity:
        print('Start parsing the variants ...')
        print('')
        start_time_variant_parsing = datetime.now()
    
    # For parsing the vcf:
    var_annotator = variant_annotator.VariantAnnotator(variant_parser, variant_queue, kwargs)
    var_annotator.annotate()
    
    for i in range(num_model_checkers):
        variant_queue.put(None)
    
    variant_queue.join()
    results.put(None)
    var_printer.join()
    
    chromosome_list = var_annotator.chromosomes
        
    if verbosity:
        print('Cromosomes found in variant file: %s' % ','.join(chromosome_list))
        print('Models checked!')
        print('Start sorting the variants:')
        print('')
        start_time_variant_sorting = datetime.now()
    
    # Add the new metadata to the headers:
    add_metadata(head, kwargs)
    print_headers(head, outfile, silent)
    
    for chromosome in chromosome_list:
        for temp_file in os.listdir(temp_dir):
            if temp_file.split('_')[0] == chromosome:
                var_sorter = variant_sorter.FileSort(os.path.join(temp_dir, temp_file), kwargs)
                var_sorter.sort()
    
    if verbosity:
        print('Sorting done!')
        print('Time for sorting: %s' % str(datetime.now()-start_time_variant_sorting))
        print('')
        print('Time for whole analyis: %s' % str(datetime.now() - start_time_analysis))
    
    # Remove all temp files:
    shutil.rmtree(temp_dir)


###           This is for analyzing the variants       ###


@click.command()    
def analyze():
    """Analyze the annotated variants in a VCF file."""
    pass


run_genmod.add_command(build_annotation)
run_genmod.add_command(annotate)
run_genmod.add_command(analyze)

def main():
    run_genmod()
        

if __name__ == '__main__':
    main()

