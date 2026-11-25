"""Run by the start file: prints which Python is used and stops if it is 32-bit."""
import struct
import sys

bits = struct.calcsize("P") * 8
print(f" Using Python {sys.version.split()[0]} ({bits}-bit) at {sys.executable}")
if bits != 64:
    print()
    print(" This is 32-bit Python, which PolyGuard cannot use.")
    print(' Install Python 3.13 "Windows installer (64-bit)" from python.org,')
    print(" then double-click the start file again.")
    sys.exit(2)
if sys.version_info < (3, 10):
    print(" This Python is too old. Install Python 3.13 (64-bit) from python.org.")
    sys.exit(3)
