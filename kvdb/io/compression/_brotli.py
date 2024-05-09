from __future__ import annotations

"""
Brotli Compression
"""

from .base import BaseCompression, logger
from typing import Optional

try:
    import brotli
    _brotli_available = True
except ImportError:
    _brotli_available = False


class BrotliCompression(BaseCompression):
    name: str = "brotli"
    compression_level: Optional[int] = 9
    lgwin: Optional[int] = 22 
    lgblock: Optional[int] = 0

    """
    Brotli Compression

    - `compression_level`: Controls the compression-speed vs compression-density tradeoff. The higher the quality, the slower the compression. Range is 0 to 11. Defaults to 9.
    - `lgwin`: Base 2 logarithm of the sliding window size. Range is 10 to 24. Defaults to 22.
    - `lgblock (int, optional): Base 2 logarithm of the maximum input block size.
        Range is 16 to 24. If set to 0, the value will be set based on the
        quality. Defaults to 0.
    """

    def validate_compression_level(self):
        """
        Validates the compression level
        """
        assert self.compression_level in range(12), "Compression level must be between 0 and 11"
        assert self.lgwin in range(10, 25), "lgwin must be between 10 and 24"
        assert self.lgblock in range(16, 25), "lgblock must be between 16 and 24"


    def check_deps(self):
        """
        Checks for dependencies
        """
        if _brotli_available is False:
            logger.error("brotli is not available. Please install `brotli` to use brotli compression")
            raise ImportError("brotli is not available. Please install `brotli` to use brotli compression")

    def compress(self, data: bytes, level: Optional[int] = None, **kwargs) -> bytes:
        """
        Compresses the data
        """
        if level is None: level = self.compression_level
        return brotli.compress(data, quality = level, lgwin = self.lgwin, lgblock = self.lgblock)

    def decompress(self, data: bytes, **kwargs) -> bytes:
        """
        Decompresses the data
        """
        return brotli.decompress(data)
    
    

