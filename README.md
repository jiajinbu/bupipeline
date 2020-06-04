## 1. 简介

bupipeline是为了便于生信分析人员开发和管理流程的python模块。现在仍处于开发测试当中。支持qsub，使用了特定的qsub和qstat命令，支持南方科技大学hpc和生物系服务器。不同的集群管理系统可能不同，可手动更改这些命令，也可以新建一个JobExcuter类。

## 2. 入门

### 2.1 测试
```
cd your_work_directory
python bupipeline.py
```

该步将运行bupipeline模块中的test函数。由于模块中设定的每个任务执行结束会等待3秒后再检测是否有错误文件生成，因此程序运行时间会花费十几秒。我们在调试小流程时可以将这个等待时间删除（后续增加参数）。

### 2.2 示例代码

test函数内容如下:

```
class Echo(Tool):

    fileouts = "{out_dir}/{label}.txt"
    sh = "echo 'abc\nabc' > {fileouts}"
    
class Wc(Tool):

    fileins = "{in_dir}/{label}.txt"
    fileouts = "{out_dir}/{label}.wc.txt"
    sh = "wc -l {fileins} > {fileouts}"

p = Pipeline(tools=[Echo(), Wc()])
p.labels = ["a", "b"]
p.excuter_class = JobExcuter
p.dry_run_flag = False
p.limit_cores = 0
p.run()
```

可将上述代码复制到一个新的python脚本文件里，如test.py。这里需要在test.py的首行添加如下内容以导入bupipeline模块:
```
from bupipeline import Pipeline, Tool, JobExcuter, QsubExcuter
```
由于要导入bupipeline模块，因此首先需要将bupipeline.py所在目录放在python模块搜索路径内。
```
#在~/.bashrc里写入：
export PYTHONPATH=bupipeline_path:$PYTHONPATH
#运行source ~/.bashrc命令
```

### 2.3 示例介绍

#### 格式化字符串

Pipeline是用于控制整个流程的类。Tool是为了创建不同的任务的基类。这里分别定义了Echo和Wc两个Tool类。定义一个新的Tool类时，一般最重要的要写出这个类fileins, fileouts和sh属性的值。在程序运行过程中，这些值需要被类似字符串format方法处理后才会被真正使用。如`fileouts = "{out_dir}/{label}.txt"`,程序会将该对象的out_dir属性的值替换{out_dir}部分，label也一样。因此{}包住的值必须是对象的属性。一些对象属性是Tool类都具有并初始化了的，如out_dir默认是'./'。需要指出的是这里的对象的属性的值不一定是字符串。如：
```
a = Echo()
a.sh = "{config} World!"
#1. 字符串
a.config = "Hello"
#运行过程中a.sh最终变成"Hello World!"
#2. 列表/元组等可迭代对象（非字典）
a.config = ["good", "bad"]
#运行过程中a.sh最终变成"good bad World!"
#而"{config[0]} World!"将变成"good World!"
#3. 字典
a.config = ["good": 1, "bad": 2]
#与列表类似，直接用{config}将会将config的值全部展开，并用' '.join连接为字符串。也可以用{config[good]}来指定字典的键。索引可以嵌套。
#4. 函数或方法
a.value = 1
a.config = lambda self, x: x["value"] + 1
#这时会调用config这个函数，需要注意的时候，这里config如果是函数，则需只有一个参数，如x。而访问对象的属性不再用x.value，而是用x["value"]。如果config是方法，则需要有两个参数，如self, x，这是类的方法规定的第一个参数是用来接收对象自身的。
```

并不是所有的属性值都会被这样处理，仅`name`,`fileins`,`fileouts`,`file_sh`,`file_stdout`,`file_stderror`,`sh`会被这样处理（而且是按照这个顺序执行，因此`sh`里的{fileins}会被替换为fileins的真实值，而`fileins`里不应该出现{sh}，事实上，一般也不该出现。）。而且`name`，`file_sh`,`file_stdout`,`file_stderror`往往用Tool默认的值即可，它们是用于生成任务的名字，任务运行的脚本文件、标准输出文件和标准错误输出文件路径。

`fileins`和`fileouts`不一定是一个字符串，也可以是一个列表，一个字典，只要列表的元素或字典的值是一个字符串就行。这样便于写`sh`。它们本身也可以是个函数或方法（参数定义和使用方式类似上面的第4个例子a.config是一个函数和方法）。

#### labels
这里需要强调一下Tool和Pipeline的labels属性。我们看到`p = Pipeline(tools=[Echo(), Cut()])`，为了更容易理解，这句可以写成
```
echo_tool = Echo()
cut_tool = Cut()
p = Pipeline(tools=[echo_tool, cut_tool])
```
。
这时p就存储了一个Echo工具对象，一个Cut工具对象。而`p.labels = ["a", "b"]`使p的labels属性值为["a","b"]。而当运行`p.run()`时，p会首先执行update方法，这时会将p的大部分属性值传给它存储的工具对象，这样echo_tool和cut_tool的labels属性值也变成了["a", "b"]。p执行update时，也会让echo_tool和cut_tool执行update方法。这时就进行了上文中所说的格式化处理。以echo_tool为例，labels属性有两个元素，因此echo_tool就会产生两个任务，每个任务的label值分别为'a'和'b'，其他值都有echo_tool的属性值传递过去，利用这些值就可以获得`fileins`,`fileouts`和`sh`的真实值。然后echo_tool的两个任务和cut_tool的两个任务共四个任务传给p，p会根据任务的fileins和fileouts来确定任务的运行先后关系，然后依次（可以并发处理）执行这些任务。如果该任务的`file_sh`.finished文件和fileouts指定的所有输出文件都存在，且修改日期比fileins指定的输入文件的修改日期都晚，那么程序判定该任务不需要执行。程序执行时会在指定的当前目录（p.cwd，默认是当前目录）中产生sh和runon文件夹，sh存储了每个任务执行的sh脚本（也就是`file_sh`，因此也存储了.finished文件），每个任务运行完成后都会在sh文件夹下的pipeline.log文件中写入这个任务运行的信息。

因此一般在pipleine run前更改Tool对象和Pipeline对象的值。而定义一个新的Tool类相当于更改一些属性值的默认值。这时可以有几种方式更改，一个是写成类的属性值（如上文），一个是写入pre_init方法和init方法中,这两个方法在实例化对象时会依次运行，这里面可以写self.fileins=""。之所以用pre_init是便于基于某个Tool类开发新的Tool类。

#### excuter_class等
示例中我们在run之前设定了`p.excuter_class = JobExcuter`。这里设定了p运行任务时用的是哪种JobExcuter。现在模块提供了两种JobExcuter类，一个是JobExcuter，一个是QsubExcuter（其父类是JobExcuter）。我么也可以根据运行环境的不同，编写新的JobExcuter，一般只需要更改运行方法和检测任务结束的方法即可。QsubExcuter用于qsub提交任务，这里支持的是南科大服务器。

`p.dry_run_flag = False`中dry_run_flag设为True，程序并不实际执行任务。设为False才会执行任务。

`p.limit_cores = 0`设置了同时可并发执行的任务，默认是1。如果是0，则指没有限制，有可执行的任务就执行，不需要等待。

事实上，Pipeline不仅可以包含tools，也可以包含其他pipeline，提高pipeline扩展的能力。

### 3. 常见属性值

#### 3.1 Pipeline类

传给Tool的类属性值:

- excuter_class
- sh_out_dir 
- cwd
- run_on_dir
- limit_cores
- core

被动传给Tool的对象属性值:
- log  log文件的路径，默认为sh_out_dir下的pipeline.log文件
- ……

不传给Tool的属性值：

- tools
- pipelines
- job_lists
- need_trans2child
- not_trans2child_value
- not_trans_value #重要，不接收主pipeline传递的值的列表。

其他类属性值：
- sleep_time

建议在pipeline中增加的对象值（可以实例化后run前添加）（除了设定不传给Tool的那些属性外的对象属性均会传给Tool）：
- softpath 字典。存储使用的soft的路径。可以专门存储在一个文件。
- lib 字典。存储基因组数据路径。

#### 3.2 Tool类

- tool_name  #默认为类名
- labels
- job_lists
- not_trans_value #重要！指定不接收pipeline传递的值。例如主流程的core设定了每个任务运行的线程数为1，而某个任务运行线程数应为12。这里就需要把"core"添加到not_trans_value，并设置self.core=12。
- name      #默认为"tool_name__label"
- fileins   #指定输入文件
- fileouts  #指定输出文件
- core      #线程数
- file_sh   #脚本文件生成路径，默认即可
- file_stdout  #标准输出文件生成路径，默认即可
- file_stderror #标准错误输出文件路径，默认即可
- sh            #指定执行的linux代码
- in_dir        #输入目录（会被转化为绝对路径）
- out_dir       #输出目录（会被转化为绝对路径）
- excuter_class #执行的类
- cwd           #运行目录（会被转化为绝对路径）

#这些值设定也没有(程序会用到并自动产生）:
- label
- job_num

#### 3.3 JobExcuter和QsubExcuter类

Tool每个任务会将值这些值传给JobExcuter以实例化一个JobExcuter对象，Tool的job_lists里存储的就是各个任务对应的JobExcuter对象。

用于任务执行的：
- file_sh  #运行的脚本所在路径
- file_stdout
- file_stderror
- core
- cwd
- run_on_dir
- finish_file

用于任务管理的：
- fileins
- fileouts
- name

不是由Tool传递的值：

- status 任务运行状态
```
0  未运行
1  排队中
2  运行中
3  运行完成
4  运行失败
5  无需运行
Status_Flag = ["Preparing", "Queue", "Running", "Finished", "Failure", "Not_need_to_be_run"]
```

## 4. 通用pipeline

针对生信分析通常对多个样品并行分析。因此大家可以使用这种pipeline书写模板(这里面处理定义class外其他基本是通用的）：

```
import bupipeline as bp
from bupipeline import Tool, LabelsOneJob, Pipeline, bp_parser, Sample
from busoft import bp_softpath
import bulib
import toml

scr_path = os.environ["BUPIPELINEPATH"] + "/RNA/bin/"
softpath = bp_softpath
softpath.update({"preDE_script": scr_path + "preDE.py",
                "extract_rpkm_from_ballgown": scr_path + "extract_rpkm_from_ballgown.R",
                "rpkm_merge_script": scr_path + "rpkm_merge.py"})
                
config_file = sys.argv[1]
configs = toml.load(config_file)

sample_info = Sample(configs["sample_file"])
labels = sample_info.labels

class STAR(Tool):
    #star不需要设置链特异性。
    #单核跑天龙基因组STAR使用了8.5%的内存，多核会略高一些。20核大概11.6%内存。
    fileins = ["{in_dir}/{label}.R1.fq.gz", "{in_dir}/{label}.R2.fq.gz"]
    only_best_flag = ""
    fileouts = "{out_dir}/{label}.Aligned.sortedByCoord.out.bam"
    config_path = "{out_dir}/{label}."
    sh = ("{softpath[star]} --genomeDir {lib[star]} --runThreadN {core} --readFilesIn "
            " {fileins} --outFileNamePrefix {config_path} " 
            " {only_best_flag} "
            " --outSAMtype BAM SortedByCoordinate "
            " --outSAMunmapped Within "
            " --outSAMattributes Standard "
            " --readFilesCommand gunzip -c "
            " --alignIntronMin 20 "
            " --alignIntronMax {configs[hisat2_max_intronlen]} && "
            " {softpath[samtools]} index {fileouts} ")
    in_dir = ""
    out_dir = "data/star"
    core = "{configs[star_core]}"
    not_trans_value = ["core"]
    
class Header_STAR(STAR):
    fileins = sample_info.get_fileins

class STAROnlyBest(STAR):
    only_best_flag = " --outFilterMultimapScoreRange 0 "
    
class Header_STAROnlyBest(STAROnlyBest):
    fileins = sample_info.get_fileins

class StarMarkDump(Tool):
    #会输出未比对序列
    fileins = "{in_dir}/{label}.Aligned.sortedByCoord.out.bam"
    fileouts = ["{out_dir}/{label}.markdump.bam", "{out_dir}/{label}.markdump.txt"]
    sh = ("{softpath[java]} -jar {softpath[picard]} MarkDuplicates "
            "REMOVE_DUPLICATES=true "
            "SORTING_COLLECTION_SIZE_RATIO=0.01 "
            "I={fileins} O={fileouts[0]} M={fileouts[1]} && "
          "{softpath[samtools]} index {fileouts[0]}")
    in_dir = "data/star"
    out_dir = "data/markdump"

class RemoveDump_FeatureCounts_Unique_Mapped_Gene(Tool):
    fileins =  "{in_dir}/{label}.markdump.bam"
    fileouts = "{out_dir}/{label}.count.txt"
    config_path = "{lib[gtf]}" ## MUST GIVEN
    config = {"multi_mapped_flag": " ", "gtf_format": "GTF"} 
    in_dir = "data/markdump"
    sh = "{softpath[featureCounts]} -a {config_path} -F {config[gtf_format]} {config[multi_mapped_flag]} -O -p -T {core} -o {fileouts} {fileins}"
    out_dir = "data/featurecounts_ir_unique_mapped_markdump"
    core = "{configs[featureCounts_core]}"
    not_trans_value = ["core"]
    
class MergeFeatureCounts(LabelsOneJob):
    
    fileouts = "{out_dir}/all.count.txt"
    in_dir = "data/featurecounts_ir_unique_mapped_markdump"
    out_dir = "data/featurecounts_ir_unique_mapped_markdump"
    
    def pre_init(self):
        def get_fileins(config):
            samples = self.get_sample_labels(config)
            return bp.extend_format_string("{in_dir}/{sample}.count.txt", config, {"sample": samples})
            
        def get_sh(config):
            labels = config["_not_trans_labels"]
            label = ",".join(labels)
            fileins = ",".join(config["fileins"])
            
            sh = "%s %s %s %s" % (bp.format_string("{softpath[Rscript]} {softpath[merge_feature_counts]} ", config), 
                            fileins, label, bp.format_string(" {fileouts} ", config))
            return sh
        
        self.fileins = get_fileins
        self.sh = get_sh
        
def main():

    tools = bp.get_tools_from_toml(configs, globals())
    main_pipeline = Pipeline(tools=tools,
                             d={"softpath": softpath,
                                "lib": getattr(bulib, configs["orgnism_name"]),
                                "labels": labels,
                                "configs": configs})
    main_pipeline.excuter_class = {"JobExcuter":bp.JobExcuter, "QsubExcuter":bp.QsubExcuter, "BsubExcuter":bp.BsubExcuter, "QueueQsubExcuter":bp.QueueQsubExcuter}[configs["excuter"]] 
    main_pipeline.limit_cores = configs["limit_cores"]
    main_pipeline.limit_jobs = configs["limit_jobs"]
    main_pipeline.dry_run_flag = configs["dry_run_flag"]
    main_pipeline.run()

main()
```

但你需要提前进行一些设置：

### 4.1 通用配置

#### 4.1.1 bulib
bulib.py模块里的记录各物种的基因组注释信息。具体请看bulib.py文件。以添加拟南芥注释信息为例，向bulib.py里写入：

```
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
```

使用时如下:
```
orgnism_name = "ath"

import bulib

#method 1
genome_fasta = bulib.all_lib[orgnism_name]["genome"]

#method 2
genome_fasta = getattr(bulib, orgnism_name)
```

#### 4.1.2 busoft
为了让主流程不受软件版本更改以及软件路径变化的影响（尤其是将流程在新的服务器上运行，很多软件路径和以前的不一致了）。因此将软件路径单独在一个新的文件里进行定义。busoft主要内容是定义bp_softpath。

```
bp_softpath = {"samtools": "samtools",
            "python": "python",
            "featureCounts": "/home/soft/bin/featureCounts",
            "ShortStack": "ShortStack",
            "java": "java",
            "star": "STAR"
            }
```

因此使用方法如下：
```
from busoft import bp_softpath
softpath = bp_softpath

sassoftpath["samtools"]
```

由于流程可能会要写一些脚本文件，譬如RNA_seq.pipeline.py放在os.environ["BUPIPELINEPATH"] + "/RNA/"路径下。
同时该路径下有个bin文件夹，放了preDE.py，extract_rpkm_from_ballgown.R，rpkm_merge.py文件。我们这时可以通过下面语句将它们加载到softpath里。
都放在os.environ["BUPIPELINEPATH"] + "/RNA/bin/"路径下。
```
scr_path = os.environ["BUPIPELINEPATH"] + "/RNA/bin/"
softpath = bp_softpath
softpath.update({"preDE_script": scr_path + "preDE.py",
                "extract_rpkm_from_ballgown": scr_path + "extract_rpkm_from_ballgown.R",
                "rpkm_merge_script": scr_path + "rpkm_merge.py"})
                
#使用：
softpath["preDE_script"]
```

#### 4.1.3 sample

```
from bupipeline import Sample
sample_info = Sample(configs["sample_file"]) #configs["sample_file"]是文件路径
labels = sample_info.labels
```

这里样本文件内容如下（可以用pandas.read_table读取，并至少含有sample, read1），对于双端文件需含有read2即可。
```
group	sample	    read1	                    read2
flower	flower_rep1	ath_flower_rep1.R1.fq.gz	ath_flower_rep1.R2.fq.gz
leaf	leaf_rep1	ath_leaf_rep1.R1.fq.gz	    ath_leaf_rep1.R2.fq.gz
```

Sample类会读取样品信息，其labels即原表的sample列（按顺序）。

对于流程来讲，第一步用到的分析是sample_file里指定的测序数据路径，如上面的Star类，由于所有Tool类指定的fileins既可以是字符串，也可以是函数。因此这里可以将其指定为Sample对象的方法，用Sample对象的方法来获取fileins。

如用fileins = sample_info.get_fileins来获取[read1, read2]路径。
如用fileins = sample_info.get_fileins_only_read1来获取[read1]路径。

#### 4.1.4 配置文件
从主流程脚本可以看到主流程只提供一个参数，也就是指定配置文件。
```
config_file = sys.argv[1]
configs = toml.load(config_file)
```
该配置文件是toml格式。

示例如下：
```
sample_file = "sample.txt" #样品信息名
orgnism_name = "ath"  #orgnism_name: ath
dry_run_flag = false #true|false
excuter = "QsubExcuter" #JobExcuter | QueueQsubExcuter | BsubExcuter | QueueQsubExcuter
limit_cores = 0  #Only is used when limit_jobs is 0
limit_jobs = 0

star_core = 16
featureCounts_core = 1

select_tools = "star"

[star]
Header_STAR = 1
Header_STAROnlyBest = 0
StarBestMarkDump = 1
RemoveDump_FeatureCounts_Unique_Mapped_Gene = 1
MergeFeatureCounts = 1

[star_best]
Header_STAR = 0
Header_STAROnlyBest = 1
StarBestMarkDump = 1
RemoveDump_FeatureCounts_Unique_Mapped_Gene = 1
MergeFeatureCounts = 1
```

在主流程里`configs = toml.load(config_file)`加载了该文件。
其中前6个是通用设置。
`star_core = 16`和`featureCounts_core = 1`是某些Tool需要的。
在用字符串指定Tool类属性时可以用如下指定: core = "{configs[star_core]}"

主流程末尾用了下面语句：
```
tools = bp.get_tools_from_toml(configs, globals())
main_pipeline = Pipeline(tools=tools, ...)
```

这里`tools = bp.get_tools_from_toml(configs, globals())`会根据configs[configs["select_tools"]]的值（是一个字典，如[star]指定的）。
```
[star]
Header_STAR = 1
Header_STAROnlyBest = 0
StarBestMarkDump = 1
RemoveDump_FeatureCounts_Unique_Mapped_Gene = 1
MergeFeatureCounts = 1
```
这里键是类名，值指定程序是否运行。如果是0则不加载该步。如果是1就加载该步。这样可以通过toml来调节运行哪些步骤。譬如这里star可以分两种模式跑，一种是默认方式，一种是只要最优比对。这里是分别建了两个Tool类。这时可以通过设定一个为0，一个为1来调节使用哪个。当然对于这种简单的star比对，只是比对时参数不同的，也可以直接设计配置文件里其他参数调节。

这里设为1只是加载，是否运行会根据是否已有输出文件以及输出文件的时间是否晚于输出文件的。也可以设为4强制运行。

0 不加载
1 加载。需要父任务不运行，fileout和filein比fileout早才不运行
2 加载。需要父任务不运行，需要fileout
3 加载。需要需要父任务不运行，需要fileout（暂时没有区分2和3，2以后再编）
4 加载。强制运行。
