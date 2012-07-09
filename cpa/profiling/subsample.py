#!/usr/bin/env python

def _compute_group_subsample((cache_dir, image_key, indices)):
    import numpy as np
    from .cache import Cache, RobustLinearNormalization
    cache = Cache(cache_dir)
    normalizeddata, normalized_colnames, _ = cache.load([image_key], normalization=RobustLinearNormalization)
    return normalizeddata[indices]

import operator
import random
import logging
from optparse import OptionParser
import numpy as np
import cpa
from .cache import Cache
from .parallel import ParallelProcessor, Uniprocessing

def _break_indices(indices, image_keys, counts):
    """Break the overall list of random indices into per-image indices."""
    sorted_indices = np.sort(indices)
    a = 0
    start = end = 0
    for image_key in image_keys:
        c = counts.get(tuple(map(int, image_key)), 0) # case from long
        while end < len(sorted_indices) and sorted_indices[end] < a + c:
            end += 1
        yield sorted_indices[start:end] - a
        start = end
        a += c

def _make_parameters(cache_dir, image_keys, per_image_indices):
    return [(cache_dir, image_key, indices)
            for image_key, indices in zip(image_keys, per_image_indices)]

def _combine_subsample(generator):
    return np.vstack([a for a in generator if len(a.shape) == 2])

def subsample(cache_dir, sample_size, filter=None, 
              parallel=Uniprocessing(), show_progress=True, verbose=True):
    cache = Cache(cache_dir)
    counts = cache.get_cell_counts()
    ncells = reduce(operator.add, counts.values())
    if sample_size is None:
        sample_size = round(0.001 * ncells)
    if verbose:
        print 'Subsampling {0} of {1} cells'.format(sample_size, ncells)

    indices = np.array(random.sample(xrange(ncells), sample_size))
    image_keys = cpa.db.GetAllImageKeys()
    per_image_indices = _break_indices(indices, image_keys, counts)
    parameters = _make_parameters(cache_dir, image_keys, per_image_indices)

    njobs = len(parameters)
    generator = parallel.view('profile_factor_analysis_mean.subsample').imap(_compute_group_subsample, parameters)
    if show_progress:
        import progressbar
        progress = progressbar.ProgressBar(widgets=['Subsampling:',
                                                    progressbar.Percentage(), ' ',
                                                    progressbar.Bar(), ' ', 
                                                    progressbar.Counter(), '/', 
                                                    str(njobs), ' ',
                                                    progressbar.ETA()],
                                           maxval=njobs)
    else:
        progress = lambda x: x
    return _combine_subsample(progress(generator))

def _parse_arguments():
    global options, parallel
    global properties_file, cache_dir, output_filename, sample_size
    parser = OptionParser("usage: %prog [options] PROPERTIES-FILE CACHE-DIR OUTPUT-FILENAME [SAMPLE-SIZE]")
    ParallelProcessor.add_options(parser)
    parser.add_option('-f', dest='filter', help='only profile images matching this CPAnalyst filter')
    parser.add_option('-p', dest='progress', action='store_true', help='show progress bar')
    parser.add_option('-v', dest='verbose', action='store_true', help='print additional information')
    options, args = parser.parse_args()
    parallel = ParallelProcessor.create_from_options(parser, options)
    if len(args) < 3 or len(args) > 4:
        parser.error('Incorrect number of arguments')
    properties_file, cache_dir, output_filename = args[:3]
    if len(args) == 4:
        sample_size = int(args[3])
    else:
        sample_size = None

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    _parse_arguments()
    cpa.properties.LoadFile(properties_file)
    sample = subsample(cache_dir, sample_size, filter=options.filter, 
                       parallel=parallel, show_progress=options.progress,
                       verbose=options.verbose)
    np.save(output_filename, sample)
