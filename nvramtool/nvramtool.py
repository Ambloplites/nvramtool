import argparse

from .nvram import build_nvram, dump_nvram
from .nvram2 import Nvram2Dumper, Nvram2Builder

def op_nvram2(args):
    if args.op == "build":
        op = Nvram2Builder
    else:
        op = Nvram2Dumper
    op(args.src, args.dst).operate()

def main():
    parser = argparse.ArgumentParser()

    fs_parser = parser.add_subparsers(required=True, dest="fs")

    nvram_parser = fs_parser.add_parser("nvram")
    action_parser = nvram_parser.add_subparsers(required=True, dest="action")
    build_parser = action_parser.add_parser("build")
    build_parser.add_argument("src", help="source directory")
    build_parser.add_argument("dst", help="destination directory")
    build_parser.add_argument("-b", "--block-size", required=True, type=int, help="block size")
    build_parser.add_argument("-n", "--nodes", required=True, type=int, help="number of inodes")
    build_parser.add_argument("-m", "--mirrors", required=True, type=int, help="number of mirrors")
    build_parser.set_defaults(func=build_nvram)
    dump_parser = action_parser.add_parser("dump")
    dump_parser.add_argument("src", help="source directory")
    dump_parser.add_argument("dst", help="destination directory")
    dump_parser.add_argument("--save-superblock", action="store_true", help="save the decrypted superblock")
    dump_parser.set_defaults(func=dump_nvram)

    nvram2_parser = fs_parser.add_parser("nvram2")
    nvram2_parser.set_defaults(func=op_nvram2)
    nvram2_parser.add_argument("op", help="the operation to perform", choices=["build", "dump"])
    nvram2_parser.add_argument("src", help="source directory")
    nvram2_parser.add_argument("dst", help="destination directory")

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
