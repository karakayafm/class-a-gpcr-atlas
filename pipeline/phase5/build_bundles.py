#!/usr/bin/env python3
"""Phase 5C — site-aware structure viewer bundles.

One bundle per PDB. It contains the receptor instance chains, every approved pharmacological
ligand entity (small molecule, polymer chain or covalent adduct), motif-relevant observed ions,
and — where the size budget allows — the auxiliary chains behind a UI toggle. It never contains
invented coordinates.

    python3 pipeline/phase5/build_bundles.py [--limit N]
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from phase3.mmcif import read, atoms                          # noqa: E402
from common.canonical import content_sha256                   # noqa: E402
IN,P3,P4=ROOT/"data/intermediate",ROOT/"data/intermediate/phase3",ROOT/"data/intermediate/phase4"
WEB=ROOT/"data/web/structures"; SCHEMA_VERSION="5.0.0"
POLYMER={"extracellular_polymer_interface","tethered_ligand_interface"}
# Deposited-chain corrections confirmed against the source entry. In 7XWO, chain D is the
# pharmacological peptide; chain F was incorrectly merged into the same ambiguous polymer
# ligand candidate and must not enter the viewer selection or its contact shell.
EXCLUDED_LIGAND_CHAINS={"7XWO":{"F"}, "3ZEV":{"D"}, "4BV0":{"D"},
                        "4RWA":{"G"}, "6UP7":{"V"}, "7W0N":{"D"},
                        "8F7Q":{"P"}, "8F7R":{"P"}, "8F7S":{"P"}, "8GY7":{"P"},
                        "8G94":{"F","G"}}
NON_LIGAND_STRUCTURES={"8G94"}  # F/G are CD69 antigen, not S1P1 ligands.
STRUCTURE_LIGAND_OVERRIDES={
  "7T9M":{"inventory_ids":{"7T9M:EI:poly:1","7T9M:EI:poly:2"},
           "ligand_chain":"H","ligand_entity":"1","display_ligand_chains":{"H","L"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"3",
           "entity_form":"polymer_chain","ligand_role":"antibody_interaction_partner",
           "binding_mode":"Not specified","binding_site_class":"extracellular_polymer_interface",
           "contact_segments":{"N-term","ECL1","ECL2","ECL3"},"ligand_name":"CS-17 antibody"},
  "7T9N":{"inventory_ids":{"7T9N:EI:poly:1","7T9N:EI:poly:2"},
           "ligand_chain":"H","ligand_entity":"2","display_ligand_chains":{"H","L"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"4",
           "entity_form":"polymer_chain","ligand_role":"antibody_interaction_partner",
           "binding_mode":"Not specified","binding_site_class":"extracellular_polymer_interface",
           "contact_segments":{"N-term","ECL1","ECL2","ECL3"},"ligand_name":"M22 Fab"},
  "7XW7":{"inventory_ids":{"7XW7:EI:poly:1"},"ligand_chain":"A","ligand_entity":"1",
           "receptor_chain":"R","receptor_entity":"2","entity_form":"polymer_chain",
           "ligand_role":"antibody_interaction_partner","binding_mode":"Not specified",
           "binding_site_class":"extracellular_polymer_interface",
           "contact_segments":{"N-term","ECL1","ECL2","ECL3"},"ligand_name":"K1-70 scFv"},
  "6MET":{"inventory_ids":{"6MET:EI:poly:1","6MET:EI:poly:2"},
           "ligand_chain":"G","ligand_entity":"1","display_ligand_chains":{"G","A"},
           "preserve_inventory_selection":True,"receptor_chain":"B","receptor_entity":"3",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "binding_mode":"Not specified","ligand_name":"gp160–CD4 complex"},
  "7FIG":{"inventory_ids":{"7FIG:EI:poly:6","7FIG:EI:poly:7"},
           "ligand_chain":"Y","ligand_entity":"7","display_ligand_chains":{"X","Y"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"5",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Chorionic gonadotropin (alpha/beta heterodimer)"},
  "7FIH":{"inventory_ids":{"7FIH:EI:poly:5","7FIH:EI:poly:6"},
           "ligand_chain":"Y","ligand_entity":"6","display_ligand_chains":{"X","Y"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"4",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Chorionic gonadotropin (alpha/beta heterodimer)"},
  "7FII":{"inventory_ids":{"7FII:EI:poly:5","7FII:EI:poly:6"},
           "ligand_chain":"Y","ligand_entity":"6","display_ligand_chains":{"X","Y"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"4",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Chorionic gonadotropin (alpha/beta heterodimer)"},
  "7T9I":{"inventory_ids":{"7T9I:EI:poly:1","7T9I:EI:poly:2"},
           "ligand_chain":"B","ligand_entity":"2","display_ligand_chains":{"A","B"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"4",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Thyrotropin (alpha/beta heterodimer)"},
  "7UTZ":{"inventory_ids":{"7UTZ:EI:poly:1","7UTZ:EI:poly:2"},
           "ligand_chain":"B","ligand_entity":"2","display_ligand_chains":{"A","B"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"4",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Thyrotropin analogue (alpha/beta heterodimer)"},
  "7XW5":{"inventory_ids":{"7XW5:EI:poly:6","7XW5:EI:poly:7"},
           "ligand_chain":"Y","ligand_entity":"7","display_ligand_chains":{"X","Y"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"5",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Thyrotropin (alpha/beta heterodimer)"},
  "8I2G":{"inventory_ids":{"8I2G:EI:poly:6","8I2G:EI:poly:7"},
           "ligand_chain":"Y","ligand_entity":"7","display_ligand_chains":{"X","Y"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"5",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "ligand_name":"Follitropin (alpha/beta heterodimer)"},
  "7XBX":{"inventory_ids":{"7XBX:EI:poly:4"},"ligand_chain":"R","ligand_entity":"4",
           "ligand_residue_start":1,"ligand_residue_end":124,
           "receptor_chain":"R","receptor_entity":"4","entity_form":"tethered_ligand",
           "binding_site_class":"tethered_ligand_interface",
           "binding_mode":"Not specified",
           "ligand_name":"CX3CL1-like N-terminal fusion segment"},
  "8U1U":{"inventory_ids":{"8U1U:EI:poly:1"},"ligand_chain":"A","ligand_entity":"1",
           "ligand_residue_start":24,"ligand_residue_end":126,
           "receptor_chain":"A","receptor_entity":"1","entity_form":"tethered_ligand",
           "binding_site_class":"tethered_ligand_interface",
           "binding_mode":"Not specified",
           "ligand_name":"CCL1–CCR8 N-terminal fusion segment"},
  "8K2X":{"inventory_ids":{"8K2X:EI:poly:6"},"ligand_chain":"L","ligand_entity":"6",
           "receptor_chain":"R","receptor_entity":"4","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"CXCL10"},
  "6MEO":{"inventory_ids":{"6MEO:EI:poly:1"},"ligand_chain":"G","ligand_entity":"1",
           "receptor_chain":"B","receptor_entity":"3","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"Envelope glycoprotein gp160"},
  "8U4Q":{"inventory_ids":{"8U4Q:EI:poly:1","8U4Q:EI:poly:2"},
           "ligand_chain":"H","ligand_entity":"2","display_ligand_chains":{"L","H"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"3",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "binding_mode":"Not specified",
           "ligand_name":"REGN7663 Fab"},
  "8U4R":{"inventory_ids":{"8U4R:EI:poly:1","8U4R:EI:poly:2"},
           "ligand_chain":"H","ligand_entity":"2","display_ligand_chains":{"L","H"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"3",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "binding_mode":"Not specified",
           "ligand_name":"REGN7663 Fab"},
  "8U4S":{"inventory_ids":{"8U4S:EI:poly:1","8U4S:EI:poly:2"},
           "ligand_chain":"H","ligand_entity":"2","display_ligand_chains":{"L","H"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"3",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "binding_mode":"Not specified",
           "ligand_name":"REGN7663 Fab"},
  "8U4T":{"inventory_ids":{"8U4T:EI:poly:1","8U4T:EI:poly:2"},
           "ligand_chain":"H","ligand_entity":"2","display_ligand_chains":{"L","H"},
           "preserve_inventory_selection":True,"receptor_chain":"R","receptor_entity":"3",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface",
           "binding_mode":"Not specified",
           "ligand_name":"REGN7663 Fab"},
  "5WB2":{"inventory_ids":{"5WB2:EI:poly:2"},"ligand_chain":"B","ligand_entity":"2",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"CX3CL1"},
  "8K4O":{"inventory_ids":{"8K4O:EI:poly:2"},"ligand_chain":"F","ligand_entity":"2",
           "receptor_chain":"E","receptor_entity":"1","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"Growth-regulated alpha protein"},
  "4J4Q":{"inventory_ids":{"4J4Q:EI:np:BOG:A:405:"},"ligand_chain":"A","ligand_residue":"405",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"B-Octylglucoside"},
  "4PXF":{"inventory_ids":{"4PXF:EI:np:BOG:A:406:"},"ligand_chain":"A","ligand_residue":"406",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"B-Octylglucoside"},
  "4X1H":{"inventory_ids":{"4X1H:EI:np:BNG:A:407:"},"ligand_chain":"A","ligand_residue":"407",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"B-Nonylglucoside"},
  "5TE3":{"inventory_ids":{"5TE3:EI:np:BOG:A:407:"},"ligand_chain":"A","ligand_residue":"407",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"B-Octylglucoside"},
  "5WKT":{"inventory_ids":{"5WKT:EI:np:BOG:A:405:"},"ligand_chain":"A","ligand_residue":"405",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"B-Octylglucoside"},
  "6NWE":{"inventory_ids":{"6NWE:EI:np:BOG:A:412:"},"ligand_chain":"A","ligand_residue":"412",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"B-Octylglucoside"},
  "6PEL":{"inventory_ids":{"6PEL:EI:np:ODM:A:401:"},"ligand_chain":"A","ligand_residue":"401",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "ligand_name":"Citronellol"},
  "6PGS":{"inventory_ids":{"6PGS:EI:np:64Z:A:403:"},"ligand_chain":"A","ligand_residue":"403",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "ligand_name":"Geraniol"},
  "6PH7":{"inventory_ids":{"6PH7:EI:np:NZZ:A:407:"},"ligand_chain":"A","ligand_residue":"407",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "ligand_name":"Nerol"},
  "7F6G":{"inventory_ids":{"7F6G:EI:poly:2"},"ligand_chain":"L","ligand_entity":"2",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"SAR1-AngII"},
  "7X1T":{"inventory_ids":{"7X1T:EI:poly:6"},"ligand_chain":"E","ligand_entity":"6",
           "receptor_chain":"A","receptor_entity":"2","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"taltirelin"},
  "7XJL":{"inventory_ids":{"7XJL:EI:poly:1"},"ligand_chain":"A","ligand_entity":"1",
           "receptor_chain":"F","receptor_entity":"6","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"spexin"},
  "8HCQ":{"inventory_ids":{"8HCQ:EI:poly:5"},"ligand_chain":"L","ligand_entity":"5",
           "receptor_chain":"R","receptor_entity":"6"},
  "8HCX":{"inventory_ids":{"8HCX:EI:poly:4"},"ligand_chain":"D","ligand_entity":"4",
           "receptor_chain":"C","receptor_entity":"3"},
  "8QJ2":{"inventory_ids":{"8QJ2:EI:poly:6"},"ligand_chain":"D","ligand_entity":"6",
           "receptor_chain":"A","receptor_entity":"5","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_polymer_interface","ligand_name":"pN162"},
  "8QOT":{"inventory_ids":{"8QOT:EI:poly:2"},"ligand_chain":"B","ligand_entity":"2",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_allosteric_pocket","ligand_name":"Nanobody-E"},
  "8TH3":{"inventory_ids":{"8TH3:EI:poly:1"},"ligand_chain":"B","ligand_entity":"1",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"polymer_chain",
           "binding_site_class":"extracellular_allosteric_pocket","ligand_name":"AT118-H Nanobody"},
  "8E0G":{"inventory_ids":set(),"ligand_chain":"A","ligand_entity":"1","ligand_residue":"54",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"covalent_adduct",
           "binding_site_class":"covalent_core_site","ligand_name":"BU72 covalent adduct"},
  "8TH4":{"inventory_ids":{"8TH4:EI:np:LSN:A:1401:"},"ligand_chain":"A","ligand_entity":"5",
           "receptor_chain":"A","receptor_entity":"1","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"LSN"},
  "8YNT":{"inventory_ids":{"8YNT:EI:np:A1D6T:R:601:"},"ligand_chain":"R","ligand_entity":"5",
           "receptor_chain":"R","receptor_entity":"4","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"CHEMBL242004"},
  "8YN7":{"inventory_ids":{"8YN7:EI:np:A1LY2:R:701:"},"ligand_chain":"R","ligand_entity":"6",
           "ligand_residue":"701","receptor_chain":"R","receptor_entity":"5",
           "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket",
           "ligand_name":"immethridine","ligand_role":"pharmacological_orthosteric_ligand"},
  # RCSB label chain A is deposited under author chain AAA.  The Phase-2 fallback retained the
  # label-chain name, so explicitly bridge that source naming difference for the viewer.
  "7B6W":{"inventory_ids":{"7B6W:EI:np:T0B:AAA:601:"},"ligand_chain":"AAA","ligand_entity":"2",
           "ligand_residue":"601","receptor_chain":"AAA","receptor_entity":"1",
           "receptor_source_chain":"A","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_name":"(+)-cyclazosin"},
  "8IRU":{"inventory_ids":{"8IRU:EI:np:R5F:R:601:"},"ligand_chain":"R","ligand_entity":"6",
           "ligand_residue":"601","receptor_chain":"R","receptor_entity":"5",
           "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket",
           "ligand_name":"rotigotine"},
}
OBSERVATION_LIGAND_OVERRIDES={
  "9D3E:LE:np:A1A1W":{"inventory_ids":{"9D3E:EI:np:A1A1W:A:503:"},
    "ligand_chain":"A","ligand_residue":"503","receptor_chain":"A","receptor_entity":"1",
    "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket"},
  "9D3E:LE:np:EBX":{"inventory_ids":{"9D3E:EI:np:EBX:A:502:"},
    "ligand_chain":"A","ligand_residue":"502","receptor_chain":"A","receptor_entity":"1",
    "entity_form":"nonpolymer_residue","binding_site_class":"intracellular_allosteric_pocket"},
  "9D3G:LE:np:A1A2A":{"inventory_ids":{"9D3G:EI:np:A1A2A:A:1003:"},
    "ligand_chain":"A","ligand_residue":"1003","receptor_chain":"A","receptor_entity":"1",
    "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket"},
  "9D3G:LE:np:EBX":{"inventory_ids":{"9D3G:EI:np:EBX:A:1002:"},
    "ligand_chain":"A","ligand_residue":"1002","receptor_chain":"A","receptor_entity":"1",
    "entity_form":"nonpolymer_residue","binding_site_class":"intracellular_allosteric_pocket"},
  "7UTZ:LE:np:Z41":{"inventory_ids":{"7UTZ:EI:np:Z41:R:805:"},
    "ligand_chain":"R","ligand_residue":"805","receptor_chain":"R","receptor_entity":"4",
    "entity_form":"nonpolymer_residue","ligand_role":"structural_lipid",
    "binding_mode":"Not specified","binding_site_class":"bitopic_or_multi_region_site",
    "ligand_name":"Structural lipid Z41"},
  "7FIH:LE:np:55Z":{"inventory_ids":{"7FIH:EI:np:55Z:R:801:"},
    "ligand_chain":"R","ligand_residue":"801","receptor_chain":"R","receptor_entity":"4",
    "entity_form":"nonpolymer_residue","binding_site_class":"extracellular_allosteric_pocket"},
  "7XW5:LE:np:HOI":{"inventory_ids":{"7XW5:EI:np:HOI:R:805:"},
    "ligand_chain":"R","ligand_residue":"805","receptor_chain":"R","receptor_entity":"5",
    "entity_form":"nonpolymer_residue","binding_site_class":"extracellular_allosteric_pocket"},
  "8I2G:LE:np:O6F":{"inventory_ids":{"8I2G:EI:np:O6F:R:720:"},
    "ligand_chain":"R","ligand_residue":"720","receptor_chain":"R","receptor_entity":"5",
    "entity_form":"nonpolymer_residue","binding_site_class":"extracellular_allosteric_pocket"},
  "7CFN:LE:np:FX0:agonist":{"inventory_ids":{"7CFN:EI:np:FX0:R:403:"},
    "ligand_chain":"R","ligand_residue":"403","receptor_chain":"R","receptor_entity":"5",
    "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket"},
  "7CFN:LE:np:FX0:pam":{"inventory_ids":{"7CFN:EI:np:FX0:R:401:"},
    "ligand_chain":"R","ligand_residue":"401","receptor_chain":"R","receptor_entity":"5",
    "entity_form":"nonpolymer_residue","binding_site_class":"lipid_facing_site"},
}
CURATED_SITE_CLASSES={
  "5LWE:LE:np:79K":"intracellular_allosteric_pocket",
  "5T1A:LE:np:VT5":"intracellular_allosteric_pocket",
  "6LFL:LE:np:EBX":"intracellular_allosteric_pocket",
  "9D3E:LE:np:EBX":"intracellular_allosteric_pocket",
  "9D3G:LE:np:EBX":"intracellular_allosteric_pocket",
  "6QZH:LE:np:JLW":"intracellular_allosteric_pocket",
  "7FIH:LE:np:55Z":"extracellular_allosteric_pocket",
  "7XW5:LE:np:HOI":"extracellular_allosteric_pocket",
  "7XW6:LE:np:HOI":"extracellular_allosteric_pocket",
  "8I2G:LE:np:O6F":"extracellular_allosteric_pocket",
  "8JHY:LE:np:IX8":"lipid_facing_site",
  "8JII:LE:np:IX8":"lipid_facing_site",
  "7CFN:LE:np:FX0:pam":"lipid_facing_site",
  "4XNV:LE:np:BUR":"lipid_facing_site",
  "7LD3:LE:np:XTD":"lipid_facing_site",
  "7EJX:LE:np:J5F":"bitopic_or_multi_region_site",
  "8DWG:LE:np:U39":"extracellular_allosteric_pocket",
  "5NDZ:LE:np:8UN":"lipid_facing_site",
  "6C1Q:LE:np:9P2":"lipid_facing_site",
  "6C1R:LE:np:EFD":"lipid_facing_site",
  "8FN0:LE:np:SRW":"intracellular_allosteric_pocket",
  "8JPB:LE:np:SRW":"intracellular_allosteric_pocket",
  "8JPC:LE:np:SRW":"intracellular_allosteric_pocket",
  "8JPF:LE:np:SRW":"intracellular_allosteric_pocket",
  "8K9L:LE:np:VV9":"intracellular_allosteric_pocket",
  "9BJK:LE:np:A1APU":"extracellular_allosteric_pocket",
  "4MQT:LE:np:2CU":"extracellular_allosteric_pocket",
  "5X7D:LE:np:8VS":"intracellular_allosteric_pocket",
  "6N48:LE:np:KBY":"intracellular_allosteric_pocket",
  "8PKM:LE:np:T7M":"lipid_facing_site",
  "6OBA:LE:np:M3J":"lipid_facing_site",
  "6OIK:LE:np:2CU":"extracellular_allosteric_pocket",
  "7CKZ:LE:np:G4C":"lipid_facing_site",
  "7LJC:LE:np:G4C":"intracellular_allosteric_pocket",
  "7LJD:LE:np:G4C":"bitopic_or_multi_region_site",
  "7T94:LE:np:2CU":"extracellular_allosteric_pocket",
  "7T96:LE:np:2CU":"extracellular_allosteric_pocket",
  "7TRP:LE:np:IUE":"extracellular_allosteric_pocket",
  "7TRQ:LE:np:IUI":"extracellular_allosteric_pocket",
  "7V68:LE:np:2CU":"extracellular_allosteric_pocket",
  "7V6A:LE:np:5XI":"extracellular_allosteric_pocket",
  "7X2F:LE:np:G4C":"intracellular_allosteric_pocket",
  "8PJK:LE:np:T7M":"lipid_facing_site",
  "4PHU:LE:np:2YB":"bitopic_or_multi_region_site",
  "5TZR:LE:np:MK6":"bitopic_or_multi_region_site",
  "5TZY:LE:np:7OS":"bitopic_or_multi_region_site",
  "5KW2:LE:np:6XQ":"lipid_facing_site",
  "6KQI:LE:np:9GL":"lipid_facing_site",
  "7FEE:LE:np:7IC":"lipid_facing_site",
  "7WV9:LE:np:7IC":"lipid_facing_site",
  "8J20:LE:np:9T4":"intracellular_allosteric_pocket",
  "8XXU:LE:np:A1D5Q":"bitopic_or_multi_region_site",
  "8XXV:LE:np:A1D5Q":"bitopic_or_multi_region_site",
}
SHORTCUT_GENERIC_POSITIONS={"5x42","5x43","5x46","5x461",
                            "6x48","6x51","6x52","7x42"}
MCHR1_SPLIT_CONSTRUCTS={"8YNS","8YNT"}
NTS1_RAT_ENGINEERED_CONSTRUCTS={"6YVR","6Z4Q","6Z4S","6Z4V","6Z66","6Z8N","6ZA8","6ZIN"}
CCR6_BRIL_CONSTRUCTS={"9D3E","9D3G"}
ANTIBODY_ONLY_INTERACTION_STRUCTURES={"7T9M","7T9N","7XW7"}
AA3_TO_1={"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E",
  "GLY":"G","HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F",
  "PRO":"P","SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V"}
AUX_BUDGET_BYTES=450_000
PHARM={"pharmacological_orthosteric_ligand","pharmacological_allosteric_ligand",
       "pharmacological_bitopic_ligand","pharmacological_covalent_ligand",
       "endogenous_polymer_ligand","tethered_ligand","pharmacological_co_ligand",
       "positive_allosteric_modulator","negative_allosteric_modulator",
       "silent_allosteric_modulator"}
def rd(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# Categories NGL's mmCIF layer needs. A bare atom_site block fails with
# "Cannot read properties of undefined (reading 'getField')"; this set was found empirically by
# removing blocks until parsing broke, and is verified by the browser test suite.
KEEP_CATEGORIES={"DATA","entry","cell","symmetry","entity","entity_poly","entity_poly_seq",
  "struct_asym","chem_comp","struct_conn","struct_conn_type","atom_site","exptl",
  "pdbx_struct_assembly","pdbx_struct_assembly_gen","pdbx_struct_oper_list",
  "pdbx_poly_seq_scheme","pdbx_nonpoly_scheme"}


def trim_categories(lines):
    """Keep only the categories the viewer needs, preserving each block verbatim."""
    blocks=[]; cur=[]
    for l in lines:
        if l.strip()=="#":
            if cur: blocks.append(cur); cur=[]
        else: cur.append(l)
    if cur: blocks.append(cur)
    out=[]
    for b in blocks:
        name="?"
        for l in b:
            if l.startswith("data_"): name="DATA"; break
            if l.startswith("_"):
                name=l[1:].split(".",1)[0].strip(); break
        if name in KEEP_CATEGORIES:
            out.extend(b); out.append("#")
    return out


def read_source(pid):
    """Return (prefix_lines, atom_col_index, atom_rows, suffix_lines) from the deposited CIF.

    The bundle is the deposited file with unwanted atom_site rows removed, rather than a CIF
    synthesised from scratch. A synthesised file parses in some readers and fails in NGL, whose
    mmCIF layer asks for categories a bare atom_site block does not provide; keeping the real
    header also preserves entity, chem_comp and struct_conn metadata for the viewer.
    """
    data=gzip.decompress((ROOT/"data/cache/coordinates"/f"{pid}.cif.gz").read_bytes()).decode("utf-8","replace")
    lines=data.splitlines()
    i=None
    for n,l in enumerate(lines):
        if l.strip()=="loop_" and n+1<len(lines) and lines[n+1].startswith("_atom_site."):
            i=n; break
    if i is None: return lines,None,[],[]
    j=i+1; cols=[]
    while j<len(lines) and lines[j].startswith("_atom_site."):
        cols.append(lines[j].strip().split(".",1)[1]); j+=1
    k=j
    while k<len(lines) and lines[k] and not lines[k].startswith(("#","loop_","_","data_")):
        k+=1
    return lines[:j], {c:n for n,c in enumerate(cols)}, lines[j:k], lines[k:]


def split_row(line):
    out=[]; i=0; n=len(line)
    while i<n:
        while i<n and line[i] in " \t": i+=1
        if i>=n: break
        if line[i] in "'\"":
            q=line[i]; i+=1; s=i
            while i<n and not (line[i]==q and (i+1>=n or line[i+1] in " \t")): i+=1
            out.append(line[s:i]); i+=1
        else:
            s=i
            while i<n and line[i] not in " \t": i+=1
            out.append(line[s:i])
    return out


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=None)
    args=ap.parse_args()
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    RI=rd(IN/"receptor_instances.jsonl"); EI=rd(IN/"entity_inventory.jsonl")
    EId={i["entity_inventory_id"]:i for i in EI}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    OB=rd(IN/"structure_ligand_observations.jsonl")
    # Human-confirmed deposited ligand that GPCRdb labels as pN162 while also marking the
    # structure-level pharmacology as apo.  Preserve that source ambiguity in the role/mode,
    # but do not discard the explicitly identified bound polymer chain from the viewer.
    LC["8QJ2:LE:poly:6"]={"ligand_entity_id":"8QJ2:LE:poly:6","entity_form":"polymer_chain",
      "entity_inventory_ids":["8QJ2:EI:poly:6"],"ligand_role":"pharmacological_co_ligand",
      "binding_mode":"Not specified","binding_site_class":"extracellular_polymer_interface",
      "biological_type":"protein","source_annotations":{"gpcrdb_ligand":{"name":"pN162"}}}
    OB.append({"pdb_id":"8QJ2","structure_ligand_id":"8QJ2:LE:poly:6::8QJ2:RI:5:A",
               "ligand_entity_id":"8QJ2:LE:poly:6"})
    LC["7UTZ:LE:np:Z41"]={"ligand_entity_id":"7UTZ:LE:np:Z41",
      "entity_form":"nonpolymer_residue","entity_inventory_ids":["7UTZ:EI:np:Z41:R:805:"],
      "ligand_role":"structural_lipid","binding_mode":"Not specified",
      "binding_site_class":"bitopic_or_multi_region_site","biological_type":"lipid",
      "source_annotations":{"gpcrdb_ligand":{"name":"Structural lipid Z41"}}}
    OB.append({"pdb_id":"7UTZ","structure_ligand_id":"7UTZ:LE:np:Z41::7UTZ:RI:4:R",
               "ligand_entity_id":"7UTZ:LE:np:Z41"})
    SUMO={s["structure_ligand_id"]:s for s in rd(ROOT/"data/contacts/observation_contact_summary.jsonl")}
    ANO={a["structure_ligand_id"]:a for a in rd(P4/"annotated_not_observed.jsonl")}
    MR=rd(P4/"motif_residues.jsonl")
    RM=rd(P3/"receptor_residue_mapping.jsonl")
    gpcr_residues=json.loads((ROOT/"data/raw/gpcrdb/receptor_residues.json").read_text(
      encoding="utf-8"))["receptors"]
    mchr1_direct={str(r["sequence_number"]):r for r in gpcr_residues["mchr1_human"]}
    nts1_rat_direct={str(r["sequence_number"]):r for r in gpcr_residues["ntr1_rat"]}
    ccr6_direct={str(r["sequence_number"]):r for r in gpcr_residues["ccr6_human"]}
    def special_construct_ref(pid,auth_seq):
        if pid in NTS1_RAT_ENGINEERED_CONSTRUCTS:
            return nts1_rat_direct.get(str(auth_seq))
        if pid in CCR6_BRIL_CONSTRUCTS:
            try: seq=int(auth_seq)
            except (TypeError,ValueError): return None
            # The deposited CCR6 construct uses native numbering through TM5.  BRIL replaces
            # ICL3 (auth 242–331); three native residues resume at 332–334, and TM6–C-tail
            # resumes at auth 357 with a +112 author-number offset.
            wt=(seq if 28<=seq<=241 else seq-90 if 332<=seq<=334 else
                seq-112 if 357<=seq<=459 else None)
            return ccr6_direct.get(str(wt)) if wt is not None else None
        return None
    core=json.loads((ROOT/"config/phase4/motifs.core.json").read_text(encoding="utf-8"))
    motif_memberships=defaultdict(list)
    for definition in core["motifs"]:
        for gp in definition["generic_positions"]: motif_memberships[gp].append(definition["id"])
    REMED={r["receptor_instance_id"]:r for r in rd(P4/"mapping_remediation.jsonl")}
    STN={r["pdb_id"]:r["chosen_normalized_state"] for r in rd(P4/"structural_state_normalization.jsonl")}
    ri_by_pdb=defaultdict(list)
    for r in RI: ri_by_pdb[r["pdb_id"]].append(r)
    ei_by_pdb=defaultdict(list)
    for i in EI: ei_by_pdb[i["pdb_id"]].append(i)
    obs_by_pdb=defaultdict(list)
    for o in OB: obs_by_pdb[o["pdb_id"]].append(o)
    mr_by=defaultdict(list)
    for m in MR: mr_by[(m["pdb_id"],m["receptor_instance_id"])].append(m)
    rm_by=defaultdict(list)
    for r in RM: rm_by[(r["pdb_id"],r["receptor_instance_id"])].append(r)
    contacts=defaultdict(list)
    for f in sorted((ROOT/"data/contacts/by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        for l in gzip.open(f,"rt"):
            c=json.loads(l); contacts[c["structure_ligand_id"]].append(c)

    idx=[]; pdbs=sorted(S)
    if args.limit: pdbs=pdbs[:args.limit]
    for n,pid in enumerate(pdbs,1):
        st=S[pid]
        pre,colidx,rows,suf=read_source(pid)
        raw=read(ROOT/"data/cache/coordinates"/f"{pid}.cif.gz",{"_atom_site"})["_atom_site"]
        A=atoms(raw)
        models=sorted({a["model"] for a in A}); model0=models[0]
        A=[a for a in A if a["model"]==model0]
        insts=ri_by_pdb[pid]
        structure_override=STRUCTURE_LIGAND_OVERRIDES.get(pid)
        # A fused/chimeric entity can be deposited as more than one author chain even though
        # only one chain is the receptor protomer paired with the curated ligand.  Do not let
        # the ligand copy re-enter the bundle as a second receptor (8TH3 is the concrete case).
        if structure_override:
            paired=[r for r in insts if r["auth_asym_id"]==structure_override["receptor_chain"]]
            if not paired and structure_override.get("receptor_source_chain"):
                paired=[]
                for r in insts:
                    if r["auth_asym_id"]!=structure_override["receptor_source_chain"]: continue
                    corrected=dict(r)
                    corrected["auth_asym_id"]=structure_override["receptor_chain"]
                    corrected["polymer_entity_id"]=structure_override["receptor_entity"]
                    paired.append(corrected)
            if paired: insts=paired
        rec_keys={(r["auth_asym_id"],str(r["polymer_entity_id"])) for r in insts}
        rec_chains={r["auth_asym_id"] for r in insts}

        def is_receptor(ch,ent,grp):
            if grp!="ATOM": return False
            for c,e in rec_keys:
                if ch==c and (not e or e=="None" or ent==e): return True
            return False

        # ligand selections per observation, from the approved Phase 2/3 records only
        lig_keys=set(); obs_meta=[]
        for o in sorted(obs_by_pdb[pid],key=lambda x:x["structure_ligand_id"]):
            if pid in NON_LIGAND_STRUCTURES:
                continue
            slid=o["structure_ligand_id"]; lg=LC[o["ligand_entity_id"]]
            override=OBSERVATION_LIGAND_OVERRIDES.get(lg["ligand_entity_id"],structure_override)
            pharm=lg["ligand_role"] in PHARM or override is not None
            observed=slid in SUMO or override is not None
            mine=set()
            if pharm and observed:
                selection_form=(override or {}).get("entity_form",lg["entity_form"])
                inventory_ids=(override["inventory_ids"] if override else
                               set(lg["entity_inventory_ids"]))
                if override and override.get("ligand_residue_start") is not None:
                    lo=int(override["ligand_residue_start"]); hi=int(override["ligand_residue_end"])
                    for a in A:
                        try: seq=int(a["auth_seq"])
                        except (TypeError,ValueError): continue
                        if (a["group"]=="ATOM" and a["auth_asym"]==override["ligand_chain"] and
                            lo <= seq <= hi):
                            mine.add(("polyseg",a["auth_asym"],a["auth_seq"]))
                elif selection_form in ("nonpolymer_residue","covalent_adduct"):
                    for i in inventory_ids:
                        if i in EId and EId[i]["auth_asym_ids"]:
                            mine.add(("np",EId[i]["auth_asym_ids"][0],str(EId[i]["auth_seq_id"])))
                    if override and override.get("ligand_residue"):
                        mine.add(("np",override["ligand_chain"],override["ligand_residue"]))
                else:
                    for i in inventory_ids:
                        if i in EId:
                            for ch in (EId[i]["auth_asym_ids"] or []):
                                mine.add(("poly",ch,str(EId[i]["polymer_entity_id"])))
                excluded=EXCLUDED_LIGAND_CHAINS.get(pid,set())
                if excluded: mine={k for k in mine if k[1] not in excluded}
                if override and override.get("display_ligand_chains"):
                    keep=override["display_ligand_chains"]
                    mine={k for k in mine if k[0]!="poly" or k[1] in keep}
            crows=list(contacts.get(slid,[]))
            # 8YNS/8YNT contain MCHR1 as two deposited sequence segments separated by BRIL.
            # The generic-mapping remediation recovered the second segment (TM6–H8), but marked
            # the first deposited MCHR1 segment (auth R 70–304; TM1–TM5) as fusion.  RCSB's
            # struct_ref_seq maps that first segment directly to the GPCRdb construct sequence,
            # so recover its viewer contact shell only when residue identity agrees exactly.
            if pid in MCHR1_SPLIT_CONSTRUCTS and mine:
                ligand_atoms=[]; receptor_atoms=defaultdict(list)
                for a in A:
                    if any((k=="np" and a["auth_asym"]==ch and a["auth_seq"]==v) or
                           (k=="poly" and a["auth_asym"]==ch and a["entity"]==v)
                           for k,ch,v in mine):
                        if a.get("element")!="H": ligand_atoms.append(a)
                    elif (a["auth_asym"]=="R" and a["group"]=="ATOM" and
                          a.get("element")!="H" and
                          (70 <= int(a["auth_seq"]) <= 304 or
                           409 <= int(a["auth_seq"]) <= 489)):
                        receptor_atoms[a["auth_seq"]].append(a)
                present={(c["receptor_auth_asym_id"],str(c["receptor_auth_seq_id"])) for c in crows}
                for rseq,ras in receptor_atoms.items():
                    # First MCHR1 segment uses the GPCRdb construct number directly; after the
                    # BRIL insertion, auth 409 resumes at construct position 316 (offset -93).
                    construct_seq=int(rseq) if int(rseq)<=304 else int(rseq)-93
                    ref=mchr1_direct.get(str(construct_seq))
                    if not ref or not ref.get("canonical_generic_number"): continue
                    if AA3_TO_1.get(ras[0]["comp"]) != ref.get("amino_acid"): continue
                    d2=min((ra["x"]-la["x"])**2+(ra["y"]-la["y"])**2+
                           (ra["z"]-la["z"])**2 for ra in ras for la in ligand_atoms)
                    if d2>25.0 or ("R",str(rseq)) in present: continue
                    crows.append({"receptor_auth_asym_id":"R","receptor_auth_seq_id":str(rseq),
                      "receptor_residue_name":ras[0]["comp"],
                      "receptor_generic_number":ref["canonical_generic_number"],
                      "receptor_segment":ref["protein_segment"],
                      "receptor_uniprot_position":ref["sequence_number"],
                      "ligand_auth_asym_id":next(iter(mine))[1],
                      "ligand_auth_seq_id":next(iter(mine))[2],
                      "ligand_residue_name":ligand_atoms[0]["comp"],
                      "min_distance_angstrom":d2**0.5})
            # Test the frozen contact source, not the viewer-augmentation list above: an override
            # such as 8YNT still needs its full raw 5 Å shell generated even after the recovered
            # first MCHR1 segment has contributed contacts.
            if override and not contacts.get(slid,[]):
                receptor_atoms=defaultdict(list); ligand_atoms=defaultdict(list)
                for a in A:
                    if (override.get("ligand_residue_start") is not None and
                        a["group"]=="ATOM" and a["auth_asym"]==override["ligand_chain"] and
                        int(override["ligand_residue_start"]) <= int(a["auth_seq"]) <=
                        int(override["ligand_residue_end"])):
                        ligand_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                    elif (a["auth_asym"]==override["ligand_chain"] and
                        a["auth_seq"]==override.get("ligand_residue") and a["group"]=="HETATM"):
                        ligand_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                    elif (a["auth_asym"]==override["receptor_chain"] and
                        a["entity"]==override["receptor_entity"]):
                        receptor_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                    elif (((override.get("display_ligand_chains") and
                            a["auth_asym"] in override["display_ligand_chains"]) or
                           (override.get("ligand_entity") and
                            a["auth_asym"]==override["ligand_chain"] and
                            a["entity"]==override["ligand_entity"])) and
                          a["group"]=="ATOM"):
                        ligand_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                mapping={}
                for inst in insts:
                    for m in rm_by.get((pid,inst["receptor_instance_id"]),[]):
                        mapping[(m["auth_asym_id"],str(m["auth_seq_id"]))]=m
                if pid in CCR6_BRIL_CONSTRUCTS:
                    for (rch,rseq),ras in receptor_atoms.items():
                        ref=special_construct_ref(pid,rseq)
                        if (ref and ref.get("canonical_generic_number") and
                            AA3_TO_1.get(ras[0]["comp"])==ref.get("amino_acid")):
                            mapping[(rch,rseq)]={"canonical_generic_number":ref["canonical_generic_number"],
                              "protein_segment":ref.get("protein_segment"),
                              "uniprot_position":ref.get("sequence_number")}
                for (rch,rseq),ras in receptor_atoms.items():
                    for (lch,lseq),las in ligand_atoms.items():
                        d2=min((ra["x"]-la["x"])**2+(ra["y"]-la["y"])**2+
                               (ra["z"]-la["z"])**2 for ra in ras for la in las)
                        if d2>25.0: continue
                        m=mapping.get((rch,rseq),{})
                        crows.append({"receptor_auth_asym_id":rch,
                          "receptor_auth_seq_id":rseq,
                          "receptor_residue_name":ras[0]["comp"],
                          "receptor_generic_number":m.get("canonical_generic_number"),
                          "receptor_segment":m.get("protein_segment"),
                          "receptor_uniprot_position":m.get("uniprot_position"),
                          "ligand_auth_asym_id":lch,"ligand_auth_seq_id":lseq,
                          "ligand_residue_name":las[0]["comp"],
                          "min_distance_angstrom":d2**0.5})
            # Recover source-coordinate contacts omitted from the frozen contact table when the
            # receptor residue nevertheless has an independently validated GPCRdb mapping.  This
            # is deliberately additive and conservative: unresolved mappings remain excluded.
            # It catches, for example, the two deposited TM7 contacts of 7T2G.
            if mine:
                receptor_atoms=defaultdict(list); ligand_atoms=[]
                receptor_chain_set={c["receptor_auth_asym_id"] for c in crows} or rec_chains
                for a in A:
                    if (a["group"]=="ATOM" and a["auth_asym"] in receptor_chain_set and
                        a.get("element")!="H"):
                        receptor_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                    if (a.get("element")!="H" and any(
                        (k=="np" and a["group"]=="HETATM" and a["auth_asym"]==ch and
                         a["auth_seq"]==v) or
                        (k=="poly" and a["group"]=="ATOM" and a["auth_asym"]==ch and
                         a["entity"]==v) for k,ch,v in mine)):
                        ligand_atoms.append(a)
                mapping={}
                for inst in insts:
                    for m in rm_by.get((pid,inst["receptor_instance_id"]),[]):
                        if m.get("mapping_confidence")=="high" and m.get("canonical_generic_number"):
                            mapping[(m["auth_asym_id"],str(m["auth_seq_id"]))]=m
                if pid in CCR6_BRIL_CONSTRUCTS:
                    for key,ras in receptor_atoms.items():
                        ref=special_construct_ref(pid,key[1])
                        if (ref and ref.get("canonical_generic_number") and
                            AA3_TO_1.get(ras[0]["comp"])==ref.get("amino_acid")):
                            mapping[key]={"canonical_generic_number":ref["canonical_generic_number"],
                              "protein_segment":ref.get("protein_segment"),
                              "uniprot_position":ref.get("sequence_number")}
                present={(c["receptor_auth_asym_id"],str(c["receptor_auth_seq_id"])) for c in crows}
                for key,ras in receptor_atoms.items():
                    m=mapping.get(key)
                    if not m or key in present or not ligand_atoms: continue
                    d2=min((ra["x"]-la["x"])**2+(ra["y"]-la["y"])**2+
                           (ra["z"]-la["z"])**2 for ra in ras for la in ligand_atoms)
                    if d2>25.0: continue
                    nearest=min(ligand_atoms,key=lambda la:min(
                      (ra["x"]-la["x"])**2+(ra["y"]-la["y"])**2+(ra["z"]-la["z"])**2
                      for ra in ras))
                    crows.append({"receptor_auth_asym_id":key[0],
                      "receptor_auth_seq_id":key[1],"receptor_residue_name":ras[0]["comp"],
                      "receptor_generic_number":m["canonical_generic_number"],
                      "receptor_segment":m.get("protein_segment"),
                      "receptor_uniprot_position":m.get("uniprot_position"),
                      "ligand_auth_asym_id":nearest["auth_asym"],
                      "ligand_auth_seq_id":nearest["auth_seq"],
                      "ligand_residue_name":nearest["comp"],"min_distance_angstrom":d2**0.5})
            # These NTS1 crystallographic constructs contain a receptor segment followed by a
            # DARPin in one deposited entity.  Whole-entity agreement therefore falls below the
            # global 0.80 threshold, although RCSB explicitly maps author residues 50–371 to rat
            # NTS1 P20789 at the same numbers.  Restore labels only inside that source-mapped
            # segment and only when the deposited amino acid exactly matches GPCRdb.
            if pid in NTS1_RAT_ENGINEERED_CONSTRUCTS | CCR6_BRIL_CONSTRUCTS:
                for c in crows:
                    if c.get("receptor_generic_number"): continue
                    ref=special_construct_ref(pid,c["receptor_auth_seq_id"])
                    if (not ref or not ref.get("canonical_generic_number") or
                        AA3_TO_1.get(c["receptor_residue_name"])!=ref.get("amino_acid")): continue
                    c["receptor_generic_number"]=ref["canonical_generic_number"]
                    c["receptor_segment"]=ref["protein_segment"]
                    c["receptor_uniprot_position"]=ref["sequence_number"]
            if override and override.get("contact_segments"):
                allowed=override["contact_segments"]
                crows=[c for c in crows if c.get("receptor_segment") in allowed]
            excluded=EXCLUDED_LIGAND_CHAINS.get(pid,set())
            if excluded: crows=[c for c in crows if c["ligand_auth_asym_id"] not in excluded]
            if override and not override.get("preserve_inventory_selection"):
                crows=[c for c in crows if c["ligand_auth_asym_id"]==override["ligand_chain"]
                       and c["receptor_auth_asym_id"]==override["receptor_chain"]]
            # A polymer entity may have symmetry-/protomer-related copies.  The contact table is
            # receptor-instance-specific, so retain only the ligand chain paired with that active
            # receptor instead of displaying every deposited copy of the entity.
            effective_form=(override or {}).get("entity_form",lg["entity_form"])
            effective_site=(override or {}).get("binding_site_class",
              CURATED_SITE_CLASSES.get(lg["ligand_entity_id"],lg["binding_site_class"]))
            if crows:
                paired_chains={c["ligand_auth_asym_id"] for c in crows}
                paired_residues={(c["ligand_auth_asym_id"],str(c["ligand_auth_seq_id"]))
                                 for c in crows}
                # Keep only the ligand instance actually paired with this receptor observation.
                # Otherwise symmetry-related/dimer copies of the same chemical entity appear as
                # a spurious second ligand in the viewer.
                paired_mine={k for k in mine if
                      (k[0]=="poly" and k[1] in paired_chains) or
                      (k[0] in ("np","polyseg") and (k[1],k[2]) in paired_residues)}
                if not (override and override.get("preserve_inventory_selection")):
                    mine=paired_mine
            lig_keys |= mine
            rres=sorted({(c["receptor_auth_asym_id"],c["receptor_auth_seq_id"]) for c in crows})
            lres=sorted({(c["ligand_auth_asym_id"],c["ligand_auth_seq_id"]) for c in crows})
            # Preserve the already-computed per-structure GPCRdb mapping in the viewer payload.
            # The old UI exposed this as D3x32 / ASP117; reducing it to chain:residue made the
            # binding-site list scientifically opaque even though the mapping was available.
            rdetail=[]
            for ch,seq in rres:
                hits=[c for c in crows if c["receptor_auth_asym_id"]==ch and
                      c["receptor_auth_seq_id"]==seq]
                hit=min(hits,key=lambda c:c["min_distance_angstrom"])
                rdetail.append({"auth_asym_id":ch,"auth_seq_id":seq,
                  "residue_name":hit["receptor_residue_name"],
                  "generic_position":hit.get("receptor_generic_number"),
                  "segment":hit.get("receptor_segment"),
                  "uniprot_position":hit.get("receptor_uniprot_position"),
                  "min_distance_angstrom":hit["min_distance_angstrom"]})
            obs_meta.append({"observation_id":slid,
              "ligand_entity_id":lg["ligand_entity_id"],
              "ligand_name":(override or {}).get("ligand_name") or
                 (lg["source_annotations"].get("gpcrdb_ligand") or {}).get("name"),
              "ligand_role":(override or {}).get("ligand_role",lg["ligand_role"]),
              "entity_form":effective_form,
              "binding_mode":(override or {}).get("binding_mode",lg["binding_mode"]),
              "binding_site_class":effective_site,
              "is_polymer_interface":effective_site in POLYMER,
              "coordinate_status":("observed" if observed else
                                   "annotated_not_observed" if slid in ANO else "no_observation"),
              "ligand_selection":({"chains":sorted({k[1] for k in mine}),
                 "residues":sorted([[k[1],k[2]] for k in mine if k[0] in ("np","polyseg")]),
                 "entities":sorted({k[2] for k in mine if k[0]=="poly"}),
                 "selection_kind":("polymer_segment" if any(k[0]=="polyseg" for k in mine) else
                   "nonpolymer" if any(k[0]=="np" for k in mine) else "polymer_chain")}
                 if mine else None),
              "contact_receptor_residues":rres,
              "contact_receptor_details":rdetail,
              "contact_ligand_residues":lres,
              "residue_pair_count":len(crows),
              "no_ligand_reason":(None if mine else
                ("annotated_not_observed" if slid in ANO else
                 "not_a_pharmacological_ligand" if not pharm else "no_coordinate_observation"))})

        # A heterodimeric hormone is represented upstream by one annotation per subunit.  Once
        # curator-confirmed subunits are joined into the same viewer selection, expose that
        # complex only once instead of offering two visually identical observation choices.
        deduped=[]; seen_observations=set()
        for o in obs_meta:
            key=(o.get("ligand_name"),json.dumps(o.get("ligand_selection"),sort_keys=True))
            if key in seen_observations: continue
            seen_observations.add(key); deduped.append(o)
        obs_meta=deduped

        # Retain the receptor protomer(s) actually paired with the displayed observations.  This
        # removes symmetry/dimer copies while preserving every distinct pharmacological ligand.
        paired_receptor_chains={ch for o in obs_meta for ch,_ in o["contact_receptor_residues"]}
        if paired_receptor_chains:
            rec_chains &= paired_receptor_chains
            rec_keys={(ch,ent) for ch,ent in rec_keys if ch in rec_chains}
            insts=[r for r in insts if r["auth_asym_id"] in rec_chains]

        def is_ligand(ch,seq,ent,grp):
            for kind,c,v in lig_keys:
                if kind=="np" and ch==c and seq==v: return True
                if kind=="poly" and ch==c and ent==v: return True
                if kind=="polyseg" and ch==c and seq==v: return True
            return False

        motif=[]
        for r in insts:
            for m in mr_by.get((pid,r["receptor_instance_id"]),[]):
                if m["coordinate_observed"]:
                    motif.append({"generic_position":m["generic_position"],
                      "motif_memberships":m["motif_memberships"],
                      "auth_asym_id":m["auth_asym_id"],"auth_seq_id":m["auth_seq_id"],
                      "residue_identity":m["residue_identity"],
                      "noncanonical":m["observation_status"]=="observed_noncanonical_identity"})
        if pid in NTS1_RAT_ENGINEERED_CONSTRUCTS | CCR6_BRIL_CONSTRUCTS:
            present={(m["auth_asym_id"],str(m["auth_seq_id"]),m["generic_position"]) for m in motif}
            observed={(a["auth_asym"],a["auth_seq"]):a for a in A
                      if a["group"]=="ATOM" and a["auth_asym"] in rec_chains}
            for (ch,seq),a in observed.items():
                ref=special_construct_ref(pid,seq); gp=(ref or {}).get("canonical_generic_number")
                if gp and "x" in gp:
                    left,right=gp.split("x",1); gp_short=f"{left.split('.',1)[0]}x{right}"
                else: gp_short=gp
                if (not gp or gp_short not in motif_memberships or
                    (ch,seq,gp) in present): continue
                actual=AA3_TO_1.get(a["comp"]); expected=(ref or {}).get("amino_acid")
                motif.append({"generic_position":gp,"motif_memberships":motif_memberships[gp_short],
                  "auth_asym_id":ch,"auth_seq_id":seq,"residue_identity":a["comp"],
                  "noncanonical":bool(actual and expected and actual!=expected)})
        shortcut=[]
        for r in insts:
            for m in rm_by.get((pid,r["receptor_instance_id"]),[]):
                gp=m.get("canonical_generic_number")
                if not gp or "x" not in gp or not m.get("observed_atom_count"): continue
                left,right=gp.split("x",1)
                short=f"{left.split('.',1)[0]}x{right}"
                if short in SHORTCUT_GENERIC_POSITIONS:
                    shortcut.append({"generic_position":gp,"generic_short":short,
                      "auth_asym_id":m["auth_asym_id"],"auth_seq_id":m["auth_seq_id"],
                      "residue_identity":m["residue_name"]})
        if pid in NTS1_RAT_ENGINEERED_CONSTRUCTS | CCR6_BRIL_CONSTRUCTS:
            present={(x["auth_asym_id"],str(x["auth_seq_id"]),x["generic_short"]) for x in shortcut}
            observed={(a["auth_asym"],a["auth_seq"]):a for a in A
                      if a["group"]=="ATOM" and a["auth_asym"] in rec_chains}
            for (ch,seq),a in observed.items():
                ref=special_construct_ref(pid,seq); gp=(ref or {}).get("canonical_generic_number")
                if not gp or "x" not in gp: continue
                left,right=gp.split("x",1); short=f"{left.split('.',1)[0]}x{right}"
                if (short not in SHORTCUT_GENERIC_POSITIONS or
                    AA3_TO_1.get(a["comp"])!=(ref or {}).get("amino_acid") or
                    (ch,seq,short) in present): continue
                shortcut.append({"generic_position":gp,"generic_short":short,
                  "auth_asym_id":ch,"auth_seq_id":seq,"residue_identity":a["comp"]})
        na=[{"auth_asym_id":a["auth_asym"],"auth_seq_id":a["auth_seq"]} for a in A if a["comp"]=="NA"]

        # filter the deposited atom_site rows
        ci=colidx or {}
        def field(parts,name,default=""):
            k=ci.get(name)
            return parts[k] if k is not None and k<len(parts) else default
        core=[]; aux=[]
        for line in rows:
            parts=split_row(line)
            if not parts: continue
            if field(parts,"pdbx_PDB_model_num","1")!=str(model0): continue
            comp=field(parts,"label_comp_id")
            if comp in ("HOH","DOD"): continue
            grp=parts[0] if parts else "ATOM"
            ch=field(parts,"auth_asym_id") or field(parts,"label_asym_id")
            ent=field(parts,"label_entity_id")
            seq=field(parts,"auth_seq_id")
            if is_receptor(ch,ent,grp) or is_ligand(ch,seq,ent,grp) or comp=="NA":
                core.append(line)
            else:
                aux.append(line)
        body_lines=trim_categories(pre+core+suf)
        body="\n".join(body_lines)+"\n"
        aux_included=False
        if aux and len(body.encode())+sum(len(x)+1 for x in aux) <= AUX_BUDGET_BYTES:
            body_lines=trim_categories(pre+core+aux+suf)
            body="\n".join(body_lines)+"\n"; aux_included=True
        aux_chains=sorted({(split_row(l)[ci["auth_asym_id"]] if "auth_asym_id" in ci else "") for l in aux}) if aux else []
        keep=core if not aux_included else core+aux
        d=WEB/pid; d.mkdir(parents=True,exist_ok=True)
        (d/"viewer.cif").write_text(body,encoding="utf-8")
        cif_bytes=len(body.encode())
        meta={"schema":"viewer_meta.schema.json","schema_version":SCHEMA_VERSION,
          "pdb_id":pid,"coordinate_file":"viewer.cif","coordinate_bytes":cif_bytes,
          "coordinate_sha256":hashlib.sha256(body.encode()).hexdigest(),
          "receptor_name":st["receptor_name"],"receptor_entry_name":st["receptor_entry_name"],
          "species":st["species"],"major_family_id":st["major_family_id"],
          "experimental_method":st["experimental_method"],"resolution":st["resolution"],
          "structural_state":STN.get(pid),
          "apo_status":("apo" if pid in ANTIBODY_ONLY_INTERACTION_STRUCTURES else st["apo_status"]),
          "receptor_instances":[{"receptor_instance_id":r["receptor_instance_id"],
            "auth_asym_id":r["auth_asym_id"],"polymer_entity_id":r["polymer_entity_id"],
            "generic_mapping":("unresolved" if REMED.get(r["receptor_instance_id"],{}).get("outcome")
                               =="mapping_unresolved_excluded_from_generic_aggregation"
                               else "validated")} for r in insts],
          "receptor_chains":sorted(rec_chains),
          "observations":obs_meta,
          "motif_residues":motif,
          "shortcut_residues":shortcut,
          "observed_sodium":na,
          "auxiliary_chains_included":aux_included,
          "auxiliary_chains":[c for c in aux_chains if c],
          "auxiliary_note_en":("Auxiliary and environment chains (antibody, nanobody, G protein, "
            "arrestin, fusion partner, detergent, buffer, bulk lipid, glycan, crystallisation "
            "additive) are hidden by default." + ("" if aux_included else
            " They are not included in this bundle because it would exceed the size budget; use "
            "the RCSB link for the full deposited structure.")),
          "auxiliary_note_tr":("Yardımcı ve çevresel zincirler (antikor, nanokor, G proteini, "
            "arrestin, füzyon ortağı, deterjan, tampon, yığın lipid, glikan ve kristalizasyon "
            "katkısı) varsayılan olarak gizlenir." + ("" if aux_included else
            " Bu bundle boyut sınırını aşacağı için bu zincirler dahil edilmemiştir; çökeltilmiş "
            "yapının tamamı için RCSB bağlantısını kullanın.")),
          "full_structure_url":f"https://www.rcsb.org/structure/{pid}",
          "invented_coordinates":False}
        (d/"viewer_meta.json").write_text(json.dumps(meta,sort_keys=True,separators=(",",":"),
                                                     ensure_ascii=False),encoding="utf-8")
        idx.append({"pdb_id":pid,"cif_bytes":cif_bytes,
                    "meta_bytes":len((d/"viewer_meta.json").read_bytes()),
                    "atoms":len(keep),"aux_included":aux_included,
                    "observations":len(obs_meta),
                    "with_ligand_selection":sum(1 for o in obs_meta if o["ligand_selection"]),
                    "sha256":meta["coordinate_sha256"]})
        if n%200==0: print(f"  {n}/{len(pdbs)}",file=sys.stderr)
    sizes=sorted(x["cif_bytes"] for x in idx)
    summary={"bundles":len(idx),"total_bytes":sum(x["cif_bytes"]+x["meta_bytes"] for x in idx),
      "cif_median":sizes[len(sizes)//2],"cif_p95":sizes[int(len(sizes)*0.95)],
      "cif_max":sizes[-1],"aux_included":sum(1 for x in idx if x["aux_included"]),
      "bundles_with_ligand_selection":sum(1 for x in idx if x["with_ligand_selection"]>0),
      "index_sha256":content_sha256(idx)}
    (ROOT/"data/intermediate/phase5"/"_bundle_index.json").write_text(
        json.dumps({"summary":summary,"bundles":idx},indent=1),encoding="utf-8")
    print(json.dumps(summary,indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
