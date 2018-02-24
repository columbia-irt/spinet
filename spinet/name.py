import proquint
import random

def generate_name():
    name = proquint.uint2quint(random.getrandbits(32))
    return name
