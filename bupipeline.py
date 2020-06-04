import time
import os, stat, re, random
import subprocess
import shutil
from optparse import OptionParser

'''
2020.01 
注意利用tool toml添加时，0表示不运行，1对应0，2对应1，3对应2，4对应3。
需要self的mode和touch_if_not_run属性
mode不同值的意思：
0 需要父任务不运行，fileout和filein比fileout早才不运行
1 需要父任务不运行，需要fileout
2 需要需要父任务不运行，重要fileout（暂时没有区分1和2，2以后再编）
3 强制运行
4 强制不运行

2018.07.16 待解决问题
1. 不同节点时间不同步
   job运行成功后，主程序监控到后，歇1秒后touch所有fileouts。不要touch fileins。
2. 运行完成后，后面又加了新的分析流程，前面的数据量太大，暂时删了，删掉后不让程序重新跑
   将生成该文件的tool注释掉，或者让tool强制不运行（需要添加新模式）
3. 某个数据Z做A分析生成A文件，后面想让它做B分析生成B文件，发现把Z生成成另一个格式更容易，跑了Z后又不想重新跑A
   强制A不运行（需要添加新模式），并把A输出文件以及其后面依赖的文件的修改时间更改了。
整体思考:
以文件为核心去思考，关键是我们想要哪些文件。

更改模式：
不再需要finish文件了。为了兼容，暂时不删除finish文件，而是后面检测状态，如果发生错误，则将文件名的后缀加上"." + self.id + ".run_error"
添加touch_if_not_run属性，如果不运行，则touch输出文件

注意not_trans_value其实是传了，只不过前面加了_not_trans_
'''

Status_Flag = ["Preparing", "Queue", "Running", "Finished", "Failure", "Not_need_to_be_run"]


#暂时弃用parser，直接用toml即可。
#usage = "usage: %prog [options] arg"  
bp_parser=OptionParser()
bp_parser.add_option("-s", "--sample", dest="sample_file", default="",
                      help="Sample File Name. e.g. /work/bio-jiajb/bio/src/pipeline/RNA/sample.txt. Column name: group sample read1 read2. []")
bp_parser.add_option("-o", "--orgnism", dest="orgnism_name", default="ath",
                      help="orgnism_name: ath|glyma|pp. [ath]")
bp_parser.add_option("-d", "--dry_run", dest="dry_run_flag", action="store_true", default=False,
                      help="True of False. -d fro dry run. [False]")
bp_parser.add_option("-e", "--excuter", dest="excuter", default="j",
                      help="excuter. j:JobExcuter | q:QueueQsubExcuter | b:BsubExcuter | qq:QueueQsubExcuter [j]")
bp_parser.add_option("-t", "--limit_cores", dest="limit_cores", default=1, type="int",
                      help="limit cores. Most core is used. Only is used when limit_jobs is 0. 0 for no limit. [1]")
bp_parser.add_option("-j", "--limit_jobs", dest="limit_jobs", default=1, type="int",
                      help="limit cores. Most jobs are running. [1]")

def list_dir_file(path, only_file=True):
    
    """
    列出指定目录path中的文件和文件夹。默认只列出文件，如果想列出文件夹，
    将only_file参数设为Fasle。
    """
    
    path = os.path.abspath(path)
    children = []
    for child_name in os.listdir(path):
        child = os.path.join(path, child_name)
        if only_file and os.path.isdir(child): continue
        children.append(child)
    return children
    
def get_filelabel_by_suffix(path, suffix=""):
    
    """
    获得指定目录path下以指定后缀suffix结尾的文件，返回这些文件的前缀。
    如path目录下有a.txt, b.txt两个文件，则
    get_filelabel_by_suffix(path, ".txt")返回["a", "b"]。
    """
    
    def _get_filename_and_suffix(file):
        _path, _file = os.path.split(file)
        return os.path.splitext(_file)
        
    children = list_dir_file(path)
    labels = []
    for child in children:
        label, this_suffix = _get_filename_and_suffix(child)
        if this_suffix == suffix:
            labels.append(label)
    return labels

def get_tools_from_toml(config, d, default_tool_value="tools"):
    
    """
    目的：给定一系列当前环境中的Tool类的名称，创建这些Tool对象。
    并返回成一个由tool对象创建的列表，用于搭建Pipeline。因此d一般
    设为globals()，以用于根据名称返回对象。为了方便使用toml，config
    是一个字典，通常由读取toml文件获得，其键"tools"存储了一个字典。
    tools是default_tool_value设置的，可以通过default_tool_value指定，
    也可以在config里指定select_tools的值。
    字典的键就是想要创建Tool对象的Tool类的名称，其值为True或False，
    用于决定是否要创建Tool对象。这样方便在toml里来控制使用哪些Tool类。
    
    输入参数：
    -------
    config : 包含值"tools"的字典。通常由读取toml文件获得。
    config:
    {
        "tools" : {
            "Fastq2fasta" : 1,
            "Bowtie" : 0
        }
    }
    对应的toml文件是：
    [tools]
    Fastq2fasta = 1
    Bowtie = 1

    d : 通常为globals()。存储着对象名称-对象的字典。
    
    输出：
    ----
    由Tool类对象组成的列表。
    """
    
    if default_tool_value == "tools":
        if "select_tools" in config:
            default_tool_value = config["select_tools"]
    
    tools = []
    for tool_class_name, tool_flag in config[default_tool_value].items():
        if tool_flag:
            t = d[tool_class_name]()
            if isinstance(t, Tool):
                t.mode = tool_flag - 1
                try:
                    t.not_trans_value.append("mode")
                except:
                    t.not_trans_value = ["mode"]
                tools.append(t)
            else:
                for t1 in t:
                    t1.mode = tool_flag - 1
                    try:
                        t1.not_trans_value.append("mode")
                    except:
                        t1.not_trans_value = ["mode"]
                    tools.append(t1)
    return tools
    
class Sample():
    
    '''
    读取样品文件，每行如下，包含表头：
    group	sample	read1	read2
    示例：
    sample_info = Sample(sample_file)
    所有样品的标记：
    sample_info.labels
    根据label获取文件返回read1和read2文件绝对路径组成的列表: [read1, read2]
    file_read1, file_read2 = sample_info[sample]
    '''
    
    def __init__(self, sample_file=""):
        if sample_file: self.load(sample_file)
    
    def load(self, sample_file):
        import pandas as pd
        
        self.sample_file = sample_file
        self.data = pd.read_table(sample_file)
        self.data.index = self.data["sample"]
        print(self.data)
        self.labels = list(self.data["sample"])
    
    def get_file(self, sample):
        data = self.data
        return [os.path.abspath(data.ix[sample, "read1"]), os.path.abspath(data.ix[sample, "read2"])]
    
    def get_file_only_read1(self, sample):
        return [os.path.abspath(self.data.ix[sample, "read1"])]
        
    def get_fileins(self, config):
        return self.get_file(config["label"])
        
    def get_fileins_only_read1(self, config):
        return self.get_file_only_read1(config["label"])
        
    def get_sample_value(self, value):
        return self.data.ix[sample, value]
    
    def get_sample_value_by_config(self, value="", na="", configs={}):
        return self.data.ix[configs["label"], value]
        
    """"    
    def load(self, sample_file):
        import pandas as pd
        
        self.sample_file = sample_file
        self.data = data = pd.read_table(sample_file)
        print(data)
        sample_info = {}
        group_info = {}
        for group, sample, read1, read2 in zip(data["group"], data["sample"], data["read1"], data["read2"]):
            sample_info[sample] = [group, read1, read2]
            try:
                group_info[group].append(sample)
            except:
                group_info[group] = [sample]
        self.sample_info = sample_info
        self.group_info = group_info
        self.labels = list(data["sample"])
        
    def get_file(self, sample):
        return [os.path.abspath(read_file) for read_file in self.sample_info[sample][1:3]]
    
    def get_file_only_read1(self, sample):
        return os.path.abspath(self.sample_info[sample][1])
        
    def get_fileins(self, config):
        return self.get_file(config["label"])
        
    def get_fileins_only_read1(self, config):
        return self.get_file_only_read1(config["label"])
    """
         
    

def try_mkdir(d):
    
    """
    输入一个目录或目录组成的列表（参数d），如果目录不存在，则创建目录。
    无输出。
    """
    
    if isinstance(d, str):
        if not os.path.exists(d):
            os.makedirs(d)
    else:
        for path in d:
            if not os.path.exists(path):
                os.makedirs(path)

def get_now_time():
    return time.asctime( time.localtime(time.time()) )

def generate_id_bytime():
    #'2020-02-04-1580802669524-266'
    #第4个是时间的数。最后一个266是随机数。防治同一时间获取id，获取重。
    t = int(round(time.time()*1000))
    r = int(random.random()*1000)
    return(time.strftime('%Y-%m-%d',time.localtime(time.time()))
+ "-" + str(t) + "-" + str(r))

def treat_all_elements(s, func=None):
    
    """
    对数据结构s中的字符串或整数，运行func，处理结果保持原来s的结构不变。
    如果s是字符串或整数，则直接返回运行func的结果。
    如果s是字典或列表，则对其每个元素，递归运行treat_all_elements。
    """
    
    if isinstance(s, str):
        return func(s)
    elif isinstance(s, int):
        return func(s)
    elif isinstance(s, dict):
        r = {}
        for k, v in s.items():
            r[k] = treat_all_elements(v, func)
        return r                        
    else:
        return [treat_all_elements(v, func) for v in s]
        
def extend_format_string(origin_string, config_dict={}, replace_dicts={}, split_char=" "):
    
    '''
    目的：如果我们想产生"out_dir/1.txt", "out_dir/2.txt"到"out_dir/10.txt"这十个文件名。本函数就可以通过
    "out_dir/{label}.txt"和 label=[1,2,....,10] 来得到这十个文件名，其原理就是讲label中的元素一次替换到
    字符串中标记的位置来产生十个字符串。有时候out_dir也不固定，但这十个文件名的out_dir又都一样。这时候我们可以写成
    "{out_dir}/{label}.txt"，并设置 out_dir="output" label=[1,2,....,10]。本函数的：
    
    输入origin_string : 字符串，如"{out_dir}/{label}.txt"。
    输入config_dict   : 字典样结构。用来替换origin_string中不变的值。即{"out_dir":"output"}
    输入replace_dicts : 字典。用来替换origin_string中变化的值。即{"label": [1,2,...,10]}
    
    replace_dicts每个键存储的值可以是字符串列表，也可以是字符串，如果是字符串，则将其值替换为config_dict[value]。
    
    Note!!! config_dict的值会被更改。更改的是replace_dicts中最后一次键值对。
    函数使用format_string进行格式化字符，因此可以实现比较复杂的字符串格式化。
    
    都应该是列表，且列表的长度是一样的。
    
    输出：字符串的列表。
    
    示例：
    > import bupipeline as bp
    > a = "{x}.{y}"
    > d = {}
    > c = {"x":[1,2], "y":["a","b"]}
    > bp.extend_format_string(a, d, c)
    ['1.a', '2.b']
    '''
    
    keys = list(replace_dicts.keys())
    values = []
    for key in keys:
        v = replace_dicts[key]
        if isinstance(v, str):
            v = config_dict[v]
        values.append(v)

    if not keys or not values[0]:
        return format_string(origin_string, config_dict, split_char)
    else:
        results = []
        for value in zip(*values):
            for k, v in zip(keys, value):
                config_dict[k] = v
            results.append(format_string(origin_string, config_dict, split_char))
        return results

def format_string(origin_string="", config_dict={}, split_char=" "):
    
    """
    目的：利用一个字典config_dict来格式化字符串origin_string。origin_string可以是以字符串为最小单位的
    数据结构，这样函数会调用treat_all_elements对原数据结构中的每个字符串进行格式化，输出保留原来的数据结构。
    
    示例：
    > a = "my name is {good[b]} is better than {list} {d} is {list[2]}! keys is: {e}\n"
    > b = {"good":{"b":1},"list":[1,2,3], "d":"abc", "e": lambda x: x.keys()}
    > c = format_string(a, b)
    
    {}里面也可以{?key1?option_string?key2}，相当于调用
    config_dict["key1"](option_string, config_dict["key2"], config_dict)
    这里key1必须是字符串，即config_dict的键，而且config_dict["key1"]必须是函数。
    但key2类似上面的`good[b]`或`list[2]`等。
    
    注意根据键得到config_dict值后，会将该值value转化为字符串。如果值是一个函数，先将值转换为value(config_dict)。
    然后将函数的输出结果，继续转化为字符串。如果是字符串就返回，如果是整数，则返回str(value)。如果是列表，则用str处理
    每个元素，并用split_char.join()将它们串联起来。如果是字典，则用同样方法将字典的values串联起来。因此这时顺序是
    乱的。
    """
    
    
    def _format_string(origin_string="", config_dict={}, split_char=" "):
    
        def re_find_all(r, s, group_num=1):
            data = []
            for match in r.finditer(s):
                data.append([match.group(group_num), match.start(), match.end()])
            return data
    
        def re_find_all_split(r, s, group_num=1):
            pattern_infos = re_find_all(r, s, group_num)
            splited_strings = []
            this_start = 0
            for nm, start, end in pattern_infos:
                this_end = start
                splited_strings.append(s[this_start:this_end])
                this_start = end
            splited_strings.append(s[this_start:])
            return([pattern_infos, splited_strings])
    
        def format_patthern(pattern, config_dict, split_char):
        
            def get_element_by_keynames(key_names, config_dict):
                v = config_dict
                for key_name in key_names:
                    try:
                        v = v[key_name]
                    except: 
                        try:
                            v = v[int(key_name)]
                        except:
                            print(v)
                            v = v[int(key_name)]
                return v
        
            def value2string(value, config_dict, split_char):
                if callable(value):
                    s = value(config_dict)
                else:
                    s = value
                if isinstance(s, str):
                    s = s
                elif isinstance(s, int):
                    s = s
                elif isinstance(s, dict):
                    s = split_char.join([str(i) for i in list(s.values())])
                elif hasattr(s, '__iter__'):
                    s = split_char.join([str(i) for i in list(s)])
                else:
                    s = str(s)
                return s
        
            pattern = pattern.strip()
            if not pattern:
                raise KeyError("Formate string Wrong! Key value is empty!")
            else:
                pattern_func = None
                if pattern == "__left_braces__":
                    return "{"
                elif pattern == "__right_braces__":
                    return "}"
                if pattern.startswith("?"):
                    pattern_splited = pattern[1:].split("?")
                    if len(pattern_splited) != 3:
                        raise KeyError("Formate string Wrong! Key value is wrong!")
                    pattern_func_key, option_string, pattern = pattern_splited
                    pattern_func = config_dict[pattern_func_key]
                    pattern = pattern.strip()
                find_results, splited_strings = re_find_all_split(re2, pattern)
                for i in splited_strings[1:]:
                    if i: raise KeyError("Formate string Wrong! Key value is wrong!")
                key_names = [splited_strings[0]] + [key_name for key_name, start, end in find_results]
                if pattern_func:
                    try:
                        value = get_element_by_keynames(key_names, config_dict)
                    except:
                        value = 0
                    value = pattern_func(option_string, value, config_dict)
                else:
                    value = get_element_by_keynames(key_names, config_dict)
                value = value2string(value, config_dict, split_char)
            return value
    
        def merge_splited_string(splited_strings, values):
            result_string = ""
            for s, v in zip(splited_strings[:-1], values):
                result_string += str(s) + str(v)
            result_string += splited_strings[-1]
            return result_string
        
        if callable(origin_string):
            return origin_string(config_dict)
        elif isinstance(origin_string, int):
            return origin_string
        else:
            re1 = re.compile(r'{(.*?)}')
            re2 = re.compile(r'\[(.*?)\]')
            patterns, splited_strings = re_find_all_split(re1, origin_string)
            replaced_values = [format_patthern(pattern, config_dict, split_char) for pattern, start, end in patterns]
            result_string = merge_splited_string(splited_strings, replaced_values)
        return result_string
        
    def _func(v):
        return _format_string(v, config_dict, split_char)
    if callable(origin_string):
        return _format_string(origin_string, config_dict, split_char)
    else:
        return treat_all_elements(origin_string, _func)
    
class ClassDict():
    
    '''
    方法： 
    load_dict(d)： 根据字典值设置属性
    get_dict(): 返回属性值的copy
    trans_dcit(obj, d, delete_keys, not_replace_if_exist): 传递属性值到对象obj。obj.not_trans_value里的值也不传。
    '''
    
    def load_dict(self, d):
        '''
        d : 字典
        '''
        for k, v in d.items():
            setattr(self, k, v)
            
    def load_dict_if_not_null(self, d):
        origin_d = self.__dict__
        for k, v in d.items():
            if k not in origin_d:
                setattr(self, k, v)
            
    def get_dict(self):
        return self.__dict__.copy()
        
    def trans_dict(self, obj, d = None, delete_keys=[], not_replace_if_exist={}):
        if d == None:
            d = self.get_dict()
        try:
            delete_keys.extend(obj.not_trans_value)
        except:
            pass
        for key in delete_keys:
            if key in d:
                del d[key]
        d1 = obj.__dict__
        for k, v in not_replace_if_exist.items():
            if k in d1.items():
                if d1[k] != v:
                    del d[key]
        for k, v in d.items():
            setattr(obj, k, v)
            
    def get_class_dict(self):
        d = {}
        for k, v in self.__class__.__dict__.items():
            if not(k.startswith("__") and k.endswith("__")):
                d[k] = v
        return d

class Tree():
    
    '''
    使用方法：
    t = Tree(tree_data)  #Tree需一次性提供树结构。用update_tree(tree_data)会丢失之前存储的值。
    #提供的数据tree_data是一个字典，键是节点名，值是一个三元素的列表。
    #第一个元素是该节点对应的信息（可以自己设定），第二个元素父节点名的列表，第三个元素是子节点名的列表。
    #
    t.get_childs(node_name) #根据node_name返回其子节点的node_name列表。
    t.get_childs_by_ids(node_names) #提供node_name的列表，返回它们的子节点的node_name列表。
    t.get_obj(node_name) #返回node_name存储的该节点对应的信息
    t.get_parents(node_name) #返回node_name的父节点node_name列表
    t.iter_nodes(parent="") #遍历parent所有子节点，默认是遍历整个树。
    t.iter_nodes_by_level() #一层一层遍历节点，每次返回一层节点（node_name组成的元组）。
    t.iter_nodes_by_level_func(func) #对每层节点的返回值进行函数处理，func是一个callable对象。
    '''
    
    def __init__(self, tree_data=[]):
        self.update_tree(tree_data)
        
    def update_tree(self, tree_data=[]):
        self._tree_data = tree_data
        self.roots = set([k  for k, v in tree_data.items() if not v[1]])
    
    def get_childs(self, node_name):
        return self._tree_data[node_name][2]
        
    def get_childs_by_ids(self, node_names = []):
        result = set()
        get_childs = self.get_childs
        for node_name in node_names:
            result.update(get_childs(node_name))            
        return list(result)
        
    def get_obj(self, node_name):
        return self._tree_data[node_name][0]
    
    def get_parents(self, node_name):
        return self._tree_data[node_name][1]    
        
    def iter_nodes(self, parent=""):
        if not parent:
            child_nodes = self.roots
        else:
            child_nodes = self.get_childs(parent)
        if child_nodes:
            for node in child_nodes:
                yield(node)
                for v in self.iter_nodes(node):
                    yield(v)
                
                
    def iter_nodes_by_level(self, parents=[]):
        
        if not parents:
            child_nodes = self.roots
        else:
            child_nodes = self.get_childs_by_ids(parents)
        if child_nodes:
            yield(child_nodes)
            for v in self.iter_nodes_by_level(child_nodes):
                yield(v)
            
    def iter_nodes_by_level_func(self, func=None):
        
        for child_nodes in self.iter_nodes_by_level():
                value = func(child_nodes)

class JobTree(Tree):
    
    '''
    使用方法：
    jt = JobTree(jobs)  #需一次性提供job对象组成的列表。用load_jobs(jobs)重新加载会丢失之前存储的值。
    更多方法同见Tree类。如
    jt.get_childs(job_name) #根据job_name返回依赖其运行的job的job_name列表。
    jt.get_childs_by_ids(job_names) #提供job_name的列表，返回依赖它们运行的job的job_name列表。
    重要属性：
    jobs_data  字典，键是job_name，值是job对象
    roots  元组。不依赖任何任务的任务的job_name组成的元组。
    
    对于开发者：
    _fileout_to_father_job  字典。键是fileout，值是能产生该文件的job_name
    _tree_data 字典。键是job_name, 值是三个元素的列表。第一个元素是job_name对应的job对象，第二个元素是父节点的列表
    （节点用job_name表示），第三个元素是子节点的列表。
    '''

    def __init__(self, jobs=[]):
        self.load_jobs(jobs)
    
    def load_jobs(self, jobs):
        
        def _jobtree_init_values():
            self.finished_jobs = set()
            self.running_jobs = set()
            self.run_cores = 0
            self.queue_jobs = set()
            #self.not_need_run_jobs = set()
            self.failure_jobs = set()
        
        _jobtree_init_values()
        
        fileout_to_father_job = {}
        jobs_data = {}
        tree_data = {}
        _jobs_info_data = []
        for job in jobs:
            job_name = job.name
            fileins = job.fileins
            fileouts = job.fileouts
            _jobs_info_data.append([job_name, fileins, fileouts])
            jobs_data[job_name] = job
            tree_data[job_name] = [job, [],[]] #[[parents],[children]]
            for fileout in fileouts:
                if fileout in fileout_to_father_job:
                    raise KeyError("{0} can be generated by at least two job!".format(fileout))
                fileout_to_father_job[fileout] = job_name
        for job_name, fileins, fileouts in _jobs_info_data:
            if fileins:
                for filein in fileins:
                    if filein in fileout_to_father_job:
                        parent_job_name = fileout_to_father_job[filein]
                        tree_data[job_name][1].append(parent_job_name)
                        tree_data[parent_job_name][2].append(job_name)
        self._fileout_to_father_job = fileout_to_father_job
        self.jobs_data = jobs_data
        self.update_tree(tree_data)

class Pipeline(JobTree, ClassDict):
    #如果limit_jobs不等于0时，用limit_jobs，只限制同时提交的任务数，不关心core。当limit_jobs等于0时，如果limit_cores也等于0，则不做任何限制，否则限制总运行的core数。
    
    """
    
    """
    
    
    need_trans2child = ["excuter_class", "sh_out_dir", "cwd", "run_on_dir", "core"]
    not_trans2child_value = ["tools", "pipelines", "job_lists", "not_trans_value", "not_trans2child_value", "need_trans2child"]
    not_trans_value = []
    excuter_class = None
    sh_out_dir = "sh/"
    cwd = ""
    run_on_dir = "runon/"
    sleep_time = 1
    limit_cores = 1
    limit_jobs = 1
    core = 1
    
    def __init__(self, tools={}, pipelines={}, d={}):
        
        """
        
        """
        
        def _pipeline_init_values():
            self.update_flag = False
            self.dry_run_flag = False
            self.job_lists = []
            self.finished = False  #如果任务失败，也会导致finished。
            self.start_run = 0
            self.id = generate_id_bytime()#str(int(time.time()))
            self.tools = []
            self.pipelines = []
        
        _pipeline_init_values()
        self.load_dict(d)
        self.load(tools=tools, pipelines=pipelines)

    def load(self, tools=[], pipelines=[]):
        '''
        只存储，不处理
        '''
        self.tools.extend(tools)
        self.pipelines.extend(pipelines)
    
    def update(self):
        '''
        处理。处理后不再进行加载和更改属性。
        '''
        
        def _attr_update():
            pass
        
        def _path2abspath():
            self.cwd = os.path.abspath(self.cwd)
            self.sh_out_dir = os.path.join(self.cwd, self.sh_out_dir)
            self.run_on_dir = os.path.join(self.cwd, self.run_on_dir )
            self.log = os.path.join(self.sh_out_dir, self.id + ".pipeline.log")
            self.log = os.path.join(self.cwd, self.log )
            if os.path.exists(self.log):
                os.remove(self.log)
        
        def trans_dict2child(self, child):
            not_trans_values = set(self.not_trans2child_value) | set(child.not_trans_value)
            all_key = set(self.__dict__.keys()) | set(self.need_trans2child)
            for key in all_key:
                if key not in not_trans_values:
                    setattr(child, key, self.__getattribute__(key))
                else:
                    setattr(child, "_not_trans_"+key, self.__getattribute__(key))        
        
        def check_root_filein_exist(self):
            for root in self.roots:
                job_obj = self.jobs_data[root]
                for filein in job_obj.fileins:
                    if not os.path.exists(filein):
                        raise KeyError("{} not found for {}!\n".format(filein, job_obj.name))
        
        _attr_update()
        _path2abspath()
        try_mkdir(self.sh_out_dir)
        try_mkdir(self.run_on_dir)
        job_lists = []
        for tool in self.tools:
            trans_dict2child(self, tool)
            tool.update()
            job_lists.extend(tool.job_lists)
        for pipeline in self.pipelines:
            trans_dict2child(self, pipeline)
            pipeline.update()
            job_lists.extend(pipeline.job_lists)
        self.job_lists = job_lists
        JobTree.__init__(self, self.job_lists)
        check_root_filein_exist(self)
        
        self.marker_whether_run_on()
        self.update_flag = True
        
    def marker_whether_run_on(self):
        
        def _func(job_names):
            for job_name in job_names:
                parents = self.get_parents(job_name)
                if parents:
                    for parent in parents:
                        parent_status = self.get_obj(parent).status
                        if parent_status != 5:
                            break
                else:
                    parent_status = 5
                self.get_obj(job_name).check_mark_need_do(parent_status)
        self.iter_nodes_by_level_func(_func)
    
    def run(self):
        
        '''
        首先运行prepare_run_try_mkdir函数,创建self.sh_out_dir文件夹以及各个job的输出文件所在的文件夹。
        '''        
        
        def get_next_jobs(just_finish_jobs=[]):
            need_to_be_run_jobs = []
            if not self.start_run:
                self.start_run = 1
                need_to_be_run_jobs = self.roots
            else:
                if just_finish_jobs:
                    potential_run_jobs = self.get_childs_by_ids(just_finish_jobs)
                    need_to_be_run_jobs = []
                    for job in potential_run_jobs:
                        parent_jobs = self.get_parents(job)
                        can_be_run = 1
                        for parent_job in parent_jobs:
                            if parent_job not in self.finished_jobs:
                                can_be_run = 0
                                break
                        if can_be_run: need_to_be_run_jobs.append(job)
            return need_to_be_run_jobs
    
        def _submit_job_untill_no_resource():
            
            def _ask_resource(job_obj):
                if self.limit_jobs == 0:
                    if self.limit_cores == 0:
                        return 1
                    else:
                        if self.run_cores + job_obj.core <= self.limit_cores:
                            return 1
                        elif job_obj.core == 1:
                            return -1
                        else:
                            return 0 
                else:
                    if len(self.running_jobs) < self.limit_jobs:
                        return 1
                    else:
                        return -1
            
            def _submit_jobs(jobs):
                #whether_have_resource = -1表示最小资源的任务也跑不了，因此不需再遍历其他排队的任务了。
                next_jobs = []
                processed_jobs = []
                remain_jobs = []
                whether_have_resource = 1
                for job in jobs:
                    job_obj = self.jobs_data[job]
                    job_status = job_obj.check_status()
                    if job_status == 5 or self.dry_run_flag:
                        self.finished_jobs.add(job)
                        write_log(job)
                        _this_next_jobs = get_next_jobs([job])
                        next_jobs.extend(_this_next_jobs)
                        processed_jobs.extend([job])
                    else:
                        whether_have_resource = _ask_resource(job_obj)
                        if whether_have_resource == -1:
                            remain_jobs.append(job)
                            break
                        elif whether_have_resource == 0:
                            remain_jobs.append(job)
                            continue
                        elif whether_have_resource == 1:
                            processed_jobs.append(job)
                            job_obj.run()
                            self.run_cores += job_obj.core
                            self.running_jobs.add(job)
                return [whether_have_resource, next_jobs, processed_jobs, remain_jobs]
            
            if self.queue_jobs:
                whether_have_resource, next_jobs, processed_jobs, remain_jobs = _submit_jobs(self.queue_jobs)
                self.queue_jobs.difference_update(processed_jobs)
                while next_jobs and (whether_have_resource != -1):
                    whether_have_resource, next_jobs, processed_jobs, remain_jobs = _submit_jobs(next_jobs)
                    self.queue_jobs.difference_update(remain_jobs)
                self.queue_jobs.difference_update(next_jobs)                
            else:
                if not self.running_jobs:
                    self.finished = True
 
        def _check_running_job_finish():
            just_finished_jobs = set()
            need_remove_jobs = []
            for job in self.running_jobs:
                job_obj = self.jobs_data[job]
                job_status = job_obj.check_status()
                if job_status in [3, 4, 5]:
                    need_remove_jobs.append(job)
                    self.run_cores -= job_obj.core
                    write_log(job)
                    if job_status == 4:
                        self.failure_jobs.add(job)
                        ###<2018.07.16 add>
                        for fileout in job_obj.fileouts:
                            if os.path.exists(fileout):
                                shutil.move(fileout, fileout+ "." + self.id + ".run_error")
                        ###</2018.07.16 add>
                    else:
                        self.finished_jobs.add(job)
                        just_finished_jobs.add(job)
                        ###<2018.07.16 add>
                        if job_status == 3:
                            for fileout in job_obj.fileouts:
                                print(fileout)
                                #os.utime(fileout)
                        ###</2018.07.16 add>
            self.running_jobs.difference_update(need_remove_jobs)
            return just_finished_jobs
    
        def write_log(job=None):
            job_obj = self.jobs_data[job]
            log = job_obj.get_log()
            log += "\n\n"
            open(self.log, 'a').write(log)
           
        def prepare_run_try_mkdir():
            def _try_mkdir():
                fileouts = []
                for job in self.job_lists:
                    fileouts.extend(job.fileouts)
                paths = set()
                for fileout in fileouts:
                    path = os.path.dirname(fileout)
                    paths.add(path)
                try_mkdir(paths)
            _try_mkdir()

        def run_main():        
            sleep_time = self.sleep_time
            self.queue_jobs.update(get_next_jobs())
            while 1:
                if self.finished:
                    break
                if self.running_jobs:
                    just_finish_jobs = _check_running_job_finish()
                    if just_finish_jobs:
                        self.queue_jobs.update(get_next_jobs(just_finish_jobs))
                        _submit_job_untill_no_resource()
                else:
                    _submit_job_untill_no_resource()
                if not self.dry_run_flag:
                    time.sleep(sleep_time)
        
        if not self.update_flag:
            self.update()

        prepare_run_try_mkdir()
        run_main()
        
class JobExcuter():
    
    '''
    用于运行脚本，并能检测运行状态。
    Job所有东西都是绝对值。
    需要提供下列属性：
    fileins         输入文件路径列表。
    fileouts        输出文件路径列表。
    file_sh         sh文件
    core            使用的线程数
    file_stdout     标准输出指向文件
    file_stderror   标准错误输出指向文件
    name        job名字
    excuter_class     用哪个excuter执行
    '''
    
    def __init__(self, file_sh="", cwd="", fileins=[], fileouts=[], 
                 file_stdout="", file_stderror="", core=1, 
                 name="", finish_file="", run_on_dir="", mode=0):
                 
        self.file_sh = file_sh
        self.file_stdout = file_stdout
        self.file_stderror = file_stderror
        self.core = core
        self.cwd = cwd
        self.run_on_dir = run_on_dir
        self.finish_file = finish_file
        self.status = 0
        self._log = ""
        self.mode = mode
        self.touch_if_not_run = 0
        
        #just for job mangement
        self.fileins = fileins
        self.fileouts = fileouts
        self.name = name
        
        self.dry_run()
        
    def run(self):
        if self.status == 0:
            if os.path.exists(self.finish_file):
                os.remove(self.finish_file)
            self.status = 1
            self._run()
    
    def _generate_run_sh_file(self, sh_file, _real_run_sh_file, _failure_file, cwd=""):
        path, na = os.path.split(_real_run_sh_file)
        try_mkdir(path)
        path, na = os.path.split(_failure_file)
        try_mkdir(path)
        with open(_real_run_sh_file, 'w') as o:
                o.write("#origin sh file: {}\n".format(sh_file))
                if cwd: o.write("cd {}\n".format(cwd))
                for l in open(sh_file):
                    l = l.rstrip()
                    if not l:
                        continue
                    o.write("\n")
                    if l.endswith("#f"):
                        l += " || touch " + _failure_file
                    if l:
                        o.write(l)
                o.write(" || touch " + _failure_file + "\n")
        os.chmod(_real_run_sh_file, stat.S_IRWXU)

    def dry_run(self):
        
        new_id = generate_id_bytime() + "." + os.path.split(self.file_sh)[1]
        self.real_run_sh_file = os.path.join(self.run_on_dir, new_id + ".sh")
        self.failure_file = self.real_run_sh_file + ".failure"
        if os.path.exists(self.failure_file): os.remove(self.failure_file)
        self._generate_run_sh_file(self.file_sh, self.real_run_sh_file, self.failure_file, self.cwd)
        if not self.file_stdout: self.file_stdout = self.file_sh + ".stdout"
        if not self.file_stderror: self.file_stderror = self.file_sh + ".stderror"
        self.start_run_time = get_now_time()
        self.end_run_time = get_now_time()
    
    def get_log(self):
        log = "#"*60 + "\n"
        d = [["Name:\t", self.name],
             ["Fileins:\t", self.fileins],
             ["Fileouts:\t", self.fileouts],
             ["Finished file:\t", self.finish_file],
             ["File stdout:\t", self.file_stdout],
             ["File stderr:\t", self.file_stderror],
             ["Sh file:\t", self.file_sh],
             ["Status:\t", Status_Flag[self.status]],
             ["Start run time:\t", self.start_run_time],
             ["End run time:\t", self.end_run_time]
            ]
        for pre, s in d:
            log += "#{0}{1}\n".format(pre, s)
        log += open(self.file_sh).read()            
        log += "#"*60 + "\n"
        return log
        
    def check_mark_need_do(self, parent_status=0, parent_touch_if_not_run=0):
        
        '''
        注意利用tool toml添加时，0表示不运行，1对应0，2对应1，3对应2，4对应3。
        需要self的mode和touch_if_not_run属性
        mode不同值的意思：
        0 需要父任务不运行，fileout和filein比fileout早才不运行
        1 需要父任务不运行，需要fileout
        2 需要需要父任务不运行，重要fileout（暂时没有区分1和2，2以后再编）
        3 强制运行
        4 强制不运行
        ......
        touch_if_not_run设为
        0时，如果parent_touch_if_not_run则touch_if_not_run会被设为1，默认值
        1时，如果不运行则会touch输出文件的修改时间
        2时，不运行时不会touch输出文件的修改时间
        '''
        
        def _check_need_do(mode):
            fileins = self.fileins
            fileouts = self.fileouts
            if not fileouts:
                raise Exception(self.name + "\t" + "No fileout" + '\t'.join(fileouts) )
            for fileout in fileouts:
                if not os.path.exists(fileout):
                    return 1
            if mode == 0:
                for f in fileins:
                    if not os.path.exists:
                        return 1
                exist_fileins = [f for f in fileins if os.path.exists(f)]
                if exist_fileins:
                    filein_last_mtime = max([os.path.getmtime(f) for f in exist_fileins])
                    fileout_last_mtime = max([os.path.getmtime(f) for f in fileouts])
                    if filein_last_mtime > fileout_last_mtime:
                        return 1
                return 0
        
        mode = self.mode
        if mode == 3:
            run = 1
        elif mode == 4:
            run = 0
        else:
            run = 0 if parent_status == 5 and not _check_need_do(mode) else 1
        
        if not run:
            self.status = 5
            if self.touch_if_not_run == 0 and parent_touch_if_not_run == 1:
                self.touch_if_not_run == 1
            if self.touch_if_not_run == 1:
                for fileout in self.fileouts:
                    os.utime(fileout)
        
    def check_status(self):
        if self.status == 1 or self.status == 2:
            self.status = self.check_finished()
            if self.status == 3:
                open(self.finish_file, 'w')
            elif self.status == 4:
                open(self.failure_file, 'w')
        return self.status

    ###不同excuter会不同
    def _run(self):
        self.status = 2
        self.start_run_time = get_now_time()
        process = subprocess.Popen(["sh", self.real_run_sh_file], 
                                   stdout=open(self.file_stdout, 'w'),
                                   stderr=open(self.file_stderror, 'w'))
        self.process = process
    
    def check_finished(self):
        status = self.status
        if self.status == 2:
            poll_signal = self.process.poll()
            if not poll_signal is None:
                self.end_run_time = get_now_time()
                time.sleep(3) #防止failure_file产生的慢
                if os.path.exists(self.failure_file):
                    status = 4
                else:
                    status = 3
        return status

class QsubExcuter(JobExcuter):
    
    def _run(self):

        self.file_qsub_submit_sh = file_qsub_submit_sh = self.real_run_sh_file + ".qsub_submit.sh"
        open(file_qsub_submit_sh, 'w').write("sh {0} > {1} 2>{2}\n".format(self.real_run_sh_file, self.file_stdout, self.file_stderror)) 
        
        #2019.07 植物所qsub加-V环境变量会有问题
        self.qsub_cmd = qsub_cmd = ["qsub", "-l", "nodes=1:ppn=" + str(self.core), #"-V", 
                                         "-o", self.run_on_dir, "-e", self.run_on_dir,
                                         "-d", self.cwd, file_qsub_submit_sh]
        self.qsub_jobid = subprocess.check_output(qsub_cmd).decode('utf-8').split(".")[0]
        print(self.qsub_cmd)
        print(self.qsub_jobid)
        
        self.check_stat_cmd = ["qstat","-x"]
        self.check_stat_cmd.append(self.qsub_jobid)
        self.qsub_stat_re = re.compile(r'<job_state>(\w)</job_state>')

    def check_finished(self):
        
        #0 unfinished 1 finished 2 failure
        status = self.status
        try:
            qsub_stat_info = subprocess.check_output(self.check_stat_cmd)
            try:
                job_stat_match = self.qsub_stat_re.search(qsub_stat_info.decode('utf-8'))
                if job_stat_match:
                    label = job_stat_match.group(1)
                    if status == 1:
                        if label != "Q":
                            self.start_run_time = get_now_time()
                            status = 2
                    else:
                        if label == "C":
                            status = 3
            except:
                pass
        except:
            status = 3
        if status > 2:
            self.end_run_time = get_now_time()
            time.sleep(3)  #防止failure_file产生的慢
            if os.path.exists(self.failure_file):
                status = 4
            else:
                status = 3
        return status

class BsubExcuter(JobExcuter):
    def _run(self):

        self.file_bsub_submit_sh = file_bsub_submit_sh = self.real_run_sh_file + ".bsub_submit.sh"
        open(file_bsub_submit_sh, 'w').write("sh {0} > {1} 2>{2}\n".format(self.real_run_sh_file, self.file_stdout, self.file_stderror)) 
        self.bsub_jobid = subprocess.check_output("bsub -R \"span[hosts=1]\" -n 20 -q short < " + file_bsub_submit_sh, shell=True).decode('utf-8').split("<")[1].split(">")[0]
        
    def check_finished(self):
        #bjobs status list: https://www.ibm.com/support/knowledgecenter/en/SSWRJV_10.1.0/lsf_admin/job_state_lsf.html
        status = self.status
        try:
            bjob_status = subprocess.check_output(["bjobs", self.bsub_jobid]).decode('utf-8').split("\n")[1].split()[2]
            #"PEND", "PSUSP", "USUSP", "SSUSP"等表示等待
            if bjob_status == "RUN":
                self.start_run_time = get_now_time()
                status = 2
            elif bjob_status == "DONE":
                status = 3
            elif bjob_status == "EXIT":
                status = 4
        except:
            status = 3
        if status > 2:
            self.end_run_time = get_now_time()
            time.sleep(3)  #防止failure_file产生的慢
            if os.path.exists(self.failure_file):
                status = 4
            else:
                status = 3
        return status

class QueueQsubExcuter(JobExcuter):
    
    def _run(self):
        import buqueue_qsub as bq
        
        self.js = bq.QueueJobSystem()
        self.jobid = self.js.submit_job(self.real_run_sh_file, self.core, self.file_stdout, self.file_stderror)

    def check_finished(self):
        job_info = self.js.get_job_info(self.jobid)
        job_status =  job_info[4]
        self.start_run_time = job_info[7]
        self.end_run_time = job_info[8]
        return job_status
    
    def _generate_run_sh_file(self, sh_file, _real_run_sh_file, _failure_file, cwd=""):
        path, na = os.path.split(_real_run_sh_file)
        try_mkdir(path)
        path, na = os.path.split(_failure_file)
        try_mkdir(path)
        with open(_real_run_sh_file, 'w') as o:
                o.write("#origin sh file: {}\n".format(sh_file))
                if cwd: o.write("cd {}\n".format(cwd))
                for l in open(sh_file):
                    o.write(l)                        
        os.chmod(_real_run_sh_file, stat.S_IRWXU)
    
class CombineItems():
    
    def __init__(self, config_class=None):
        self.config_class = config_class
    
    def load(self, config_dict):
        for k, v in config_dict.items():
            setattr(self, k, v)
    
    def __getitem__(self, key):
        try:
            v = self.__getattribute__(key)
        except:
            v = self.config_class.__getattribute__(key)
        return v
    
    def __setitem__(self, name, val):
        setattr(self, name, val)

class Tool(ClassDict):
    
    '''
    使用方法：
    Tool仅仅是一个母类，需要编写子类，并使用子类。
    需要注意几个重要的属性：
    labels: label的列表。必须给出。根据label产生job，有多少label就产生多少个label。labels的元素是字符串还是列表？

    不同的任务有个0-based index。还有个label_tag.
    每个小任务的label可以是任意类型的变量，如果提供label_tags，则用label_tag来标记每个label，
    否则根据label推断label_tag.
    not_trans_value列表，定义哪些属性值不从Pipeline里传过来。
    '''

    #其他不能随便设的值： label, job_num, ....
    not_trans_value = []
    tool_name = __name__
    labels = []
    #除tool_name是字符串，labels是列表或字典外，其他均可以是字符串，列表，字典，函数。
    config = []
    config_path = []
    fileins = []  #如果要给绝对值，可以写个函数或方法
    fileouts = []
    ##NEED TO MODIFY
    file_sh = lambda self, config: os.path.join(config["sh_out_dir"], config["child_dir"], config["name"] + ".sh")
    file_stdout = "{file_sh}.stdout"
    file_stderror = "{file_sh}.stderror"
    sh = "" 
    in_dir = "./"
    out_dir = "./"
    excuter_class = None
    core = 1
    max_job_in_dir = 100
    name = "{tool_name}__{label}"
    mode = 0
    
    def __init__(self, d={}):
        
        def _tool_init_values():
            self.tool_name = self.__class__.__name__
            self.job_lists = []

        _tool_init_values()
        self.pre_init()
        self.init()
        self.load_dict(d)
        self.init_after_load()
    
    def format(self, origin_string="", config_dict={}, split_char=" "):
        return format_string(origin_string, config_dict, split_char)
    
    def pre_init(self):
        pass
        
    def init(self):
        pass
        
    def init_after_load(self):
        pass
    
    def update_run(self, d):
        pass
    
    def option(self, option_string, value, config_dict):
        '''
        ?option?-M?x if x exist, -M, fouze not -M
        ?option?!-M?x -M x,
        '''
        
        if value:
            if option_string.startswith("!"):
                r = option_string[1:] + " " + value + " "
            else:
                r = option_string
        else:
            r = ""
        return r
    
    def update(self):
        '''
        jobs的key是label_tag,值是每个小任务Job对象。
        '''
        
        def _path2abspath(s, cwd):
            def _func(v):
                return os.path.abspath(os.path.join(cwd, v))
            return treat_all_elements(s, _func)
        
        def generate_job(config):
            
            def generate_value(config, tag):
                origin_value = config[tag]
                try:
                    value = self.format(origin_value, config)
                except:
                    print("Bu Wrong:")
                    print(self)
                    print(tag)
                    print(origin_value)
                    value = self.format(origin_value, config)
                #name不含空格
                if tag == "name":
                    value = value.replace(" ","")
                if tag == "core":
                    value = int(value)
                if tag in ["config_path", "fileins", "fileouts", "file_stdout", "file_stderror"]:
                    value = _path2abspath(value, config["cwd"])
                return value
            
            def generate_sh_file(config):
                cwd = config["cwd"]
                file_sh = config["file_sh"]
                file_path, na = os.path.split(file_sh)
                try_mkdir(file_path)
                sh = config["sh"]
                with open(file_sh, 'w') as o:
                    o.write("cd {}\n".format(cwd))
                    if isinstance(sh, str):
                        o.write(sh + "\n")
                    else:
                        o.write('\n'.join(sh) + "\n")
                return file_sh
    
            def to_list(d, str_to_list=True):
                '''
                提取字符串，列表，字典的值，转化为列表类型存储。
                str_to_list=False则不将字符串转化为列表。
                '''
                if isinstance(d, str):
                    if str_to_list:
                        values = [d]
                    else:
                        values = d
                elif isinstance(d, dict):
                    #<2018.07.16>
                    #<origin>
                    #values = [v for k, v in d.items()]
                    #</origin>
                    values = []
                    for k, v in d.items():
                        values += to_list(v)
                    #</2018.07.16>
                else:
                    #<2018.07.16>
                    #<origin>
                    #values = [v for v in d]
                    #</origin>
                    values = []
                    for v in d:
                        values += to_list(v)
                    #</2018.07.16>
                return(values) 

            ###注意生成顺序
            for tag in ["config", "config_path", "name", "core", "fileins", "fileouts", "file_sh", "file_stdout", "file_stderror", "sh"]:
                config[tag] = generate_value(config, tag)
            
            generate_sh_file(config)
            config["finish_file"] = config["file_sh"] + ".finished"
            config["fileins"] = to_list(config["fileins"])
            config["fileouts"] = to_list(config["fileouts"])
            self.update_run(config)
            return self.excuter_class(file_sh=config["file_sh"], 
                                      cwd=config["cwd"],
                                      fileins=config["fileins"],
                                      fileouts=config["fileouts"],
                                      file_stdout=config["file_stdout"],
                                      file_stderror=config["file_stderror"],
                                      core=config["core"],
                                      name=config["name"],
                                      run_on_dir=os.path.join(config["run_on_dir"], config["child_dir"]),
                                      finish_file=config["finish_file"],
                                      mode=config["mode"])

        self.cwd = os.path.abspath(self.cwd)
        self.in_dir = _path2abspath(self.in_dir, self.cwd)
        self.out_dir = _path2abspath(self.out_dir, self.cwd)
        self.labels = self.format(self.labels, self)
        for num, label in enumerate(self.labels):
            config = CombineItems(self)
            config.label = label
            config.job_num = num
            config.child_dir = os.path.join(self.tool_name, str(num//self.max_job_in_dir))
            job_obj = generate_job(config)
            self.job_lists.append(job_obj)
        return self

class OneJob(Tool):
    sample_labels = []
    not_trans_value = ["labels"]
    labels = ["All"]
    
class LabelsOneJob(OneJob):
    
    def get_sample_labels(self, config):
        try:
            sample_labels = config["sample_labels"]
        except:
            sample_labels = []
        if not sample_labels:
            sample_labels = config["_not_trans_labels"]
        return sample_labels

class RunJob(Tool):
    
    fileouts = ["{in_dir}/{label}.out"]
    in_dir = "runon"
    
    def pre_init(self):
        def get_sh(config):
            label = int(config["label"])
            sh = config["shs"][label]
            sh.append("touch " + config["fileouts"][0])
            sh = "\n".join(sh)
            return sh
        self.sh = get_sh

def multi_run_sh(shs, excuter="JobExcuter", limit_cores=20, limit_jobs=0, dry_run_flag=False, core=1):
    runjob = RunJob()
    runjob.shs = shs
    main_pipeline = Pipeline(tools=[runjob])
    main_pipeline.labels = list(range(len(shs)))
    main_pipeline.core = core
    main_pipeline.excuter_class = {"JobExcuter":bp.JobExcuter, "QsubExcuter":bp.QsubExcuter, "BsubExcuter":bp.BsubExcuter, "QueueQsubExcuter":bp.QueueQsubExcuter}[excuter] 
    main_pipeline.limit_cores = limit_cores
    main_pipeline.limit_jobs = limit_jobs
    main_pipeline.dry_run_flag = dry_run_flag
    main_pipeline.run()
    
def multi_run_file_sh(filein, excuter="JobExcuter", limit_cores=20, limit_jobs=0, dry_run_flag=False, core=1):
    def read_sh_file(filein):
        shs = []
        for l in open(filein):
            l = l.rstrip()
            if l.startswith("#"): continue
            shs.append([l])
        return shs
    shs = read_sh_file(filein)
    multi_run_sh(shs, excuter, limit_cores, limit_jobs, dry_run_flag, core)

def test():
    
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

if __name__ == "__main__":
    test()
