#!/bin/env python2.7
# encoding: utf-8
'''
 -- Sample Set Enrichment Analysis (SSEA) --

Assessment of enrichment in a ranked list of quantitative measurements 

@author:     mkiyer
@author:     yniknafs
        
@copyright:  2013 Michigan Center for Translational Pathology. All rights reserved.
        
@license:    GPL2

@contact:    mkiyer@umich.edu
@deffield    updated: Updated
'''
# set matplotlib backend
import matplotlib
matplotlib.use('Agg')

import sys
import os
import argparse
import logging
from time import time
from datetime import datetime
import json
import matplotlib.pyplot as plt

# setup html template environment
from jinja2 import Environment, PackageLoader
env = Environment(loader=PackageLoader("ssea", "templates"))

# local imports
from algo import ssea, SampleSet, WEIGHT_METHODS

__all__ = []
__version__ = 0.1
__date__ = '2013-10-09'
__updated__ = '2013-10-09'

DEBUG = 1
TESTRUN = 0
PROFILE = 1

class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "ERROR: %s" % msg
    def __str__(self):
        return self.msg
    def __unicode__(self):
        return self.msg

class ParserError(Exception):
    '''Error parsing a file.'''
    def __init__(self, msg):
        super(ParserError).__init__(type(self))
        self.msg = "ERROR: %s" % msg
    def __str__(self):
        return self.msg
    def __unicode__(self):
        return self.msg

def render_sample_set(name, json_dict):
    t = env.get_template('detailedreport.html')
    htmlstring = t.render(name=name,data=json_dict)
    return htmlstring

def timestamp():
    return datetime.fromtimestamp(time()).strftime('%Y-%m-%d-%H-%M-%S-%f')

def parse_gmx(filename):
    fileh = open(filename)
    names = fileh.next().strip().split('\t')
    descs = fileh.next().strip().split('\t')
    if len(names) != len(descs):
        raise ParserError("Number of fields in differ in columns 1 and 2 of sample set file")
    sample_sets = [SampleSet(name=n,desc=d,value=set()) for n,d in zip(names,descs)]
    lineno = 3
    for line in fileh:
        if not line:
            continue
        line = line.strip()
        if not line:
            continue
        fields = line.split('\t')
        for i,f in enumerate(fields):
            if not f:
                continue
            sample_sets[i].value.add(f)
        lineno += 1
    fileh.close()
    return sample_sets

def parse_gmt(filename):
    sample_sets = []
    fileh = open(filename)    
    for line in fileh:
        fields = line.strip().split('\t')
        name = fields[0]
        desc = fields[1]
        values = set(fields[2:])
        sample_sets.append(SampleSet(name, desc, values))
    fileh.close()
    return sample_sets

def parse_weights(filename):
    samples = []
    weights = []
    fileh = open(filename)
    lineno = 1
    for line in open(filename):
        fields = line.strip().split('\t')
        if len(fields) == 0:
            continue
        elif len(fields) == 1:
            raise ParserError("Only one field at line number %d" % (lineno))
        sample = fields[0]
        try:
            rank = float(fields[1])
        except ValueError:
            raise ParserError("Value at line number %d cannot be converted to a floating point number" % (lineno))    
        samples.append(sample)
        weights.append(rank)
        lineno += 1
    fileh.close()
    return samples,weights

def main(argv=None):
    '''Command line options.'''    
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = '''%s

  Created by mkiyer and yniknafs on %s.
  Copyright 2013 MCTP. All rights reserved.
  
  Licensed under the GPL
  http://www.gnu.org/licenses/gpl.html
  
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
''' % (program_shortdesc, str(__date__))

    try:
        # Setup argument parser
        parser = argparse.ArgumentParser(description=program_license, 
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("-v", "--verbose", dest="verbose", 
                            action="store_true", default=False, 
                            help="set verbosity level [default: %(default)s]")
        parser.add_argument('-V', '--version', action='version', 
                            version=program_version_message)
        parser.add_argument('--weight-miss', dest='weight_miss',
                            choices=WEIGHT_METHODS, default='weighted') 
        parser.add_argument('--weight-hit', dest='weight_hit', 
                            choices=WEIGHT_METHODS, default='weighted')
        parser.add_argument('--perms', type=int, default=1000)
        parser.add_argument('--no-plot-conf-int', dest="plot_conf_int", 
                            action="store_false", default=True)
        parser.add_argument('--conf-int', dest="conf_int", type=float, 
                            default=0.95)
        parser.add_argument('--gmx', dest="gmx_files", action='append')
        parser.add_argument('--gmt', dest="gmt_files", action='append')
        parser.add_argument('-o', '--output-dir', dest="output_dir", default=None)
        parser.add_argument('-n', '--name', dest="name", default="myssea")
        parser.add_argument('weights_file') 
        # Process arguments
        args = parser.parse_args()
        verbose = args.verbose
        weights_file = args.weights_file
        gmx_files = args.gmx_files
        gmt_files = args.gmt_files
        output_dir = args.output_dir
        name = args.name
        # setup logging
        if DEBUG or (verbose > 0):
            level = logging.DEBUG
        else:
            level = logging.INFO
        logging.basicConfig(level=level,
                            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        # check and get parameters
        perms = max(1, args.perms)
        # read sample sets
        sample_sets = []
        if gmx_files is not None:
            for filename in gmx_files:
                if not os.path.exists(filename):
                    parser.error("gmx file '%s' not found" % (filename))
                sample_sets.extend(parse_gmx(filename))
        if gmt_files is not None:
            for filename in gmt_files:
                if not os.path.exists(filename):
                    parser.error("gmt file '%s' not found" % (filename))
                sample_sets.extend(parse_gmt(filename))
        # read weights
        if not os.path.exists(weights_file):
            parser.error("weights file '%s' not found" % (weights_file))
        samples, weights = parse_weights(weights_file)
        # output directory
        if output_dir is None:
            output_dir = "SSEA_%s" % (timestamp())
        #if os.path.exists(output_dir):
        #    parser.error("output directory '%s' already exists" % (output_dir))
        # run
        logging.info("Parameters")
        logging.info("\tname:               %s" % (name))
        logging.info("\toutput directory:   %s" % (output_dir))
        logging.info("\tnum sample sets:    %d" % (len(sample_sets)))
        logging.info("\tpermutations:       %d" % (perms))
        logging.info("\tweight method miss: %s" % (args.weight_miss))
        logging.info("\tweight method hit:  %s" % (args.weight_hit))
        logging.info("\tplot conf interval: %s" % (args.plot_conf_int))
        logging.info("\tconf interval:      %f" % (args.conf_int))
        logging.info("Running SSEA")
        results = ssea(samples, weights, sample_sets, 
                       weight_method_miss=args.weight_miss,
                       weight_method_hit=args.weight_hit,
                       perms=perms)
        if not os.path.exists(output_dir):
            logging.info("Creating output directory '%s'" % (output_dir))
            os.makedirs(output_dir)
        logging.info("Writing output")
        json_data = []
        for res in results:
            # create enrichment plot
            enrichment_png = '%s.%s.eplot.png' % (name, res.sample_set.name)
            enrichment_pdf = '%s.%s.eplot.pdf' % (name, res.sample_set.name)
            fig = res.plot(plot_conf_int=args.plot_conf_int,
                           conf_int=args.conf_int)
            fig.savefig(os.path.join(output_dir, enrichment_png))
            fig.savefig(os.path.join(output_dir, enrichment_pdf))
            plt.close()
            # create null distribution plot
            null_png = '%s.%s.null.png' % (name, res.sample_set.name)
            null_pdf = '%s.%s.null.pdf' % (name, res.sample_set.name)            
            fig = res.plot_null_distribution()
            fig.savefig(os.path.join(output_dir, null_png))
            fig.savefig(os.path.join(output_dir, null_pdf))
            plt.close()
            # create report dictionary for json
            d = res.get_report_json()
            # update dictionary with image files
            d.update({'eplot_png': enrichment_png,
                      'eplot_pdf': enrichment_pdf,
                      'null_png': null_png,
                      'null_pdf': null_pdf})
            details_filename = '%s.%s.json' % (name, res.sample_set.name)
            fp = open(os.path.join(output_dir, details_filename), 'w')
            json.dump(d, fp)
            fp.close()
            # render to html
            t = env.get_template('detailedreport.html')
            html_filename = '%s.%s.html' % (name, res.sample_set.name)
            fp = open(os.path.join(output_dir, html_filename), 'w')
            print >>fp, t.render(name=name,data=d)
            fp.close()
            # delete details and save overview stats
            del d['details'] 
            d['details'] = details_filename
            json_data.append(d)
        # write main json file
        json_data = {'name': name,
                     'prog': program_version_message,
                     'perms': perms,
                     'weight_method_miss': args.weight_miss,
                     'weight_method_hit': args.weight_hit,
                     'results': json_data}
        report_filename = '%s.json' % (name)
        fp = open(os.path.join(output_dir, report_filename), 'w')              
        json.dump(json_data, fp, indent=2, sort_keys=True)
        fp.close()
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        pass
#     except Exception, e:
#         pass
#         if DEBUG or TESTRUN:
#             raise(e)
#         indent = len(program_name) * " "
#         logging.error(program_name + ": " + repr(e) + "\n")
#         logging.error(indent + "  for help use --help")
#         return 2
    return 0

if __name__ == "__main__":
    if DEBUG:
        pass
    if TESTRUN:
        pass
        #import doctest
        #doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = '_profile.bin'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())