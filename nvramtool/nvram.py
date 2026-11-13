from dataclasses import dataclass
import struct, os

from typing import List
from Crypto.Hash import MD5
from Crypto.Cipher import ARC4

SUPERBLOCK_FILENAME = "info.bin"

SUPERBLOCK_HEADER_MAGIC = 0xDA38C05A
SUPERBLOCK_FOOTER_MAGIC = 0xD97E462E

FILENAME_SIZE = 16

MIRROR_COUNT = 5
NVRAM_KEY = bytearray(16)

SUPERBLOCK_HEADER_FMT = "<IIII24s"
SUPERBLOCK_FOOTER_FMT = "<24sI"
INODE_METADATA_FMT = "<QQQQ16s16s"
INODE_MIRROR_METADATA_FMT = "<QQQ"
INODE_FMT = "<QQQ QQQ QQQ QQQ QQQ QQQQ16s16s"

SUPERBLOCK_HEADER_SIZE = struct.calcsize(SUPERBLOCK_HEADER_FMT)
INODE_MIRROR_SIZE = struct.calcsize(INODE_MIRROR_METADATA_FMT)
INODE_TOTAL_SIZE = struct.calcsize(INODE_FMT)

@dataclass
class MirrorMetadata:
    create_time: int
    access_time: int
    size_on_disk: int

@dataclass
class INode:
    mirrors: List[MirrorMetadata]
    create_time: int
    access_time: int
    modify_time: int
    size: int
    checksum: bytes
    filename: str

class SuperblockBuilder:
    def __init__(self, block_size, number_of_inodes, number_of_mirrors):
        self.__block_size = block_size
        self.__number_of_inodes = number_of_inodes
        self.__number_of_mirrors = number_of_mirrors
        self.__inodes = []

    def append_inode(self, inode):
        if len(self.__inodes) >= self.__number_of_inodes:
            raise ValueError("Too many inodes")
        if len(inode.filename) >= FILENAME_SIZE:
            raise ValueError("Filename '{}' is too long".format(inode.filename))

        self.__inodes.append(inode)

    def save(self):
        header = struct.pack(SUPERBLOCK_HEADER_FMT, SUPERBLOCK_HEADER_MAGIC,
                                                    self.__block_size,
                                                    self.__number_of_mirrors,
                                                    self.__number_of_inodes,
                                                    b":^)")
        footer = struct.pack(SUPERBLOCK_FOOTER_FMT, b":^)", SUPERBLOCK_FOOTER_MAGIC)

        inodes = bytearray()
        for inode in self.__inodes:
            mirrors = bytearray()
            for mirror in inode.mirrors:
                mirrors += struct.pack(INODE_MIRROR_METADATA_FMT, mirror.create_time,
                                                                  mirror.access_time,
                                                                  mirror.size_on_disk)
            if self.__number_of_mirrors < MIRROR_COUNT:
                mirrors += bytearray(INODE_MIRROR_SIZE * (MIRROR_COUNT - self.__number_of_mirrors))

            inodes += mirrors + struct.pack(INODE_METADATA_FMT, inode.create_time, inode.access_time, inode.modify_time,
                                                                inode.size, inode.checksum, inode.filename.encode("ASCII"))

        superblock = header + inodes.ljust(self.__number_of_inodes * INODE_TOTAL_SIZE, b"\0") + footer
        checksum = MD5.new(superblock).digest()

        return superblock + checksum

class Superblock:
    def __init__(self, data):
        (magic, self.__block_size, self.__number_of_mirrors, self.__number_of_inodes, _,) = struct.unpack(SUPERBLOCK_HEADER_FMT, data[:SUPERBLOCK_HEADER_SIZE])

        if magic != SUPERBLOCK_HEADER_MAGIC:
            raise ValueError("Invalid magic number in superblock header")
        if self.__number_of_mirrors > MIRROR_COUNT or self.__number_of_mirrors < 1:
            raise ValueError("Invalid number of mirrors")

        self.__data = data

    @property
    def block_size(self):
        return self.__block_size

    @property
    def number_of_mirrors(self):
        return self.__number_of_mirrors

    @property
    def number_of_inodes(self):
        return self.__number_of_inodes

    def iter_inodes(self):
        for i in range(self.__number_of_inodes):
            i = SUPERBLOCK_HEADER_SIZE + i * INODE_TOTAL_SIZE
            fields = struct.unpack(INODE_FMT, self.__data[i:i + INODE_TOTAL_SIZE])

            mirrors = []
            for mirror in range(MIRROR_COUNT):
                i = mirror * 3
                create_time = fields[i]
                access_time = fields[i + 1]
                size_on_disk = fields[i + 2]

                mirrors.append(MirrorMetadata(create_time, access_time, size_on_disk))

            create_time = fields[15]
            access_time = fields[16]
            modify_time = fields[17]
            source_size = fields[18]
            checksum = fields[19]
            filename = fields[20].decode("ASCII").strip("\0")
            yield INode(mirrors, create_time, access_time, modify_time, source_size, checksum, filename)

def print_fs_params(block_size, number_of_mirrors, number_of_inodes):
    print("BLOCK SIZE           [{}]".format(block_size))
    print("NUMBER OF MIRRORS    [{}]".format(number_of_mirrors))
    print("NUMBER OF INODES     [{}]".format(number_of_inodes))
    print()

def crypt(file, file_size, block_size):
    out = bytearray()

    while file.tell() < file_size:
        block = file.read(block_size).ljust(block_size, b"\0")
        out += ARC4.new(NVRAM_KEY).encrypt(block)

    return out

def build_nvram(args):
    src = args.src
    dst = args.dst

    block_size = args.block_size
    number_of_mirrors = args.mirrors
    number_of_inodes = args.nodes
    print_fs_params(block_size, number_of_mirrors, number_of_inodes)

    if block_size <= 0:
        raise ValueError("Invalid block size")
    if number_of_mirrors > MIRROR_COUNT or number_of_mirrors < 1:
        raise ValueError("Invalid number of mirrors")
    if number_of_inodes <= 0:
        raise ValueError("Invalid number of inodes")
    files = os.listdir(src)
    if len(files) > number_of_inodes:
        raise ValueError("Number of files is greater than the number of inodes")

    mirror_paths = [os.path.join(dst, str(i)) for i in range(number_of_mirrors)]
    for mirror_path in mirror_paths:
        os.makedirs(mirror_path, exist_ok=True)

    superblock = SuperblockBuilder(block_size, number_of_inodes, number_of_mirrors)
    for filename in files:
        print("processing {}...".format(filename))

        ipath = os.path.join(src, filename)
        if os.path.isdir(ipath):
            print("'{}' is a directory; skipping".format(ipath))
            continue

        source_size = os.path.getsize(ipath)
        with open(ipath, "rb") as f:
            out = crypt(f, source_size, block_size)
        checksum = MD5.new(out).digest()

        mirrors = []
        for mirror_path in mirror_paths:
            opath = os.path.join(mirror_path, filename)
            with open(opath, "wb") as ofile:
                ofile.write(out)
            stat = os.stat(opath)
            mirrors.append(MirrorMetadata(stat.st_ctime_ns // 1000000, stat.st_atime_ns // 1000000, stat.st_size))

        superblock.append_inode(INode(mirrors, 5, 7, 3, source_size, checksum, filename))

    with open(os.path.join(dst, SUPERBLOCK_FILENAME), "wb") as f:
        f.write(ARC4.new(NVRAM_KEY).encrypt(superblock.save()))

def dump_nvram(args):
    src = args.src
    dst = args.dst
    save_superblock = args.save_superblock

    with open(os.path.join(src, SUPERBLOCK_FILENAME), "rb") as f:
        superblock_bytes = ARC4.new(NVRAM_KEY).decrypt(f.read())

    if save_superblock:
        with open(os.path.join(dst, SUPERBLOCK_FILENAME), "wb") as f:
            f.write(superblock_bytes)

    superblock = Superblock(superblock_bytes)
    block_size = superblock.block_size
    print_fs_params(block_size, superblock.number_of_mirrors, superblock.number_of_inodes)

    for inode in superblock.iter_inodes():
        filename = inode.filename
        size = inode.size

        if filename != "":
            print("processing {}...".format(filename))

            with open(os.path.join(dst, filename), "wb") as ofile:
                for mirror in range(superblock.number_of_mirrors):
                    try:
                        with open(os.path.join(src, str(mirror), filename), "rb") as ifile:
                            ofile.write(crypt(ifile, size, block_size)[:size])
                            break
                    except FileNotFoundError as e:
                        print(e)
