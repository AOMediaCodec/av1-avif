CAVIF=cavif
DAVIF=davif

.PHONY: all clean hato kimono decode-hato decode-kimono

all: hato kimono;

hato: \
	hato.profile2.8bpc.yuv422.no-cdef.avif \
	hato.profile2.8bpc.yuv422.monochrome.no-cdef.avif \
  hato.profile2.10bpc.yuv422.no-cdef.no-restoration.avif \
	hato.profile2.10bpc.yuv422.monochrome.no-cdef.no-restoration.avif \
	hato.profile2.12bpc.yuv422.no-cdef.no-restoration.avif \
	hato.profile2.12bpc.yuv422.monochrome.no-cdef.no-restoration.avif \
	hato.profile0.8bpc.yuv420.no-cdef.avif \
	hato.profile0.8bpc.yuv420.monochrome.no-cdef.avif \
	hato.profile0.10bpc.yuv420.no-cdef.no-restoration.avif \
	hato.profile0.10bpc.yuv420.monochrome.no-cdef.no-restoration.avif

kimono: \
	kimono.avif \
	kimono.rotate90.avif \
	kimono.rotate270.avif \
	kimono.mirror-horizontal.avif \
	kimono.mirror-vertical.avif \
	kimono.mirror-vertical.rotate270.avif \
	kimono.crop.avif \
	kimono.mirror-vertical.rotate270.crop.avif

decode-hato:
	find . -type f -name hato.\*.avif -exec $(DAVIF) -i {} -o {}.png \;

decode-kimono:
	find . -type f -name kimono.\*.avif -exec $(DAVIF) -i {} -o {}.png \;

clean:
	rm -fv *.avif *.avif.png

## YUV422

hato.profile2.8bpc.yuv422.no-cdef.avif: hato.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 2 --bit-depth 8 --pix-fmt yuv422 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

hato.profile2.8bpc.yuv422.monochrome.no-cdef.avif: hato.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 2 --bit-depth 8 --pix-fmt yuv422 --disable-cdef --enable-loop-restoration --monochrome --cpu-used 0 --rate-control q --crf 22

hato.profile2.10bpc.yuv422.no-cdef.no-restoration.avif: hato.16bpc.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 2 --bit-depth 10 --pix-fmt yuv422 --disable-cdef --disable-loop-restoration --cpu-used 0 --rate-control q --crf 22

hato.profile2.10bpc.yuv422.monochrome.no-cdef.no-restoration.avif: hato.16bpc.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 2 --bit-depth 10 --pix-fmt yuv422 --disable-cdef --disable-loop-restoration --monochrome --cpu-used 0 --rate-control q --crf 22

hato.profile2.12bpc.yuv422.no-cdef.no-restoration.avif: hato.16bpc.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 2 --bit-depth 12 --pix-fmt yuv422 --disable-cdef --disable-loop-restoration --cpu-used 0 --rate-control q --crf 22

hato.profile2.12bpc.yuv422.monochrome.no-cdef.no-restoration.avif: hato.16bpc.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 2 --bit-depth 12 --pix-fmt yuv422 --disable-cdef --disable-loop-restoration --cpu-used 0 --rate-control q --crf 22

## YUV420

hato.profile0.8bpc.yuv420.no-cdef.avif: hato.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

hato.profile0.8bpc.yuv420.monochrome.no-cdef.avif: hato.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --monochrome --cpu-used 0 --rate-control q --crf 22

hato.profile0.10bpc.yuv420.no-cdef.no-restoration.avif: hato.16bpc.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 0 --bit-depth 10 --pix-fmt yuv420 --disable-cdef --disable-loop-restoration --cpu-used 0 --rate-control q --crf 22

hato.profile0.10bpc.yuv420.monochrome.no-cdef.no-restoration.avif: hato.16bpc.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 0 --bit-depth 10 --pix-fmt yuv420 --disable-cdef --disable-loop-restoration --monochrome --cpu-used 0 --rate-control q --crf 22

## Kimono

kimono.avif: kimono.png
	$(CAVIF) -i $< -o $@ --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.rotate90.avif: kimono.rotate90.png
	$(CAVIF) -i $< -o $@ --rotation 270 --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.rotate270.avif: kimono.rotate270.png
	$(CAVIF) -i $< -o $@ --rotation 90 --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.mirror-horizontal.avif: kimono.mirror-horizontal.png
	$(CAVIF) -i $< -o $@ --mirror horizontal --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.mirror-vertical.avif: kimono.mirror-vertical.png
	$(CAVIF) -i $< -o $@ --mirror vertical --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.mirror-vertical.rotate270.avif: kimono.mirror-vertical.rotate270.png
	$(CAVIF) -i $< -o $@ --mirror vertical --rotation 90 --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.crop.avif: kimono.png
	$(CAVIF) -i $< -o $@ --crop-offset 103,-308 --crop-size 385,330 --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22

kimono.mirror-vertical.rotate270.crop.avif: kimono.mirror-vertical.rotate270.png
	$(CAVIF) -i $< -o $@ --crop-offset -308,103 --crop-size 330,385 --mirror vertical --rotation 90 --tune ssim --profile 0 --bit-depth 8 --pix-fmt yuv420 --disable-cdef --enable-loop-restoration --cpu-used 0 --rate-control q --crf 22
