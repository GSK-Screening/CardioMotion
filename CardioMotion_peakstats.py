###This script reads the signal data produced, and calculates peakstats data. This script can optionally graph the data.

#import packages
import argparse
import logging
import os.path
import re
import sys
import numpy as np
import pandas as pd
import scipy.signal as sig
from scipy.interpolate import interp1d

logger = logging.getLogger('Cardio-Motion_logger')

#small function for converting row letter to number (A->1, B->2 etc.)
def alpha_to_int(row_str):
    return ord(row_str.lower())-96

def calc_peakstats(source_dir, dest_dir, min_prominence, min_width, cutoff, show_graphs):
        
    raw_data = pd.DataFrame(columns=['Plate', 'Well','Column', 'Row', 'Row Number', 'Time (s)', 'Contractile_Movement (nm)']) #data input format

    # Find csv files
    logger.info('Loading directory {0}'.format(source_dir))
    source_files = os.listdir(source_dir)
    source_files = list(filter(lambda f: f.endswith('.csv'), source_files))
    for source in source_files:
        try:
            source_data = pd.read_csv(os.path.join(source_dir, source))
        except Exception:
            logger.exception('Exception while reading {0}'.format(source))
            continue
        if source_data.columns.tolist() != raw_data.columns.tolist(): # In case we have any rogue .csv files
            logger.warning('Unexpected column names - ignoring {0}'.format(source))
            continue
        raw_data = raw_data.append(source_data, ignore_index=True)
        logger.info('Loaded {0}'.format(source))

    plates = raw_data['Plate'].unique().tolist()
    logger.info('Plates found: {0}'.format(len(plates)))
    for plate in plates:
        logger.info('Processing plate <{0}>'.format(plate))
        plate_data = raw_data.loc[raw_data['Plate'] == plate]

        output_path = os.path.join(dest_dir, '{0}_Cardio-Motion_raw.csv'.format(plate))
        logger.info('Saving raw data to {0}'.format(output_path))
        plate_data.to_csv(output_path, index=False)

        wells = plate_data['Well'].unique().tolist()
        logger.info('Found {0} wells on plate <{1}>'.format(len(wells), plate))
        peak_data = []
        for well in wells:
            well_data = plate_data.loc[plate_data['Well'] == well]
            logger.info('Processing well <{0}> on plate <{1}>'.format(well, plate))
            times, signal = (list(l) for l in zip(*sorted(zip(well_data['Time (s)'], well_data['Contractile_Movement (nm)']))))
            t = interp1d(list(range(len(times))), times)

           
            
            # Find peaks according to parameters
            peaks, props = sig.find_peaks(signal, prominence=min_prominence, width=min_width, height=0, rel_height=(1.0 - cutoff))
            logger.info('Peaks found: {0}'.format(len(peaks)))

            if show_graphs: # Visualise
                import matplotlib.pyplot as plt
                plt.plot(times, signal, "-k")
                plt.plot([t(p) for p in peaks], [signal[p] for p in peaks], "xr")
                plt.plot([t(p) for p in peaks], [signal[p] for p in peaks], "xr")
                plt.plot([t(p) for p in props['left_ips']], [signal[p] for p in peaks], '|b')
                plt.plot([t(p) for p in props['right_ips']], [signal[p] for p in peaks], '|b')
                plt.plot([t(p) for p in peaks], [signal[p] - pr for p, pr in zip(peaks, props['prominences'])], '_r')
                plt.title('Plate <{0}>, well <{1}>'.format(plate, well))
                plt.xlabel('Time (s)'); plt.ylabel('Contractile Movement (nm)')
                plt.ylim(bottom=0)
                plt.show()
            
            height = 0.0
            width = 0.0
            freq = 0.0
            gap = 0.0

            if len(peaks) > 0:
                height = np.median(props['prominences'])
                width = np.median([(t(b) - t(a)) for a, b in zip(props['left_ips'], props['right_ips'])])
                freq = 60 * len(peaks) / (times[-1] - times[0] + times[1] - times[0])
            if len(peaks) > 1:
                periods = [t(x1) - t(x0) for x0, x1 in zip(peaks[:-1], peaks[1:])]
                freq = 60 / np.median(periods)
                gaps = [t(b) - t(a) for a, b in zip(props['right_ips'][:-1], props['left_ips'][1:])]
                gap = np.median(gaps)
            
            #for extracting column and row numbers
            row = well[0]
            column = well[1:]
            row_num = alpha_to_int(row)

            peak_data.append([plate, well, row, row_num, column, height, width, freq, gap])
        
        columns = ['Plate', 'Well',
            'Row', 'Row Number',
            'Column',
            'Peak Amplitude (nm)',
            'Peak Width (s)',
            'Peak Frequency (bpm)',
            'Peak Spacing (s)'] #output format
        output_path = os.path.join(dest_dir, '{0}_Cardio-Motion_peakstats.csv'.format(plate))
        logger.info('Saving peak statistics to {0}'.format(output_path))
        pd.DataFrame.from_records(peak_data, columns=columns).to_csv(output_path, index=False)
