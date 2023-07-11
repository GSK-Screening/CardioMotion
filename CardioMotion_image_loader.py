###this script imports images, based on the output from the Yokogawa CV8000 imager. See comments for 
###adapting to other imagers.

#import necessary packages
import logging
import os
import re
from multiprocessing.pool import ThreadPool #script is paralelisable for rapid processing
import lxml.etree as xmlet
import numpy as np
import pandas as pd
import cv2 as cv

# Code expects filename to contain 4 groups: plate id, well id, frame number, series id. 
re_image_file = r'(.*)_([A-Z]\d{2})_T(\d{4})(F\d{3}L\d{2}A\d{2}Z\d{2}C\d{2}).tif' ###!!!Change this regex for other imagers!!!###
n_threads = 4
camera_pixel_size = 6500 # Nanometres - may require changing for other imagers

logger = logging.getLogger('Cardio-Motion_logger')

# Search for .mes file in directory and calculate (fps, scale). 
#!!!.mes file is xml metadata file from CV8000. Adapt for other imagers. If no .mes file found, script will use defaults
#as defined in parent script, or command line arguments)!!!#
def load_metadata(dir_path):
    fps = None
    scale = None
    mes_files = list(filter(lambda f: f.endswith('.mes'), os.listdir(dir_path)))
    if len(mes_files) > 1:
        logger.warning('Found multiple .mes files, using {0}'.format(mes_files[0]))
    if len(mes_files) > 0:
        logger.info('Reading .mes file: {0}'.format(mes_files[0]))
        try:
            mes_data = xmlet.parse(os.path.join(dir_path, mes_files[0]))
            root = mes_data.getroot()
            liveoption = root.find('.//bts:LiveOption', root.nsmap)
            if liveoption is not None:
                interval = int(liveoption.attrib['{{{0}}}Interval'.format(root.nsmap['bts'])])
                fps = 1000 / interval # Interval is measured in milliseconds
            else: logger.error('Failure processing .mes file')
            channel = root.find('.//bts:Channel', root.nsmap)
            if channel is not None:
                binning = int(channel.attrib['{{{0}}}Binning'.format(root.nsmap['bts'])])
                magnification = float(channel.attrib['{{{0}}}Magnification'.format(root.nsmap['bts'])])
                scale = camera_pixel_size * binning / magnification # Formula may need adjusting
            else: logger.error('Failure processing .mes file')
        except Exception:
            fps = None
            scale = None
            logger.exception('Exception while processing {0}'.format(mes_files[0]))
    else: logger.warning('No .mes file found')
    
    return fps, scale

# Search for image files in directory and return a table with file paths
def find_images(dir_path, fps):
    dir_files = os.listdir(dir_path)
    rows_list = []
    series_list = []

    # Find files that look like microsope image output
    logger.info('Regex to match image files: {0}'.format(re_image_file)) #This line requires the given regex to be correct
    for file_name in dir_files:
        match = re.fullmatch(re_image_file, file_name)
        if match is not None:
            rows_list.append([match.group(1), match.group(2), (int(match.group(3)) - 1) / fps, os.path.join(dir_path, file_name)])
            series_list.append(match.group(4))
    if len(rows_list) > 0:
        logger.info('Found {0} image files'.format(len(rows_list)))
    else: logger.warning('No image files found')

    # Group by series if there are more than one
    if len(set(series_list)) > 1:
        for row, s in zip(rows_list, series_list): row[0] += '_' + s

    # Return list of located images
    return pd.DataFrame(rows_list, columns=['Plate', 'Well', 'Time', 'Path'])

# Read a single video to memory
def load_images(source_data):
    num_frames = len(source_data)
    times = source_data['Time'].to_numpy()

    # Read all files
    if n_threads > 1: #allows paralelizing
        pool = ThreadPool(n_threads)
        raw_data = pool.map(lambda path: cv.imread(path, cv.IMREAD_ANYDEPTH | cv.IMREAD_GRAYSCALE), source_data['Path'])
        pool.terminate()
    else: raw_data = [cv.imread(path, cv.IMREAD_ANYDEPTH | cv.IMREAD_GRAYSCALE) for path in source_data['Path']]

    # Record which loads succeeded
    successes = np.fromiter((img is not None for img in raw_data), dtype=bool)

    # Determine normalisation
    val_min = np.inf
    val_max = 0
    for i in range(num_frames):
        if not successes[i]:
            logger.error('Failed to load {0}'.format(source_data['Path'][i]))
            continue
        val_min = min(val_min, raw_data[i].min())
        val_max = max(val_max, raw_data[i].max())

    # Contrast stretch and save to 3d array ('data')
    data = None
    for i in range(num_frames):
        if not successes[i]: continue
        if data is None: # Infer frame size from first image
            data = np.zeros((num_frames, raw_data[i].shape[0], raw_data[i].shape[1]), dtype=np.uint8)
        if raw_data[i].shape != data[i,:,:].shape:
            logger.error('Inconsistent dimensions across images - check {0}'.format(source_data['Path'][i]))
            successes[i] = False
            continue
        data[i,:,:] = (256 * ((raw_data[i] - val_min) / max(1, val_max - val_min))).clip(0, 255).astype(np.uint8)

    del raw_data # Could be very big, so deletes asap

    if successes.sum() == 0:
        logger.error('No frames successfully loaded')
        return None, None
    elif successes.sum() < num_frames:
        logger.warning('Only {0} out of {1} frames successfully loaded'.format(successes.sum(), num_frames))
        # Cut frames that failed to load
        times = np.asarray([p[1] for p in filter(lambda p: p[0], zip(successes, times))])
        data = np.vstack(p[1] for p in filter(lambda p: p[0], zip(successes, data)))
    else: logger.info('Successfully loaded {0} frames'.format(num_frames))
    return times, data
