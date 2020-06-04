import os

bp_softpath = {"samtools": "samtools",
            "python": "python",
            "featureCounts": "/home/soft/bin/featureCounts",
            "ShortStack": "ShortStack",
            "java": "java",
            "star": "STAR"
            }
            
get_environ = {"picard": "PICARD",
               "trimmomatic": "TRIMMOMATIC"}
               
for i, j in get_environ.items():
    try:
        bp_softpath[i] = os.environ[j]
    except:
        print("busoft Warning: environment '%s' is not found! So softpath '%s' cann't be used!" % (j, i))