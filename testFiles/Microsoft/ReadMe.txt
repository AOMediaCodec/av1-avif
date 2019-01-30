======= AVIF test file collection from Microsoft. ==========

All files contain Exif metadata and are tagged as MIAF compatible.
All files are tagged as compatible with the AVIF Baseline Profile, unless stated otherwise.
Copyright statement, if any, is included in the Exif metadata.


Irvine_CA.avif
Small portrait orientation image. 480x640 pixels. This image does not require the client to rotate.

Kids_720p.avif
Small landscape orientation image. 1280x720 pixels.

Mexico.avif
Landscape image, 1920x1080 pixels.

Mexico_YUV444.avif
AVIF Advanced Profile image. Low resolution (970x540 pixels) but uses 4:4:4 chroma subsampling instead of the usual 4:2:0 subsampling.

bbb_4k.avif
4K image (3840x2160 pixels)

Summer_Nature_4k.avif
4K image (3840x2160 pixels)

Ronda_rotate90.avif
Encode resolution: 1920x1080. Display resolution: 1080x1920. This image is encoded in landscape mode and shall be rotated 90 degrees clockwise by the client, such that it is displayed in portrait mode.

Chimera_8bit_cropped_480x256.avif
Encode resolution: 480x270. Display resolution: 480x256. This image is encoded with black bars at the top and bottom of the image. The client shall crop this image to 480x256 resolution prior to displaying it, such that the black bars are not visible.

Summer_in_Tomsk_720p_5x4_grid.avif
5x4 element grid image, derived from 20 coded images. Each coded image is 1280x720. The client shall display all 20 images in a 5x4 grid with no seams betwen the images. Display resolution: 6400x2880 pixels.

Chimera_10bit_cropped_to_1920x1008.avif
10-bit AV1 encode at 1920x1080 pixels. Display resolution: 1920x1008. This image is encoded with black bars at the top and bottom of the image. The client shall crop this image to 1920x1008 resolution prior to displaying it, such that the black bars are not visible.

Chimera_10bit_cropped_to_1920x1008_with_HDR_metadata.avif
This file is encoded the same way as Chimera_10bit_cropped_to_1920x1008.avif but also includes Mastering Display Color Volume metadata and Content Light Level metadata. Note, the metadata values were chosen arbitrarily and may not match the encoding.

still_picture.avif
Encode and display resolution: 1280x720. This file has the "still_picture" flag set to 1 in the AV1 Sequence Header.

reduced_still_picture_header.avif
This file is encoded the same way as "still_picture.avif" but it also has the "reduced_still_picture_header" flag set to 1 in the AV1 Sequence Header.

Monochrome.avif
Encode and display resolution: 1280x720. This file is encoded as monochrome.

Tomsk_with_thumbnails.avif
The primary image is encoded at 1280x720. The file contains two embedded thumbnails, encoded at 320x180 and 160x90 resolution, respectively.

bbb_alpha_inverted.avif
An image with an associated alpha plane image. Both the master image and the alpha plane image have a resolution of 3840x2160 pixels.
The alpha image is encoded as a monochrome image in AV1 format.
Note: In this particular image, the transparancy is applied on the "Big Buck BUNNY" text, while the background remains solid.

==== Attributions/Copyright =====
bbb_4k.avif:
bbb_alpha_inverted.avif:
Copyright Blender Foundation 2008, Janus Bager Kristensen 2013 - Creative Commons Attribution 3.0 - http://bbb3d.renderfarming.net

Chimera_8bit_cropped_480x256.avif:
Chimera_10bit_cropped_to_1920x1008.avif:
Chimera_10bit_cropped_to_1920x1008_with_HDR_metadata.avif:
Copyright Netflix Inc. These video sequences are licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License.

Summer_in_Tomsk_720p_5x4_grid.avif:
Summer_Nature_4k.avif:
still_picture.avif:
reduced_still_picture_header.avif:
Monochrome.avif:
Tomsk_with_thumbnails.avif:
Derived from video streams downloaded from https://www.elecard.com/videos
