import os

"""
使用方法：
1. 将bulib.py所在路径添加到python模式搜索路径

2. 脚本中使用
#载入库文件
from bulib import all_lib
#根据物种名读取库数据
genome_lib = all_lib["orgnism_name"]
#访问相关数据
genome_lib["genome"] #访问基因组序列
genome_lib["hisat2"] #访问hisat2索引

#另一种使用方式（不推荐）
import bulib
genome_lib = getattr(bulib, orgnism_name)

3. 支持的物种名
运行python bulib.py 查看

4. 部分包含的库的意义
genome #基因组序列
genome_fasta_index #基因组序列
gtf #基因注释gtf文件
hisat2 #hisat2索引
star #star索引
"""
all_lib = {}

GENOME_PATH =  "/home/bio/genome/"
    
ath_tail10 = {"star": GENOME_PATH + "/ath/build_lib/star",
             "hisat2": GENOME_PATH + "/ath/build_lib/hisat2/ath",
             "genome": GENOME_PATH + "/ath/genome.fasta",
             "genome_fasta_index": GENOME_PATH + "/ath/genome.fasta.fai",
             "gtf": GENOME_PATH + "/ath/tail10_gene.gtf"
            }
            
ath_Araport11 = ath_tail10.copy()
ath_Araport11["gtf"] = GENOME_PATH + "/ath/Araport11_gene.gtf"
                  
ath = ath_Araport11

all_lib = {}
all_lib["ath"] = ath

def print_all_lib():
    for lib_name, lib in all_lib.items():
        print("#####################   " + lib_name + "    ############################")
        for key, value in lib.items():
            print(key + "\t" + value)
        print("########################################################################\n")
        
if __name__ == '__main__':
    print_all_lib()