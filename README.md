# pydarc

## Summary

This software decodes Data Radio Channel (DARC) bitstream.

You can use [GNU Radio](https://github.com/gnuradio/gnuradio) and [darc_demod.grc](https://gist.github.com/soltia48/2a635cf2a5b6921559327317c710ecd8) for demodulation.

## Usage

### Decode

```
$ python decode_darc.py --help
usage: decode_darc.py [-h] input_path

DARC bitstream Decoder

positional arguments:
  input_path  Input DARC bitstream path (- to stdin)

options:
  -h, --help  show this help message and exit
```

## Authors

- soltia48 (ソルティアよんはち)

## License

[MIT](https://opensource.org/licenses/MIT)

Copyright (c) 2023 soltia48 (ソルティアよんはち)
