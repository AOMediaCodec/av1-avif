# Originals

Original sources are named as such and contain the following profiles:

    original_hdr_*.png - BT2020 PQ @ 16bpc (upscaled from original 12bpc P3 PQ sources)
    original_sdr_*.png - SRGB @ 8bpc

SDR content was subjectively (manually) tonemapped down into SDR range from the original HDR frames.

# HDR AVIF generation

HDR avifs were generated with the following command patterns:

    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --lossless --cicp 9/16/0 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-0_lossless.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --cicp 9/16/9 --range full --yuv 444 --min 10 --max 10 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-9_yuv444_full_qp10.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --cicp 9/16/9 --range full --yuv 444 --min 20 --max 20 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-9_yuv444_full_qp20.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --cicp 9/16/9 --range full --yuv 444 --min 40 --max 40 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-9_yuv444_full_qp40.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --cicp 9/16/9 --range limited --yuv 420 --min 10 --max 10 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-9_yuv420_limited_qp10.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --cicp 9/16/9 --range limited --yuv 420 --min 20 --max 20 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-9_yuv420_limited_qp20.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 10 --ignore-icc --cicp 9/16/9 --range limited --yuv 420 --min 40 --max 40 original_hdr_cosmosXXXXX.png hdr_cosmosXXXXX_cicp9-16-9_yuv420_limited_qp40.avif

Note: The `--lossless` command here will warn simply because the source material is 16bpc and the destination is 10bpc, but it is otherwise encoded as lossless.

# SDR AVIF generation

SDR avifs were generated with the following command patterns:

    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --lossless --cicp 1/13/0 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-0_lossless.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --cicp 1/13/6 --range full --yuv 444 --min 10 --max 10 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-6_yuv444_full_qp10.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --cicp 1/13/6 --range full --yuv 444 --min 20 --max 20 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-6_yuv444_full_qp20.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --cicp 1/13/6 --range full --yuv 444 --min 40 --max 40 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-6_yuv444_full_qp40.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --cicp 1/13/6 --range limited --yuv 420 --min 10 --max 10 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-6_yuv420_limited_qp10.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --cicp 1/13/6 --range limited --yuv 420 --min 20 --max 20 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-6_yuv420_limited_qp20.avif
    avifenc -c aom --speed 0 --jobs 12 --depth 8 --ignore-icc --cicp 1/13/6 --range limited --yuv 420 --min 40 --max 40 original_sdr_cosmosXXXXX.png sdr_cosmosXXXXX_cicp1-13-6_yuv420_limited_qp40.avif

# Adjacent PNGs

All `.avif` files should have an adjacent `.png` with the same basename, which was generated with the following command:

    avifdec name_of_file.avif name_of_file.png

It will not contain an ICC profile but should be considered to have the same color profile as the associated AVIF.
