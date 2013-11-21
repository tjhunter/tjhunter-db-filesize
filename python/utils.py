__author__ = 'tjhunter'
import locale

# Taken from the file:
# http://homepages.inf.ed.ac.uk/imurray2/code/hacks/urlsize
def pretty_print_size(num_bytes):
    """
    Output number of bytes according to locale and with IEC binary prefixes
    """
    if num_bytes is None:
        print('File size unavailable.')
        return
    KiB = 1024
    MiB = KiB * KiB
    GiB = KiB * MiB
    TiB = KiB * GiB
    PiB = KiB * TiB
    EiB = KiB * PiB
    ZiB = KiB * EiB
    YiB = KiB * ZiB
    locale.setlocale(locale.LC_ALL, '')
    output = ''
    if num_bytes > YiB:
        output += '%.3g YiB' % (num_bytes / YiB)
    elif num_bytes > ZiB:
        output += '%.3g ZiB' % (num_bytes / ZiB)
    elif num_bytes > EiB:
        output += '%.3g EiB' % (num_bytes / EiB)
    elif num_bytes > PiB:
        output += '%.3g PiB' % (num_bytes / PiB)
    elif num_bytes > TiB:
        output += '%.3g TiB' % (num_bytes / TiB)
    elif num_bytes > GiB:
        output += '%.3g GiB' % (num_bytes / GiB)
    elif num_bytes > MiB:
        output += '%.3g MiB' % (num_bytes / MiB)
    elif num_bytes > KiB:
        output += '%.3g KiB' % (num_bytes / KiB)
    elif num_bytes > 0:
        output += '%.3g bytes' % (num_bytes)
    else:
        output += 'empty'
    return (output)