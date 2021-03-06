#! /usr/bin/python

#Analyze read depth in comparison to transcription start

#V2: replace mean slope by regression line fitting
import sys
import argparse
from subprocess import call
import numpy
import scipy
import scipy.stats
import os.path
import multiprocessing


# Calculate mean and confidence intervals ###################################################################################
def mean_confidence_interval(data, confidence=0.95):
    a = 1.0*numpy.array(data)
    n = len(a)
    m, se = numpy.mean(a), scipy.stats.sem(a)
    h = se * scipy.stats.t.ppf((1+confidence)/2., n-1)
    return m, m-h, m+h

# sliding window smoothing ###################################################################################
def sliding_window(data, window_size = 400):
    data_smoothed = list()
    for i in range(0,len(data)-window_size):
        data_smoothed.append(numpy.mean(numpy.array(data[i:i+window_size])))
    return data_smoothed

# sliding window smoothing ###################################################################################
#def mean_slope(data):
#    cum_slope = 0
#    for i in range(1,len(data)):
#        cum_slope += data[i]-data[i-1]
#    return float(cum_slope) / float(len(data))

# Run this for each thread ###################################################################################
def thread_proc(q,thread_number,transcript_list):
    sys.stderr.write("Thread "+str(thread_number)+" started\n")
    sys.stderr.flush()
    slope_5_dict=dict()
    slope_3_dict=dict()

    #create a list of visited TSS not to count some more than once
    tss_visited = list()

    line_count = 0
    skipped = 0

    #iterate through transcript list from UCSC genome browser
    for transcript in transcript_list:
        coverage_list=dict()
        gene_name = transcript.split("\t")[4].rstrip()
        for i in range(-args.start,0):
            coverage_list[i] = 0
        for i in range(0,args.end+1):
            coverage_list[i] = 0
        line_count += 1
        if (line_count  % 100 == 0):
            sys.stderr.write("\rThread "+str(thread_number)+"\t"+str(line_count)+" genes analyzed")
            sys.stderr.flush()
        #transcription starts are marked at txEnd Field of RefGene Txt file for reverse transcribed genes
        if transcript.split()[1] == '+':
            forward = True
            chrom = transcript.split()[0]
            pos = int(transcript.split()[2])
        else:
            forward = False
            chrom = transcript.split()[0]
            pos = int(transcript.split()[3])
        if chrom+"_"+str(pos) in tss_visited:
            continue
        tss_visited.append(chrom+"_"+str(pos))

        TMP_COVERAGE_BED = open(args.temp_dir+os.path.basename(args.bam_file)+str(thread_number)+"tmp_coverage.bed","w")
        call(["samtools","depth","-r",chrom+":"+str(pos-args.start)+"-"+str(pos+args.end),args.bam_file],stdout=TMP_COVERAGE_BED)
        TMP_COVERAGE_BED.close()
    
        TMP_COVERAGE_BED_OUTPUT = open(args.temp_dir+os.path.basename(args.bam_file)+str(thread_number)+"tmp_coverage.bed","r")
        content = TMP_COVERAGE_BED_OUTPUT.readlines()
        for i in range(pos-args.start,pos+args.start):
            found = False
            for line in content:
                chrom_found = line.split()[0]
                pos_found = int(line.split()[1])
                if pos_found == i:
                    found = True
                    coverage = int(line.split()[2])
                    if forward:
                        coverage_list[i-pos] = coverage
                    elif not forward:
                        coverage_list[-(i-pos)] = coverage
                    continue
            if not found:
                if forward:
                    coverage_list[i-pos] = 0
                elif not forward:      
                    coverage_list[-(i-pos)] = 0
        TMP_COVERAGE_BED_OUTPUT.close()
        call(["rm",args.temp_dir+os.path.basename(args.bam_file)+str(thread_number)+"tmp_coverage.bed"])    
        list_values_in_order = list()
        for i in range(-args.start,0):
            list_values_in_order.append(coverage_list[i])
        for i in range(0,args.end+1):
            list_values_in_order.append(coverage_list[i])
        smoothed_data = sliding_window(list_values_in_order)   
   
        #fit a regression line instaed of calculating mean slopes
        slope_5_dict[gene_name] = numpy.polyfit(range(0,len(smoothed_data))[:int(0.5*len(smoothed_data))],smoothed_data[:int(0.5*len(smoothed_data))],1)[0]
        slope_3_dict[gene_name] = numpy.polyfit(range(0,len(smoothed_data))[int(0.5*len(smoothed_data)):],smoothed_data[int(0.5*len(smoothed_data)):],1)[0]
    
    sys.stderr.write("\rThread "+str(thread_number)+"\t finished\n")
    sys.stderr.flush() 
    q.put([slope_5_dict,slope_3_dict])
#######################################################################################################

# Parse command line arguments ###################################################################################
parser = argparse.ArgumentParser(description='Analyze read depth in comparison to transcription start')
parser.add_argument('-rg','--ref-gene', dest='refgene_file', 
                   help='RefGene file, transcription start should be stored in column 1-3',required=True)
parser.add_argument('-b','--bam', dest='bam_file',
                   help='BAM file',required=True)
parser.add_argument('-s','--start', dest='start',
                   help='Start analyzing coverage at this point before TSS [default:1000]',default=1000,type=int)
parser.add_argument('-e','--end', dest='end',
                   help='Stop analyzing coverage at this point after TSS [default:1000]',default=1000,type=int)
parser.add_argument('-t','--threads', dest='threads',
                   help='Threads to use for computation [default:1]',default=1,type=int)
parser.add_argument('-gl','--gene-list', dest='gene_list',
                   help='List of gene names',required=True)
parser.add_argument('-tmp','--temp-dir', dest='temp_dir',
                   help='Temporary Directory',default="./intermediate/")


args = parser.parse_args()
if args.temp_dir[-1:] != "/":
    args.temp_dir = args.temp_dir+"/"
sys.stderr.write("Bam file: "+args.bam_file+"\n")
sys.stderr.write("RefGene file: "+args.refgene_file+"\n")
sys.stderr.write("Genes: "+str(args.gene_list)+"\n")
sys.stderr.write("Threads: "+str(args.threads)+"\n")

###############################################################################################
# Analyze data ###################################################################################

try:
    REFGENE = open(args.refgene_file,"r")
except:
    print "Fail to open files specified"
    sys.exit(1)
target_genes = list()
try:
    GENELIST_H = open(args.gene_list,"r")
    for item in GENELIST_H.readlines():
        target_genes.append(item.rstrip())
    GENELIST_H.close()
except:
    print "Failed to open genelist"
    sys.exit(1)
    
#filter genes from genelist if specified
header = REFGENE.readline()
refgene_content = REFGENE.readlines()
target_genes_count = 0
target_content = list()
for i in refgene_content:
    chrom = i.split()[0]
    if chrom.find("_") != -1:
        continue
    if chrom.find("X") != -1:
        continue
    if chrom.find("Y") != -1:
        continue
    if i.split()[4].rstrip() in target_genes:
        target_content.append(i)

#initialize input data
gene_count = 0
sys.stderr.write("\n")
sys.stderr.flush()
thread_input_list = dict()
thread_coverage_list = dict()

for thread_number in range(0,args.threads):
    thread_input_list[thread_number] = list()
    thread_coverage_list[thread_number] = dict()

#dispatch input data
max_gene = len(target_content)
partition_point = max_gene/ args.threads
for thread_number in range(0,args.threads):
    thread_input_list[thread_number] = target_content[(thread_number*partition_point):(thread_number+1)*partition_point]

sys.stderr.write(str(len(thread_input_list[0]))+" genes per thread\n")
sys.stderr.write("--------------------------------------------------\n")
sys.stderr.flush()

#start multiple processes
processes = dict()
queues = dict()
for thread in range(0,args.threads):
    queues[thread] = multiprocessing.Queue()
    processes[thread] = multiprocessing.Process(target=thread_proc,args=(queues[thread],thread,thread_input_list[thread]))
    processes[thread].start()

#wait for processes to finish
for thread in range(0,args.threads):
    thread_coverage_list[thread] = queues[thread].get()
    processes[thread].join()

#collect all data
slope5_all=dict()
slope3_all=dict()
for thread in range(0,args.threads):
    for i in  thread_coverage_list[thread][0].keys():
        slope5_all[i] = thread_coverage_list[thread][0][i]
        slope3_all[i] = thread_coverage_list[thread][1][i]

print "Gene\t5'Slope\t3'Slope"
for gene in slope5_all.keys():
    if gene not in slope3_all.keys():
        continue
    if gene in target_genes:
        print gene+"\t"+str(slope5_all[gene])+"\t"+str(slope3_all[gene])



 
