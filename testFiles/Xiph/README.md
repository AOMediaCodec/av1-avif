AVIF test file collection from Xiph.Org
========================================

These files were produced from the following source files:
* https://media.xiph.org/sets/subset1-64.tar.gz
  * 08-2011._Panthera_tigris_tigris_-_Texas_Park_-_Lanzarote_-TP04.png.y4m
* https://media.xiph.org/sets/subset1.tar.gz
  * Fruits_oranges,_jardin_japonais_2.png.y4m
  * 125 - Québec - Pont de Québec de nuit - Septembre 2009.png.y4m
  * Abandoned Packard Automobile Factory Detroit 200.png.y4m

Encoding was done with a modified svc_encoder_rtc example and packaged with a modified MP4Box.

These files pass validation via https://gpac.github.io/ComplianceWarden-wasm/avif.html

* [tiger_3layer_1res.avif](tiger_3layer_1res.avif)
  3-layer progressively decodeable image, without operating point selection. Decoded layers are provided in:
  * [Layer 0, 1216x832](tiger_3layer_1res_layer0.png)
  * [Layer 1, 1216x832](tiger_3layer_1res_layer1.png)
  * [Layer 2, 1216x832](tiger_3layer_1res_layer2.png)

* [tiger_3layer_3res.avif](tiger_3layer_3res.avif)
  3-layer progressively decodeable image, at three different resolutions, without operating point selection. Decoded layers are provided in:
  * [Layer 0, 304x208](tiger_3layer_3res_layer0.png) 
  * [Layer 1, 608x416](tiger_3layer_3res_layer1.png)
  * [Layer 2, 1216x832](tiger_3layer_3res_layer2.png)

* [fruits_2layer_thumbsize.avif](fruits_2layer_thumbsize.avif)
  2-layer progressively decodeable image, with one resolution thumbnail-sized, without operating point selection. Decoded layers are provided in:
  * [Layer 0, 82x54](fruits_2layer_thumbsize_layer0.png) 
  * [Layer 1, 1296x864](fruits_2layer_thumbsize_layer1.png)

* [quebec_3layer_op2.avif](quebec_3layer_op2.avif)
  3-layer progressively decodeable image, at three different resolutions, with operating points and operating point selection. Operating point 2, corresponding to layer 0, is chosen, resulting in ispe dimensions of 360x182. Decoded layers are provided in:
  * [Layer 0, 360x182](quebec_3layer_op2_layer0.png) 
  * [Layer 1, 718x366](quebec_3layer_op2_layer1.png)
  * [Layer 2, 1436x730](quebec_3layer_op2_layer2.png)

* [abandoned_filmgrain.avif](abandoned_filmgrain.avif)
  2-layer progressively decodeable image, without filmgrain on the first layer, and with filmgrain on the second layer. Decoded layers are provided in:
  * [Layer 0, 1404x936](abandoned_filmgrain_layer0.png)
  * [Layer 1, 1404x936](abandoned_filmgrain_layer1.png)
