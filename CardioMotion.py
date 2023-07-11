### CardioMotion ###

##Import required packages. If using Anaconda,  all packages required are installed in the base environment except openCV. 
			  ##### See README for environment setup instructions. ########

import argparse
import logging
import os.path
import sys
import pandas as pd


#Import child scripts#

import CardioMotion_image_loader
import CardioMotion_signal_extractor
import CardioMotion_peakstats

#These default values are used if neither an argument value is given nor a suitably formatted metadata file is available. 
#The script will give warning if these defaults are used.

default_fps_value = 40.0
default_scale_value = 650 # nm/px
default_min_prominence = 65 # nm
default_min_width = 0.2 # seconds
default_cutoff = 0.25

# Read command line arguments - the only required argument is source_dir. All other arguments should be used as necessary
parser = argparse.ArgumentParser()
parser.add_argument('source_dir', help='path to the directory containing the input image files')
parser.add_argument('dest_dir', nargs='?', default=None, help='path to a directory in which to save the output files (default is to create a subdirectory of source_dir)')
parser.add_argument('--fps', type=float, default=None, help='video fps (default is to read from the .mes file)')
parser.add_argument('--scale', type=float, default=None, help='nanometers per pixel (default is to calculate using information in the .mes file)')
parser.add_argument('--prominence', type=float, default=default_min_prominence, help='minimum acceptable peak topographic prominence to register')
parser.add_argument('--width', type=float, default=default_min_width, help='minimum acceptable peak width to register (measured in seconds)')
parser.add_argument('--cutoff', type=float, default=default_cutoff, help='proportion of the height of the peak at which to measure width - must be between 0.0 (measure at base) and 1.0 (measure at top)')
parser.add_argument('--graph', action='store_true', help='display a graph of each signal with the located peaks marked')
args = parser.parse_args()

# Set up logging - script produces both a 'log' and 'error' file.
log_format = '[%(asctime)s] %(levelname)s: %(message)s'
formatter = logging.Formatter(log_format)
logger = logging.getLogger('Cardio-Motion_logger')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)
handler = logging.FileHandler('Cardio-Motion_log.txt')
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)
handler = logging.FileHandler('Cardio-Motion_errors.txt')
handler.setLevel(logging.WARNING)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Check arguments are ok
if args.fps is not None and not (args.fps > 0.0 and args.fps < 1000.0):
    logger.error('Invalid fps: {0}'.format(args.fps))
    args.fps = None
if not os.path.isdir(args.source_dir):
    logger.error('Directory does not exist: {0}'.format(args.source_dir))
    exit(1)
if args.dest_dir == None:
    dest_dir = os.path.join(args.source_dir, 'Cardio-Motion_Data')
    if not os.path.exists(dest_dir):
        os.mkdir(dest_dir)
else: dest_dir = args.dest_dir
if not os.path.isdir(dest_dir):
    logger.error('Directory does not exist: {0}'.format(args.dest_dir))
    logger.warning('Defaulting to saving in working directory')
    args.dest_dir = '.'
if not (args.cutoff >= 0.0 and args.cutoff <= 1.0):
    logger.error('Invalid cutoff: {0}'.format(args.cutoff))
    exit(1)

# Ensure subdirectory for output
logger.info('Output directory: {0}'.format(dest_dir))

# Set up metadata - see CardioMotion_image_loader.py 
logger.info('Loading directory: {0}'.format(args.source_dir))
fps, scale = CardioMotion_image_loader.load_metadata(args.source_dir)
if args.fps != None: fps = args.fps
if fps == None: fps = default_fps_value
logger.info('Using fps: {0}'.format(fps))
if args.scale != None: scale = args.scale
if scale == None: scale = default_scale_value
logger.info('Using scale: {0}nm/px'.format(scale))

# Search directory for image files - see CardioMotion_image_loader.py 
source_data = CardioMotion_image_loader.find_images(args.source_dir, fps)
if len(set((source_data['Well'] == w).sum() for w in source_data['Well'].unique())) > 1:
    logger.warning('Inconsistent number of frames per well')

# Process images
def alpha_to_int(row_str):
    return ord(row_str.lower())-96
plates = source_data['Plate'].unique().tolist()
logger.info('Number of plates to process: {0}'.format(len(plates)))
for plate in plates:
    logger.info('Processing plate <{0}>'.format(plate))
    output_dir = os.path.join(dest_dir, 'Raw Well level data')
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    wells = source_data.loc[source_data['Plate'] == plate]['Well'].unique().tolist()
    logger.info('Number of wells to process on plate <{0}>: {1}'.format(plate, len(wells)))
    for well in wells:
        try:
            # This allows you to restart where you left off, e.g. if you killed the program with Ctrl-C. All
	    # previously run wells will be skipped.
            output_path = os.path.join(output_dir, '{0}_{1}.csv'.format(plate, well))
            if os.path.isfile(output_path):
                logger.info('File already exists: {0}'.format(output_path))
                logger.info('Skipping <{0}>/<{1}>'.format(plate, well))
                continue

            logger.info('Processing well <{0}> on plate <{1}>'.format(well, plate))
            times, data = CardioMotion_image_loader.load_images(source_data.loc[(source_data['Plate'] == plate) & (source_data['Well'] == well)])
            if times is None or data is None:
                logger.warning('Skipping <{0}>/<{1}>'.format(plate, well))
                continue
            signal = CardioMotion_signal_extractor.calc(data) # This is the most important line in the file - see CardioMotion_signal_extractor.py
            
	    #extract row / column / row number info
	    row = well[0] 
            column = well[1:]
            row_num = alpha_to_int(row)
            
            logger.info('Finished processing, saving to {0}'.format(output_path))
            df = pd.DataFrame(columns=['Plate', 'Well', 'Column' , 'Row', 'Row Number', 'Time (s)', 'Contractile_Movement (nm)'])
            df = df.append(pd.DataFrame.from_records(((plate, well, column, row, row_num, times[i], signal[i] * scale) for i in range(times.size)), columns=df.columns))
            df.to_csv(output_path, index=False)
        except KeyboardInterrupt:
            print('Keyboard Interrupt')
            exit(1)
        except Exception:
            logger.exception('Exception while processing <{0}>/<{1}>'.format(plate, well))
logger.info('Finished signal calculation')

# Find peaks in signal data - see CardioMotion_peakstats.py
logger.info('Finding peaks')
for plate in plates:
    CardioMotion_peakstats.calc_peakstats(os.path.join(dest_dir, 'Raw Well level data'), dest_dir, args.prominence, args.width * fps, args.cutoff, args.graph)
