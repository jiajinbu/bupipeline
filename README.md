## 1. 简介

bupipeline是为了便于生信分析人员开发和管理流程的python模块。现在仍处于开发测试当中。

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

`fileins`和`fileouts`不一定是一个字符串，也可以是一个列表，一个字典，只要列表的元素或字典的值是一个字符串就行。这样便于写`sh`。

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
示例中我们在run之前设定了`p.excuter_class = JobExcuter`。这里设定了p运行任务时用的是哪种JobExcuter。现在模块提供了两种JobExcuter类，一个是JobExcuter，一个是QsubExcuter（其父类是JobExcuter）。我么也可以根据运行环境的不同，编写新的JobExcuter，一般只需要更改运行方法和检测任务结束的方法即可。

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
