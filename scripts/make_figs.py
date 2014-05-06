#!/usr/bin/env python
from itertools import permutations
import os, glob, re
from optparse import make_option
from cogent.util.option_parsing import parse_command_line_parameters

import numpy
from cogent import LoadSeqs, DNA, LoadTable
from cogent.core.alignment import DenseAlignment
from mutation_motif import profile, util, height, logo, entropy, distribution

dir_pattern = re.compile(r"[ACGT]{1,2}to[ACGT]{1,2}")

def PutN(data, direction, ylabel):
    """put N text on plot"""
    N = data.shape[0]
    
    # following is an ugly hack to get better number formatting on plots
    n = list(str(N))
    n.reverse()
    n = [''.join(reversed(n[i:i+3])) for i in range(0, len(n),3)]
    n.reverse()
    N = ','.join(n)
    
    direction = r"$%s \rightarrow %s$" % direction
    def call(fig):
        ax = fig.gca()
        ax.set_ylabel(ylabel, fontsize=20)
        y = ax.get_ylim()[1]
        fig.gca().text(0.2, y * 0.75, direction, fontsize=20)
        fig.gca().text(0.2, y * 0.67, 'N=' + N)
    return call

def get_re_char_hts(orig, ctl, chosen_base, step, flank_size):
    ret = entropy.get_ret(orig, ctl)
    char_hts = height.get_re_char_heights(ret)
    return char_hts, ret.sum(axis=0).max()

def get_mi_char_hts(seqs, flank_size):
    midpt = (seqs.shape[1] -1) // 2
    assert 2 * midpt + 1 == seqs.shape[1], midpt
    start = midpt - flank_size
    seqs = seqs[:, start: start + (flank_size * 2 + 1)]
    probs = entropy.as_freq_matrix(seqs)
    mit = entropy.get_mit(seqs)
    mi = mit.sum(axis=0)
    char_hts = height.get_mi_char_heights(probs, mi)
    return char_hts, mi.max()

def main(script_info):
    option_parser, opts, args =\
       parse_command_line_parameters(disallow_positional_arguments=False, **script_info)
    
    fns = glob.glob(opts.input_path)
    if not len(fns):
        print "No input files matching glob pattern '%s'" % opts.input_path
        exit(-1)
    
    if len(args) > 1:
        raise RuntimeError("too many positional args")
    
    # have a command line label from sumatra which requires we put all results
    # in a sub-directory of the same name
    if args:
        outpath = os.path.join(opts.outpath, args[0])
    else:
        outpath = opts.outpath
    
    util.create_path(outpath)
    
    specified_direction = opts.direction is not None
    if specified_direction:
        direction = tuple(opts.direction.split('to'))
        chosen_base = direction[0]
    
    use_mi = opts.use_mi
    step = [1,3][opts.coding]
    
    ylabel = ['RE', 'MI'][use_mi]
    max_values = []
    
    flank_size = opts.flank_size
    
    for fn in fns:
        print 'working on', fn
        if not specified_direction:
            d = dir_pattern.findall(fn)
            assert len(d) == 1, d
            direction = tuple(d[0].split('to'))
            chosen_base = direction[0]
            if len(chosen_base) > 1:
                raise NotImplementedError('cannot handle strand symmetry yet')
        
        if opts.verbose:
            print "chosen_base", chosen_base
        
        basename = os.path.basename(fn).replace('.fasta.gz', '.pdf')
        if use_mi:
            basename = 'mi-' + basename
        else:
            basename = 're-' + basename
        
        outfile_name = os.path.join(outpath, basename)
        if os.path.exists(outfile_name) and not opts.force_overwrite:
            print 'Skipping', outfile_name
            continue
        
        orig_seqs = util.load_from_fasta(fn)
        seqs = orig_seqs.ArraySeqs
        seqs = util.just_nucs(seqs)
        if seqs.shape[0] < 200:
            print 'Skipped, too few sequences', fn, seqs.shape
            continue
        
        callback = PutN(seqs, direction, ylabel)
        if not use_mi:
            orig, ctl = profile.get_profiles(seqs, chosen_base=chosen_base,
                                         step=step, flank_size=flank_size)
            char_hts, max_val = get_re_char_hts(orig, ctl, chosen_base, step, flank_size)
        else:
            char_hts, max_val = get_mi_char_hts(seqs, flank_size)
        
        fig = logo.draw_alignment(char_hts.T, figsize=(9,3),
                        fig_callback=callback, verbose=False, ylim=opts.ylim)
        
        if not use_mi and opts.sig:
            num_reps = 100
            sigc = distribution.get_max_re_distribution(seqs, chosen_base,
                                            step, flank_size, num_reps=num_reps)
            fig.gca().plot(numpy.arange(0.5, sigc.shape[0], 1), sigc,
                        color='k', linestyle='-.', alpha=0.6)
            
            # determine the bootstrapped 95% CI for heights
            #lower, upper = distribution.estimate_re_ci(seqs, chosen_base, step, flank_size, num_reps=30)
            lower, upper = distribution.bootstrapped_quantiles(orig, ctl,
                                                    num_reps=num_reps)
            ax = fig.gca()
            y = numpy.fabs(char_hts).sum(axis=0)
            y_lo = numpy.fabs(y - lower)
            y_hi = numpy.fabs(y - upper)
            x = numpy.arange(0.5, y.shape[0], 1)
            ax.errorbar(x, y, yerr=[y_lo, y_hi], fmt='.', color='k',
                        ecolor='k', alpha=0.6)
        
        fig.savefig(outfile_name, bbox_inches='tight')
        print 'Wrote', outfile_name

script_info = {}
script_info['brief_description'] = ""
script_info['script_description'] = "export fasta formatted seqs matching specified conditions."


script_info['required_options'] = [
     make_option('-i','--input_path', help='glob pattern to data files.'),
     make_option('-o','--outpath', help='Path to write data.'),
    ]

script_info['optional_options'] = [
    make_option('--direction', default=None,
     choices=['AtoC', 'AtoG', 'AtoT', 'CtoA', 'CtoG', 'CtoT', 'GtoA', 'GtoC',
             'GtoT', 'TtoA', 'TtoC', 'TtoG'], help='Mutation direction.'),
    make_option('--ylim', type=float, default=None,
        help='Y-axis limit Defaults to automatic.'),
    make_option('--flank_size', type=int, default=5,
        help='Flank size.'),
    make_option('--coding', action='store_true', default=False,
        help='If True, samples pseudo-SNPs at 3-bp intervals from real SNP.'),
    make_option('--use_mi', action='store_true', default=False,
        help='Use MI for producing logo.'),
    make_option('--sig', action='store_true', default=False,
        help='Put a significance line on the plots.'),
    make_option('-F','--force_overwrite', action='store_true', default=False,
        help='Overwrite existing files.'),
    make_option('-D','--dry_run', action='store_true', default=False,
        help='Do a dry run of the analysis without writing output.'),
    ]

script_info['version'] = '0.1'
script_info['authors'] = 'Gavin Huttley'


if __name__ == "__main__":
    main(script_info)
    