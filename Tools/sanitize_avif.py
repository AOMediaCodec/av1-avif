#!/usr/bin/env python3
"""
Tool to fix commonly identified container level issues in AVIF files.

----------------------
https://aomedia.org/license/software-license/bsd-3-c-c/

The Clear BSD License

Copyright (c) 2022, Alliance for Open Media

All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted (subject to the limitations in the disclaimer below) provided that
the following conditions are met:

Redistributions of source code must retain the above copyright notice, this list
of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or other
materials provided with the distribution.

Neither the name of the Alliance for Open Media nor the names of its contributors
may be used to endorse or promote products derived from this software without
specific prior written permission.

NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS
LICENSE. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
----------------------

Kept "nice" by running:
isort sanitize_avif.py --interactive
black -l 100 sanitize_avif.py
pylint sanitize_avif.py
mypy --strict sanitize_avif.py
"""

# pylint: disable=too-many-lines, too-many-lines, too-many-arguments
# pylint: disable=too-many-locals, too-many-branches, too-many-statements

import argparse
import os
import struct
import sys
import typing
from functools import reduce
from itertools import accumulate
from typing import Any, BinaryIO, Callable, NewType, NoReturn, Optional, Union

# ===========================================
# Types
# ===========================================

BoxType = NewType("BoxType", str)
BoxHeader = dict[str, int]
BoxBody = dict[str, Any]
BoxSequenceMap = dict[str, "BoxRecipe"]
BoxBodyParser = Callable[["FileReader", "Box", int], BoxBody]
OBUParser = Callable[..., dict[str, Any]]

NCLXBodyType = dict[str, Union[str, int]]

BoxWriterReturn = tuple[bytes, list["PlaceholderFileOffset"]]
BoxWriter = Callable[["Box", int], BoxWriterReturn]

IssueFixer = Callable[[], None]


# ===========================================
# Printing utilities
# ===========================================
NONVERBOSE_PRINT_LEVEL = -1000000


def print_indent(lvl: int, string: str) -> None:
    """Print a message with the specified indentation level if lvl is positive."""
    if lvl >= 0:
        print("  " * lvl + string)


def decode_data_to_string(data: bytes) -> str:
    """Handles potential unicode decoding errors (typically happens for corrupt files)."""
    try:
        string = data.decode()
    except UnicodeDecodeError:
        string = "CORRUPT"
    # Strip out NULL terminated strings (typically only for corrupt files)
    return string.rstrip("\x00")


def bold(string: str) -> str:
    """Returns the string with bold terminal color escape symbols"""
    return f"\033[1m{string}\033[0m"


def red(string: str) -> str:
    """Returns the string with red terminal color escape symbols"""
    return f"\033[1;31m{string}\033[0m"


def float_from_rational(arr: list[int]) -> float:
    """Returns a float value given a rational."""
    assert len(arr) == 2
    if arr[1] == 0:
        return float("inf")
    return arr[0] / arr[1]


# ===========================================
# Reading utilities
# ===========================================
def get_struct_type(nbytes: int, unsigned: bool = True) -> str:
    """Returns the appropriate struct type string for an element size."""
    if unsigned:
        nbytes_to_format_map = {1: "B", 2: "H", 4: "I", 8: "Q"}
    else:
        nbytes_to_format_map = {1: "b", 2: "h", 4: "i", 8: "q"}
    assert nbytes in nbytes_to_format_map
    return ">" + nbytes_to_format_map[nbytes]


def write_integer_of_size(value: int, nbytes: int, unsigned: bool = True) -> bytes:
    """Writes a value as an integer of nbytes size."""
    return struct.pack(get_struct_type(nbytes, unsigned=unsigned), value)


def write_integer_array_of_size(values: list[int], nbytes: int, unsigned: bool = True) -> bytes:
    """Writes values as integers each of nbytes size."""
    return struct.pack(">" + get_struct_type(nbytes, unsigned=unsigned)[1] * len(values), *values)


class FileReader:
    """Utility class for handling file reading operations."""

    def __init__(self, input_file: BinaryIO) -> None:
        self.file = input_file
        self.file.seek(0, os.SEEK_END)
        self.size = self.file.tell()
        self.file.seek(0, os.SEEK_SET)

    class BitReader:
        """Utility class for handling bit reading operations."""

        def __init__(self, data: bytes) -> None:
            self.data = data
            self.pos = 0
            self.bit_pos = 0

        def get_next_bit(self) -> int:
            """Returns the next bit from the stream."""
            byte = self.data[self.pos]
            bit = (byte >> (7 - self.bit_pos)) & 1
            self.bit_pos += 1
            if self.bit_pos >= 8:
                self.bit_pos -= 8
                self.pos += 1
            return bit

        # pylint: disable=invalid-name
        def f(self, num_bits: int) -> int:
            """Returns the next 'num_bits' bits from the stream."""
            value = 0
            for _ in range(num_bits):
                value <<= 1
                value |= self.get_next_bit()
            return value

        # pylint: enable=invalid-name

        def get_byte(self) -> int:
            """Returns the next byte from the stream."""
            assert self.bit_pos == 0
            byte = self.data[self.pos]
            self.pos += 1
            return byte

        def skip_bytes(self, num: int) -> None:
            """Skips forward 'num' bytes in the stream."""
            assert self.bit_pos == 0
            self.pos += num

        def eof(self) -> bool:
            """Returns true when the end of the stream has been reached."""
            return len(self.data) == self.pos

        def get_bytes(self, num_bytes: int = 0) -> bytes:
            """Returns the next num_bytes bytes, with 'num_bytes == 0' meaning until end."""
            assert self.bit_pos == 0
            pos = self.pos
            if num_bytes == 0:
                num_bytes = len(self.data) - pos
            else:
                assert self.pos + num_bytes <= len(self.data)
            self.pos += num_bytes
            return self.data[pos : pos + num_bytes]

        def bit_reader_for_bytes(self, num_bytes: int) -> "FileReader.BitReader":
            """Returns a new BitReader for the next 'num_bytes'."""
            return FileReader.BitReader(self.get_bytes(num_bytes))

        def read_leb128_value(self) -> int:
            """Returns a leb128 value from the stream."""
            value = 0
            for i in range(8):
                byte = self.get_byte()
                value |= (byte & 0x7F) << (i * 7)
                if (byte & 0x80) == 0:
                    break
            return value

    def position(self) -> int:
        """Returns the current position in the file."""
        return self.file.tell()

    # -----------------------------------
    # Methods that move the file position
    # -----------------------------------

    def rewind(self) -> None:
        """Rewinds the position to the start of the file."""
        self.file.seek(0, os.SEEK_SET)

    def read_data(self, nbytes: int, end: Optional[int] = None) -> bytes:
        """Reads nbytes of data from the file."""
        if end is None:
            assert self.position() + nbytes <= self.size, "File ended prematurely"
        else:
            assert self.position() + nbytes <= end, "Box/data ended prematurely"
        return self.file.read(nbytes)

    def bit_reader_for_bytes(
        self, nbytes: int, end: Optional[int] = None
    ) -> "FileReader.BitReader":
        """Returns a BitReader for the next nbytes of data."""
        data = self.read_data(nbytes, end)
        return FileReader.BitReader(data)

    def skip_to(self, position: int) -> None:
        """Moves the position to the indicated position."""
        self.file.seek(position)

    def read_integer_of_size(self, end: int, nbytes: int, unsigned: bool = True) -> int:
        """Reads a big-endian integer of size nbytes from file."""
        data = self.read_data(nbytes, end)
        unpacked = struct.unpack(get_struct_type(nbytes, unsigned=unsigned), data)
        return typing.cast(int, unpacked[0])

    def read_integer_array_of_size(
        self, end: int, nbytes: int, count: int, unsigned: bool = True
    ) -> list[int]:
        """Reads an array of size count of integers of size nbytes from file."""
        return [self.read_integer_of_size(end, nbytes, unsigned) for _ in range(count)]

    def read_string(self, end: int, size: int = 0) -> Optional[str]:
        """Reads a NULL-terminated or fixed-length string from file."""
        if size == 0:
            max_length = end - self.file.tell()
            buf = bytearray()
            read = 0
            while read < max_length:
                byte = self.file.read(1)
                read += 1
                if byte is None or int(byte[0]) == 0:
                    return decode_data_to_string(buf) if len(buf) > 0 else None
                buf.append(byte[0])
            return decode_data_to_string(buf) if len(buf) > 0 else None
        return decode_data_to_string(self.read_data(size, end))

    # ---------------------------------------
    # Methods that maintain the file position
    # ---------------------------------------

    def read_data_from_offset(self, offset: int, nbytes: int) -> bytes:
        """Read nbytes bytes from offset in file without moving position."""
        pos = self.file.tell()
        self.file.seek(offset, os.SEEK_SET)
        data = self.file.read(nbytes)
        assert len(data) == nbytes
        self.file.seek(pos, os.SEEK_SET)
        return data

    def copy_data_to_destination(self, output_file: BinaryIO, offset: int, count: int) -> None:
        """Copy data from source file to destination file without holding all in memory."""
        pos = self.file.tell()
        self.file.seek(offset, os.SEEK_SET)
        while count > 0:
            data = self.file.read(min(32768, count))
            output_file.write(data)
            count -= len(data)
        self.file.seek(pos, os.SEEK_SET)


# ===========================================
# Utility classes
# ===========================================
class Box:
    """Class representing a parsed ISOBMFF box."""

    def __init__(self, box_type: BoxType, parent: Optional["Box"], size: int, start: int):
        self.type = box_type
        self.size = size
        self.start = start
        self.end = start + size
        self.sub_boxes: Optional[list[Box]] = None
        self.header: BoxHeader = {}
        self.body: BoxBody = {}
        self.needs_rewrite = False
        self.parent = parent

    @classmethod
    def from_reader(cls, reader: FileReader, end: int, parent: Optional["Box"] = None) -> "Box":
        """Read a box header from file and return as a Box."""
        start = reader.position()
        size = reader.read_integer_of_size(end, 4)
        box_type = reader.read_string(end, 4)
        assert box_type is not None, "Could not get box type"
        if size == 1:
            size = reader.read_integer_of_size(end, 8)
        elif size == 0:
            size = end - size
        assert (
            size >= 8
        ), f"Encountered box of type {box_type} with invalid size {size}. Cannot continue."
        return cls(BoxType(box_type), parent, size, start)

    def print_start(self, lvl: int, name: Optional[str] = None) -> None:
        """For verbose output, prints start of box."""
        string = f"('{red(self.type)}'"
        if name:
            string += f' "{name}",'
        string += f" size = {self.size}, offset = {self.start}) {{"
        print_indent(lvl, string)

    def print_end(self, lvl: int) -> None:
        """For verbose output, prints end of box."""
        print_indent(lvl, "}")

    def __repr__(self) -> str:
        sub_boxes = [] if self.sub_boxes is None else self.sub_boxes
        types_string = ",".join([box.type for box in sub_boxes])
        sub_box_str = f"[{types_string}]"
        return (
            f"Box(type={self.type}, start={self.start}, size={self.size}, "
            + f"header={self.header}, sub_boxes={sub_box_str}, clean={not self.needs_rewrite})"
        )

    def mark_for_rewrite(self) -> None:
        """Marks box and all parent boxes as needing rewriting."""
        box: Optional[Box] = self
        while box is not None:
            box.needs_rewrite = True
            box = box.parent

    def write_box_header(self, body_size: int) -> bytes:
        """Writes the Box/Full-Box header."""
        data = bytes()
        box_type_data = self.type.encode()
        assert len(box_type_data) == 4
        total_size = 4  # size bytes
        total_size += len(box_type_data)
        total_size += 0 if len(self.header) == 0 else 4
        total_size += body_size
        assert total_size <= 0xFFFFFFFF, "8-byte box size not implemented"
        data += struct.pack(">I", total_size)
        data += box_type_data
        if len(self.header) > 0:
            version = self.header["version"]
            data += struct.pack(">B", version)
            flags = self.header["flags"]
            data += struct.pack(">I", flags)[1:]
        return data


class BoxRecipe:
    """Class representing how to parse a specific box."""

    def __init__(
        self,
        name: str,
        full_box: bool = False,
        sequence_map: Optional[BoxSequenceMap] = None,
        body_parser: Optional[BoxBodyParser] = None,
    ) -> None:
        assert sequence_map is None or body_parser is None
        self.name = name
        self.full_box = full_box
        self.sequence_map = sequence_map
        self.body_parser = body_parser

    def parse(self, reader: FileReader, dst_box: Box, lvl: int) -> None:
        """Parses box."""

        # Header
        if self.full_box:
            (version, flags1, flags2, flags3) = reader.read_integer_array_of_size(dst_box.end, 1, 4)
            flags = (flags1 << 16) | (flags2 << 8) | flags3
            print_indent(lvl, f"Version: {version}, Flags: 0x{flags:06X}")
            dst_box.header = {"version": version, "flags": flags}

        # Body
        if self.sequence_map is not None:
            dst_box.sub_boxes = parse_box_sequence(
                reader, dst_box.end, lvl, parent=dst_box, box_map=self.sequence_map
            )
        elif self.body_parser:
            dst_box.body = self.body_parser(reader, dst_box, lvl)
        else:
            reader.skip_to(dst_box.end)

    def __repr__(self) -> str:
        return f"BoxRecipe(name: {self.name}, full: {self.full_box}, map: {self.sequence_map})"


class BoxIssue:
    """Class representing found issues for a specific box."""

    def __init__(self, box_id: int, box_type: str, is_track: bool = False) -> None:
        self.box_id = box_id
        self.box_type = box_type
        self.issues: dict[str, list[str]] = {}
        self.fix: Optional[IssueFixer] = None
        self.fix_description: Optional[str] = None
        self.info_url: Optional[str] = None
        self.is_track = is_track
        self.base_url = (
            "https://github.com/AOMediaCodec/av1-avif/wiki/Identified-issues-in-existing-AVIF-files"
        )

    def add_issue(self, severity: str, description: str) -> None:
        """Adds an issue for the box."""
        if severity not in self.issues:
            self.issues[severity] = []
        self.issues[severity].append(description)

    def add_info_url(self, url_section: str) -> None:
        """Adds an info url section in the AVIF Wiki that gives more information."""
        self.info_url = url_section

    def add_fix(self, fix: IssueFixer, fix_description: str) -> None:
        """Adds a fix for the identified issues."""
        self.fix = fix
        self.fix_description = fix_description

    def apply_fix(self) -> None:
        """Applies the fix for the identified issues."""
        assert self.fix, f"No possible fix for issue:\n{self.issues}"
        self.fix()

    def print(self, lvl: int, others: Optional[list["BoxIssue"]] = None) -> None:
        """Prints the identified issues."""
        type_str = "Track " if self.is_track else "Item "
        if others is None or len(others) == 0:
            print_indent(lvl, f"{type_str} {self.box_id}")
        else:
            other_ids_int = sorted([issue.box_id for issue in others])
            other_ids: list[str] = list(map(str, other_ids_int))
            print_indent(lvl, f'{type_str} {self.box_id} (also applies to [{",".join(other_ids)}])')
        print_indent(lvl + 1, f"Box {self.box_type}")
        for severity, values in self.issues.items():
            print_indent(lvl + 2, f"{severity}")
            for description in values:
                print_indent(lvl + 3, f"{description}")
        if self.info_url:
            print_indent(lvl + 1, f"See {self.base_url}#{self.info_url}")
        if self.fix_description:
            print_indent(lvl + 1, f"FIX: {self.fix_description}")

    def issue_hash(self) -> int:
        """Creates a hash of the issues in this object for aggregating items with the same issue."""

        def _freeze(val: Any) -> Any:
            if isinstance(val, dict):
                return frozenset((key, _freeze(value)) for key, value in val.items())
            if isinstance(val, list):
                return tuple(_freeze(value) for value in val)
            return val

        return hash((self.is_track, self.fix_description, _freeze(self.issues)))


class PlaceholderFileOffset:
    """Class representing a placeholder file offset."""

    def __init__(
        self,
        box: Box,
        file_pos: int,
        size: int,
        value: int,
        base: Optional["PlaceholderFileOffset"] = None,
    ) -> None:
        self.box = box
        self.file_pos = file_pos
        self.size = size
        self.value = value
        self.base = base
        self.dependents: list["PlaceholderFileOffset"] = []
        if base is not None:
            base.add_dependent(self)

    def add_dependent(self, dependent: "PlaceholderFileOffset") -> None:
        """Adds a new file sub-offset that depends on this file offset."""
        self.dependents.append(dependent)

    def get_offset_list(self) -> list[int]:
        """Returns this offset and dependents as a list of values."""
        if len(self.dependents) > 0:
            return [self.value + dep.value for dep in self.dependents]
        return [self.value]

    def write_delta(self, file: BinaryIO, delta: int) -> None:
        """Applies a delta to this placeholder and writes to file."""
        new_value = self.value + delta
        assert new_value >= 0, "Base offset too small, can't apply delta"
        max_val = (1 << self.size * 8) - 1
        assert new_value <= max_val, "Offset size is too small to contain moved offset"
        data = write_integer_of_size(new_value, self.size)
        current_pos = file.tell()
        file.seek(self.file_pos, os.SEEK_SET)
        file.write(data)
        file.seek(current_pos, os.SEEK_SET)


# ===========================================
# Box parsing
# ===========================================
def parse_unsupported_box(_reader: FileReader, box: Box, _lvl: int) -> NoReturn:
    """Function that generates an assertion error when a critical unsupported box is encountered"""
    assert False, f"'{box.type}' box is currently unsupported"


def parse_ftyp_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse File Type Box."""
    body: dict[str, Any] = {}
    body["major"] = reader.read_string(box.end, size=4)
    body["version"] = reader.read_integer_of_size(box.end, 4)
    num_brands = int((box.end - reader.position()) / 4)
    body["compatible"] = []
    for _ in range(num_brands):
        body["compatible"].append(reader.read_string(box.end, size=4))
    print_indent(lvl, f"Major brand: {body['major']}")
    print_indent(lvl, f"Version: {body['version']}")
    print_indent(lvl, f"Compatible brands: [{','.join(body['compatible'])}]")
    return body


def parse_tkhd_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Track Header Box."""
    time_size = 8 if box.header["version"] == 1 else 4
    body: dict[str, Any] = {}
    body["creation_time"] = reader.read_integer_of_size(box.end, time_size)
    body["modification_time"] = reader.read_integer_of_size(box.end, time_size)
    body["track_id"] = reader.read_integer_of_size(box.end, 4)
    reader.read_data(4, box.end)  # Reserved
    body["duration"] = reader.read_integer_of_size(box.end, time_size)

    print_indent(lvl, f"Creation time: {body['creation_time']}")
    print_indent(lvl, f"Modification time: {body['modification_time']}")
    print_indent(lvl, f"Track ID: {body['track_id']}")
    print_indent(lvl, f"Duration: {body['duration']}")

    reader.read_data(8, box.end)  # Reserved
    body["layer"] = reader.read_integer_of_size(box.end, 2)
    body["alternate_group"] = reader.read_integer_of_size(box.end, 2)
    body["volume"] = reader.read_integer_of_size(box.end, 2)
    reader.read_data(2, box.end)  # Reserved
    print_indent(lvl, f"Layer: {body['layer']}")
    print_indent(lvl, f"Alternate Group: {body['alternate_group']}")
    print_indent(lvl, f"Volume: {body['volume']}")

    body["matrix"] = reader.read_integer_array_of_size(box.end, 4, 9)
    print_indent(lvl, "Matrix: {")
    for index in range(3):
        vals = [f"{val:7.1f}" for val in body["matrix"][index : index + 3]]
        print_indent(lvl + 1, ",".join(vals))
    print_indent(lvl, "}")
    body["width"] = reader.read_integer_of_size(box.end, 4)
    body["height"] = reader.read_integer_of_size(box.end, 4)
    print_indent(lvl, f"Width: {body['width'] / (1 << 16)}")
    print_indent(lvl, f"Height: {body['height'] / (1 << 16)}")
    return body


def parse_stsd_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Sample Description Box."""
    entry_count = reader.read_integer_of_size(box.end, 4)

    def _parse_av01_box(sub_reader: FileReader, sub_box: Box, sub_lvl: int) -> BoxBody:
        body = {}
        body["sampleentry"] = sub_reader.read_data(8, sub_box.end)
        body["visualsampleentry"] = sub_reader.read_data(70, sub_box.end)
        sub_box.sub_boxes = parse_box_sequence(
            sub_reader, sub_box.end, sub_lvl + 1, parent=sub_box, box_map={}
        )
        return body

    box_map = {
        "av01": BoxRecipe("AV1 Sample Entry", body_parser=_parse_av01_box),
    }
    box.sub_boxes = parse_box_sequence(
        reader, box.end, lvl + 1, parent=box, box_map=box_map, expected_box_count=entry_count
    )
    return {}


def parse_dref_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Data Reference Box."""
    entry_count = reader.read_integer_of_size(box.end, 4)

    def _parse_dref_url(sub_reader: FileReader, sub_box: Box, sub_lvl: int) -> BoxBody:
        url = sub_reader.read_string(sub_box.end)
        print_indent(sub_lvl, f"URL: {url}")
        assert (
            sub_box.header["flags"] == 1 and url is None
        ), "Non-local data references not supported"
        return {"url": url}

    box_map = {
        "url ": BoxRecipe("Data Entry URL", full_box=True, body_parser=_parse_dref_url),
        "default": BoxRecipe("Data Entry", full_box=True, body_parser=parse_unsupported_box),
    }
    box.sub_boxes = parse_box_sequence(
        reader, box.end, lvl + 1, parent=box, box_map=box_map, expected_box_count=entry_count
    )
    return {}


def parse_stco_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Sample Chunk Offset Box."""
    entry_count = reader.read_integer_of_size(box.end, 4)
    print_indent(lvl, f"Entry count: {entry_count}")
    entries = []
    for chunk in range(entry_count):
        offset = reader.read_integer_of_size(box.end, 4)
        print_indent(lvl + 1, f"Chunk #{chunk}: {offset}")
        entries.append(offset)
    return {"entries": entries}


def parse_hdlr_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Handler Reference Box."""
    predef = reader.read_integer_of_size(box.end, 4)
    hdlr_type = reader.read_string(box.end, size=4)
    reader.read_integer_array_of_size(box.end, 4, 3)  # Reserved

    print_indent(lvl, f"Pre defined: {predef}")
    print_indent(lvl, f"Handler type: {hdlr_type}")
    name = reader.read_string(box.end)
    print_indent(lvl, f"Name: {name}")
    return {
        "pre_defined": predef,
        "hdlr_type": hdlr_type,
        "name": name,
    }


def parse_pitm_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Primary Item Box."""
    body: dict[str, Any] = {}
    id_size = 2 if box.header["version"] == 0 else 4
    body["item_id"] = reader.read_integer_of_size(box.end, id_size)
    print_indent(lvl, f"Primary item id: {body['item_id']}")
    return body


def parse_av1c_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse AV1 Codec Configuration Box."""

    # https://aomediacodec.github.io/av1-isobmff/ section 2.3.3
    bit_reader = reader.bit_reader_for_bytes(4, box.end)
    body: dict[str, Any] = {}
    body["marker"] = bit_reader.f(1)
    body["version"] = bit_reader.f(7)
    body["seq_profile"] = bit_reader.f(3)
    body["seq_level_idx_0"] = bit_reader.f(5)
    body["seq_tier_0"] = bit_reader.f(1)
    body["high_bitdepth"] = bit_reader.f(1)
    body["twelve_bit"] = bit_reader.f(1)
    body["monochrome"] = bit_reader.f(1)
    body["chroma_subsampling_x"] = bit_reader.f(1)
    body["chroma_subsampling_y"] = bit_reader.f(1)
    body["chroma_sample_position"] = bit_reader.f(2)
    bit_reader.f(3)  # Reserved
    body["initial_presentation_delay_present"] = bit_reader.f(1)
    if body["initial_presentation_delay_present"] == 1:
        body["initial_presentation_delay_minus_one"] = bit_reader.f(4)
    else:
        bit_reader.f(4)  # Reserved

    if reader.position() < box.end:
        body["configOBUs"] = reader.read_data(box.end - reader.position())

    print_indent(lvl, f"marker: {body['marker']}")
    print_indent(lvl, f"version: {body['version']}")
    print_indent(lvl, f"seq_profile: {body['seq_profile']}")
    print_indent(lvl, f"seq_level_idx_0: {body['seq_level_idx_0']}")
    print_indent(lvl, f"seq_tier_0: {body['seq_tier_0']}")
    print_indent(lvl, f"high_bitdepth: {body['high_bitdepth']}")
    print_indent(lvl, f"twelve_bit: {body['twelve_bit']}")
    print_indent(lvl, f"monochrome: {body['monochrome']}")
    print_indent(lvl, f"chroma_subsampling_x: {body['chroma_subsampling_x']}")
    print_indent(lvl, f"chroma_subsampling_y: {body['chroma_subsampling_y']}")
    print_indent(lvl, f"chroma_sample_position: {body['chroma_sample_position']}")
    print_indent(
        lvl,
        f"initial_presentation_delay_present: {body['initial_presentation_delay_present']}",
    )
    if body["initial_presentation_delay_present"] == 1:
        print_indent(
            lvl,
            "initial_presentation_delay_minus_one: "
            + f"{body['initial_presentation_delay_minus_one']}",
        )
    if "configOBUs" in body:
        print_indent(lvl, f"configOBUs: {len(body['configOBUs'])} bytes")
    return body


def parse_iref_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Item Reference Box."""
    id_size = 2 if box.header["version"] == 0 else 4

    def _parse_sitref(sub_reader: FileReader, sub_box: Box, sub_lvl: int) -> BoxBody:
        body: BoxBody = {}
        body["from_item_ID"] = sub_reader.read_integer_of_size(sub_box.end, id_size)
        reference_count = sub_reader.read_integer_of_size(sub_box.end, 2)
        print_indent(sub_lvl, f"Reference count: {reference_count}")
        references = []
        print_indent(sub_lvl, f"From item {body['from_item_ID']}; To items: {{")
        for _ in range(reference_count):
            reference = sub_reader.read_integer_of_size(sub_box.end, id_size)
            print_indent(sub_lvl + 1, f"{reference}")
            references.append(reference)
        print_indent(sub_lvl, "}")
        body["to_item_ID"] = references
        return body

    box_map = {"default": BoxRecipe("Single Item Reference Box", body_parser=_parse_sitref)}
    box.sub_boxes = parse_box_sequence(reader, box.end, lvl + 1, parent=box, box_map=box_map)

    return {}


def parse_ipma_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Item Property Association Box."""
    item_id_size = 2 if box.header["version"] < 1 else 4

    body: dict[str, Any] = {}
    body["entry_count"] = reader.read_integer_of_size(box.end, 4)
    body["associations"] = {}

    for _ in range(body["entry_count"]):
        item_id = reader.read_integer_of_size(box.end, item_id_size)
        association_count = reader.read_integer_of_size(box.end, 1)
        print_indent(lvl, f"Item ID {item_id}:")

        properties = []
        for _ in range(association_count):
            tmp = reader.read_integer_of_size(box.end, 1)
            essential = tmp >> 7 != 0
            prop_index = tmp & 0x7F
            if (box.header["flags"] & 1) == 1:
                prop_index = (prop_index << 8) | reader.read_integer_of_size(box.end, 1)
            print_indent(
                lvl + 1,
                f"Property Index: {prop_index}; " + f'Essential: {"Yes" if essential else "No"}',
            )

            properties.append((prop_index, essential))
        body["associations"][item_id] = properties
    return body


def print_iloc_box(body: BoxBody, lvl: int, version: int) -> None:
    """Print Item Location Box."""
    print_indent(lvl, f"Offset size: {body['offset_size']}")
    print_indent(lvl, f"Length size: {body['length_size']}")
    print_indent(lvl, f"Base offset size: {body['base_offset_size']}")
    if version in [1, 2]:
        print_indent(lvl, f"Index size: {body['index_size']}")

    for item in body["items"]:
        print_indent(
            lvl,
            f"Item {item['item_ID']}: construction_method = "
            + f"{item['construction_method']}; base_offset = {item['base_offset']}",
        )
        for extent_index, extent in enumerate(item["extents"]):
            reference_index_string = ""
            if "item_reference_index" in extent:
                reference_index_string = (
                    f"; item_reference_index = {extent['item_reference_index']}"
                )
            print_indent(
                lvl + 1,
                f"Extent {extent_index}: offset = {extent['offset']} "
                + f"(total = {extent['calculated_total_offset']}); length = "
                + f"{extent['length']}{reference_index_string}",
            )


def parse_iloc_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Item Location Box."""
    version = box.header["version"]
    assert 0 <= version <= 2

    body: dict[str, Any] = {}
    byte = reader.read_integer_of_size(box.end, 1)
    body["offset_size"] = byte >> 4
    body["length_size"] = byte & 0xF
    byte = reader.read_integer_of_size(box.end, 1)
    body["base_offset_size"] = byte >> 4
    body["index_size" if version > 0 else "reserved1"] = byte & 0xF

    items = []
    if version < 2:
        item_count = reader.read_integer_of_size(box.end, 2)
    elif version == 2:
        item_count = reader.read_integer_of_size(box.end, 4)

    for _ in range(item_count):
        item: dict[str, Any] = {}
        if version < 2:
            item["item_ID"] = reader.read_integer_of_size(box.end, 2)
        elif version == 2:
            item["item_ID"] = reader.read_integer_of_size(box.end, 4)

        if version in [1, 2]:
            item["reserved0"], item["construction_method"] = reader.read_integer_array_of_size(
                box.end, 1, 2
            )
        else:
            item["construction_method"] = 0
        item["data_reference_index"] = reader.read_integer_of_size(box.end, 2)
        assert item["data_reference_index"] == 0, "Non-zero data_reference_index not supported"
        item["base_offset"] = 0
        if body["base_offset_size"] > 0:
            item["base_offset"] = reader.read_integer_of_size(box.end, body["base_offset_size"])

        extent_count = reader.read_integer_of_size(box.end, 2)
        extents = []
        for _ in range(extent_count):
            extent = {}
            if (version in [1, 2]) and body["index_size"] > 0:
                extent["item_reference_index"] = reader.read_integer_of_size(
                    box.end, body["index_size"]
                )
            extent["offset"] = 0
            if body["offset_size"] > 0:
                extent["offset"] = reader.read_integer_of_size(box.end, body["offset_size"])
            extent["length"] = reader.read_integer_of_size(box.end, body["length_size"])
            extent["calculated_total_offset"] = item["base_offset"] + extent["offset"]
            extents += [extent]
        item["extents"] = extents
        items += [item]
    body["items"] = items

    print_iloc_box(body, lvl, version)
    return body


def parse_infe_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Item Information Entry Box."""
    version = box.header["version"]
    assert 2 <= version <= 3, "Only version 2 and 3 of 'infe' box supported"
    hidden = box.header["flags"] == 1

    body: dict[str, Any] = {}
    item_id_size = 2 if version == 2 else 4
    body["item_id"] = reader.read_integer_of_size(box.end, item_id_size)
    body["item_protection_index"] = reader.read_integer_of_size(box.end, 2)
    body["item_type"] = reader.read_string(box.end, size=4)
    body["name"] = reader.read_string(box.end)

    print_indent(lvl, f"Item ID: {body['item_id']}{' (Hidden)' if hidden else ''}")
    print_indent(lvl, f"Item protection index: {body['item_protection_index']}")
    print_indent(lvl, f"Item type: {body['item_type']}")

    if body["item_type"] == "mime":
        body["content_type"] = reader.read_string(box.end)
        body["content_encoding"] = reader.read_string(box.end)
        print_indent(lvl, f"Content type: {body['content_type']}")
        print_indent(lvl, f"Content encoding: {body['content_encoding']}")
    elif body["item_type"] == "uri ":
        body["uri_type"] = reader.read_string(box.end)
        print_indent(lvl, f"URI type: {body['uri_type']}")
    return body


def parse_iinf_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Item Information Box."""
    version = box.header["version"]
    assert 0 <= version <= 1, "MIAF requires version 0 or 1 for 'iinf' box"

    entry_count_size = 4 if version != 0 else 2
    entry_count = reader.read_integer_of_size(box.end, entry_count_size)
    print_indent(lvl, f"Entry count: {entry_count}")

    box_map = {
        "infe": BoxRecipe("Item Information Entry Box", full_box=True, body_parser=parse_infe_box)
    }
    box.sub_boxes = parse_box_sequence(
        reader, box.end, lvl + 1, parent=box, box_map=box_map, expected_box_count=entry_count
    )
    return {}


def parse_colr_box(reader: FileReader, box: Box, lvl: int) -> NCLXBodyType:
    """Parse Color Information Box."""
    body: dict[str, Any] = {}
    body["type"] = reader.read_string(box.end, size=4)
    if body["type"] == "nclx":
        body["color_primaries"] = reader.read_integer_of_size(box.end, 2)
        body["transfer_characteristics"] = reader.read_integer_of_size(box.end, 2)
        body["matrix_coefficients"] = reader.read_integer_of_size(box.end, 2)
        body["full_range_flag"] = reader.read_integer_of_size(box.end, 1) >> 7
        print_indent(
            lvl,
            f"NCLX: ({body['color_primaries']},{body['transfer_characteristics']},"
            + f"{body['matrix_coefficients']},{body['full_range_flag']})",
        )
    elif body["type"] in ["rICC", "prof"]:
        body["icc_data"] = reader.read_data(box.end - reader.position(), box.end)
        print_indent(lvl, f"{body['type']} of size {len(body['icc_data'])}")
    else:
        assert False, f'Unsupported colr type {body["type"]}'
    return body


def parse_pixi_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Pixel Information Box."""
    num_channels = reader.read_integer_of_size(box.end, 1)
    bpp = reader.read_integer_array_of_size(box.end, 1, num_channels)
    print_indent(lvl, f"bits_per_channel: {bpp}")
    return {"bits_per_channel": bpp}


def parse_ispe_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Image Spatial Extents Box."""
    body = {}
    body["width"] = reader.read_integer_of_size(box.end, 4)
    body["height"] = reader.read_integer_of_size(box.end, 4)
    print_indent(lvl, f"Dimensions: {body['width']}x{body['height']}")
    return body


def parse_clap_box(reader: FileReader, box: Box, lvl: int) -> BoxBody:
    """Parse Clean Aperture Box."""
    body = {}
    body["width"] = reader.read_integer_array_of_size(box.end, 4, 2, unsigned=False)
    body["height"] = reader.read_integer_array_of_size(box.end, 4, 2, unsigned=False)
    body["h_offset"] = reader.read_integer_array_of_size(box.end, 4, 2, unsigned=False)
    body["v_offset"] = reader.read_integer_array_of_size(box.end, 4, 2, unsigned=False)

    def _print_field(descr: str, key: str) -> None:
        print_indent(
            lvl, f"{descr}: {body[key][0]} / {body[key][1]} ({float_from_rational(body[key])})"
        )

    _print_field("Width", "width")
    _print_field("Height", "height")
    _print_field("Horizontal offset", "h_offset")
    _print_field("Vertical offset", "v_offset")
    return body


def parse_box_sequence(
    reader: FileReader,
    end: int,
    lvl: int,
    parent: Optional[Box] = None,
    box_map: Optional[BoxSequenceMap] = None,
    expected_box_count: Optional[int] = None,
) -> list[Box]:
    """Reads the file as a sequence of ISOBMFF boxes."""

    if box_map is None:
        box_map = {}

    mdat_box_count = 0
    boxes = []
    while reader.position() <= (end - 8):
        # Process Box
        box = Box.from_reader(reader, end, parent=parent)
        if box.type == "mdat":
            mdat_box_count += 1
            if mdat_box_count > 1:
                print(
                    "WARNING: Files with multiple mdat boxes should be supported but have "
                    + "not been tested."
                )

        recipe: Optional[BoxRecipe] = box_map.get(box.type, None)
        if recipe is None:
            recipe = box_map.get("default", BoxRecipe("Unknown"))
        assert recipe is not None
        box.print_start(lvl, name=recipe.name)
        recipe.parse(reader, box, lvl + 1)

        # End bounds check
        assert (
            reader.position() <= box.end
        ), f"Error: Read past the box with {reader.position() - box.end} bytes"
        if reader.position() < box.end:
            print(
                "Warning: Did not read all data in the box. "
                + f"({box.end - reader.position()}) byte(s) more)"
            )

        box.print_end(lvl)
        boxes.append(box)
        reader.skip_to(box.end)

    # If specified, check if the expected number of boxes was read
    if expected_box_count is not None and expected_box_count != len(boxes):
        assert expected_box_count != len(
            boxes
        ), f"Error: Expected {expected_box_count} boxes but read {len(boxes)}"
    return boxes


# Recipes for how to parse various boxes.
# Any box not listed here will be copied as-is from source to destination.
MAP_IPCO_BOX: BoxSequenceMap = {
    "av1C": BoxRecipe("AV1 Decoder Configuration Record", body_parser=parse_av1c_box),
    "colr": BoxRecipe("Color Information Box", body_parser=parse_colr_box),
    "pixi": BoxRecipe("Pixel Information Box", full_box=True, body_parser=parse_pixi_box),
    "ispe": BoxRecipe("Image Spatial Extents Box", full_box=True, body_parser=parse_ispe_box),
    "clap": BoxRecipe("Clean Aperture Box", body_parser=parse_clap_box),
}

MAP_IPRP_BOX: BoxSequenceMap = {
    "ipco": BoxRecipe("Item Property Container Box", sequence_map=MAP_IPCO_BOX),
    "ipma": BoxRecipe("Item Property Association Box", full_box=True, body_parser=parse_ipma_box),
}

MAP_META_BOX: BoxSequenceMap = {
    "iprp": BoxRecipe("Item Properties Box", sequence_map=MAP_IPRP_BOX),
    "iloc": BoxRecipe("Item Location Box", full_box=True, body_parser=parse_iloc_box),
    "iinf": BoxRecipe("Item Information Box", full_box=True, body_parser=parse_iinf_box),
    "iref": BoxRecipe("Item Reference Box", full_box=True, body_parser=parse_iref_box),
    "pitm": BoxRecipe("Primary Item Box", full_box=True, body_parser=parse_pitm_box),
}

MAP_STBL_BOX: BoxSequenceMap = {
    "stco": BoxRecipe("Sample Chunk Offset Box", full_box=True, body_parser=parse_stco_box),
    "stsd": BoxRecipe("Sample Description Box", full_box=True, body_parser=parse_stsd_box),
}

MAP_DINF_BOX: BoxSequenceMap = {
    "dref": BoxRecipe("Data Reference Box", full_box=True, body_parser=parse_dref_box),
}

MAP_MINF_BOX: BoxSequenceMap = {
    "dinf": BoxRecipe("Data Information Box", sequence_map=MAP_DINF_BOX),
    "stbl": BoxRecipe("Sample Table Box", sequence_map=MAP_STBL_BOX),
}

MAP_MDIA_BOX: BoxSequenceMap = {
    "hdlr": BoxRecipe("Handler Reference Box", full_box=True, body_parser=parse_hdlr_box),
    "minf": BoxRecipe("Media Information Box", sequence_map=MAP_MINF_BOX),
}

MAP_TRAK_BOX: BoxSequenceMap = {
    "mdia": BoxRecipe("Media Box", sequence_map=MAP_MDIA_BOX),
    "tref": BoxRecipe("Track Reference Box", sequence_map={}),
    "tkhd": BoxRecipe("Track Header Box", full_box=True, body_parser=parse_tkhd_box),
}

MAP_MOOV_BOX: BoxSequenceMap = {
    "trak": BoxRecipe("Track Box", sequence_map=MAP_TRAK_BOX),
}

MAP_TOP_LEVEL: BoxSequenceMap = {
    "ftyp": BoxRecipe("File Type Box", body_parser=parse_ftyp_box),
    "meta": BoxRecipe("Meta Box", full_box=True, sequence_map=MAP_META_BOX),
    "moov": BoxRecipe("Movie Box", sequence_map=MAP_MOOV_BOX),
    "moof": BoxRecipe("Unsupported box", body_parser=parse_unsupported_box),
}


# ===========================================
# AV1 OBU parsing
# ===========================================
class AV1ElementaryStream:
    """Class representing an AV1 elementary stream."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.obu_list: Optional[list[dict[str, Any]]] = None

    def get_sequence_header_obu(self) -> Optional[dict[str, Any]]:
        """Returns the parsed Sequence Header OBU."""
        if self.obu_list is None:
            self._parse_obus()
        if self.obu_list is not None:
            for obu in self.obu_list:
                if obu["description"] == "OBU_SEQUENCE_HEADER":
                    return obu
        return None

    def generate_av1c_from_sequence_header(self) -> BoxBody:
        """Generate av1C body from Sequence Header OBU."""

        sequence_header_obu = self.get_sequence_header_obu()
        assert sequence_header_obu is not None
        sh_body = sequence_header_obu["body"]
        body = {}
        body["marker"] = 1
        body["version"] = 1
        body["seq_profile"] = sh_body["seq_profile"]
        body["seq_level_idx_0"] = sh_body["seq_level_idx[0]"]
        body["seq_tier_0"] = sh_body["seq_tier[0]"]
        body["high_bitdepth"] = sh_body["high_bitdepth"]
        body["twelve_bit"] = sh_body.get("twelve_bit", 0)
        body["monochrome"] = sh_body["mono_chrome"]
        body["chroma_subsampling_x"] = sh_body["subsampling_x"]
        body["chroma_subsampling_y"] = sh_body["subsampling_y"]
        body["chroma_sample_position"] = sh_body.get("chroma_sample_position", 0)
        assert (
            sh_body["initial_display_delay_present_flag"] == 0
        ), "initial_display_delay_present_flag not implemented"
        body["initial_presentation_delay_present"] = 0
        return body

    def generate_nclx_from_sequence_header(self) -> BoxBody:
        """Generate nclx-colr box body from Sequence Header OBU."""
        sequence_header_obu = self.get_sequence_header_obu()
        assert sequence_header_obu is not None
        sh_body = sequence_header_obu["body"]
        return {
            "type": "nclx",
            "color_primaries": sh_body["color_primaries"],
            "transfer_characteristics": sh_body["transfer_characteristics"],
            "matrix_coefficients": sh_body["matrix_coefficients"],
            "full_range_flag": sh_body["color_range"],
        }

    def generate_ispe_from_sequence_header(self) -> dict[str, int]:
        """Generate ispe box body from Sequence Header OBU."""
        sequence_header_obu = self.get_sequence_header_obu()
        assert sequence_header_obu is not None
        sh_body = sequence_header_obu["body"]
        return {
            "width": sh_body["max_frame_width_minus_1"] + 1,
            "height": sh_body["max_frame_height_minus_1"] + 1,
        }

    def generate_pixi_from_sequence_header(self) -> BoxBody:
        """Generate pixi box body from Sequence Header OBU."""
        sequence_header_obu = self.get_sequence_header_obu()
        assert sequence_header_obu is not None
        sh_body = sequence_header_obu["body"]
        return {
            "bits_per_channel": [sh_body["calculated_bitdepth"]] * sh_body["calculated_numplanes"]
        }

    def _parse_av1_sequence_header_obu(self, reader: FileReader.BitReader) -> dict[str, int]:
        """Parse AV1 Sequence Header OBU and return as a dictionary of properties."""
        parsed = {}
        parsed["seq_profile"] = reader.f(3)
        parsed["still_picture"] = reader.f(1)
        parsed["reduced_still_picture_header"] = reader.f(1)
        if parsed["reduced_still_picture_header"]:
            parsed["timing_info_present_flag"] = 0
            parsed["decoder_model_info_present_flag"] = 0
            parsed["initial_display_delay_present_flag"] = 0
            parsed["operating_points_cnt_minus_1"] = 0
            parsed["operating_point_idc[0]"] = 0
            parsed["seq_level_idx[0]"] = reader.f(5)
            parsed["seq_tier[0]"] = 0
            parsed["decoder_model_present_for_this_op[0]"] = 0
            parsed["initial_display_delay_present_for_this_op[0]"] = 0
        else:
            parsed["timing_info_present_flag"] = reader.f(1)
            assert parsed["timing_info_present_flag"] == 0, "Not yet implemented"
            parsed["decoder_model_info_present_flag"] = 0

            parsed["initial_display_delay_present_flag"] = reader.f(1)
            parsed["operating_points_cnt_minus_1"] = reader.f(5)
            for i in range(parsed["operating_points_cnt_minus_1"] + 1):
                parsed[f"operating_point_idc[{i}]"] = reader.f(12)
                parsed[f"seq_level_idx[{i}]"] = reader.f(5)
                if parsed[f"seq_level_idx[{i}]"] > 7:
                    parsed[f"seq_tier[{i}]"] = reader.f(1)
                else:
                    parsed[f"seq_tier[{i}]"] = 0
                parsed[f"decoder_model_present_for_this_op[{i}]"] = 0
                if parsed["initial_display_delay_present_flag"]:
                    parsed[f"initial_display_delay_present_for_this_op[{i}]"] = reader.f(1)
                    if parsed[f"initial_display_delay_present_for_this_op[{i}]"]:
                        parsed[f"initial_display_delay_minus_1[{i}]"] = reader.f(4)
        parsed["frame_width_bits_minus_1"] = reader.f(4)
        parsed["frame_height_bits_minus_1"] = reader.f(4)
        parsed["max_frame_width_minus_1"] = reader.f(parsed["frame_width_bits_minus_1"] + 1)
        parsed["max_frame_height_minus_1"] = reader.f(parsed["frame_height_bits_minus_1"] + 1)
        if parsed["reduced_still_picture_header"]:
            parsed["frame_id_numbers_present_flag"] = 0
        else:
            parsed["frame_id_numbers_present_flag"] = reader.f(1)
        if parsed["frame_id_numbers_present_flag"]:
            parsed["delta_frame_id_length_minus_2"] = reader.f(4)
            parsed["additional_frame_id_length_minus_1"] = reader.f(3)
        parsed["use_128x128_superblock"] = reader.f(1)
        parsed["enable_filter_intra"] = reader.f(1)
        parsed["enable_intra_edge_filter"] = reader.f(1)
        if parsed["reduced_still_picture_header"]:
            parsed["enable_interintra_compound"] = 0
            parsed["enable_masked_compound"] = 0
            parsed["enable_warped_motion"] = 0
            parsed["enable_dual_filter"] = 0
            parsed["enable_order_hint"] = 0
            parsed["enable_jnt_comp"] = 0
            parsed["enable_ref_frame_mvs"] = 0
            parsed["seq_force_screen_content_tools"] = 2  # SELECT_SCREEN_CONTENT_TOOLS
            parsed["seq_choose_integer_mv"] = 2  # SELECT_INTEGER_MV
        else:
            parsed["enable_interintra_compound"] = reader.f(1)
            parsed["enable_masked_compound"] = reader.f(1)
            parsed["enable_warped_motion"] = reader.f(1)
            parsed["enable_dual_filter"] = reader.f(1)
            parsed["enable_order_hint"] = reader.f(1)
            if parsed["enable_order_hint"]:
                parsed["enable_jnt_comp"] = reader.f(1)
                parsed["enable_ref_frame_mvs"] = reader.f(1)
            else:
                parsed["enable_jnt_comp"] = 0
                parsed["enable_ref_frame_mvs"] = 0
            parsed["seq_choose_screen_content_tools"] = reader.f(1)
            if parsed["seq_choose_screen_content_tools"]:
                parsed["seq_force_screen_content_tools"] = 2  # SELECT_SCREEN_CONTENT_TOOLS
            else:
                parsed["seq_force_screen_content_tools"] = reader.f(1)

            if parsed["seq_force_screen_content_tools"] > 0:
                parsed["seq_choose_integer_mv"] = reader.f(1)
                if parsed["seq_choose_integer_mv"]:
                    parsed["seq_force_integer_mv"] = 2  # SELECT_INTEGER_MV
                else:
                    parsed["seq_force_integer_mv"] = reader.f(1)
            else:
                parsed["seq_force_integer_mv"] = 2  # SELECT_INTEGER_MV
            if parsed["enable_order_hint"]:
                parsed["order_hint_bits_minus_1"] = reader.f(3)
        parsed["enable_superres"] = reader.f(1)
        parsed["enable_cdef"] = reader.f(1)
        parsed["enable_restoration"] = reader.f(1)

        # color_config()
        parsed["high_bitdepth"] = reader.f(1)
        if parsed["seq_profile"] == 2 and parsed["high_bitdepth"]:
            parsed["twelve_bit"] = reader.f(1)
            bitdepth = 12 if parsed["twelve_bit"] else 10
        elif parsed["seq_profile"] <= 2:
            bitdepth = 10 if parsed["high_bitdepth"] else 8
        parsed["calculated_bitdepth"] = bitdepth

        if parsed["seq_profile"] != 1:
            parsed["mono_chrome"] = reader.f(1)
        else:
            parsed["mono_chrome"] = 0
        numplanes = 1 if parsed["mono_chrome"] else 3
        parsed["calculated_numplanes"] = numplanes
        parsed["color_description_present_flag"] = reader.f(1)
        if parsed["color_description_present_flag"]:
            parsed["color_primaries"] = reader.f(8)
            parsed["transfer_characteristics"] = reader.f(8)
            parsed["matrix_coefficients"] = reader.f(8)
        else:
            parsed["color_primaries"] = 2
            parsed["transfer_characteristics"] = 2
            parsed["matrix_coefficients"] = 2
        if parsed["mono_chrome"]:
            parsed["color_range"] = reader.f(1)
            parsed["subsampling_x"] = 1
            parsed["subsampling_y"] = 1
            parsed["chroma_sample_position"] = 0
        elif (
            parsed["color_primaries"] == 1
            and parsed["transfer_characteristics"] == 13
            and parsed["matrix_coefficients"] == 0
        ):
            parsed["color_range"] = 1
            parsed["subsampling_x"] = 0
            parsed["subsampling_y"] = 0
        else:
            parsed["color_range"] = reader.f(1)
            if parsed["seq_profile"] == 0:
                parsed["subsampling_x"] = parsed["subsampling_y"] = 1
            elif parsed["seq_profile"] == 1:
                parsed["subsampling_x"] = parsed["subsampling_y"] = 0
            else:
                if parsed["twelve_bit"]:
                    parsed["subsampling_x"] = reader.f(1)
                    if parsed["subsampling_x"]:
                        parsed["subsampling_y"] = reader.f(1)
                    else:
                        parsed["subsampling_y"] = 0
                else:
                    parsed["subsampling_x"] = 1
                    parsed["subsampling_y"] = 0
            if parsed["subsampling_x"] and parsed["subsampling_y"]:
                parsed["chroma_sample_position"] = reader.f(2)
        parsed["separate_uv_delta_q"] = reader.f(1)
        # end color_config()

        parsed["film_grain_params_present"] = reader.f(1)
        return parsed

    def _parse_obus(self) -> None:
        """Parse data as sequence of AV1 OBUs."""
        reader = FileReader.BitReader(self.data)
        obu_map: dict[int, tuple[Optional[OBUParser], str]] = {
            1: (self._parse_av1_sequence_header_obu, "OBU_SEQUENCE_HEADER"),
            2: (None, "OBU_TEMPORAL_DELIMITER"),
            3: (None, "OBU_FRAME_HEADER"),
            4: (None, "OBU_TILE_GROUP"),
            5: (None, "OBU_METADATA"),
            6: (None, "OBU_FRAME"),
            7: (None, "OBU_REDUNDANT_FRAME_HEADER"),
            8: (None, "OBU_TILE_LIST"),
            15: (None, "OBU_PADDING"),
        }

        def _read_obu_header(bit_reader: FileReader.BitReader) -> dict[str, int]:
            header = {}
            header["forbidden_bit"] = bit_reader.f(1)
            header["type"] = bit_reader.f(4)
            header["extension_flag"] = bit_reader.f(1)
            header["has_size_field"] = bit_reader.f(1)
            header["reserved_1bit"] = bit_reader.f(1)
            if header["extension_flag"] != 0:
                header["temporal_id"] = bit_reader.f(3)
                header["spatial_id"] = bit_reader.f(2)
                header["extension_reserved_3bits"] = bit_reader.f(3)
            return header

        obu_list = []

        while not reader.eof():
            obu_header = _read_obu_header(reader)
            assert obu_header["has_size_field"] != 0
            obu_size = reader.read_leb128_value()
            parse_function = None
            description = "Unknown OBU"
            if obu_header["type"] in obu_map:
                parse_function, description = obu_map[obu_header["type"]]

            body = {}
            if parse_function is not None:
                body = parse_function(reader.bit_reader_for_bytes(obu_size))
            else:
                reader.skip_bytes(obu_size)

            obu = {
                "description": description,
                "header": obu_header,
                "body": body,
            }
            obu_list.append(obu)
        self.obu_list = obu_list


# ===========================================
# Box validation
# ===========================================
class ParsedFile:
    """Class describing a parsed AVIF file."""

    def __init__(self, file: BinaryIO, verbose: bool) -> None:
        self.reader = FileReader(file)

        assert self.reader.size > 8, "Size of file is too small to be AVIF"

        # Check if file seems to be HEIF
        box_size = self.reader.read_integer_of_size(self.reader.size, 4)
        assert box_size > 8, "Size of ftyp box is too small to be AVIF"

        box_type = self.reader.read_string(self.reader.size, 4)
        if box_type != "ftyp":
            print('File does not start with "ftyp" box. Cannot proceed.')
            sys.exit(1)
        self.reader.rewind()

        # Parse the boxes
        self.lvl = 0 if verbose else NONVERBOSE_PRINT_LEVEL
        self.boxes = parse_box_sequence(
            self.reader, self.reader.size, self.lvl, box_map=MAP_TOP_LEVEL
        )

        self.ipma = self.get_box_from_hierarchy(["meta", "iprp", "ipma"])
        self.ipco = self.get_box_from_hierarchy(["meta", "iprp", "ipco"])

    def get_box_from_hierarchy(
        self, box_hierarchy: list[str], box_array: Optional[list[Box]] = None
    ) -> Optional[Box]:
        """Extracts the first box matching a given hierarchy."""
        box_array = self.boxes if box_array is None else box_array
        for box in box_array:
            if box.type == box_hierarchy[0]:
                if len(box_hierarchy) == 1:
                    return box
                return self.get_box_from_hierarchy(box_hierarchy[1:], box_array=box.sub_boxes)
        return None

    def get_iloc_entry_for_item(self, item_id: int) -> Optional[dict[str, Any]]:
        """Extracts the iloc entry for the given item_id."""
        iloc_box = self.get_box_from_hierarchy(["meta", "iloc"])
        if iloc_box is not None:
            body = iloc_box.body
            for item in body["items"]:
                if item["item_ID"] == item_id:
                    return typing.cast(dict[str, Any], item)
        return None

    def get_item_properties_for_item(self, item_id: int) -> list[tuple[Box, bool]]:
        """Extracts the item properties associated with a given item_id."""
        if self.ipma is None or self.ipco is None or self.ipco.sub_boxes is None:
            return []
        associations = self.ipma.body["associations"].get(item_id, [])
        properties = []
        for property_index, essential in associations:
            assert 1 <= property_index <= len(self.ipco.sub_boxes) + 1
            property_box = self.ipco.sub_boxes[property_index - 1]
            properties.append((property_box, essential))
        return properties

    def get_items(self) -> dict[int, dict[str, Any]]:
        """Creates a list of items from parsed boxes."""
        items: dict[int, dict[str, Any]] = {}
        iinf_box = self.get_box_from_hierarchy(["meta", "iinf"])
        if iinf_box is None or iinf_box.sub_boxes is None:
            return items

        for infe_box in iinf_box.sub_boxes:
            item_id = infe_box.body["item_id"]
            items[item_id] = {}

            iloc = self.get_iloc_entry_for_item(item_id)
            items[item_id]["item_id"] = item_id
            items[item_id]["infe"] = infe_box
            items[item_id]["iloc"] = iloc
            items[item_id]["item_properties"] = self.get_item_properties_for_item(item_id)
            if infe_box.body["item_type"] == "av01" and iloc is not None:
                items[item_id]["av01_stream"] = self.get_av1_elementary_stream_for_item(iloc)
        return items

    def get_av1_elementary_stream_for_item(self, iloc_entry: dict[str, Any]) -> AV1ElementaryStream:
        """Extract and parse AV1 elementary stream for a given item iloc."""
        assert iloc_entry["construction_method"] == 0, "Only construction_method 0 implemented"
        base = iloc_entry["base_offset"]
        data = bytes()
        for extent in iloc_entry["extents"]:
            total_offset = base + extent["offset"]
            length = extent["length"]
            data += self.reader.read_data_from_offset(total_offset, length)
        return AV1ElementaryStream(data)

    def get_existing_property_if_present(
        self,
        property_type: BoxType,
        property_header: Optional[BoxHeader],
        property_body: Optional[BoxBody],
    ) -> int:
        """Gets the index in the 'ipco' for an existing property, or -1 if none exists."""
        existing_box_index = -1
        if self.ipco is None or self.ipco.sub_boxes is None:
            return existing_box_index
        for box_index, box in enumerate(self.ipco.sub_boxes):
            if (
                box.type == property_type
                and box.header == property_header
                and box.body == property_body
            ):
                existing_box_index = box_index
                break
        return existing_box_index

    def add_property_association(
        self, item_id: int, ipco_index: int, essential: bool, position: Optional[int] = None
    ) -> None:
        """Add an association from an item to a property in the ipco box if not already present."""
        if self.ipma is None or self.ipco is None or self.ipco.sub_boxes is None:
            return
        associations = self.ipma.body["associations"].get(item_id, [])
        association_index = -1
        existing_association_essential = False
        for cur_index, (property_index, cur_essential) in enumerate(associations):
            assert 1 <= property_index <= len(self.ipco.sub_boxes)
            if ipco_index == property_index - 1:
                association_index = cur_index
                existing_association_essential = cur_essential
                break

        # If association is not present, we need to add it
        if association_index == -1:
            if item_id not in self.ipma.body["associations"]:
                self.ipma.body["associations"][item_id] = []
            val = (ipco_index + 1, essential)
            if position is None:
                position = len(self.ipma.body["associations"][item_id])
            self.ipma.body["associations"][item_id].insert(position, val)
            self.ipma.mark_for_rewrite()
        elif essential and not existing_association_essential:
            self.ipma.body["associations"][item_id][association_index] = (ipco_index + 1, essential)
            self.ipma.mark_for_rewrite()

    def remove_property_associations(
        self,
        item_id: int,
        property_type: BoxType,
        header: Optional[BoxHeader] = None,
        body: Optional[BoxBody] = None,
    ) -> tuple[Optional[int], bool]:
        """Remove all association from an item to a property type in the ipco box."""
        if self.ipma is None or self.ipco is None or self.ipco.sub_boxes is None:
            return (None, True)
        associations = self.ipma.body["associations"].get(item_id, [])

        def _should_keep(prop_index: int, _essential: bool) -> bool:
            assert self.ipco and self.ipco.sub_boxes
            assert 1 <= prop_index <= len(self.ipco.sub_boxes)
            box = self.ipco.sub_boxes[prop_index - 1]

            keep = box.type != property_type
            if header is not None:
                keep = keep or box.header != header
            if body is not None:
                keep = keep or box.body != body
            return keep

        filtered_associations = []
        first_removed_assoc: tuple[Optional[int], bool] = (None, True)
        for position, (prop_index, essential) in enumerate(associations):
            if _should_keep(prop_index, essential):
                filtered_associations.append((prop_index, essential))
            elif first_removed_assoc[0] is None:
                first_removed_assoc = (position, essential)

        if associations != filtered_associations:
            self.ipma.body["associations"][item_id] = filtered_associations
            self.ipma.mark_for_rewrite()
            return first_removed_assoc
        return (None, True)

    def drop_unused_item_properties(self) -> None:
        """Drops any item properties with no associations."""
        if self.ipma is None or self.ipco is None or self.ipco.sub_boxes is None:
            return
        prop_assoc_count = [0] * len(self.ipco.sub_boxes)
        for _, associations in self.ipma.body["associations"].items():
            for prop_index, _ in associations:
                prop_assoc_count[prop_index - 1] += 1

        if prop_assoc_count.count(0) == 0:
            return

        # Change association indices to account for dropped properties
        props_to_drop = [0 if v > 0 else 1 for v in prop_assoc_count]
        decrement_count = list(accumulate(props_to_drop))
        for _, associations in self.ipma.body["associations"].items():
            for assoc_index, (prop_index, essential) in enumerate(associations):
                associations[assoc_index] = (
                    prop_index - decrement_count[prop_index - 1],
                    essential,
                )

        # Drop unused properties
        self.ipco.sub_boxes = [
            box for index, box in enumerate(self.ipco.sub_boxes) if props_to_drop[index] == 0
        ]
        self.ipco.mark_for_rewrite()

    def _add_property_if_needed(
        self, property_type: BoxType, header: BoxHeader, body: BoxBody
    ) -> int:
        if self.ipma is None or self.ipco is None or self.ipco.sub_boxes is None:
            return -1
        existing_box_index = self.get_existing_property_if_present(property_type, header, body)
        # No existing box, we need to add one
        if existing_box_index == -1:
            box = Box(property_type, self.ipco, 0, 0)
            box.header = header if header is not None else {}
            box.body = body
            existing_box_index = len(self.ipco.sub_boxes)
            self.ipco.sub_boxes += [box]
            box.mark_for_rewrite()
        return existing_box_index

    def replace_property_for_item(
        self,
        property_type: BoxType,
        header: BoxHeader,
        body: BoxBody,
        item_id: int,
        old_header: Optional[BoxHeader] = None,
        old_body: Optional[BoxBody] = None,
    ) -> None:
        """Replace a property for an item_id."""
        box_index = self._add_property_if_needed(property_type, header, body)
        position, essential = self.remove_property_associations(
            item_id, property_type, old_header, old_body
        )
        self.add_property_association(item_id, box_index, essential, position=position)
        self.drop_unused_item_properties()

    def add_property_for_item(
        self,
        property_type: BoxType,
        header: BoxHeader,
        body: BoxBody,
        item_id: int,
        essential: bool,
        position: Optional[int] = None,
    ) -> None:
        """Adds a new property box if needed and adds an association from the item_id to it."""
        box_index = self._add_property_if_needed(property_type, header, body)
        self.add_property_association(item_id, box_index, essential, position)

    def mark_offset_boxes_for_rewrite(self) -> None:
        """Marks boxes containing offsets as needing rewriting."""
        iloc = self.get_box_from_hierarchy(["meta", "iloc"])
        if iloc is not None:
            iloc.mark_for_rewrite()

        moov_box = self.get_box_from_hierarchy(["moov"])
        if moov_box is not None and moov_box.sub_boxes is not None:
            for box in moov_box.sub_boxes:
                if box.type != "trak":
                    continue
                stco = self.get_box_from_hierarchy(["mdia", "minf", "stbl", "stco"], box.sub_boxes)
                if stco is not None:
                    stco.mark_for_rewrite()

    def boxes_have_changed(self) -> bool:
        """Returns true if any box has changed."""
        return any(box.needs_rewrite for box in self.boxes)


# ===========================================
# Box rewriting
# ===========================================
class AVIFWriter:
    """Class containing functionality for writing out AVIF files."""

    def __init__(self, parsed_file: ParsedFile, output: BinaryIO) -> None:
        self.parsed_file = parsed_file
        self.output = output
        self.box_writer_map: dict[BoxType, BoxWriter] = {
            BoxType("av1C"): self._write_av1c_box,
            BoxType("colr"): self._write_colr_box,
            BoxType("pixi"): self._write_pixi_box,
            BoxType("ipco"): self._write_generic_container_box,
            BoxType("ipma"): self._write_ipma_box,
            BoxType("iprp"): self._write_generic_container_box,
            BoxType("iloc"): self._write_iloc_box,
            BoxType("meta"): self._write_generic_container_box,
            BoxType("moov"): self._write_generic_container_box,
            BoxType("trak"): self._write_generic_container_box,
            BoxType("mdia"): self._write_generic_container_box,
            BoxType("minf"): self._write_generic_container_box,
            BoxType("stbl"): self._write_generic_container_box,
            BoxType("stco"): self._write_stco_box,
            BoxType("hdlr"): self._write_hdlr_box,
            BoxType("stsd"): self._write_stsd_box,
            BoxType("av01"): self._write_av01_box,
            BoxType("auxi"): self._write_auxi_box,
            BoxType("tkhd"): self._write_tkhd_box,
            BoxType("ccst"): self._write_ccst_box,
            BoxType("ispe"): self._write_ispe_box,
            BoxType("clap"): self._write_clap_box,
            BoxType("ftyp"): self._write_ftyp_box,
            BoxType("pitm"): self._write_pitm_box,
        }

    def _write_ftyp_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        body_data = bytes()
        body_data += box.body["major"].encode("utf8")
        body_data += write_integer_of_size(box.body["version"], 4)
        for brand in box.body["compatible"]:
            body_data += brand.encode("utf8")
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_av1c_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        byte0 = (box.body["marker"] << 7) | (box.body["version"])
        byte1 = (box.body["seq_profile"] << 5) | (box.body["seq_level_idx_0"])
        byte2 = (box.body["seq_tier_0"] << 7) | (box.body["high_bitdepth"] << 6)
        byte2 |= (box.body["twelve_bit"] << 5) | (box.body["monochrome"] << 4)
        byte2 |= (box.body["chroma_subsampling_x"] << 3) | (box.body["chroma_subsampling_y"] << 2)
        byte2 |= box.body["chroma_sample_position"]
        byte3 = box.body["initial_presentation_delay_present"] << 4
        assert box.body["initial_presentation_delay_present"] == 0
        body_data = struct.pack(">BBBB", byte0, byte1, byte2, byte3)
        return box.write_box_header(len(body_data)) + body_data, []

    def _write_pitm_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        assert box.header["version"] in [0, 1]
        body_data = bytes()
        item_id_size = 2 if box.header["version"] < 1 else 4
        body_data += write_integer_of_size(box.body["item_id"], item_id_size)
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_colr_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        assert box.body["type"] == "nclx"
        body_data = bytes()
        body_data += "nclx".encode("utf-8")
        body_data += write_integer_of_size(box.body["color_primaries"], 2)
        body_data += write_integer_of_size(box.body["transfer_characteristics"], 2)
        body_data += write_integer_of_size(box.body["matrix_coefficients"], 2)
        body_data += write_integer_of_size(box.body["full_range_flag"] << 7, 1)
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_pixi_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        body_data = bytes()
        bpp = box.body["bits_per_channel"]
        body_data += write_integer_of_size(len(bpp), 1)
        for value in bpp:
            body_data += write_integer_of_size(value, 1)
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_clap_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        body_data = bytes()
        body_data += write_integer_array_of_size(box.body["width"], 4, unsigned=False)
        body_data += write_integer_array_of_size(box.body["height"], 4, unsigned=False)
        body_data += write_integer_array_of_size(box.body["h_offset"], 4, unsigned=False)
        body_data += write_integer_array_of_size(box.body["v_offset"], 4, unsigned=False)
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_ispe_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        body_data = bytes()
        body_data += write_integer_of_size(box.body["width"], 4)
        body_data += write_integer_of_size(box.body["height"], 4)
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_box_sequence(
        self, boxes: Optional[list[Box]], current_offset: int
    ) -> BoxWriterReturn:
        body_data = bytes()
        placeholder_offsets: list[PlaceholderFileOffset] = []
        if boxes is None:
            return body_data, placeholder_offsets
        for sub_box in boxes:
            if not sub_box.needs_rewrite:
                body_data += self.parsed_file.reader.read_data_from_offset(
                    sub_box.start, sub_box.size
                )
                continue

            writer = self.box_writer_map.get(sub_box.type, None)
            if writer is None:
                assert sub_box.body[
                    "serialized"
                ], f"Have no box writer for un-serialized box of type '{sub_box.type}'"
                writer = self._write_serialized_box
            data, offsets = writer(sub_box, current_offset + len(body_data))
            body_data += data
            placeholder_offsets += offsets
        return body_data, placeholder_offsets

    def _write_generic_container_box(self, box: Box, current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        current_offset += 8
        if len(box.header) > 0:
            current_offset += 4

        body_data, placeholder_offsets = self._write_box_sequence(box.sub_boxes, current_offset)
        return box.write_box_header(len(body_data)) + body_data, placeholder_offsets

    def _write_ipma_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        associations = box.body["associations"]

        item_id_type = ">H" if box.header["version"] < 1 else ">I"
        association_size = 2 if (box.header["flags"] & 1) == 1 else 1
        max_property_index = (1 << association_size * 8) - 1

        body_data = bytes()
        body_data += struct.pack(">I", len(associations))
        item_ids = sorted(associations.keys())
        for item_id in item_ids:
            item_assocs = associations[item_id]
            body_data += struct.pack(item_id_type, item_id)
            body_data += struct.pack(">B", len(item_assocs))
            for prop_index, essential in item_assocs:
                assert prop_index <= max_property_index
                essential_bit = 1 if essential else 0
                if association_size == 2:
                    body_data += struct.pack(">H", (essential_bit << 15) | prop_index)
                else:
                    body_data += struct.pack(">B", (essential_bit << 7) | prop_index)

        return box.write_box_header(len(body_data)) + body_data, []

    def _write_iloc_box(self, box: Box, current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite

        version = box.header["version"]
        offset_size = box.body["offset_size"]
        length_size = box.body["length_size"]
        base_offset_size = box.body["base_offset_size"]
        index_size = box.body.get("index_size", 0)
        item_count_and_id_size = 2 if version < 2 else 4

        current_offset += 12  # Full-box header

        # These offsets need to be corrected once it is known how offsets have moved.
        placeholder_offsets = []

        items = box.body["items"]
        body_data = bytes()
        body_data += struct.pack(">B", (offset_size << 4) | length_size)
        body_data += struct.pack(">B", (base_offset_size << 4) | index_size)
        body_data += write_integer_of_size(len(items), item_count_and_id_size)
        for item in items:
            base_placeholder = None
            body_data += write_integer_of_size(item["item_ID"], item_count_and_id_size)
            if version in [1, 2]:
                body_data += struct.pack(">BB", 0, item["construction_method"])
            body_data += struct.pack(">H", 0)  # data_reference_index
            if base_offset_size > 0:
                if item["construction_method"] == 0:
                    base_placeholder = PlaceholderFileOffset(
                        box, current_offset + len(body_data), base_offset_size, item["base_offset"]
                    )
                    placeholder_offsets.append(base_placeholder)
                body_data += write_integer_of_size(item["base_offset"], base_offset_size)

            extents = item["extents"]
            body_data += write_integer_of_size(len(extents), 2)
            for extent in extents:
                if index_size > 0:
                    body_data += write_integer_of_size(extent["item_reference_index"], index_size)
                if offset_size > 0:
                    if item["construction_method"] == 0:
                        placeholder = PlaceholderFileOffset(
                            box,
                            current_offset + len(body_data),
                            offset_size,
                            extent["offset"],
                            base=base_placeholder,
                        )
                        if base_offset_size == 0:
                            placeholder_offsets.append(placeholder)
                    body_data += write_integer_of_size(extent["offset"], offset_size)
                body_data += write_integer_of_size(extent["length"], length_size)

        data = box.write_box_header(len(body_data)) + body_data
        return data, placeholder_offsets

    def _write_stco_box(self, box: Box, current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite

        current_offset += 12  # Full-box header

        # These offsets need to be corrected once it is known how offsets have moved.
        placeholder_offsets = []

        entries = box.body["entries"]
        entry_count = len(entries)
        body_data = bytes()
        body_data += write_integer_of_size(entry_count, 4)
        for entry in entries:
            placeholder = PlaceholderFileOffset(box, current_offset + len(body_data), 4, entry)
            placeholder_offsets.append(placeholder)
            body_data += write_integer_of_size(entry, 4)
        data = box.write_box_header(len(body_data)) + body_data
        return data, placeholder_offsets

    def _write_stsd_box(self, box: Box, current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        current_offset += 12  # Full-box header
        body_data = bytes()
        sub_boxes = [] if box.sub_boxes is None else box.sub_boxes
        body_data += write_integer_of_size(len(sub_boxes), 4)
        current_offset += len(body_data)
        sub_data, placeholder_offsets = self._write_box_sequence(sub_boxes, current_offset)
        body_data += sub_data
        data = box.write_box_header(len(body_data)) + body_data
        return data, placeholder_offsets

    def _write_av01_box(self, box: Box, current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        current_offset += 8  # Box header
        body_data = bytes()
        body_data += box.body["sampleentry"]
        body_data += box.body["visualsampleentry"]
        current_offset += len(body_data)
        sub_data, placeholder_offsets = self._write_box_sequence(box.sub_boxes, current_offset)
        body_data += sub_data
        data = box.write_box_header(len(body_data)) + body_data
        return data, placeholder_offsets

    def _write_auxi_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        body_data = box.body["aux_track_type"].encode("utf8")
        body_data += write_integer_of_size(0, 1)
        data = box.write_box_header(len(body_data)) + body_data
        return data, []

    def _write_hdlr_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        body_data = bytes()
        body_data += write_integer_of_size(box.body["pre_defined"], 4)
        body_data += box.body["hdlr_type"].encode("utf8")
        body_data += write_integer_of_size(0, 4)
        body_data += write_integer_of_size(0, 4)
        body_data += write_integer_of_size(0, 4)
        if box.body["name"] is not None:
            body_data += box.body["name"].encode("utf8")
        body_data += write_integer_of_size(0, 1)
        return box.write_box_header(len(body_data)) + body_data, []

    def _write_tkhd_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        time_size = 8 if box.header["version"] == 1 else 4
        body_data = bytes()
        body_data += write_integer_of_size(box.body["creation_time"], time_size)
        body_data += write_integer_of_size(box.body["modification_time"], time_size)
        body_data += write_integer_of_size(box.body["track_id"], 4)
        body_data += write_integer_of_size(0, 4)
        body_data += write_integer_of_size(box.body["duration"], time_size)
        body_data += write_integer_of_size(0, 8)
        body_data += write_integer_of_size(box.body["layer"], 2)
        body_data += write_integer_of_size(box.body["alternate_group"], 2)
        body_data += write_integer_of_size(box.body["volume"], 2)
        body_data += write_integer_of_size(0, 2)
        for value in box.body["matrix"]:
            body_data += write_integer_of_size(value, 4)
        body_data += write_integer_of_size(box.body["width"], 4)
        body_data += write_integer_of_size(box.body["height"], 4)
        return box.write_box_header(len(body_data)) + body_data, []

    def _write_ccst_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        value = 0
        value |= box.body["all_ref_pics_intra"] << 31
        value |= box.body["intra_pred_used"] << 30
        value |= box.body["max_ref_per_pic"] << 26
        body_data = write_integer_of_size(value, 4)
        return box.write_box_header(len(body_data)) + body_data, []

    def _write_serialized_box(self, box: Box, _current_offset: int) -> BoxWriterReturn:
        assert box.needs_rewrite
        assert "serialized" in box.body
        data = box.body["serialized"]
        assert isinstance(data, bytes)
        return box.write_box_header(len(data)) + data, []

    def write(self) -> None:
        """Writes out all boxes to the destination file."""
        placeholder_offsets = []
        mdat_boxes: list[tuple[Box, int]] = []

        # Mark iloc/stco as needing rewrite if any boxes are changing
        if self.parsed_file.boxes_have_changed():
            self.parsed_file.mark_offset_boxes_for_rewrite()

        for box in self.parsed_file.boxes:
            if box.type == "mdat":
                current_pos = self.output.tell()
                mdat_boxes.append((box, current_pos))

            if not box.needs_rewrite:
                self.parsed_file.reader.copy_data_to_destination(self.output, box.start, box.size)
                continue

            writer = self.box_writer_map.get(box.type, None)
            if writer is None:
                assert isinstance(
                    box.body, bytes
                ), f"Have no box writer for un-serialized box of type '{box.type}'"
                writer = self._write_serialized_box
            box_data, cur_offsets = writer(box, self.output.tell())
            self.output.write(box_data)
            placeholder_offsets += cur_offsets

        # 'mdat's may have moved. We need to update any file offset placeholders.
        for placeholder in placeholder_offsets:
            offsets = placeholder.get_offset_list()

            # Find which 'mdat' the offset belonged to
            mdat_box, new_offset = None, None
            for mdat_box, new_offset in mdat_boxes:
                offsets_in_mdat = [mdat_box.start <= o < mdat_box.end for o in offsets]
                if all(offsets_in_mdat):
                    break
                assert not any(
                    offsets_in_mdat
                ), "Items with base_offset + [offset] pointing to multiple 'mdat's not supported"
            delta = new_offset - mdat_box.start
            placeholder.write_delta(self.output, delta)

    def __repr__(self) -> str:
        return f"AVIFWriter(output: {self.output})"


# ===========================================
# File validation and fix-up
# ===========================================


def _get_max_profile_and_limit_for_items(parsed_file: ParsedFile) -> tuple[int, int]:
    items = parsed_file.get_items()
    max_profile = -1
    max_level = -1
    for _, item in items.items():
        if item["infe"].body["item_type"] == "av01":
            generated_av1c = item["av01_stream"].generate_av1c_from_sequence_header()
            max_profile = max(max_profile, generated_av1c["seq_profile"])
            max_level = max(max_level, generated_av1c["seq_level_idx_0"])
    return max_profile, max_level


def _get_max_profile_and_limit_for_tracks(parsed_file: ParsedFile) -> tuple[int, int]:
    moov = parsed_file.get_box_from_hierarchy(["moov"])
    max_profile = -1
    max_level = -1
    if moov is not None and moov.sub_boxes is not None:
        for box in moov.sub_boxes:
            if box.type != "trak":
                continue
            av1c_box = parsed_file.get_box_from_hierarchy(
                ["mdia", "minf", "stbl", "stsd", "av01", "av1C"], box.sub_boxes
            )
            if av1c_box is None:
                continue
            max_profile = max(max_profile, av1c_box.body["seq_profile"])
            max_level = max(max_level, av1c_box.body["seq_level_idx_0"])
    return max_profile, max_level


def _remove_brand_factory(ftyp: Box, brand: str) -> IssueFixer:
    def _fix_brand() -> None:
        if brand == ftyp.body["major"]:
            ftyp.body["major"] = "avif"
            ftyp.body["compatible"].remove("avif")
            ftyp.body["compatible"].remove(brand)
        else:
            ftyp.body["compatible"].remove(brand)
        ftyp.mark_for_rewrite()

    return _fix_brand


def validate_profile_brands(parsed_file: ParsedFile) -> list[BoxIssue]:
    """Validates that profile brands are correct in the ftyp box."""
    ftyp = parsed_file.get_box_from_hierarchy(["ftyp"])
    assert ftyp
    all_brands = [ftyp.body["major"]] + ftyp.body["compatible"]
    max_prof_items, max_lvl_items = _get_max_profile_and_limit_for_items(parsed_file)
    max_prof_sequences, max_lvl_sequences = _get_max_profile_and_limit_for_items(parsed_file)
    max_prof = max(max_prof_items, max_prof_sequences)

    issues = []
    for brand in all_brands:
        profile_limit = None
        level_limit_items = None
        level_limit_sequences = None
        if brand == "MA1B":
            profile_limit = 0  # main profile
            level_limit_items = level_limit_sequences = 13  # level 5.1
        elif brand == "MA1A":
            profile_limit = 1  # main profile
            level_limit_items = 16  # level 6.0
            level_limit_sequences = 13  # level 5.1
        else:
            continue

        issue = BoxIssue(-1, "ftyp")
        template = "Max {} used exceeds highest allowed by {} brand. {} > {}"
        if max_prof > profile_limit:
            issue.add_issue("WARNING", template.format("profile", brand, max_prof, profile_limit))
        if max_lvl_items > level_limit_items:
            issue.add_issue(
                "WARNING", template.format("item level", brand, max_lvl_items, level_limit_items)
            )
        if max_lvl_sequences > level_limit_sequences:
            issue.add_issue(
                "WARNING",
                template.format("sequence level", brand, max_lvl_sequences, level_limit_sequences),
            )
        if len(issue.issues) == 0:
            continue

        issue.add_info_url("incorrect-profile-brands")
        issue.add_fix(_remove_brand_factory(ftyp, brand), f"Remove {brand} from brands in ftyp")
        issues.append(issue)
    return issues


def validate_av1c_property(parsed_file: ParsedFile, item: dict[str, Any]) -> list[BoxIssue]:
    """Validates that av1C property is correct for an item."""
    item_id = item["item_id"]
    generated_av1c = item["av01_stream"].generate_av1c_from_sequence_header()
    existing_av1c = None
    for prop, _ in item["item_properties"]:
        if prop.type == "av1C":
            existing_av1c = prop.body
            break
    assert existing_av1c, "Could not find av1C"

    issue = BoxIssue(item_id, "av1C")
    if "configOBUs" in existing_av1c:
        issue.add_issue("WARNING", "av1C in AVIF should not contain optional config OBUs")
        section = "av1c-contains-optional-config-obus"
    for key, value in generated_av1c.items():
        if existing_av1c[key] != value:
            severity = "CRITICAL"
            description = (
                f"av1C[{key}] does not match Sequence Header OBU. "
                + f"'{existing_av1c[key]}' != '{value}'."
            )
            issue.add_issue(severity, description)
            section = "bad-av1c"
    if len(issue.issues) == 0:
        return []

    def _fix_av1c() -> None:
        parsed_file.replace_property_for_item(BoxType("av1C"), {}, generated_av1c, item_id)

    issue.add_info_url(section)
    issue.add_fix(_fix_av1c, "Regenerate av1C from Sequence Header OBU")
    return [issue]


def validate_colr_property(
    parsed_file: ParsedFile,
    item: dict[str, Any],
    default_nclx: dict[str, list[int]],
    generated_nclx: Optional[BoxBody] = None,
) -> list[BoxIssue]:
    """Validates that colr properties are correct for an item."""
    if generated_nclx is None:
        generated_nclx = item["av01_stream"].generate_nclx_from_sequence_header()
        assert generated_nclx, "Failed to create NCLX property from av01"

    existing_nclx = None
    existing_icc = None
    is_aux_item = False
    for prop, _ in item["item_properties"]:
        if prop.type == "colr":
            if prop.body["type"] == "nclx":
                existing_nclx = prop.body
            elif prop.body["type"] in ["rICC", "prof"]:
                existing_icc = prop.body
        elif prop.type == "auxC":
            is_aux_item = True

    issue = BoxIssue(item["item_id"], "colr")

    if is_aux_item:
        # TODO: Figure out what is correct here. Some stuff may only apply to alpha.
        pass
    elif existing_nclx is None:
        severity = "RENDERING DIFFERENCES"
        template = (
            "Item lacks {} and Sequence Header OBU specifies {} = {}. "
            + "This may not render correctly in all implementations."
        )
        missing = "nclx-colr box" if existing_icc else "any colr box"

        specified_by_icc = ["color_primaries", "transfer_characteristics"] if existing_icc else []
        for key, val in default_nclx.items():
            if key in specified_by_icc:
                continue
            if generated_nclx[key] not in val:
                issue.add_issue(severity, template.format(missing, key, generated_nclx[key]))
    if len(issue.issues) == 0:
        return []

    if existing_icc:
        # If we have existing ICC profile, we only want to add NCLX for matrix and full/video-range
        generated_nclx["color_primaries"] = 2
        generated_nclx["transfer_characteristics"] = 2
    elif existing_nclx is None:
        # If we have no colr box, and Sequence Header does not specify color,
        # explicitly set to the defaults.
        for key, value in default_nclx.items():
            if key == "full_range_flag":
                continue
            if generated_nclx[key] == 2:
                generated_nclx[key] = value[0]

    def _fix_colr() -> None:
        assert generated_nclx
        parsed_file.add_property_for_item(
            BoxType("colr"), {}, generated_nclx, item["item_id"], True
        )

    order = [
        "color_primaries",
        "transfer_characteristics",
        "matrix_coefficients",
        "full_range_flag",
    ]
    nclx_string = ",".join(str(generated_nclx[key]) for key in order)
    description = f"Add 'colr' box of type 'nclx', with values {nclx_string}"
    if existing_icc:
        description = (
            "Add second 'colr' box of type 'nclx' "
            + f"(in addition to existing ICC box), with values {nclx_string}"
        )

    url_section = "missing-nclx-colr-box" if existing_icc else "missing-colr-box"
    issue.add_info_url(url_section)
    issue.add_fix(_fix_colr, description)
    return [issue]


def validate_pixi_property(
    parsed_file: ParsedFile, item: dict[str, Any], generated_pixi: Optional[BoxBody] = None
) -> list[BoxIssue]:
    """Validates that pixi property is present and correct for an item."""
    item_id = item["item_id"]
    if generated_pixi is None:
        generated_pixi = item["av01_stream"].generate_pixi_from_sequence_header()
        assert generated_pixi, "Failed to create pixi from av01"
    existing_pixi = None
    for prop, _ in item["item_properties"]:
        if prop.type == "pixi":
            existing_pixi = prop.body
            break

    if existing_pixi == generated_pixi:
        return []

    issue = BoxIssue(item_id, "pixi")
    severity = "WARNING"
    if existing_pixi is None:
        description = "No 'pixi' present. This is a requirement by MIAF."
    else:
        description = (
            "'pixi' does not match AV1 Sequence Header OBU."
            + f" {existing_pixi} != {generated_pixi}."
        )
    issue.add_issue(severity, description)

    def _fix_pixi() -> None:
        assert generated_pixi
        header = {"version": 0, "flags": 0}
        if existing_pixi is not None:
            parsed_file.replace_property_for_item(BoxType("pixi"), header, generated_pixi, item_id)
        else:
            parsed_file.add_property_for_item(
                BoxType("pixi"), header, generated_pixi, item_id, False
            )

    action_string = "Regenerate" if existing_pixi else "Add"
    issue.add_info_url("missing-or-incorrect-pixi")
    issue.add_fix(_fix_pixi, f"{action_string} pixi from Sequence Header OBU")
    return [issue]


def validate_lsel_property(parsed_file: ParsedFile, item: dict[str, Any]) -> list[BoxIssue]:
    """Validates that lsel property is present for items with a1lx properties."""
    item_id = item["item_id"]
    is_multilayer = False
    has_lsel = False
    for prop, _ in item["item_properties"]:
        if prop.type in ["a1lx", "a1op"]:
            is_multilayer = True
        elif prop.type == "lsel":
            has_lsel = True

    if is_multilayer == has_lsel or not is_multilayer:
        return []

    issue = BoxIssue(item_id, "lsel")
    severity = "CRITICAL"
    issue.add_issue(
        severity,
        "'a1lx' or 'a1op' property present, but 'lsel' not present. "
        + "'lsel' is required for multilayer content.",
    )

    def _fix_lsel() -> None:
        body: BoxBody = {"serialized": write_integer_of_size(0xFFFF, 2)}
        parsed_file.add_property_for_item(BoxType("lsel"), {}, body, item_id, True)

    issue.add_fix(_fix_lsel, "Add 0xFFFF 'lsel' property.")
    return [issue]


def validate_ispe_property(parsed_file: ParsedFile, item: dict[str, Any]) -> list[BoxIssue]:
    """Validates that ispe property is present and comes before any transformational properties."""
    generated_ispe = item["av01_stream"].generate_ispe_from_sequence_header()
    assert generated_ispe, "Could not generate ispe from av01"
    item_id = item["item_id"]
    ispe_index = None
    first_transform_index = None
    for index, (prop, _) in enumerate(item["item_properties"]):
        if prop.type in ["clap", "imir", "irot"] and first_transform_index is None:
            first_transform_index = index
        elif prop.type == "ispe":
            ispe_index = index

    issues = []
    if ispe_index is None:
        issue = BoxIssue(item_id, "ispe")
        severity = "CRITICAL"
        issue.add_issue(severity, "Image item lacks 'ispe' property.")

        def _fix_add_ispe() -> None:
            assert generated_ispe
            parsed_file.add_property_for_item(
                BoxType("ispe"),
                {"version": 0, "flags": 0},
                generated_ispe,
                item_id,
                True,
                position=0,
            )

        issue.add_info_url("missing-ispe")
        issue.add_fix(
            _fix_add_ispe,
            "Add 'ispe' with dimensions "
            + f"{generated_ispe['width']}x{generated_ispe['height']}.",
        )
        issues.append(issue)
    elif first_transform_index and ispe_index > first_transform_index:
        issue = BoxIssue(item_id, "ispe")
        severity = "WARNING"
        issue.add_issue(severity, "'ispe' property comes after transformational properties.")

        def _fix_ispe_order() -> None:
            ispe_box = item["item_properties"][ispe_index][0]
            ipco_index = parsed_file.get_existing_property_if_present(
                BoxType("ispe"), ispe_box.header, ispe_box.body
            )
            parsed_file.remove_property_associations(item_id, BoxType("ispe"))
            parsed_file.add_property_association(item_id, ipco_index, True, position=0)

        issue.add_info_url("ispe-comes-after-transformational-properties")
        issue.add_fix(
            _fix_ispe_order, "Change order of property associations to place 'ispe' first."
        )
        issues.append(issue)
    return issues


def validate_clap_property(parsed_file: ParsedFile, item: dict[str, Any]) -> list[BoxIssue]:
    """Validates that clap property is contained within the image spatial extents."""
    item_id = item["item_id"]
    ispe_box = None
    clap_box = None
    incorrect_order = False
    for index, (prop, _) in enumerate(item["item_properties"]):
        if prop.type in ["imir", "irot"] and clap_box is None:
            incorrect_order = True
        elif prop.type == "ispe":
            ispe_box = prop
        elif prop.type == "clap":
            clap_box = prop

    if clap_box is None:
        return []
    if ispe_box is None:
        print("WARNING: Found 'clap' box but no 'ispe'. First fix file by adding 'ispe'.")
        return []
    if incorrect_order:
        print(
            "WARNING: 'clap' property comes after 'imir'/'irot'. "
            + "Validating 'clap' for files like this is unsupported."
        )
        return []

    def _origin_from_clap(image_dim: float, clap_dim: float, clap_offs: float) -> float:
        return clap_offs + (image_dim - clap_dim) / 2

    def _offset_from_crop(image_dim: float, clap_dim: float, origin: float) -> float:
        return origin + (clap_dim - image_dim) / 2

    ispe_dimensions = [ispe_box.body["width"], ispe_box.body["height"]]
    offset = [
        float_from_rational(clap_box.body["h_offset"]),
        float_from_rational(clap_box.body["v_offset"]),
    ]
    dimensions = [
        float_from_rational(clap_box.body["width"]),
        float_from_rational(clap_box.body["height"]),
    ]
    origin = [
        _origin_from_clap(ispe_dimensions[index], dimensions[index], offset[index])
        for index in range(2)
    ]
    trunc_origin = [int(val) for val in origin]

    issues = []
    if any(val < 0 for val in trunc_origin):
        issue = BoxIssue(item_id, "clap")
        issue.add_issue("CRITICAL", f"'clap' origin is negative. {origin[0]}x{origin[1]}")
        issues.append(issue)
    elif any(abs(val1 - val2) > 0.0001 for val1, val2 in zip(origin, trunc_origin)):
        issue = BoxIssue(item_id, "clap")
        severity = "CRITICAL"
        if all(origin[index] + dimensions[index] <= ispe_dimensions[index] for index in range(2)):
            severity = "WARNING"
        issue.add_issue(severity, f"'clap' origin is not integer valued. {origin[0]}x{origin[1]}")
        fixed_offset = [
            _offset_from_crop(ispe_dimensions[index], dimensions[index], trunc_origin[index])
            for index in range(2)
        ]

        def _fix_clap_origin() -> None:
            assert clap_box
            fixed_clap = clap_box.body.copy()
            fixed_clap["h_offset"] = [round(fixed_offset[0] * 2), 2]
            fixed_clap["v_offset"] = [round(fixed_offset[1] * 2), 2]
            parsed_file.replace_property_for_item(BoxType("clap"), {}, fixed_clap, item_id)

        issue.add_fix(
            _fix_clap_origin, f"Truncate 'clap' origin to {trunc_origin[0]}x{trunc_origin[1]}"
        )
        issues.append(issue)

    if any(trunc_origin[index] + dimensions[index] > ispe_dimensions[index] for index in range(2)):
        issue = BoxIssue(item_id, "clap")
        severity = "CRITICAL"
        issue.add_issue(severity, "'clap' property is out of bounds.")
        issues.append(issue)
    return issues


def validate_grid_item(
    parsed_file: ParsedFile, item: dict[str, Any], default_nclx: dict[str, list[int]]
) -> list[BoxIssue]:
    """Validates that a grid item is correct."""
    item_id = item["item_id"]
    iref_box = parsed_file.get_box_from_hierarchy(["meta", "iref"])
    if iref_box is None or iref_box.sub_boxes is None:
        return []
    tile_items = None
    for ref in iref_box.sub_boxes:
        if ref.type == "dimg" and ref.body["from_item_ID"] == item_id:
            tile_items = ref.body["to_item_ID"]
            break
    assert tile_items is not None, "Could not find tile references for grid item"

    items = parsed_file.get_items()
    first_av1c = items[tile_items[0]]["av01_stream"].generate_av1c_from_sequence_header()
    for tile_item_id in tile_items[1:]:
        other_av1c = items[tile_item_id]["av01_stream"].generate_av1c_from_sequence_header()
        assert first_av1c == other_av1c, "Not all tiles in a grid have the same av1C"

    issues = []
    generated_nclx = items[tile_items[0]]["av01_stream"].generate_nclx_from_sequence_header()
    generated_pixi = items[tile_items[0]]["av01_stream"].generate_pixi_from_sequence_header()
    issues += validate_colr_property(parsed_file, item, default_nclx, generated_nclx)
    issues += validate_pixi_property(parsed_file, item, generated_pixi)
    return issues


def validate_av01_item(
    parsed_file: ParsedFile, item: dict[str, Any], default_nclx: dict[str, list[int]]
) -> list[BoxIssue]:
    """Validates that an av01 item is correct."""
    issues = []
    issues += validate_av1c_property(parsed_file, item)
    issues += validate_colr_property(parsed_file, item, default_nclx)
    issues += validate_pixi_property(parsed_file, item)
    issues += validate_lsel_property(parsed_file, item)
    issues += validate_ispe_property(parsed_file, item)
    issues += validate_clap_property(parsed_file, item)
    return issues


def validate_primary_item(parsed_file: ParsedFile) -> list[BoxIssue]:
    """Validates that 'meta' box contains a primary item."""
    issues: list[BoxIssue] = []

    meta_box = parsed_file.get_box_from_hierarchy(["meta"])
    pitm_box = parsed_file.get_box_from_hierarchy(["meta", "pitm"])

    if pitm_box is None and meta_box is not None:
        # Get item ID of first non-hidden item
        item_id = None
        for cur_id, item in parsed_file.get_items().items():
            if item["infe"].header["flags"] == 0:
                item_id = cur_id
                break
        assert item_id is not None, "Could not find any non-hidden item"
        issue = BoxIssue(item_id, "pitm")
        issue.add_issue("CRITICAL", "No primary item found.")

        def _fix_pitm() -> None:
            assert meta_box
            assert item_id is not None
            pitm_box = Box(BoxType("pitm"), parent=meta_box, size=0, start=0)
            version = 0 if item_id <= 0xFFFF else 1
            pitm_box.header = {"version": version, "flags": 0}
            pitm_box.body = {"item_id": item_id}
            if meta_box.sub_boxes is not None:
                meta_box.sub_boxes.append(pitm_box)
            else:
                meta_box.sub_boxes = [pitm_box]
            pitm_box.mark_for_rewrite()

        issue.add_fix(_fix_pitm, "Add primary item to first non-hidden item in file")
        issues.append(issue)
    return issues


def validate_regular_track(parsed_file: ParsedFile, track: Box) -> list[BoxIssue]:
    """Validates that a non-auxiliary track is correct."""
    issues: list[BoxIssue] = []
    if track.sub_boxes is None:
        return issues
    tkhd_box = parsed_file.get_box_from_hierarchy(["tkhd"], track.sub_boxes)
    hdlr_box = parsed_file.get_box_from_hierarchy(["mdia", "hdlr"], track.sub_boxes)
    if tkhd_box is None or hdlr_box is None:
        return issues
    track_id = tkhd_box.body["track_id"]

    # TODO: Add checks for 'vide' tracks
    if hdlr_box.body["hdlr_type"] != "pict":
        return issues

    if tkhd_box.header["flags"] & 0x2 == 0:
        issue = BoxIssue(track_id, "tkhd", is_track=True)
        issue.add_issue(
            "WARNING",
            "'pict' track has track_in_movie flag set to false. "
            + "Some parsers may ignore this track.",
        )

        def _fix_tkhd() -> None:
            assert tkhd_box
            tkhd_box.header["flags"] |= 0x2
            tkhd_box.mark_for_rewrite()

        issue.add_info_url("incorrect-value-for-track_in_movie-flag")
        issue.add_fix(_fix_tkhd, "Set track_in_movie flag to true.")
        issues.append(issue)

    av01_box = parsed_file.get_box_from_hierarchy(
        ["mdia", "minf", "stbl", "stsd", "av01"], track.sub_boxes
    )
    if av01_box is not None:
        ccst_box = parsed_file.get_box_from_hierarchy(["ccst"], av01_box.sub_boxes)
        if ccst_box is None:
            issue = BoxIssue(track_id, "av01", is_track=True)
            issue.add_issue("WARNING", "'ccst' not present in sample entry.")

            def _fix_ccst() -> None:
                assert av01_box and av01_box.sub_boxes
                ccst_box = Box(BoxType("ccst"), av01_box, 0, 0)
                ccst_box.header = {"version": 0, "flags": 0}
                # TODO: Populate this with less permissive values from the stss
                ccst_box.body = {
                    "all_ref_pics_intra": 0,
                    "intra_pred_used": 1,
                    "max_ref_per_pic": 15,
                }
                av01_box.sub_boxes.append(ccst_box)
                ccst_box.mark_for_rewrite()

            issue.add_info_url("ccst-not-present-for-pict-track")
            issue.add_fix(_fix_ccst, "Add most permissive 'ccst' box")
            issues.append(issue)

    return issues


def validate_aux_track(parsed_file: ParsedFile, track: Box) -> list[BoxIssue]:
    """Validates that an auxiliary track is correct."""
    issues: list[BoxIssue] = []
    if track.sub_boxes is None:
        return issues
    tkhd_box = parsed_file.get_box_from_hierarchy(["tkhd"], track.sub_boxes)
    hdlr_box = parsed_file.get_box_from_hierarchy(["mdia", "hdlr"], track.sub_boxes)
    if tkhd_box is None or hdlr_box is None:
        return issues
    track_id = tkhd_box.body["track_id"]

    hdlr_type = hdlr_box.body["hdlr_type"]
    if hdlr_type != "auxv":
        issue = BoxIssue(track_id, "hdlr", is_track=True)
        issue.add_issue(
            "CRITICAL", "Handler type for auxiliary track is " + f"'{hdlr_type}', not 'auxv'"
        )

        def _fix_hdlr() -> None:
            assert hdlr_box
            hdlr_box.body["hdlr_type"] = "auxv"
            hdlr_box.mark_for_rewrite()

        issue.add_info_url("incorrect-track-handler-type-for-auxiliary-track")
        issue.add_fix(_fix_hdlr, "Change handler type to auxv")
        issues.append(issue)

    av01_box = parsed_file.get_box_from_hierarchy(
        ["mdia", "minf", "stbl", "stsd", "av01"], track.sub_boxes
    )
    if av01_box is not None:
        auxi_box = parsed_file.get_box_from_hierarchy(["auxi"], av01_box.sub_boxes)
        if auxi_box is None:
            issue = BoxIssue(track_id, "av01", is_track=True)
            issue.add_issue(
                "WARNING",
                "'auxi' not present in sample entry. Most readers will assume track is alpha.",
            )

            def _fix_auxi() -> None:
                assert av01_box and av01_box.sub_boxes
                auxi_box = Box(BoxType("auxi"), av01_box, 0, 0)
                auxi_box.header = {"version": 0, "flags": 0}
                auxi_box.body = {"aux_track_type": "urn:mpeg:mpegB:cicp:systems:auxiliary:alpha"}
                av01_box.sub_boxes.append(auxi_box)
                auxi_box.mark_for_rewrite()

            issue.add_info_url("auxi-not-present-for-auxv-track")
            issue.add_fix(_fix_auxi, "Add alpha 'auxi' box")
            issues.append(issue)

    if tkhd_box.header["flags"] & 0x2:
        issue = BoxIssue(track_id, "tkhd", is_track=True)
        issue.add_issue(
            "WARNING",
            "Auxiliary track has track_in_movie flag set to true. "
            + "Some parsers may treat this track as directly displayable.",
        )

        def _fix_tkhd() -> None:
            assert tkhd_box
            tkhd_box.header["flags"] &= ~0x2
            tkhd_box.mark_for_rewrite()

        issue.add_info_url("incorrect-value-for-track_in_movie-flag")
        issue.add_fix(_fix_tkhd, "Set track_in_movie flag to false.")
        issues.append(issue)

    return issues


def validate_track(parsed_file: ParsedFile, track: Box) -> list[BoxIssue]:
    """Validates that a track is correct."""
    issues = []
    is_aux_track = (
        parsed_file.get_box_from_hierarchy(["tref", "auxl"], box_array=track.sub_boxes) is not None
    )
    if is_aux_track:
        issues += validate_aux_track(parsed_file, track)
    else:
        issues += validate_regular_track(parsed_file, track)
    return issues


def validate_file(parsed_file: ParsedFile, default_nclx: dict[str, list[int]]) -> list[BoxIssue]:
    """Validates that an AVIF file is correct."""
    items = parsed_file.get_items()
    issues = []
    for _, item in items.items():
        item_type = item["infe"].body["item_type"]
        if item_type == "av01":
            issues += validate_av01_item(parsed_file, item, default_nclx)
        elif item_type == "grid":
            issues += validate_grid_item(parsed_file, item, default_nclx)

    issues += validate_primary_item(parsed_file)

    moov_box = parsed_file.get_box_from_hierarchy(["moov"])
    if moov_box and moov_box.sub_boxes:
        for box in moov_box.sub_boxes:
            if box.type != "trak":
                continue
            issues += validate_track(parsed_file, box)

    issues += validate_profile_brands(parsed_file)
    return issues


# ===========================================
# Entry point
# ===========================================
def query_issues(all_issues: list[BoxIssue], interactive_prompt: bool = False) -> list[BoxIssue]:
    """Prints issues and optionally queries whether any should be ignored."""
    filtered_issues = []
    if interactive_prompt:
        for issue in all_issues:
            issue.print(0)
            if input("Fix (Y/n)?: ").lower() == "n":
                print_indent(0, "Skipping fix")
            else:
                filtered_issues.append(issue)
    else:
        # Try to condense the list into single issues that apply to multiple items
        def issue_applier(
            condenser: dict[int, list[BoxIssue]], issue: BoxIssue
        ) -> dict[int, list[BoxIssue]]:
            key = issue.issue_hash()
            if key in condenser:
                condenser[key].append(issue)
            else:
                condenser[key] = [issue]
            return condenser

        condensed_issues: dict[int, list[BoxIssue]] = {}
        reduce(issue_applier, all_issues, condensed_issues)
        for issue_list in condensed_issues.values():
            issue_list[0].print(0, issue_list[1:])

        filtered_issues = all_issues

    return filtered_issues


def process(args: argparse.Namespace) -> None:
    """Process file."""
    if not args.dry_run and args.dst_file is None:
        print("'dst_file' must be specified if --dry-run is not set")
        sys.exit(1)

    if args.dry_run and args.interactive:
        print("'dry-run' and 'interactive' are mutually exclusive")
        sys.exit(1)

    if args.src_file == args.dst_file:
        print("'src_file' and 'dst_file' must be different files")
        sys.exit(1)

    default_nclx = {
        "color_primaries": [1],
        "transfer_characteristics": [13],
        "matrix_coefficients": [6, 5],
        "full_range_flag": [1],
    }
    if args.nclx_default is not None:
        default_nclx["matrix_coefficients"] = [args.nclx_default[0]]
        default_nclx["transfer_characteristics"] = [args.nclx_default[1]]
        default_nclx["matrix_coefficients"] = [args.nclx_default[2]]
        default_nclx["full_range_flag"] = [args.nclx_default[3]]

    with open(args.src_file, "rb") as file:
        parsed_file = ParsedFile(file, args.verbose)
        issues = validate_file(parsed_file, default_nclx)

        if args.verbose or args.interactive:
            issues = query_issues(issues, args.interactive)

        if args.dry_run:
            if len(issues) > 0:
                sys.exit(2)
            sys.exit(0)

        for issue in issues:
            issue.apply_fix()

        with open(args.dst_file, "wb") as output_file:
            writer = AVIFWriter(parsed_file, output_file)
            writer.write()


HELP_TEXT = """Sanitize AVIF files without recompression.

This script fixes some commonly identified container level issues in AVIF files. 
It is not exhaustive and should not be considered a replacement for the AVIF 
compliance warden available here:
https://gpac.github.io/ComplianceWarden-wasm/avif.html

It will not identify or fix issues that requires recompression.
"""

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=HELP_TEXT, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-o",
        "--dry-run",
        action="store_true",
        help="Don't rewrite file, only check for known issues. Returns "
        + "code 2 if errors are found.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Ask whether a specific issue should be fixed or not",
    )
    parser.add_argument(
        "-n",
        "--nclx-default",
        nargs=4,
        type=int,
        help="When adding missing nclx colr box, "
        + "use these values instead of the default values of 1,13,6,1",
    )
    parser.add_argument("src_file", help="The source file")
    parser.add_argument(
        "dst_file", nargs="?", help="The destination file (required unless -o is set)"
    )

    process(parser.parse_args())
