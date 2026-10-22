#!/usr/bin/env python3
"""One-command offline reproduction: originals + frozen evidence -> tables + plots + checks."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=ROOT/'results')
    p.add_argument('--figures-dir',type=Path,default=ROOT/'figures')
    a=p.parse_args();out=str(a.output_dir.resolve());figs=str(a.figures_dir.resolve())
    commands=[['analysis.py','--no-figures','--output-dir',out],
              ['extended_analysis.py','--output-dir',out],['audit_evidence.py','--output-dir',out],
              ['verify_results.py','--output-dir',out],
              ['plot_figures.py','--results',out,'--output',figs],
              ['plot_extended.py','--results',out,'--output',figs]]
    for command in commands:
        print('Running',command[0],flush=True)
        subprocess.run([sys.executable,str(ROOT/command[0]),*command[1:]],cwd=ROOT,check=True)
