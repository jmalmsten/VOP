"""
VOP Module:     media_formats.py
Description:    Single source of truth for which still-image file types the
                VOP accepts for Proj Mag / BiPack layers. Imported by both
                vop.py (upload + counting + aspect routes) and
                graphics_utils.py (texture loading), so they can never
                disagree again.
"""
###########################################################################
#
#                                   VOP
#                       Copyright (C) 2025  jmalmsten
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as
#     published by the Free Software Foundation, either version 3 of the
#     License, or (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with this program.  If not, see
#     <http://www.gnu.org/licenses/>.
#
#     Source code for this application can be found at
#     https://github.com/jmalmsten/VOP
#
###########################################################################

# MUST be a tuple. str.endswith() accepts a str or a TUPLE of str; a list or
# set raises TypeError, so don't "tidy" this into a list.
# Matching is done on f.lower() by the callers, so .JPG / .Jpeg are fine.
# Every entry was verified through TextureManager.load() on OpenCV 4.13.
# Deliberately NOT here: .gif / animated formats (need ffmpeg frame extraction),
# .exr / float TIFF (loader only handles 8/16-bit integer data), .heic
# (OpenCV can't read it).
STILL_IMAGE_EXTS = (
    '.png',
    '.jpg', '.jpeg',
    '.tif', '.tiff',
    '.webp',
    '.bmp',
    '.pbm', '.pgm', '.ppm',
    '.jp2',
    '.avif',
)