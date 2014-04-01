#!/usr/bin/env python
# encoding: utf-8
"""
test_models_compound.py

Test the so that the genetic models behave as suspected.


Created by Måns Magnusson on 2013-03-07.
Copyright (c) 2013 __MyCompanyName__. All rights reserved.
"""

import sys
import os
from ped_parser import family, individual
from genmod.models import genetic_models
from genmod.variants import genotype


class TestRecessiveModels(object):
    """Test class for testing how the genetic models behave with a recessive variant"""

    def setup_class(self):
        """Setup a simple family with family id 1, sick son id 1,
         healthy father id 2, healthy mother id 3"""
        # Setup family with sick kid, sick father and healthy mother:
        self.recessive_family = family.Family(family_id = '1')
        sick_son = individual.Individual(ind='1', family='1',mother='3', father='2', sex=1, phenotype=2)
        healthy_father = individual.Individual(ind='2', family='1',mother='0', father='0', sex=1, phenotype=1)
        healthy_mother = individual.Individual(ind='3', family='1',mother='0', father='0', sex=2, phenotype=1)
        self.recessive_family.add_individual(healthy_father)
        self.recessive_family.add_individual(sick_son)
        self.recessive_family.add_individual(healthy_mother)
        
        #Setup two variants with only autosomal recessive pattern
        self.recessive_variant = {'CHROM':'1', 'POS':'5', 'ALT':'A', 'REF':'C', 'ID':'rs2230749', '1':'1/1', '2':'0/1', '3':'0/1'}
        self.recessive_dn =  {'CHROM':'1', 'POS':'7', 'ALT':'G', 'REF':'T', 'ID':'.', '1':'1/1', '2':'0/1', '3':'0/0'}
        
        self.recessive_missing = {'CHROM':'1', 'POS':'10', 'ALT':'C', 'REF':'T', 'ID':'.', '1':'1/1', '2':'./.', '3':'0/1'}

        self.not_recessive = {'CHROM':'1', 'POS':'15', 'ALT':'C', 'REF':'T', 'ID':'.', '1':'0/1', '2':'0/1', '3':'./.'}
        
        #This batch simulates two genes, one variant is present in both genes
        batch = {'ABC':{'1_5_A_C':self.recessive_variant, '1_10_C_T':self.recessive_missing, '1_7_G_T':self.recessive_dn},
                'BBC':{'1_10_C_T':self.recessive_missing, '1_15_C_T':self.not_recessive}}
        
        genetic_models.check_genetic_models(batch, self.recessive_family)
    
    def test_recessive_variant(self):
        """Check if variant follows the heterozygous inheritance pattern."""
        assert self.recessive_variant['Inheritance_model']['AR_hom']
        assert not self.recessive_variant['Inheritance_model']['AR_hom_denovo']
        assert not self.recessive_variant['Inheritance_model']['AD']
        assert not self.recessive_variant['Inheritance_model']['AD_denovo']
        assert not self.recessive_variant['Inheritance_model']['AR_compound']
    
    def test_recessive_dn(self):
        """Check if variant follows the heterozygous de novo inheritance pattern."""
        assert not self.recessive_dn['Inheritance_model']['AR_hom']
        assert self.recessive_dn['Inheritance_model']['AR_hom_denovo']
        assert not self.recessive_dn['Inheritance_model']['AD']
        assert not self.recessive_dn['Inheritance_model']['AD_denovo']
        assert not self.recessive_dn['Inheritance_model']['AR_compound']
    
    def test_recessive_missing(self):
        """Check if variant follows both heterozygous inheritance patterns."""
        assert self.recessive_missing['Inheritance_model']['AR_hom']
        assert self.recessive_missing['Inheritance_model']['AR_hom_denovo']
        assert not self.recessive_missing['Inheritance_model']['AD']
        assert not self.recessive_missing['Inheritance_model']['AD_denovo']
        assert not self.recessive_missing['Inheritance_model']['AR_compound']
    
    def test_not_recessive(self):
        """Check that the the variant does not follow any inheritance pattern."""
        assert not self.not_recessive['Inheritance_model']['AR_hom']
        assert not self.not_recessive['Inheritance_model']['AR_hom_denovo']
        assert not self.not_recessive['Inheritance_model']['AD']
        assert not self.not_recessive['Inheritance_model']['AD_denovo']
        assert not self.not_recessive['Inheritance_model']['AR_compound']
    

def main():
    pass


if __name__ == '__main__':
    main()

