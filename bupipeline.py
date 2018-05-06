import time
import os, stat, re, random
import subprocess

Status_Flag = ["Preparing", "Queue", "Running", "Finished", "Failure", "Not_need_to_be_run"]

def try_mkdir(d):
    
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
    t = int(round(time.time()*1000))
    r = int(random.random()*1000)
    i = t * 1000 + r
    return(str(i))

def format_string(origin_string="", config_dict={}, split_char=" "):
    
    '''
    test:
    a = "my name is {good[b]} is better than {list} {d} is {list[2]}! keys is: {e}\n"
    b = {"good":{"b":1},"list":[1,2,3], "d":"abc", "e": lambda x: x.keys()}
    c = format_string(a, b)
    c
    '''
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
                    v = v[int(key_name)]
            return v
        
        def value2string(value, config_dict, split_char):
            if callable(value):
                s = value(config_dict)
            else:
                s = value
            if isinstance(s, str):
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
            find_results, splited_strings = re_find_all_split(re2, pattern)
            for i in splited_strings[1:]:
                if i: raise KeyError("Formate string Wrong! Key value is wrong!")
            key_names = [splited_strings[0]] + [key_name for key_name, start, end in find_results]
            value = get_element_by_keynames(key_names, config_dict)
            value = value2string(value, config_dict, split_char)
        return value
    
    def merge_splited_string(splited_strings, values):
        result_string = ""
        for s, v in zip(splited_strings[:-1], values):
            result_string += s + v
        result_string += splited_strings[-1]
        return result_string
        
        
    re1 = re.compile(r'{(.*?)}')
    re2 = re.compile(r'\[(.*?)\]')
    patterns, splited_strings = re_find_all_split(re1, origin_string)
    replaced_values = [format_patthern(pattern, config_dict, split_char) for pattern, start, end in patterns]
    result_string = merge_splited_string(splited_strings, replaced_values)
    return result_string
  
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
            self.queue_jobs = []
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
                    print(data)
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
    
    need_trans2child = ["excuter_class", "sh_out_dir", "cwd", "run_on_dir", "core"]
    not_trans2child_value = ["tools", "pipelines", "job_lists", "not_trans_value", "not_trans2child_value", "need_trans2child"]
    not_trans_value = []
    excuter_class = None
    sh_out_dir = "sh/"
    cwd = ""
    run_on_dir = "runon/"
    sleep_time = 1
    limit_cores = 1
    core = 1
    
    def __init__(self, tools={}, pipelines={}, d={}):
    
        def _pipeline_init_values():
            self.update_flag = False
            self.dry_run_flag = False
            self.job_lists = []
            self.finished = False  #如果任务失败，也会导致finished。
            self.start_run = 0
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
            self.log = os.path.join(self.sh_out_dir, "pipeline.log")
            self.log = os.path.join(self.cwd, self.log )
            if os.path.exists(self.log):
                os.remove(self.log)
        
        def trans_dict2child(self, child):
            not_trans_values = set(self.not_trans2child_value) | set(child.not_trans_value)
            all_key = set(self.__dict__.keys()) | set(self.need_trans2child)
            for key in all_key:
                if key not in not_trans_values:
                    setattr(child, key, self.__getattribute__(key))        
        
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
        self.marker_whether_run_on()
        self.update_flag = True
        
    def marker_whether_run_on(self):
        
        def _func(job_names):
            for job_name in job_names:
                parents = self.get_parents(job_name)
                if parents:
                    for parent in parents:
                        parent_status = self.get_obj(parent).status
                        if parent_status == 5:
                            break
                else:
                    parent_status = 5
                self.get_obj(job_name).check_mark_need_do(parent_status)
        self.iter_nodes_by_level_func(_func)
    
    def run(self):
        
        '''
        首先运行prepare_run_try_mkdir函数,创建self.sh_out_dir文件夹以及各个job的输出文件所在的文件夹。
        '''        
        
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
            while 1:
                if self.finished:
                    break        
                if self.running_jobs:
                    just_finish_jobs = _check_running_job_finish()
                    if just_finish_jobs:
                        _submit_job(just_finish_jobs)
                else:
                    _submit_job()
                if not self.dry_run_flag:
                    time.sleep(sleep_time)
        
        def push_job2queue(just_finish_jobs=[]):
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
            self.queue_jobs.extend(need_to_be_run_jobs)
    
        def _submit_job(just_finish_jobs=[]):
            push_job2queue(just_finish_jobs)
            if self.queue_jobs:
                while self.queue_jobs:
                    whether_have_resource = _ask_resource()
                    if whether_have_resource:
                        job = self.queue_jobs.pop(0)
                        job_obj = self.jobs_data[job]
                        job_status = job_obj.check_status()
                        if job_status == 5 or self.dry_run_flag:
                            self.finished_jobs.add(job)
                            write_log(job)
                            push_job2queue([job])
                        else:
                            job_obj.run()
                            self.running_jobs.add(job)
                    else:
                        break
            else:
                if not self.running_jobs:
                    self.finished = True
    
        def _check_running_job_finish():
            just_finished_jobs = set()
            need_remove_jobs = []
            for job in self.running_jobs:
                job_obj = self.jobs_data[job]
                job_status = job_obj.check_status()
                if job_status >2:
                    need_remove_jobs.append(job)
                    write_log(job)
                    if job_status == 4:
                        self.failure_jobs.add(job)
                    else:
                        self.finished_jobs.add(job)
                        just_finished_jobs.add(job)
            self.running_jobs.difference_update(need_remove_jobs)
            return just_finished_jobs
        
        def _ask_resource():
            if self.limit_cores == 0:
                return 1
            else:
                if len(self.running_jobs) < self.limit_cores:
                    return 1
                else:
                    return 0
    
        def write_log(job=None):
            job_obj = self.jobs_data[job]
            log = job_obj.get_log()
            log += "\n\n"
            open(self.log, 'a').write(log)

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
                 name="", finish_file="", run_on_dir=""):
                 
        
        
        self.file_sh = file_sh
        self.file_stdout = file_stdout
        self.file_stderror = file_stderror
        self.core = core
        self.cwd = cwd
        self.run_on_dir = run_on_dir
        self.finish_file = finish_file
        self.status = 0
        self._log = ""

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
        with open(_real_run_sh_file, 'w') as o:
                o.write("#origin sh file: {}\n".format(sh_file))
                if cwd: o.write("cd {}\n".format(cwd))
                for l in open(sh_file):
                    o.write("\n")
                    l = l.rstrip()
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
        log += "#"*60 + "\n"
        return log
        
    def check_mark_need_do(self, parent_status=0):
        
        def _check_need_do():
            fileins = self.fileins
            fileouts = self.fileouts
            finish_file = self.finish_file
            if not os.path.exists(finish_file):
                return 1
            for fileout in fileouts:
                if not os.path.exists(fileout):
                    return 1
            exist_fileins = [f for f in fileins if os.path.exists(f)]
            if exist_fileins:
                filein_last_mtime = max([os.path.getmtime(f) for f in exist_fileins])
                fileout_last_mtime = max([os.path.getmtime(f) for f in fileouts])
                if filein_last_mtime > fileout_last_mtime:
                    return 1
            return 0
        if parent_status == 5 and not _check_need_do():
            self.status = 5
            return 0
        else:
            return 1
    
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
        process = subprocess.Popen(["sh", self.real_run_sh_file], 
                                   stdout=open(self.file_stdout, 'w'),
                                   stderr=open(self.file_stderror, 'w'))
        self.process = process
    
    def check_finished(self):
        if self.status == 1:
            self.start_run_time = get_now_time()
            return 2
        poll_signal = self.process.poll()
        if poll_signal is None:
            return 2
        else:
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
        open(file_qsub_submit_sh, 'w').write("sh {0} > {1} 2>{2}".format(self.real_run_sh_file, self.file_stdout, self.file_stderr)) 
        
        self.qsub_cmd = ["qsub", "-l", "nodes=1:ppn=" + str(self.core), "-V", 
                         "-o", self.run_on_dir, "-e", self.run_on_dir,
                         "-d", self.cwd, file_qsub_submit_sh]
        self.qsub_jobid = subprocess.check_output(qsub_cmd).decode('utf-8').split(".")[0]
        
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
    fileins = []  #如果要给绝对值，可以写个函数或方法
    fileouts = []
    file_sh = lambda self, config: os.path.join(config["sh_out_dir"], config["name"] + ".sh")
    file_stdout = "{file_sh}.stdout"
    file_stderror = "{file_sh}.stderror"
    sh = "" 
    in_dir = "./"
    out_dir = "./"
    excuter_class = None
    core = 1
    name = "{tool_name}__{label}"

    def __init__(self, d={}):
        
        def _tool_init_values():
            self.tool_name = self.__class__.__name__
            self.job_lists = []

        _tool_init_values()
        self.pre_init()
        self.init()
        self.load_dict(d)
    
    def pre_init(self):
        pass
        
    def init(self):
        pass
    
    def update(self):
        '''
        jobs的key是label_tag,值是每个小任务Job对象。
        '''

        def _treat_all_elements(s, func=None):
            if isinstance(s, str):
                return func(s)
            elif isinstance(s, dict):
                r = {}
                for k, v in s.items():
                    r[k] = func(v)
                return r                        
            else:
                return [func(v) for v in s]
                
        def _format_str(s, d, split_char=" "):
            def _func(v):
                return format_string(v, d, split_char)
            return _treat_all_elements(s, _func)
        
        def _path2abspath(s, cwd):
            def _func(v):
                return os.path.abspath(os.path.join(cwd, v))
            return _treat_all_elements(s, _func)
        
        def generate_job(config):
            
            def generate_value(config, tag):
                
                origin_value = config[tag]
                if callable(origin_value):
                    value = origin_value(config)
                else:
                    value = _format_str(origin_value, config)
                    #name不含空格
                    if tag == "name":
                        value = value.replace(" ","")
                if tag in ["fileins", "fileouts", "file_stdout", "file_stderror"]:
                    value = _path2abspath(value, config["cwd"])
                return value
            
            def generate_sh_file(config):
                cwd = config["cwd"]
                file_sh = config["file_sh"]
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
                    values = [v for k, v in d.items()]
                else:
                    values = [v for v in d]
                return(values) 

            ###注意生成顺序
            for tag in ["name", "fileins", "fileouts", "file_sh", "file_stdout", "file_stderror", "sh"]:
                config[tag] = generate_value(config, tag)
            generate_sh_file(config)
            config["finish_file"] = config["file_sh"] + ".finishd"
            config["fileins"] = to_list(config["fileins"])
            config["fileouts"] = to_list(config["fileouts"])

            return self.excuter_class(file_sh=config["file_sh"], 
                                      cwd=config["cwd"],
                                      fileins=config["fileins"],
                                      fileouts=config["fileouts"],
                                      file_stdout=config["file_stdout"],
                                      file_stderror=config["file_stderror"],
                                      core=config["core"],
                                      name=config["name"],
                                      run_on_dir=config["run_on_dir"],
                                      finish_file=config["finish_file"])

        self.cwd = os.path.abspath(self.cwd)
        self.in_dir = _path2abspath(self.in_dir, self.cwd)
        self.out_dir = _path2abspath(self.out_dir, self.cwd)

        for num, label in enumerate(self.labels):
            config = CombineItems(self)
            config.label = label
            config.job_num = num
            job_obj = generate_job(config)
            self.job_lists.append(job_obj)
        return self

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
