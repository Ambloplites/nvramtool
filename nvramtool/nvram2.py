import errno, os, struct

from Crypto.Cipher import ARC4
from Crypto.Hash import SHA1, MD5

FILENAME_SIZE = 64

MIRRORFS_MAGIC = 0x491CA4A6
MIRRORFS_HEADER_FMT = ">IIQQQQQ64s16s"
MIRRORFS_HEADER_SIZE = struct.calcsize(MIRRORFS_HEADER_FMT)

MIRROR_NAMES = ["0", "1", "2", "3"]

def generate_key(i):
    i += i // 16 * 16

    i1 = (((i + 1) ^ 0x123456789ABCDEF1) + 0x23456789ABCDEF12) & 0xFFFFFFFFFFFFFFFF
    i2 = ((~i ^ 0x3456789ABCDEF123) + 0x456789ABCDEF1234) & 0xFFFFFFFFFFFFFFFF

    hob = ((i1 & 0xFFFFFFFF00000000)) | ((i2 >> 32) & 0xFFFFFFFF)
    lob = ((i1 & 0xFFFFFFFF) << 32) | (i2 & 0xFFFFFFFF)

    return struct.pack(">QQ", hob, lob)

def crypt(data):
    result = bytearray()
    for i in range((len(data) + 31) // 32):
        cipher = ARC4.new(generate_key(i))
        start = i * 32
        result += cipher.encrypt(data[start:start + 32])

    return result

class MirrorPathProvider:
    def __init__(self, root):
        self.__root = root

    @classmethod
    def __hash_filename(cls, filename):
        digest = SHA1.new(filename.ljust(FILENAME_SIZE, "\0").encode("ASCII")).hexdigest()
        return "{}/{}".format(digest[:2], digest)

    def generate_paths(self, filename):
        return [os.path.join(self.__root, mirror, self.__hash_filename(filename)) for mirror in MIRROR_NAMES]

class MirrorFileList:
    def __init__(self):
        self.__files = []

    def load(self, buffer):
        for i in range(len(buffer) // FILENAME_SIZE):
            start = i * FILENAME_SIZE
            b = buffer[start:start + FILENAME_SIZE]
            filename = b.rstrip(b"\0").decode("ASCII")

            self.__files.append(filename)

    def iter_filenames(self):
        return [filename for filename in self.__files]

    def append_file(self, filename):
        self.__files.append(filename)

    def save(self):
        out = bytearray()
        for filename in self.__files:
            out += filename.ljust(FILENAME_SIZE, "\0").encode("ASCII")

        return out

class Nvram2Builder:
    def __init__(self, src, dst):
        self.__src = src
        self.__path = MirrorPathProvider(dst)

    def __save_mirrorfs_file(self, filename, body):
        if len(filename) >= FILENAME_SIZE:
            raise ValueError("Filename '{}' is too long".format(filename))

        data = bytearray(MIRRORFS_HEADER_SIZE)
        struct.pack_into(MIRRORFS_HEADER_FMT, data, 0, MIRRORFS_MAGIC,
                                                    0,
                                                    len(body),
                                                    0,
                                                    0,
                                                    0,
                                                    0,
                                                    filename.ljust(FILENAME_SIZE, "\0").encode("ASCII"),
                                                    b"\0" * 16)
        data += body

        checksum = MD5.new(data).digest()
        data[112:128] = checksum

        for path in self.__path.generate_paths(filename):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as file:
                file.write(data)

    def operate(self, dir = "/"):
        files = MirrorFileList()

        dir_path = os.path.join(self.__src, dir[1:])
        for filename in os.listdir(dir_path):
            nvram_path = dir + filename
            print("processing {}...".format(nvram_path))

            full_path = os.path.join(dir_path, filename)
            if os.path.isdir(full_path):
                nvram_path += "/"
                self.operate(nvram_path)
            else:
                with open(full_path, "rb") as in_file:
                    encrypted = crypt(in_file.read())
                self.__save_mirrorfs_file(nvram_path, encrypted) 

            files.append_file(nvram_path)

        self.__save_mirrorfs_file(dir, files.save())
        
class Nvram2Dumper:
    def __init__(self, src, dst):
        self.__path = MirrorPathProvider(src)
        self.__dst = dst

    def __read_mirrorfs_file(self, filename):
        for path in self.__path.generate_paths(filename):
            try:
                with open(path, "rb") as file:
                    file.seek(MIRRORFS_HEADER_SIZE, os.SEEK_SET)
                    return file.read()

            except FileNotFoundError as e:
                e.filename = filename
                e.filename2 = path
                print(e)

        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), filename)

    def operate(self, dir="/"):
        files = MirrorFileList()
        files.load(self.__read_mirrorfs_file(dir))

        for filename in files.iter_filenames():
            print("processing {}...".format(filename))

            # Thank you Subject :)
            if filename.endswith('/'):
                os.makedirs(os.path.join(self.__dst, filename.lstrip("/")), exist_ok=True)
                self.operate(filename)
                continue

            with open(os.path.join(self.__dst, filename.lstrip("/")), "wb") as out:
                try:
                    out.write(crypt(self.__read_mirrorfs_file(filename)))
                except FileNotFoundError as e:
                    print(e)
