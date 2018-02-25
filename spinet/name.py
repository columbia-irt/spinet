import hashlib
import random
import proquint


# Generate a new Proquint-based name from the given seed. The seed can be
# either a byte array or a string. The seed is first hashed with SHA256, the
# hash output is then truncated to a 32-bit integer and fed to Proquint. If no
# seed is provided by the caller, the function generates a random 32-bit
# number as seed.
#
def generate_name(seed=None):
    if seed is not None:
        if isinstance(seed, str):
            seed = seed.encode()
        seed = int.from_bytes(hashlib.sha256(seed).digest()[:4], byteorder='big')
    else:
        seed = random.getrandbits(32)
    return proquint.uint2quint(seed)
