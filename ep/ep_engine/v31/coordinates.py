"""Pixel-center transforms between processing, source, and review frames."""

import numpy as np


def resize_frame(source_shape, target_shape):
    sh, sw = source_shape
    th, tw = target_shape
    sx, sy = tw / sw, th / sh
    return np.array([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1.0]])


def original_transform(matrix, before_processing, after_processing, before_source, after_source):
    return (
        resize_frame(after_processing, after_source)
        @ matrix
        @ resize_frame(before_source, before_processing)
    )


def crop_frame(box, dimensions):
    x, y, right, bottom = box
    width, height = dimensions
    return resize_frame((bottom - y, right - x), (height, width)) @ np.array(
        [[1.0, 0, -x], [0, 1.0, -y], [0, 0, 1.0]]
    )
