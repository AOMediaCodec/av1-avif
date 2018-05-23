# av1-avif

This is a Netflix DRAFT proposal for a still image format specification.
This document describes how to use ISO-BMFF structures to generate a HEIF/MIAF
compatible file that contains one or more still images encoded using AV1
intra-frame tools.

The target use case for this format is for delivery of image assets.

The specification is written using a special syntax (mixing markup and markdown)
to enable generation of cross-references, syntax highlighting, ...
The file using this syntax is index.bs.

index.bs is processed to produce an HTML version (index.html) by a tool
called Bikeshed (https://github.com/tabatkins/bikeshed).

The repository contains both the input and the result of the Bikeshed processing.
