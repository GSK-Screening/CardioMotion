###This script performs the key function - calculating signal based on Farneback. 

import os 
from multiprocessing.pool import ThreadPool

import numpy as np

import cv2 as cv #This package is not available in the base environment of anaconda, and must be installed. See documentation.

#Allow script to be parallelisable
n_threads = os.cpu_count()
if n_threads is None: n_threads = 1

window_size = 16

# Two frame comparison
def calc_single(img_pair):
    flow = cv.calcOpticalFlowFarneback(img_pair[0], img_pair[1], None, 0.5, 2, window_size, 3, 5, 1.2, 0)
    for d in (0, 1): flow[...,d] -= flow[...,d].mean()
    return np.sqrt(np.square(flow[...,0]) + np.square(flow[...,1])).mean()
# Video to signal
def calc(data):
    reference = np.median(data, axis=0) #reference frame is median of all images
    if n_threads > 1:
        pool = ThreadPool(n_threads)
        signal = pool.map(calc_single, ((reference, img) for img in data))
        pool.terminate()
    else: signal = [calc_single((reference, img)) for img in data]
    return np.asarray(signal)
