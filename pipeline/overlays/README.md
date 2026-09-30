# Overlays: content the viewer bundles left out

A viewer bundle (`site/data/web/structures/<PDB>/viewer.cif`) carries the receptor and its ligands.
Auxiliary chains and the environment around them were kept only where the whole of them fitted the
450 kB budget in `pipeline/phase5/build_bundles.py`, so most cryo-EM complexes lost their G protein
and the lipids with it. The scripts here write that content as separate files beside the frozen
bundles, copied unchanged from the RCSB PDB entry (CC0) in the deposited frame the bundle uses, so
the viewer loads them without any transformation and only when a layer asks for them.

| script | writes | viewer layer |
|---|---|---|
| `build_lipid_overlay.py` | `overlay/structures/<PDB>/lipids.cif`, `overlay/lipids_index.json` | *Lipids* |
| `build_transducer_overlay.py` | `overlay/structures/<PDB>/transducer.cif.gz`, `overlay/transducer_index.json` | *Transducer* |

Both download each entry once into `data/cache/coordinates/` (the cache `build_bundles.py` reads)
and record the source file's SHA-256 and the selection rule in their index.

## Lipids

Membrane lipids and detergents (component reference classes `membrane_lipid`, `detergent`) with a
heavy atom within 6 Å of the receptor, never a component the structure counts as its ligand. This is
interim: `build_bundles.py` puts these lipids into the bundles from the next full build. Details and
the review that preceded it: `curation/lipid_review/README.md`.

## Transducers

G protein and arrestin chains: the polymer entities `config/polymer_role_reference.json` classes as
`transducer_component` (curated UniProt accession first, then description pattern), so Gα, Gβ, Gγ,
mini-G constructs and arrestins. Nanobodies, scFv16 and Fab fragments are excluded by the reference's
antibody patterns; fusion partners (BRIL, T4 lysozyme) and receptor copies are not transducers and
are never selected.

Each file holds the backbone (N, CA, C, O) of every transducer residue - what a cartoon is drawn from -
and the whole residue wherever a heavy atom is within 8 Å of a receptor heavy atom, so the interface
can be read and measured atom by atom. Files are gzip-compressed (NGL decompresses them on load);
the index gives, per structure, each chain's subunit (`G alpha`, `G beta`, `G gamma`, `arrestin`)
and description, the number of interface residues and the file size.

The transducers stay out of the bundles by design: they would more than double most bundles, and
the file is fetched only when the layer is switched on.

## Re-running

```bash
python3 pipeline/overlays/build_lipid_overlay.py         # [--pdb 7CKZ ...] [--limit N]
python3 pipeline/overlays/build_transducer_overlay.py    # [--pdb 7CKZ ...] [--limit N]
```

Run both after a full build, before the site is published; they read the published
`viewer_meta.json` files for the receptor chains and ligand residues.
