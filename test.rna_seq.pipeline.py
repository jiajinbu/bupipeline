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