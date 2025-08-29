# AV1 Image File Format (AVIF)

This document describes how to use ISO-BMFF structures to generate a HEIF/MIAF
compatible file that contains one or more still images encoded using AV1.

The specification is written using a special syntax (mixing markup and markdown)
to enable generation of cross-references, syntax highlighting, ...
The file using this syntax is [index.bs](./index.bs).

[index.bs](./index.bs) is processed to produce an HTML version (`index.html`) by a tool called [Bikeshed](https://github.com/tabatkins/bikeshed), which is run when content is pushed onto the `main` branch or when Pull Requests are made.

# Building locally

Make sure python is installed on your system. It is recommended to use a dedicated environment, if you haven't done so you can set it up like this:

```shell
python3 -m venv venv
source venv/bin/activate
```

Then install dependencies using:

```shell
pip install -r requirements.txt
```

Finally you can compile the spec by running:

```shell
bikeshed spec
```
