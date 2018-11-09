# coding=utf-8
import codecs, argparse
# c richter / ricca@seas.upenn.edu

# defaults
outfile = 'resources/settings.txt'

# runtime user input
parser = argparse.ArgumentParser()
parser.add_argument("iptf", help="input file name")
parser.add_argument("-o", help="output file name")

args = parser.parse_args()
ipt = args.iptf
if args.o:
    outfile = args.o

# read report
rep = codecs.open(ipt, 'r', 'utf-8')
bins = [ln for ln in rep.readlines() if "BIN" in ln]
rep.close()

# write settings
outf = codecs.open(outfile,'w', 'utf-8')
for b in bins:
    binID = b.split()[1]
    action = b.split()[-1]
    outf.write(binID + u'\t' + action + u'\n')
outf.close()
